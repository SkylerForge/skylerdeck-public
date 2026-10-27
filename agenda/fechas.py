"""Dates in the agenda's time zone (AGENDA_TZ, Europe/Madrid by default) and their Spanish names."""
from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("AGENDA_TZ") or "Europe/Madrid")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def sin_tildes(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def clave(text: str) -> str:
    """Lowercase, accent-free form used to compare names typed by hand."""
    return sin_tildes(text).casefold().strip()


def ahora() -> dt.datetime:
    return dt.datetime.now(TZ)


def hoy() -> dt.date:
    return ahora().date()


def sello(momento: dt.datetime | None = None) -> str:
    return (momento or ahora()).strftime("%Y-%m-%d %H:%M")


def iso(dia: dt.date) -> str:
    return dia.isoformat()


def desde_iso(text: str) -> dt.date:
    return dt.date.fromisoformat(text[:10])


def dia_semana(nombre: str) -> int | None:
    """'miercoles', 'Miércoles', 'mié' → 2."""
    key = clave(nombre).rstrip(".")
    for i, (largo, corto) in enumerate(zip(DIAS, DIAS_CORTOS)):
        if key in (clave(largo), clave(corto)):
            return i
    return None


def mes(nombre: str) -> int | None:
    key = clave(nombre)
    for i, largo in enumerate(MESES, start=1):
        if key == largo or (len(key) >= 3 and largo.startswith(key)):
            return i
    return None


def proximo_dia_semana(desde: dt.date, weekday: int, incluir_hoy: bool = False) -> dt.date:
    delta = (weekday - desde.weekday()) % 7
    if delta == 0 and not incluir_hoy:
        delta = 7
    return desde + dt.timedelta(days=delta)


def sumar_meses(dia: dt.date, n: int) -> dt.date:
    total = dia.month - 1 + n
    year, month = dia.year + total // 12, total % 12 + 1
    for day in range(dia.day, 27, -1):
        try:
            return dt.date(year, month, day)
        except ValueError:
            continue
    return dt.date(year, month, min(dia.day, 28))


def corta(dia: dt.date) -> str:
    return f"{dia.day:02d}/{dia.month:02d}"


def humana(dia: dt.date, referencia: dt.date | None = None) -> str:
    """'hoy', 'mañana', 'ayer', 'jue 30/10'."""
    ref = referencia or hoy()
    diff = (dia - ref).days
    if diff == 0:
        return "hoy"
    if diff == 1:
        return "mañana"
    if diff == -1:
        return "ayer"
    return f"{DIAS_CORTOS[dia.weekday()]} {corta(dia)}"

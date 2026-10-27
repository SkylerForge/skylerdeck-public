"""Times in Spanish for the quick-add parser: «a las cinco y media», «a las diez menos cuarto»,
«a la una del mediodía», «esta tarde», «de 9 a 11», «dentro de 2 horas», «durante hora y media».

Only the patterns and their arithmetic; quickadd.py decides in which order they are tried.
"""
from __future__ import annotations

import re

from . import fechas

B = r"(?<![\w#@/:-])"  # start of a word
E = r"(?![\w/:])"  # end of a word
HH = r"(?:[01]?\d|2[0-3])"
MM = r"[0-5]\d"
NUM = (r"(?:\d{1,3}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince"
        r"|veinticinco|veinte|treinta|cuarenta|noventa)")
_HPAL = r"(?:una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"  # hours in words
_MPAL = r"(?:media|cuarto|veinticinco|veinte|diez|cinco|\d{1,2})"  # «y media», «menos cuarto», «y 20»
_PERIODO = r"de\s+la\s+(?:ma[ñn]ana|tarde|noche|madrugada)|del\s+mediod[íi]a"
_LAPSO = rf"(?:(?P<n>{NUM}|media)\s+(?P<u>horas?|minutos?|mins?)(?P<ymedia>\s+y\s+media)?|(?P<hymedia>hora\s+y\s+media))"
NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
           "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
           "veinticinco": 25, "treinta": 30, "cuarenta": 40, "noventa": 90, "cuarto": 15, "media": 30}
# The usual hour for a part of the day said without one («esta tarde», «por la mañana»).
HORA_PERIODO = {"manana": "09:00", "mediodia": "14:00", "tarde": "17:00", "noche": "21:00"}

RANGO_RE = re.compile(
    rf"{B}(?:(?P<de>de|desde)\s+(?:las?\s+)?(?P<h1>{HH})(?:[:.](?P<m1>{MM}))?h?\s+(?:a|hasta)\s+(?:las?\s+)?(?P<h2>{HH})(?:[:.](?P<m2>{MM}))?h?"
    rf"|(?P<h3>{HH}):(?P<m3>{MM})\s*[-–]\s*(?P<h4>{HH}):(?P<m4>{MM}))"
    rf"(?:\s+(?P<periodo>{_PERIODO}))?{E}",
    re.IGNORECASE,
)
HORA_RE = re.compile(
    rf"{B}(?:(?:a|sobre|hacia|a\s+eso\s+de)\s+las?\s+(?P<h1>{HH}|{_HPAL})(?:[:.h](?P<m1>{MM}))?"
    rf"(?:\s+(?P<signo>y|menos)\s+(?P<mp>{_MPAL}))?(?:\s*h(?:oras|rs)?\.?)?"
    rf"|(?P<h2>{HH})(?::|h)(?P<m2>{MM})|(?P<h3>{HH})h)"
    rf"(?:\s+(?P<periodo>{_PERIODO}))?{E}",
    re.IGNORECASE,
)
PERIODO_RE = re.compile(
    rf"{B}(?:(?P<esta>esta)\s+(?P<p1>ma[ñn]ana|tarde|noche)|(?:por|en)\s+la\s+(?P<p2>ma[ñn]ana|tarde|noche)"
    rf"|(?:a|al|para\s+el)\s+(?P<p3>mediod[íi]a)){E}",
    re.IGNORECASE,
)
RELATIVO_RE = re.compile(rf"{B}(?:en|dentro\s+de)\s+{_LAPSO}{E}", re.IGNORECASE)
DURACION_RE = re.compile(rf"{B}(?:que\s+)?(?:dura(?:r[áa])?|durante|de)\s+{_LAPSO}{E}", re.IGNORECASE)

def numero(texto: str) -> int:
    return int(texto) if texto.isdigit() else NUMEROS[texto.lower()]


def periodo(texto: str | None) -> str:
    """'de la tarde', 'por la tarde', 'tarde' → 'tarde'; '' when there is none."""
    p = fechas.clave(texto or "")
    return next((k for k in ("madrugada", "mediodia", "manana", "tarde", "noche") if p.endswith(k)), "")


def _tarde(hour: int, periodo: str) -> int:
    if periodo in ("tarde", "noche") and hour < 12:
        return hour + 12
    if periodo == "mediodia" and hour <= 4:  # «a la una del mediodía»
        return hour + 12
    return hour


def hora(m: re.Match, periodo: str, avisos: list[str]) -> str | None:
    h = next(m[f"h{i}"] for i in (1, 2, 3) if m[f"h{i}"])
    hour = numero(h)
    minute = int(m["m1"] or m["m2"] or 0)
    if m["mp"]:
        extra = numero(m["mp"])
        if extra >= 60:
            return None
        if m["signo"].lower() == "menos":
            hour, minute = hour - 1, 60 - extra
        else:
            minute = extra
    if periodo:
        hour = _tarde(hour, periodo)
    elif m["h1"] and 1 <= hour <= 7:
        # «a las 5» in everyday Spanish is the afternoon.
        hour += 12
        avisos.append(f"«{' '.join(m.group(0).split())}» lo entiendo como {hour:02d}:{minute:02d}")
    return f"{hour % 24:02d}:{minute:02d}"


def rango(m: re.Match, periodo: str, avisos: list[str]) -> tuple[str, int] | None:
    h1, m1, h2, m2 = (m["h1"], m["m1"], m["h2"], m["m2"]) if m["h1"] else (m["h3"], m["m3"], m["h4"], m["m4"])
    inicio, fin = int(h1) * 60 + int(m1 or 0), int(h2) * 60 + int(m2 or 0)
    if periodo:
        inicio = _tarde(int(h1), periodo) * 60 + int(m1 or 0)
        fin = _tarde(int(h2), periodo) * 60 + int(m2 or 0)
    elif m["de"] and 1 <= int(h1) <= 7:
        inicio, fin = inicio + 720, fin + (720 if int(h2) < 12 else 0)
        avisos.append(f"«{' '.join(m.group(0).split())}» lo entiendo como de {inicio // 60:02d}:{inicio % 60:02d}"
                      f" a {fin // 60:02d}:{fin % 60:02d}")
    if fin <= inicio and fin + 720 > inicio and int(h2) < 12:
        fin += 720  # «de 11 a 1»
    if not inicio < fin < 24 * 60:
        return None
    return f"{inicio // 60:02d}:{inicio % 60:02d}", fin - inicio


def lapso(m: re.Match) -> int:
    """Minutes in «2 horas», «media hora», «una hora y media», «20 minutos»."""
    if m["hymedia"]:
        return 90
    n = 0.5 if m["n"].lower() == "media" else numero(m["n"])
    minutos = n * 60 if fechas.clave(m["u"]).startswith("hora") else n
    return int(minutos + (30 if m["ymedia"] else 0))

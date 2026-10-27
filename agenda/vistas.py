"""Which tasks each view shows, and in what order. Shared by the CLI and the panel."""
from __future__ import annotations

import datetime as dt

from . import fechas
from .fichas import Tarea

VISTAS = ["inicio", "hoy", "proximo", "bandeja", "abiertas", "cerradas", "todas"]
DIAS_PROXIMO = 14
# Open tasks parked for later stay out of the daily views until their review day.
ACTIVOS = {"pendiente", "en-curso", "esperando"}


def _dia(t: Tarea) -> dt.date | None:
    return fechas.desde_iso(t.fecha) if t.fecha else None


def orden_agenda(t: Tarea) -> tuple:
    """Day, then tasks with a time by time, then by priority."""
    dia = _dia(t) or dt.date.max
    return (dia, 0 if t.hora else 1, t.hora or "", t.prioridad, int(t.id[2:]))


def orden_prioridad(t: Tarea) -> tuple:
    return (t.prioridad, _dia(t) or dt.date.max, t.hora or "99:99", int(t.id[2:]))


def activa(t: Tarea, hoy: dt.date) -> bool:
    if t.estado in ACTIVOS:
        return True
    return t.estado == "mas-adelante" and bool(t.revisar) and fechas.desde_iso(t.revisar) <= hoy


def filtrar(tareas: list[Tarea], vista: str = "abiertas", hoy: dt.date | None = None,
            ambito: str | None = None, proyecto: str | None = None,
            estado: str | None = None, etiqueta: str | None = None) -> list[Tarea]:
    hoy = hoy or fechas.hoy()
    if vista not in VISTAS:
        raise ValueError(f"Vista no válida: {vista}. Usa: {', '.join(VISTAS)}")
    out = []
    for t in tareas:
        if ambito and ambito != "todo" and t.ambito != ambito:
            continue
        if proyecto and t.proyecto != proyecto:
            continue
        if estado and t.estado != estado:
            continue
        if etiqueta and etiqueta.lstrip("@").lower() not in t.etiquetas:
            continue
        dia = _dia(t)
        if vista in ("hoy", "inicio"):
            # Inicio is Hoy plus whatever waits for a review today (shown with its reason in the panel).
            toca_revisar = bool(t.revisar) and fechas.desde_iso(t.revisar) <= hoy
            ok = activa(t, hoy) and ((dia is not None and dia <= hoy) or (vista == "inicio" and toca_revisar))
        elif vista == "proximo":
            ok = activa(t, hoy) and dia is not None and hoy <= dia <= hoy + dt.timedelta(days=DIAS_PROXIMO)
        elif vista == "bandeja":
            ok = t.abierta and t.estado != "mas-adelante" and not t.proyecto
        elif vista == "abiertas":
            ok = t.abierta
        elif vista == "cerradas":
            ok = not t.abierta
        else:
            ok = True
        if ok:
            out.append(t)
    key = orden_prioridad if vista in ("hoy", "inicio", "bandeja") else orden_agenda
    return sorted(out, key=key)


def vencida(t: Tarea, momento: dt.datetime | None = None) -> bool:
    if not t.fecha or not t.abierta:
        return False
    now = momento or fechas.ahora()
    dia = fechas.desde_iso(t.fecha)
    if dia != now.date():
        return dia < now.date()
    return bool(t.hora) and t.hora < now.strftime("%H:%M")


def cuando(t: Tarea, momento: dt.datetime | None = None) -> str:
    """'Vencida ayer', 'Hoy, 14:00', 'Bloque 13:00–14:00', 'jue 30/10'."""
    if not t.fecha:
        return ""
    now = momento or fechas.ahora()
    dia = fechas.desde_iso(t.fecha)
    texto = fechas.humana(dia, now.date())
    if dia < now.date() and t.abierta:
        return f"Vencida {texto}" if texto == "ayer" else f"Vencida el {fechas.corta(dia)}"
    texto = texto[:1].upper() + texto[1:]
    if t.hora and t.duracion:
        inicio = dt.datetime.combine(dia, dt.time.fromisoformat(t.hora))
        fin = (inicio + dt.timedelta(minutes=int(t.duracion))).strftime("%H:%M")
        return f"{texto}, {t.hora}–{fin}"
    return f"{texto}, {t.hora}" if t.hora else texto

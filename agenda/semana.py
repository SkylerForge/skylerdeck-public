"""The weekly sheet shown on Inicio: every task of one week (Monday to Sunday), day by day.

A day lists the tasks planned for it, the later repeats of recurring tasks (projected
from their rule, not real cards yet), the reviews of waiting or parked tasks, and the
tasks already done that day. Tasks overdue from earlier weeks go apart.
"""
from __future__ import annotations

import datetime as dt

from . import fechas, recurrencia, vistas
from .fichas import Fichas, Tarea
from .panel import tarea_json

MAX_REPETICIONES = 400


def lunes_de(dia: dt.date) -> dt.date:
    return dia - dt.timedelta(days=dia.weekday())


def _repeticiones(t: Tarea, lunes: dt.date, domingo: dt.date) -> list[dt.date]:
    try:
        regla = recurrencia.parsear(t.repetir)
    except ValueError:
        return []
    out, dia = [], fechas.desde_iso(t.fecha)
    fin = min(domingo, fechas.desde_iso(t.hasta)) if t.hasta else domingo  # «hasta»: no repeats after it
    for _ in range(MAX_REPETICIONES):
        dia = regla.siguiente(dia)
        if dia > fin:
            break
        if dia >= lunes:
            out.append(dia)
    return out


def _orden(item: dict, t: Tarea) -> tuple:
    return (item["tipo"] == "hecha", 0 if t.hora else 1, t.hora or "", t.prioridad, int(t.id[2:]))


def construir(fichas: Fichas, ambito: str | None, ahora: dt.datetime, desde: dt.date | None = None,
              semanas: int = 1) -> dict:
    """`semanas` whole weeks from the Monday of `desde` (the month view asks for 5 or 6)."""
    hoy = ahora.date()
    lunes = lunes_de(desde or hoy)
    domingo = lunes + dt.timedelta(days=7 * semanas - 1)
    amb = ambito if ambito in ("personal", "laboral") else None
    nombres = {p.slug: p.nombre for p in fichas.proyectos.listar()}
    todas = [t for t in fichas.listar() if not amb or t.ambito == amb]

    dias: dict[str, list[dict]] = {(lunes + dt.timedelta(days=i)).isoformat(): [] for i in range(7 * semanas)}
    usadas: dict[str, Tarea] = {}

    def poner(dia: str, t: Tarea, tipo: str) -> None:
        dias[dia].append({"id": t.id, "tipo": tipo})
        usadas[t.id] = t

    vencidas = []
    for t in todas:
        if t.estado == "soltada":
            continue
        en_semana = bool(t.fecha) and t.fecha in dias
        if t.estado == "hecha":
            if en_semana:
                poner(t.fecha, t, "hecha")
            continue
        if en_semana and t.estado != "mas-adelante":
            poner(t.fecha, t, "tarea")
        if t.repetir and t.fecha:
            for dia in _repeticiones(t, lunes, domingo):
                poner(dia.isoformat(), t, "repeticion")
        if t.revisar and t.revisar in dias and t.estado in ("esperando", "mas-adelante") and t.revisar != t.fecha:
            poner(t.revisar, t, "revisar")
        if lunes <= hoy <= domingo and t.fecha and t.fecha < lunes.isoformat() and vistas.activa(t, hoy):
            vencidas.append(t)
            usadas[t.id] = t

    for dia, items in dias.items():
        items.sort(key=lambda item: _orden(item, usadas[item["id"]]))
    vencidas.sort(key=vistas.orden_prioridad)
    pendientes = {i["id"] for items in dias.values() for i in items if i["tipo"] != "hecha"}
    return {
        "lunes": lunes.isoformat(),
        "hoy": hoy.isoformat(),
        "ahora": ahora.strftime("%Y-%m-%dT%H:%M"),
        "dias": [{"fecha": dia, "items": items} for dia, items in dias.items()],
        "vencidas": [t.id for t in vencidas],
        "pendientes": len(pendientes | {t.id for t in vencidas}),
        "tareas": {id_: tarea_json(t, nombres, ahora) for id_, t in usadas.items()},
    }


def construir_mes(fichas: Fichas, ambito: str | None, ahora: dt.datetime, mes: str | None = None) -> dict:
    """The month grid: whole weeks from the Monday before day 1 to the Sunday after the last day."""
    primero = dt.date.fromisoformat(f"{mes}-01") if mes else ahora.date().replace(day=1)
    siguiente = (primero.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    lunes = lunes_de(primero)
    semanas = -(-((siguiente - lunes).days) // 7)
    data = construir(fichas, ambito, ahora, lunes, semanas)
    data["mes"] = primero.strftime("%Y-%m")
    return data


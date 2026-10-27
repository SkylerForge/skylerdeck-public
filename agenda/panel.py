"""What the page gets in one request: tasks, views, today's agenda and projects."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path

from . import fechas, frontmatter, vistas
from .fichas import Fichas, Tarea

DIAS_PROGRESO = 7


def _fin(t: Tarea) -> str:
    if not t.hora:
        return ""
    inicio = dt.datetime.combine(fechas.desde_iso(t.fecha), dt.time.fromisoformat(t.hora))
    return (inicio + dt.timedelta(minutes=int(t.duracion or 0))).strftime("%H:%M")


def tarea_json(t: Tarea, nombres: dict[str, str], ahora: dt.datetime) -> dict:
    data = t.to_dict()
    data["cuando"] = vistas.cuando(t, ahora)
    data["vencida"] = vistas.vencida(t, ahora)
    data["fin"] = _fin(t)
    data["proyecto_nombre"] = nombres.get(t.proyecto, t.proyecto)
    data["toca_revisar"] = bool(t.revisar) and t.revisar <= ahora.date().isoformat() and t.abierta
    return data


def construir(fichas: Fichas, ambito: str | None, ahora: dt.datetime) -> dict:
    hoy = ahora.date()
    amb = ambito if ambito in ("personal", "laboral") else None
    todas = fichas.listar()
    proyectos = fichas.proyectos.listar(amb)
    nombres = {p.slug: p.nombre for p in fichas.proyectos.listar()}
    abiertas = vistas.filtrar(todas, "abiertas", hoy, ambito=amb)

    def ids(vista: str) -> list[str]:
        return [t.id for t in vistas.filtrar(todas, vista, hoy, ambito=amb)]

    def agenda(dia: dt.date) -> list[str]:
        timed = [t for t in abiertas if t.fecha == dia.isoformat() and t.hora and vistas.activa(t, hoy)]
        return [t.id for t in sorted(timed, key=lambda t: t.hora)]

    hoy_agenda = agenda(hoy)
    por_id = {t.id: t for t in abiertas}
    reloj = ahora.strftime("%H:%M")
    siguiente = None
    for id_ in hoy_agenda:
        t = por_id[id_]
        fin = _fin(t) if t.duracion else t.hora
        if fin >= reloj:
            siguiente = {"id": id_, "ahora": t.hora <= reloj, "hasta": _fin(t) if t.duracion else ""}
            break

    desde = (hoy - dt.timedelta(days=DIAS_PROGRESO)).isoformat()
    lista_proyectos = []
    for p in proyectos:
        suyas = [t for t in todas if t.proyecto == p.slug]
        abiertas_p = sum(1 for t in suyas if t.abierta)
        hechas = sum(1 for t in suyas if t.estado == "hecha" and (t.cerrada or "") >= desde)
        total = abiertas_p + hechas
        lista_proyectos.append({**p.to_dict(), "abiertas": abiertas_p, "hechas": hechas,
                                "progreso": round(hechas / total, 3) if total else 0})

    vistas_ids = {v: ids(v) for v in ("inicio", "hoy", "proximo", "bandeja")}
    return {
        "ahora": ahora.strftime("%Y-%m-%dT%H:%M"),
        "hoy": hoy.isoformat(),
        "nombre": os.environ.get("AGENDA_NOMBRE", "").strip()[:40],
        "zona": fechas.TZ.key,
        "ambito": amb or "todo",
        "tareas": [tarea_json(t, nombres, ahora) for t in abiertas],
        "vistas": vistas_ids,
        "conteos": {v: len(x) for v, x in vistas_ids.items()},
        "agenda": {"hoy": hoy_agenda, "manana": agenda(hoy + dt.timedelta(days=1))},
        "siguiente": siguiente,
        "proyectos": lista_proyectos,
        "todos_proyectos": [p.to_dict() for p in fichas.proyectos.listar()],
    }


def ficha_json(fichas: Fichas, id_: str, ahora: dt.datetime) -> dict:
    t = fichas.obtener(id_)
    nombres = {p.slug: p.nombre for p in fichas.proyectos.listar()}
    data = tarea_json(t, nombres, ahora)
    data["contexto"] = frontmatter.section(t.cuerpo, "Contexto") or ""
    bitacora = frontmatter.section(t.cuerpo, "Bitácora") or ""
    data["bitacora"] = [line[2:] for line in bitacora.splitlines() if line.startswith("- ")]
    return data


def huella(*dirs: Path) -> str:
    """Changes whenever a file in these folders is added, removed or written."""
    h = hashlib.sha1()
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                st = p.stat()
                h.update(f"{p.relative_to(d)}:{st.st_mtime_ns}:{st.st_size};".encode())
    return h.hexdigest()[:12]

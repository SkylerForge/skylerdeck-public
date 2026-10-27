"""Finds open tasks from a few words, so the bot never needs task numbers.

«dentista», «la cita del dentista», «la reunión con Marta del lunes»: a date or time in the words
narrows the search (through the quick-add parser), and every other word must start a word of the
title (accents and case ignored; plurals match). Words like «cita» or «evento» only count when
nothing else is given, since people say «borra la cita del dentista» about a task called «Dentista».
"""
from __future__ import annotations

import datetime as dt
import re

from . import fechas, quickadd, vistas
from .fichas import ID_RE, Fichas, Tarea, normalizar_id

VACIAS = {"el", "la", "los", "las", "lo", "un", "una", "unos", "unas", "de", "del", "al", "a", "con", "en",
          "para", "por", "y", "o", "mi", "mis", "tu", "tus", "su", "sus", "que", "esa", "ese", "esta", "este",
          # how many, not which: «borra las dos clases de crossfit», «quita todas las del gimnasio»
          "esas", "esos", "estas", "estos", "dos", "tres", "cuatro", "ambas", "ambos", "todas", "todos"}
GENERICAS = {"cita", "citas", "tarea", "tareas", "evento", "eventos", "recordatorio", "recordatorios", "aviso", "cosa"}
PALABRA_RE = re.compile(r"[a-z0-9ñ]+")


def es_id(texto: str) -> bool:
    return bool(ID_RE.match(texto.strip()))


def _palabras(texto: str) -> list[str]:
    return [w for w in PALABRA_RE.findall(fechas.clave(texto).replace("ñ", "n")) if w not in VACIAS]


def _encaja(buscada: str, titulo: list[str]) -> bool:
    # «dentista» finds «Dentistas» and the other way round; short words must start a word.
    return any(w.startswith(buscada) or (len(w) >= 4 and buscada.startswith(w)) for w in titulo)


def encontrar(fichas: Fichas, texto: str, hoy: dt.date | None = None) -> list[Tarea]:
    """Open tasks that match, soonest first. A task number finds that task alone."""
    hoy = hoy or fechas.hoy()
    texto = texto.strip()
    abiertas = vistas.filtrar(fichas.listar(), "abiertas", hoy)
    if es_id(texto):
        id_ = normalizar_id(texto)
        return [t for t in abiertas if t.id == id_]
    r = quickadd.parsear(texto)
    if r.fecha:
        abiertas = [t for t in abiertas if t.fecha == r.fecha]
    if r.hora:
        abiertas = [t for t in abiertas if t.hora == r.hora] or abiertas
    palabras = _palabras(r.titulo)
    concretas = [w for w in palabras if w not in GENERICAS] or palabras
    if not concretas:
        return abiertas if r.fecha else []
    return [t for t in abiertas if all(_encaja(w, _palabras(t.titulo)) for w in concretas)]

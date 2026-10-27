"""Links between tasks, notes and projects (`[[...]]`), backlinks, tags, suggestions and search.

A link target is, in this order: a task id (`[[T-012]]`), a note (by title or slug,
daily notes by date: `[[2026-10-26]]`) or a project (by name or slug). `[[target|text]]`
shows another text. Links are written in note bodies and in the body of task cards.
Everything is computed from the files on each call: there is no index to go stale.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import fechas
from .errores import AgendaError
from .fichas import ID_RE, Fichas, Tarea, normalizar_id
from .notas import Nota, Notas, es_diario
from .proyectos import Proyecto, slugify

ENLACE_RE = re.compile(r"\[\[([^\[\]|\n]{1,120})(?:\|([^\[\]\n]{1,120}))?\]\]")
MAX_SUGERENCIAS = 12
MAX_RESULTADOS = 20


@dataclass
class Destino:
    tipo: str  # tarea | nota | proyecto
    ref: str  # task id, note slug or project slug
    titulo: str

    def to_dict(self) -> dict:
        return {"tipo": self.tipo, "ref": self.ref, "titulo": self.titulo}


def enlaces_de(texto: str) -> list[str]:
    return [m.group(1).strip() for m in ENLACE_RE.finditer(texto or "")]


class Indice:
    """Everything that can be linked, read once per request."""

    def __init__(self, fichas: Fichas, notas: Notas):
        self.fichas = fichas
        self.notas_store = notas
        self.tareas: list[Tarea] = fichas.listar()
        self.notas: list[Nota] = notas.listar()
        self.proyectos: list[Proyecto] = fichas.proyectos.listar()
        self._por_id = {t.id: t for t in self.tareas}
        self._notas: dict[str, Nota] = {}
        for n in self.notas:
            self._notas.setdefault(fechas.clave(n.titulo), n)
            self._notas.setdefault(n.slug, n)
        self._proyectos: dict[str, Proyecto] = {}
        for p in self.proyectos:
            self._proyectos.setdefault(slugify(p.nombre), p)
            self._proyectos.setdefault(p.slug, p)

    def resolver(self, texto: str) -> Destino | None:
        texto = texto.strip()
        if ID_RE.match(texto):
            t = self._por_id.get(normalizar_id(texto))
            if t:
                return Destino("tarea", t.id, t.titulo)
        n = self._notas.get(fechas.clave(texto)) or self._notas.get(slugify(texto))
        if n:
            return Destino("nota", n.slug, n.titulo)
        if es_diario(texto):
            return Destino("nota", texto, self.notas_store.obtener(texto).titulo)
        p = self._proyectos.get(slugify(texto))
        if p:
            return Destino("proyecto", p.slug, p.nombre)
        return None

    # ---------- backlinks ----------

    def menciones(self, tipo: str, ref: str) -> list[dict]:
        """Notes and tasks that link to (tipo, ref), with the line where the link is."""
        out = []
        fuentes = [("nota", n.slug, n.titulo, n.cuerpo) for n in self.notas]
        fuentes += [("tarea", t.id, t.titulo, t.cuerpo) for t in self.tareas]
        for fuente_tipo, fuente_ref, titulo, cuerpo in fuentes:
            if (fuente_tipo, fuente_ref) == (tipo, ref):
                continue
            for linea in cuerpo.splitlines():
                if any((d := self.resolver(e)) and (d.tipo, d.ref) == (tipo, ref) for e in enlaces_de(linea)):
                    out.append({"tipo": fuente_tipo, "ref": fuente_ref, "titulo": titulo,
                                "fragmento": _legible(linea)[:200]})
                    break
        return out

    # ---------- tags ----------

    def etiquetas(self) -> list[dict]:
        cuenta: dict[str, dict] = {}
        for t in self.tareas:
            if t.abierta:
                for e in t.etiquetas:
                    cuenta.setdefault(e, {"etiqueta": e, "tareas": 0, "notas": 0})["tareas"] += 1
        for n in self.notas:
            for e in n.etiquetas:
                cuenta.setdefault(e, {"etiqueta": e, "tareas": 0, "notas": 0})["notas"] += 1
        return sorted(cuenta.values(), key=lambda x: (-(x["tareas"] + x["notas"]), x["etiqueta"]))

    def con_etiqueta(self, etiqueta: str) -> tuple[list[Tarea], list[Nota]]:
        e = etiqueta.lstrip("@").lower()
        return ([t for t in self.tareas if t.abierta and e in t.etiquetas],
                [n for n in self.notas if e in n.etiquetas])

    # ---------- suggestions and search ----------

    def _candidatos(self, incluir_cerradas: bool):
        for t in self.tareas:
            if t.abierta or incluir_cerradas:
                # Inserted as [[T-012|title]], so the text reads well and the link survives a new title.
                alias = re.sub(r"[\[\]|]", "", t.titulo)[:100].strip()
                yield "tarea", t.id, t.titulo, f"{t.id}|{alias}", f"{t.id} · {t.estado.replace('-', ' ')}", t.ambito
        for n in self.notas:
            detalle = "Nota del día" if n.tipo == "diario" else ("Nota" + (f" · {n.proyecto}" if n.proyecto else ""))
            yield "nota", n.slug, n.titulo, n.titulo, detalle, ""
        for p in self.proyectos:
            yield "proyecto", p.slug, p.nombre, p.nombre, f"Proyecto {p.ambito}", p.ambito

    def sugerir(self, consulta: str) -> list[dict]:
        """For `[[` autocomplete: what to insert (`enlace`) for each match."""
        q = fechas.clave(consulta)
        out = []
        for tipo, ref, titulo, enlace, detalle, ambito in self._candidatos(incluir_cerradas=False):
            puntos = _puntuar(q, titulo) or (3 if tipo == "tarea" and q and fechas.clave(ref).startswith(q) else 0)
            if puntos or not q:
                out.append((puntos, {"tipo": tipo, "ref": ref, "titulo": titulo, "enlace": enlace,
                                     "detalle": detalle, "ambito": ambito}))
        out.sort(key=lambda x: (-x[0], x[1]["titulo"]))
        return [x[1] for x in out[:MAX_SUGERENCIAS]]

    def buscar(self, consulta: str) -> list[dict]:
        """Ctrl+K: tasks (closed ones too), notes (titles and text), projects and tags."""
        q = fechas.clave(consulta)
        if not q:
            return []
        out = []
        for tipo, ref, titulo, _, detalle, ambito in self._candidatos(incluir_cerradas=True):
            puntos = _puntuar(q, titulo)
            if tipo == "tarea" and fechas.clave(ref).startswith(q):
                puntos = 4
            if tipo == "tarea" and not self._por_id[ref].abierta:
                puntos -= 0.5
            if not puntos and tipo == "nota":
                n = self._notas[ref] if ref in self._notas else None
                if n and q in fechas.clave(n.cuerpo):
                    puntos, detalle = 0.5, n.resumen(90)
            if puntos > 0:
                out.append((puntos, {"tipo": tipo, "ref": ref, "titulo": titulo, "detalle": detalle, "ambito": ambito}))
        for e in self.etiquetas():
            if fechas.clave(e["etiqueta"]).startswith(q.lstrip("@")):
                out.append((2.5, {"tipo": "etiqueta", "ref": e["etiqueta"], "titulo": f"@{e['etiqueta']}",
                                  "detalle": f"{e['tareas']} tareas · {e['notas']} notas", "ambito": ""}))
        out.sort(key=lambda x: (-x[0], x[1]["titulo"]))
        return [x[1] for x in out[:MAX_RESULTADOS]]


def _legible(linea: str) -> str:
    """A line as it reads: `[[T-003|el informe]]` becomes «el informe», list marks go."""
    texto = ENLACE_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), linea)
    return re.sub(r"^\s*(?:[-*+>]|\d+[.)])\s*(?:\[[ xX]\]\s*)?", "", texto).strip()


def _puntuar(q: str, titulo: str) -> float:
    if not q:
        return 0
    t = fechas.clave(titulo)
    if t.startswith(q):
        return 3
    if any(w.startswith(q) for w in re.split(r"[\s\-_/.,:;()]+", t)):
        return 2
    return 1 if q in t else 0


# ---------- rewriting links when something is renamed ----------

def reescribir(texto: str, viejos: set[str], nuevo: str) -> str:
    """Points `[[old]]` and `[[old|text]]` at `nuevo`; `viejos` holds keys from fechas.clave."""
    def cambio(m: re.Match) -> str:
        if fechas.clave(m.group(1)) not in viejos:
            return m.group(0)
        return f"[[{nuevo}|{m.group(2)}]]" if m.group(2) else f"[[{nuevo}]]"
    return ENLACE_RE.sub(cambio, texto)


def renombrar_enlaces(fichas: Fichas, notas: Notas, viejos: list[str], nuevo: str, quien: str = "yo") -> int:
    """Rewrites every link to one of `viejos` (old names) so it points at `nuevo`. Returns how many files changed."""
    claves = {fechas.clave(v) for v in viejos if v} - {fechas.clave(nuevo)}
    if not claves:
        return 0
    cambiados = 0
    for n in notas.listar():
        if any(fechas.clave(e) in claves for e in enlaces_de(n.cuerpo)):
            cambiados += notas.reescribir(n.slug, lambda cuerpo: reescribir(cuerpo, claves, nuevo))
    for t in fichas.listar():
        if any(fechas.clave(e) in claves for e in enlaces_de(t.cuerpo)):
            fichas.actualizar(t.id, lambda campos, cuerpo: (reescribir(cuerpo, claves, nuevo), f"Enlaces a «{nuevo}» actualizados"), quien)
            cambiados += 1
    return cambiados


def guardar_nota(fichas: Fichas, notas: Notas, slug: str, *, cuerpo=None, titulo=None, proyecto=None,
                 version=None, quien: str = "yo") -> Nota:
    nota, anterior = notas.guardar(slug, cuerpo=cuerpo, titulo=titulo, proyecto=proyecto, version=version)
    if anterior:
        renombrar_enlaces(fichas, notas, [anterior], nota.titulo, quien)
        nota = notas.obtener(slug)
    return nota


def renombrar_proyecto(fichas: Fichas, notas: Notas, texto: str, nuevo: str, quien: str = "yo") -> Proyecto:
    """Renames a project: new name and slug, its cards and notes follow it, and links to the old name are rewritten."""
    anterior = fichas.proyectos.obtener(texto).nombre
    proyecto, slug_anterior = fichas.proyectos.renombrar(texto, nuevo)
    if proyecto.slug != slug_anterior:
        for t in fichas.listar():
            if t.proyecto == slug_anterior:
                def cambio(campos, cuerpo):
                    campos["proyecto"] = proyecto.slug
                    return cuerpo, f"Proyecto renombrado: «{anterior}» → «{proyecto.nombre}»"
                fichas.actualizar(t.id, cambio, quien)
        for n in notas.listar():
            if n.proyecto == slug_anterior:
                notas.guardar(n.slug, proyecto=proyecto.slug)
    renombrar_enlaces(fichas, notas, [anterior, slug_anterior], proyecto.nombre, quien)
    return proyecto


def crear_desde_enlace(fichas: Fichas, notas: Notas, texto: str, proyecto: str = "") -> Destino:
    """A click on a link that goes nowhere: creates the note (or the daily note) it names."""
    indice = Indice(fichas, notas)
    destino = indice.resolver(texto)
    if destino:
        return destino
    if ID_RE.match(texto.strip()):
        raise AgendaError(f"No existe la tarea {texto.strip()}", 404)
    n = notas.crear(texto, proyecto=proyecto)
    return Destino("nota", n.slug, n.titulo)

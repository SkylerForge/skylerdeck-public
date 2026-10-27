"""Notes: one Markdown file per note in datos/notas/<slug>.md.

The header holds the title, the type (`nota` or `diario`), an optional project and the
dates; the body is free Markdown with `[[links]]` and `@tags`. The slug never changes,
so a renamed note keeps its URL; links to it are rewritten by enlaces.py.
A daily note's slug is its date (`2026-10-26`), and its file only appears once
something is written in it.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import fechas, frontmatter
from .errores import AgendaError
from .escritura import write_atomic, write_new
from .proyectos import Proyectos, slugify

ORDER = ["titulo", "tipo", "proyecto", "creada", "actualizada"]
PLAIN = {"tipo", "proyecto", "creada"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
FECHA_SLUG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ETIQUETA_RE = re.compile(r"(?<![\w@/.])@([^\W_][\w-]{0,39})")
MAX_CUERPO = 200_000


@dataclass
class Nota:
    slug: str
    titulo: str
    tipo: str
    proyecto: str
    cuerpo: str
    version: str
    creada: str
    actualizada: str
    existe: bool = True

    @property
    def etiquetas(self) -> list[str]:
        return etiquetas_de(self.cuerpo)

    def resumen(self, largo: int = 140) -> str:
        texto = re.sub(r"[#>*_`\[\]]", "", self.cuerpo)
        return frontmatter.one_line(texto)[:largo]

    def to_dict(self, con_cuerpo: bool = False) -> dict:
        data = {
            "slug": self.slug, "titulo": self.titulo, "tipo": self.tipo, "proyecto": self.proyecto,
            "etiquetas": self.etiquetas, "creada": self.creada, "actualizada": self.actualizada,
            "version": self.version, "existe": self.existe, "resumen": self.resumen(),
        }
        if con_cuerpo:
            data["cuerpo"] = self.cuerpo
        return data


def etiquetas_de(texto: str) -> list[str]:
    sin_codigo = re.sub(r"```.*?```|`[^`\n]*`", " ", texto, flags=re.DOTALL)
    out: list[str] = []
    for m in ETIQUETA_RE.finditer(sin_codigo):
        tag = m.group(1).lower()
        if tag not in out:
            out.append(tag)
    return out


def titulo_diario(dia: dt.date) -> str:
    nombre = fechas.DIAS[dia.weekday()]
    return f"{nombre[0].upper()}{nombre[1:]}, {dia.day} de {fechas.MESES[dia.month - 1]} de {dia.year}"


def es_diario(slug: str) -> bool:
    if not FECHA_SLUG_RE.match(slug):
        return False
    try:
        fechas.desde_iso(slug)
    except ValueError:
        return False
    return True


class Notas:
    def __init__(self, datos: Path):
        self.dir = Path(datos) / "notas"
        # Deleted notes are moved here, never removed, so a delete can be undone (by the page or by hand).
        self.papelera = Path(datos) / "papelera" / "notas"
        self.proyectos = Proyectos(datos)

    def _path(self, slug: str) -> Path:
        if not SLUG_RE.match(slug or ""):
            raise AgendaError(f"Nota no válida: {slug}", 404)
        return self.dir / f"{slug}.md"

    def _leer(self, path: Path) -> Nota:
        text = path.read_text("utf-8")
        campos, cuerpo = frontmatter.parse(text)
        return Nota(
            slug=path.stem,
            titulo=str(campos.get("titulo") or path.stem),
            tipo=str(campos.get("tipo") or ("diario" if es_diario(path.stem) else "nota")),
            proyecto=str(campos.get("proyecto") or ""),
            cuerpo=cuerpo.strip("\n"),
            version=frontmatter.version_of(text),
            creada=str(campos.get("creada") or ""),
            actualizada=str(campos.get("actualizada") or ""),
        )

    def listar(self) -> list[Nota]:
        if not self.dir.is_dir():
            return []
        notas = [self._leer(p) for p in self.dir.glob("*.md") if SLUG_RE.match(p.stem)]
        return sorted(notas, key=lambda n: n.actualizada, reverse=True)

    def obtener(self, slug: str) -> Nota:
        path = self._path(slug)
        if path.exists():
            return self._leer(path)
        if es_diario(slug):
            # Not written yet: shown as an empty daily note, created on its first save.
            return Nota(slug, titulo_diario(fechas.desde_iso(slug)), "diario", "", "", "", "", "", existe=False)
        raise AgendaError(f"No existe la nota «{slug}»", 404)

    def buscar_titulo(self, titulo: str) -> Nota | None:
        key = fechas.clave(titulo)
        return next((n for n in self.listar() if fechas.clave(n.titulo) == key), None)

    def _campos(self, titulo: str, proyecto: str) -> tuple[str, str]:
        titulo = frontmatter.one_line(titulo)
        if not titulo or len(titulo) > 120:
            raise AgendaError("El título de la nota debe tener entre 1 y 120 caracteres")
        if "[" in titulo or "]" in titulo or "|" in titulo:
            raise AgendaError("El título de la nota no puede llevar [ ] ni |")
        slug_proyecto = self.proyectos.obtener(proyecto).slug if proyecto else ""
        return titulo, slug_proyecto

    def crear(self, titulo: str, cuerpo: str = "", proyecto: str = "") -> Nota:
        titulo, proyecto = self._campos(titulo, proyecto)
        if self.buscar_titulo(titulo):
            raise AgendaError(f"Ya hay una nota que se llama «{titulo}»", 409)
        base = slugify(titulo)[:60].strip("-") or "nota"
        if es_diario(base):
            base = f"nota-{base}"
        self.dir.mkdir(parents=True, exist_ok=True)
        campos = {"titulo": titulo, "tipo": "nota", "proyecto": proyecto,
                  "creada": fechas.iso(fechas.hoy()), "actualizada": fechas.sello()}
        texto = frontmatter.serialize(campos, _limpiar(cuerpo), ORDER, PLAIN)
        for n in range(1, 100):
            slug = base if n == 1 else f"{base}-{n}"
            if write_new(self.dir / f"{slug}.md", texto):
                return self.obtener(slug)
        raise AgendaError("No he podido reservar un nombre de archivo para la nota", 500)

    def guardar(self, slug: str, cuerpo: str | None = None, titulo: str | None = None,
                proyecto: str | None = None, version: str | None = None) -> tuple[Nota, str | None]:
        """Saves a note; returns it with its previous title when the title changed (to rewrite links)."""
        path = self._path(slug)
        if not path.exists():
            if not es_diario(slug):
                raise AgendaError(f"No existe la nota «{slug}»", 404)
            if version:
                raise AgendaError("La nota del día ya no existe. Recarga y vuelve a intentarlo.", 409)
            return self._crear_diario(slug, cuerpo or ""), None
        text = path.read_text("utf-8")
        if version and version != frontmatter.version_of(text):
            raise AgendaError("La nota ha cambiado mientras tanto. Recarga y vuelve a intentarlo.", 409)
        campos, cuerpo_actual = frontmatter.parse(text)
        anterior = str(campos.get("titulo") or slug)
        nuevo_titulo, nuevo_proyecto = self._campos(
            anterior if titulo is None or campos.get("tipo") == "diario" else titulo,
            str(campos.get("proyecto") or "") if proyecto is None else proyecto)
        if fechas.clave(nuevo_titulo) != fechas.clave(anterior):
            otra = self.buscar_titulo(nuevo_titulo)
            if otra and otra.slug != slug:
                raise AgendaError(f"Ya hay una nota que se llama «{nuevo_titulo}»", 409)
        campos.update(titulo=nuevo_titulo, proyecto=nuevo_proyecto, actualizada=fechas.sello())
        nuevo_cuerpo = _limpiar(cuerpo) if cuerpo is not None else cuerpo_actual
        write_atomic(path, frontmatter.serialize(campos, nuevo_cuerpo, ORDER, PLAIN))
        return self.obtener(slug), (anterior if nuevo_titulo != anterior else None)

    def _crear_diario(self, slug: str, cuerpo: str) -> Nota:
        self.dir.mkdir(parents=True, exist_ok=True)
        campos = {"titulo": titulo_diario(fechas.desde_iso(slug)), "tipo": "diario",
                  "creada": fechas.iso(fechas.hoy()), "actualizada": fechas.sello()}
        if not write_new(self.dir / f"{slug}.md", frontmatter.serialize(campos, _limpiar(cuerpo), ORDER, PLAIN)):
            raise AgendaError("La nota del día se ha creado mientras tanto. Recarga y vuelve a intentarlo.", 409)
        return self.obtener(slug)

    def borrar(self, slug: str, version: str | None = None) -> str:
        """Moves the note to the bin; returns the name it has there (to undo)."""
        path = self._path(slug)
        if not path.exists():
            raise AgendaError(f"No existe la nota «{slug}»", 404)
        if version and version != frontmatter.version_of(path.read_text("utf-8")):
            raise AgendaError("La nota ha cambiado mientras tanto. Recarga y vuelve a intentarlo.", 409)
        self.papelera.mkdir(parents=True, exist_ok=True)
        nombre = f"{slug}--{fechas.ahora().strftime('%Y%m%d-%H%M%S')}.md"
        os.replace(path, self.papelera / nombre)
        return nombre

    def restaurar(self, nombre: str) -> Nota:
        """Brings a deleted note back from the bin, if its name is still free."""
        m = re.fullmatch(r"([a-z0-9][a-z0-9-]{0,80})--\d{8}-\d{6}\.md", nombre or "")
        origen = self.papelera / nombre if m else None
        if not origen or not origen.exists():
            raise AgendaError("Esa nota ya no está en la papelera", 404)
        destino = self._path(m.group(1))
        if destino.exists():
            raise AgendaError("Ya hay otra nota con ese nombre: recupérala a mano desde datos/papelera/notas", 409)
        titulo = str(frontmatter.parse(origen.read_text("utf-8"))[0].get("titulo") or "")
        if titulo and (otra := self.buscar_titulo(titulo)):
            raise AgendaError(f"Ya hay otra nota que se llama «{otra.titulo}»", 409)
        os.replace(origen, destino)
        return self.obtener(m.group(1))

    def reescribir(self, slug: str, cambio) -> bool:
        """Applies `cambio(cuerpo) -> cuerpo` to a note (used to rewrite links). True if it changed."""
        path = self._path(slug)
        campos, cuerpo = frontmatter.parse(path.read_text("utf-8"))
        nuevo = cambio(cuerpo)
        if nuevo == cuerpo:
            return False
        campos["actualizada"] = fechas.sello()
        write_atomic(path, frontmatter.serialize(campos, nuevo, ORDER, PLAIN))
        return True


def _limpiar(cuerpo: str) -> str:
    texto = str(cuerpo or "").replace("\r\n", "\n")
    if len(texto) > MAX_CUERPO:
        raise AgendaError("La nota es demasiado larga")
    return texto.strip("\n")

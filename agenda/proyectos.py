"""Projects: one Markdown file per project in datos/proyectos/<slug>.md.

The slug never changes, so renaming a project only touches its own file; cards keep
pointing at the slug (`proyecto: clientes`).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import fechas, frontmatter
from .errores import AgendaError
from .escritura import write_atomic, write_new

AMBITOS = ("laboral", "personal")
ORDER = ["nombre", "ambito", "orden", "creado", "actualizado"]
PLAIN = {"ambito", "orden", "creado"}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fechas.clave(text)).strip("-")


@dataclass
class Proyecto:
    slug: str
    nombre: str
    ambito: str
    orden: int
    cuerpo: str = ""

    def to_dict(self) -> dict:
        return {"slug": self.slug, "nombre": self.nombre, "ambito": self.ambito, "orden": self.orden}


def comprobar_ambito(ambito: str) -> str:
    value = fechas.clave(ambito)
    if value not in AMBITOS:
        raise AgendaError(f"Ámbito no válido: {ambito}. Usa personal o laboral")
    return value


class Proyectos:
    def __init__(self, datos: Path):
        self.dir = Path(datos) / "proyectos"

    def _leer(self, path: Path) -> Proyecto:
        fields, body = frontmatter.parse(path.read_text("utf-8"))
        orden = str(fields.get("orden", "0"))
        return Proyecto(
            slug=path.stem,
            nombre=str(fields.get("nombre") or path.stem),
            ambito=str(fields.get("ambito") or "personal"),
            orden=int(orden) if orden.isdigit() else 0,
            cuerpo=body,
        )

    def listar(self, ambito: str | None = None) -> list[Proyecto]:
        if not self.dir.is_dir():
            return []
        items = [self._leer(p) for p in self.dir.glob("*.md") if not p.name.startswith(".")]
        if ambito:
            items = [p for p in items if p.ambito == ambito]
        return sorted(items, key=lambda p: (AMBITOS.index(p.ambito) if p.ambito in AMBITOS else 9, p.orden, fechas.clave(p.nombre)))

    def buscar(self, texto: str) -> Proyecto | None:
        """By slug or by name, ignoring case, accents and spaces vs hyphens."""
        key = slugify(texto)
        for p in self.listar():
            if key in (p.slug, slugify(p.nombre)):
                return p
        return None

    def obtener(self, texto: str) -> Proyecto:
        found = self.buscar(texto)
        if not found:
            nombres = ", ".join(p.nombre for p in self.listar()) or "ninguno todavía"
            raise AgendaError(f"No existe el proyecto «{texto}». Hay: {nombres}", 404)
        return found

    def crear(self, nombre: str, ambito: str) -> Proyecto:
        nombre = frontmatter.one_line(nombre)
        if not nombre or len(nombre) > 60:
            raise AgendaError("El nombre del proyecto debe tener entre 1 y 60 caracteres")
        ambito = comprobar_ambito(ambito)
        slug = slugify(nombre)
        if not slug:
            raise AgendaError("El nombre del proyecto necesita alguna letra o número")
        if self.buscar(nombre):
            raise AgendaError(f"Ya existe el proyecto «{nombre}»", 409)
        orden = max((p.orden for p in self.listar(ambito)), default=0) + 1
        fields = {"nombre": nombre, "ambito": ambito, "orden": str(orden), "creado": fechas.iso(fechas.hoy())}
        self.dir.mkdir(parents=True, exist_ok=True)
        text = frontmatter.serialize(fields, "", ORDER, PLAIN)
        if not write_new(self.dir / f"{slug}.md", text):
            raise AgendaError(f"Ya existe un proyecto con el identificador «{slug}»", 409)
        return self.obtener(slug)

    def renombrar(self, texto: str, nuevo: str) -> tuple[Proyecto, str]:
        """Renames a project and moves it to the slug of its new name, so the old name is free again.

        Returns the project and its previous slug; the caller points cards and notes at the new one
        (enlaces.renombrar_proyecto).
        """
        proyecto = self.obtener(texto)
        nuevo = frontmatter.one_line(nuevo)
        if not nuevo or len(nuevo) > 60:
            raise AgendaError("El nombre del proyecto debe tener entre 1 y 60 caracteres")
        nuevo_slug = slugify(nuevo)
        if not nuevo_slug:
            raise AgendaError("El nombre del proyecto necesita alguna letra o número")
        otro = self.buscar(nuevo)
        if otro and otro.slug != proyecto.slug:
            raise AgendaError(f"Ya existe el proyecto «{otro.nombre}»", 409)
        path = self.dir / f"{proyecto.slug}.md"
        destino = self.dir / f"{nuevo_slug}.md"
        if nuevo_slug != proyecto.slug and destino.exists():
            raise AgendaError(f"Ya hay un proyecto guardado como «{nuevo_slug}»", 409)
        fields, body = frontmatter.parse(path.read_text("utf-8"))
        fields["nombre"] = nuevo
        fields["actualizado"] = fechas.sello()
        write_atomic(path, frontmatter.serialize(fields, body, ORDER, PLAIN))
        if nuevo_slug != proyecto.slug:
            os.replace(path, destino)
        return self.obtener(nuevo_slug), proyecto.slug


def datos_dir() -> Path:
    """AGENDA_DATOS, or datos/ next to the code."""
    env = os.environ.get("AGENDA_DATOS")
    return Path(env).expanduser() if env else Path(__file__).resolve().parent.parent / "datos"

"""Task cards: one Markdown file per task in datos/tareas/T-NNN.md.

The header holds what lists and filters need; the body holds `## Contexto`,
`## Subtareas` (a Markdown checklist) and `## Bitácora` (one line per change).
The CLI, the server and the bot all go through this module; nothing else writes cards.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import fechas, frontmatter, recurrencia
from .errores import AgendaError
from .escritura import write_atomic, write_new
from .proyectos import AMBITOS, Proyectos, comprobar_ambito

ESTADOS = ["pendiente", "en-curso", "esperando", "mas-adelante", "hecha", "soltada"]
ETIQUETAS_ESTADO = {
    "pendiente": "Pendiente", "en-curso": "En curso", "esperando": "Esperando",
    "mas-adelante": "Más adelante", "hecha": "Hecha", "soltada": "Soltada",
}
CERRADOS = {"hecha", "soltada"}
PRIORIDADES = ["p1", "p2", "p3", "p4"]

ORDER = [
    "id", "titulo", "estado", "ambito", "proyecto", "prioridad", "etiquetas",
    "fecha", "hora", "duracion", "repetir", "hasta", "esperando_a", "revisar", "caso",
    "creada", "actualizada", "cerrada",
]
PLAIN = {"id", "estado", "ambito", "proyecto", "prioridad", "fecha", "duracion", "hasta", "revisar", "creada", "cerrada"}
EDITABLES = [
    "titulo", "ambito", "proyecto", "prioridad", "etiquetas", "fecha", "hora", "duracion",
    "repetir", "hasta", "esperando_a", "revisar", "caso",
]
MAX_LEN = {"titulo": 200, "esperando_a": 80}
ETIQUETA_RE = re.compile(r"^[^\W_][\w-]{0,39}$")
# A short reference (case, file or order number), never details: it is shown on every list.
CASO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,29}$")
CHECK_RE = re.compile(r"^- \[([ xX])\] (.+)$")
ID_RE = re.compile(r"^(?:T-?)?(\d{1,6})$", re.IGNORECASE)


@dataclass
class Subtarea:
    texto: str
    hecha: bool


@dataclass
class Tarea:
    campos: dict
    cuerpo: str
    version: str
    subtareas: list[Subtarea] = field(default_factory=list)

    def __getattr__(self, name):
        campos = self.__dict__.get("campos", {})
        if name in ORDER:
            return campos.get(name, [] if name == "etiquetas" else "")
        raise AttributeError(name)

    @property
    def abierta(self) -> bool:
        return self.estado not in CERRADOS

    def to_dict(self, con_cuerpo: bool = False) -> dict:
        data = {k: self.campos.get(k, [] if k == "etiquetas" else "") for k in ORDER}
        data["subtareas"] = [{"texto": s.texto, "hecha": s.hecha} for s in self.subtareas]
        data["version"] = self.version
        if con_cuerpo:
            data["cuerpo"] = self.cuerpo
        return data


def normalizar_id(texto: str) -> str:
    m = ID_RE.match(str(texto).strip())
    if not m:
        raise AgendaError(f"Id de tarea no válido: {texto}")
    return f"T-{int(m.group(1)):03d}"


def leer_subtareas(cuerpo: str) -> list[Subtarea]:
    items = []
    for line in (frontmatter.section(cuerpo, "Subtareas") or "").splitlines():
        m = CHECK_RE.match(line.strip())
        if m:
            items.append(Subtarea(m.group(2).strip(), m.group(1) != " "))
    return items


def escribir_subtareas(cuerpo: str, items: list[Subtarea]) -> str:
    content = "\n".join(f"- [{'x' if s.hecha else ' '}] {s.texto}" for s in items)
    return frontmatter.set_section(cuerpo, "Subtareas", content, before="Bitácora")


def _fecha(key: str, value: str) -> str:
    try:
        return fechas.iso(fechas.desde_iso(value)) if fechas.DATE_RE.match(value) else _fail(key)
    except ValueError:
        return _fail(key)


def _fail(key: str):
    raise AgendaError(f"«{key}» debe ser una fecha AAAA-MM-DD")


def limpiar(key: str, value) -> str | list[str]:
    """Validates and normalises one editable field. Empty string clears it."""
    if key == "etiquetas":
        items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
        tags = []
        for tag in (t.strip().lstrip("@").lower() for t in items):
            if not tag:
                continue
            if not ETIQUETA_RE.match(tag):
                raise AgendaError(f"Etiqueta no válida: {tag}")
            if tag not in tags:
                tags.append(tag)
        return tags
    text = frontmatter.one_line(value)
    if not text:
        return ""
    if len(text) > MAX_LEN.get(key, 200):
        raise AgendaError(f"«{key}» es demasiado largo")
    if key in ("fecha", "revisar", "hasta"):
        return _fecha(key, text)
    if key == "hora":
        if not fechas.TIME_RE.match(text):
            raise AgendaError("«hora» debe ser HH:MM")
        return text
    if key == "duracion":
        if not text.isdigit() or not 5 <= int(text) <= 720:
            raise AgendaError("«duracion» son minutos, entre 5 y 720")
        return str(int(text))
    if key == "prioridad":
        if text.lower() not in PRIORIDADES:
            raise AgendaError("«prioridad» debe ser p1, p2, p3 o p4")
        return text.lower()
    if key == "ambito":
        return comprobar_ambito(text)
    if key == "repetir":
        try:
            return recurrencia.parsear(text).texto()
        except ValueError as err:
            raise AgendaError(str(err)) from err
    if key == "caso":
        if not CASO_RE.match(text):
            raise AgendaError("La referencia es solo un código corto (letras, números, / . - _), sin más datos")
        return text
    return text


class Fichas:
    def __init__(self, datos: Path):
        self.datos = Path(datos)
        self.dir = self.datos / "tareas"
        self.proyectos = Proyectos(self.datos)

    # ---------- reading ----------

    def _path(self, id_: str) -> Path:
        return self.dir / f"{normalizar_id(id_)}.md"

    def _leer(self, path: Path) -> Tarea:
        text = path.read_text("utf-8")
        campos, cuerpo = frontmatter.parse(text)
        campos.setdefault("id", path.stem)
        campos["estado"] = campos.get("estado") or "pendiente"
        campos["prioridad"] = campos.get("prioridad") or "p4"
        if not isinstance(campos.get("etiquetas", []), list):
            campos["etiquetas"] = limpiar("etiquetas", campos["etiquetas"])
        return Tarea(campos, cuerpo, frontmatter.version_of(text), leer_subtareas(cuerpo))

    def listar(self) -> list[Tarea]:
        if not self.dir.is_dir():
            return []
        paths = [p for p in self.dir.glob("T-*.md") if re.fullmatch(r"T-\d+\.md", p.name)]
        return sorted((self._leer(p) for p in paths), key=lambda t: int(t.id[2:]))

    def obtener(self, id_: str) -> Tarea:
        path = self._path(id_)
        if not path.exists():
            raise AgendaError(f"No existe la tarea {normalizar_id(id_)}", 404)
        return self._leer(path)

    # ---------- writing ----------

    def _coherente(self, campos: dict) -> None:
        """Cross-field rules: project sets the scope, a time needs a day, a rule needs a first day."""
        if campos.get("proyecto"):
            proyecto = self.proyectos.obtener(campos["proyecto"])
            campos["proyecto"] = proyecto.slug
            campos["ambito"] = proyecto.ambito
        if campos.get("ambito") not in AMBITOS:
            campos["ambito"] = "personal"
        if campos.get("hora") and not campos.get("fecha"):
            raise AgendaError("Para poner hora hace falta una fecha")
        if campos.get("duracion") and not campos.get("hora"):
            raise AgendaError("Para poner duración hace falta una hora")
        if campos.get("repetir") and not campos.get("fecha"):
            campos["fecha"] = fechas.iso(recurrencia.parsear(campos["repetir"]).primera(fechas.hoy()))
        # «hasta»: the last day a recurring task may fall on. Without a rule it means nothing, so it goes.
        if not campos.get("repetir"):
            campos.pop("hasta", None)
        elif campos.get("hasta") and campos["hasta"] < campos.get("fecha", ""):
            raise AgendaError("La repetición no puede acabar antes de su primera fecha")

    def crear(self, datos: dict, quien: str = "yo", nota: str = "") -> Tarea:
        titulo = limpiar("titulo", datos.get("titulo"))
        if not titulo:
            raise AgendaError("La tarea necesita un título")
        estado = datos.get("estado") or "pendiente"
        comprobar_estado(estado)
        campos: dict = {"titulo": titulo, "estado": estado}
        for key in EDITABLES:
            if key != "titulo" and datos.get(key):
                campos[key] = limpiar(key, datos[key])
        campos.setdefault("ambito", limpiar("ambito", datos.get("ambito") or "personal"))
        campos.setdefault("prioridad", "p4")
        self._coherente(campos)
        if estado in CERRADOS:
            campos["cerrada"] = fechas.iso(fechas.hoy())
        campos["creada"] = fechas.iso(fechas.hoy())
        campos["actualizada"] = fechas.sello()

        cuerpo = f"## Contexto\n\n{str(datos.get('contexto') or '').strip()}\n"
        if datos.get("subtareas"):
            cuerpo = escribir_subtareas(cuerpo, [Subtarea(frontmatter.one_line(s), False) for s in datos["subtareas"]])
        cuerpo = frontmatter.append_to_section(cuerpo, "Bitácora", _log(quien, nota or f"Creada en {ETIQUETAS_ESTADO[estado]}"))

        self.dir.mkdir(parents=True, exist_ok=True)
        taken = [int(p.stem[2:]) for p in self.dir.glob("T-*.md") if re.fullmatch(r"T-\d+", p.stem)]
        siguiente = max(taken, default=0) + 1
        for n in range(siguiente, siguiente + 50):
            id_ = f"T-{n:03d}"
            text = frontmatter.serialize({"id": id_, **campos}, cuerpo, ORDER, PLAIN)
            if write_new(self.dir / f"{id_}.md", text):
                return self.obtener(id_)
        raise AgendaError("No he podido reservar un id libre", 500)

    def actualizar(self, id_: str, cambio, quien: str = "yo", version: str | None = None) -> Tarea:
        """Reads the card, lets `cambio(campos, cuerpo)` edit it and return (cuerpo, log line), writes it back.

        With `version`, refuses (409) if the card changed since that version was read.
        """
        path = self._path(id_)
        if not path.exists():
            raise AgendaError(f"No existe la tarea {normalizar_id(id_)}", 404)
        text = path.read_text("utf-8")
        if version and version != frontmatter.version_of(text):
            raise AgendaError("La tarea ha cambiado mientras tanto. Recarga y vuelve a intentarlo.", 409)
        campos, cuerpo = frontmatter.parse(text)
        cuerpo, entrada = cambio(campos, cuerpo)
        self._coherente(campos)
        campos["actualizada"] = fechas.sello()
        if entrada:
            cuerpo = frontmatter.append_to_section(cuerpo, "Bitácora", _log(quien, entrada))
        write_atomic(path, frontmatter.serialize(campos, cuerpo, ORDER, PLAIN))
        return self.obtener(id_)

    def editar(self, id_: str, cambios: dict, quien: str = "yo", version: str | None = None) -> Tarea:
        keys = [k for k, v in cambios.items() if v is not None]
        desconocidos = [k for k in keys if k not in EDITABLES]
        if desconocidos:
            raise AgendaError(f"No se puede editar: {', '.join(desconocidos)}")
        if not keys:
            raise AgendaError("No hay cambios")
        limpios = {k: limpiar(k, cambios[k]) for k in keys}
        if "titulo" in limpios and not limpios["titulo"]:
            raise AgendaError("La tarea necesita un título")

        def cambio(campos, cuerpo):
            cambiados = [k for k in keys if campos.get(k, [] if k == "etiquetas" else "") != limpios[k]]
            campos.update(limpios)
            if "hora" in limpios and not limpios["hora"]:
                campos["duracion"] = ""
            if "fecha" in limpios and not limpios["fecha"]:
                campos["hora"] = campos["duracion"] = campos["repetir"] = ""
            return cuerpo, (f"Edita {', '.join(cambiados)}" if cambiados else "")

        return self.actualizar(id_, cambio, quien, version)

    def mover(self, id_: str, estado: str, quien: str = "yo", version: str | None = None,
              esperando_a: str | None = None, revisar: str | None = None, nota: str = "") -> Tarea:
        comprobar_estado(estado)
        if estado == "hecha":
            return self.completar(id_, quien, version, nota)

        def cambio(campos, cuerpo):
            desde = campos.get("estado") or "pendiente"
            campos["estado"] = estado
            campos["cerrada"] = fechas.iso(fechas.hoy()) if estado in CERRADOS else ""
            if esperando_a is not None:
                campos["esperando_a"] = limpiar("esperando_a", esperando_a)
            elif estado != "esperando":
                campos["esperando_a"] = ""
            if revisar is not None:
                campos["revisar"] = limpiar("revisar", revisar)
            elif estado not in ("esperando", "mas-adelante"):
                campos["revisar"] = ""
            paso = ETIQUETAS_ESTADO[estado] if desde == estado else f"{ETIQUETAS_ESTADO.get(desde, desde)} → {ETIQUETAS_ESTADO[estado]}"
            if estado == "esperando" and campos.get("esperando_a"):
                paso += f" (a {campos['esperando_a']})"
            return cuerpo, f"{paso}. {nota}" if nota else paso

        return self.actualizar(id_, cambio, quien, version)

    def completar(self, id_: str, quien: str = "yo", version: str | None = None, nota: str = "") -> Tarea:
        """Closes the task; a recurring one moves on to its next date instead and starts over."""

        def cambio(campos, cuerpo):
            regla_texto = campos.get("repetir")
            if not regla_texto or not campos.get("fecha"):
                campos["estado"] = "hecha"
                campos["cerrada"] = fechas.iso(fechas.hoy())
                return cuerpo, f"Hecha. {nota}" if nota else "Hecha"
            regla = recurrencia.parsear(regla_texto)
            hoy = fechas.hoy()
            siguiente = regla.siguiente(fechas.desde_iso(campos["fecha"]), hasta_pasar=hoy)
            if campos.get("hasta") and fechas.iso(siguiente) > campos["hasta"]:
                campos["estado"] = "hecha"
                campos["cerrada"] = fechas.iso(hoy)
                entrada = f"Hecha; era la última ({regla_texto} hasta el {fechas.corta(fechas.desde_iso(campos['hasta']))})"
                return cuerpo, f"{entrada}. {nota}" if nota else entrada
            campos["fecha"] = fechas.iso(siguiente)
            campos["estado"] = "pendiente"
            campos["esperando_a"] = campos["revisar"] = ""
            subtareas = leer_subtareas(cuerpo)
            if subtareas:
                cuerpo = escribir_subtareas(cuerpo, [Subtarea(s.texto, False) for s in subtareas])
            entrada = f"Hecha ({regla_texto}); la siguiente, {fechas.humana(siguiente, hoy)}"
            return cuerpo, f"{entrada}. {nota}" if nota else entrada

        return self.actualizar(id_, cambio, quien, version)

    def saltar(self, id_: str, quien: str = "yo", version: str | None = None) -> Tarea:
        """Skips the next date of a recurring task without doing it: it moves on, nothing is ticked.
        Skipping the last one before «hasta» drops the task."""

        def cambio(campos, cuerpo):
            regla_texto = campos.get("repetir")
            if not regla_texto or not campos.get("fecha"):
                raise AgendaError("Solo se puede saltar una tarea que se repite")
            actual = fechas.desde_iso(campos["fecha"])
            siguiente = recurrencia.parsear(regla_texto).siguiente(actual)
            if campos.get("hasta") and fechas.iso(siguiente) > campos["hasta"]:
                campos["estado"] = "soltada"
                campos["cerrada"] = fechas.iso(fechas.hoy())
                return cuerpo, f"Saltada la del {fechas.corta(actual)}; era la última"
            campos["fecha"] = fechas.iso(siguiente)
            return cuerpo, f"Saltada la del {fechas.corta(actual)}; la siguiente, {fechas.humana(siguiente)}"

        return self.actualizar(id_, cambio, quien, version)

    def anotar(self, id_: str, texto: str, quien: str = "yo") -> Tarea:
        nota = frontmatter.one_line(texto)
        if not nota:
            raise AgendaError("La nota está vacía")
        if len(nota) > 4000:
            raise AgendaError("La nota es demasiado larga")
        return self.actualizar(id_, lambda campos, cuerpo: (cuerpo, nota), quien)

    def contexto(self, id_: str, texto: str, quien: str = "yo", version: str | None = None) -> Tarea:
        """Replaces the free Markdown of `## Contexto`."""
        texto = str(texto or "").replace("\r\n", "\n").strip()
        if len(texto) > 20000:
            raise AgendaError("El contexto es demasiado largo")
        if re.search(r"^## ", texto, re.MULTILINE):
            raise AgendaError("El contexto no puede tener títulos de nivel 2 (##); usa ### o menos")

        def cambio(campos, cuerpo):
            if (frontmatter.section(cuerpo, "Contexto") or "").strip() == texto:
                return cuerpo, ""
            return frontmatter.set_section(cuerpo, "Contexto", texto, before="Subtareas"), "Edita el contexto"

        return self.actualizar(id_, cambio, quien, version)

    def subtarea(self, id_: str, accion: str, valor: str, quien: str = "yo", version: str | None = None) -> Tarea:
        """accion: anadir (valor = texto), marcar / desmarcar / quitar (valor = número, desde 1)."""

        def cambio(campos, cuerpo):
            items = leer_subtareas(cuerpo)
            if accion == "anadir":
                texto = frontmatter.one_line(valor)
                if not texto or len(texto) > 200:
                    raise AgendaError("La subtarea debe tener entre 1 y 200 caracteres")
                items.append(Subtarea(texto, False))
                entrada = f"Subtarea: {texto}"
            else:
                if not str(valor).isdigit() or not 1 <= int(valor) <= len(items):
                    raise AgendaError(f"No hay subtarea {valor} (hay {len(items)})")
                item = items[int(valor) - 1]
                if accion == "quitar":
                    items.remove(item)
                    entrada = f"Quita la subtarea «{item.texto}»"
                elif accion in ("marcar", "desmarcar"):
                    item.hecha = accion == "marcar"
                    entrada = f"{'Hecha' if item.hecha else 'Reabierta'} la subtarea «{item.texto}»"
                else:
                    raise AgendaError(f"Acción de subtarea no válida: {accion}")
            return escribir_subtareas(cuerpo, items), entrada

        return self.actualizar(id_, cambio, quien, version)


def comprobar_estado(estado: str) -> None:
    if estado not in ESTADOS:
        raise AgendaError(f"Estado no válido: {estado}. Usa: {', '.join(ESTADOS)}")


def _log(quien: str, texto: str) -> str:
    nombre = frontmatter.one_line(quien) or "yo"
    return f"- {fechas.sello()} · {nombre[:1].upper()}{nombre[1:]}: {frontmatter.one_line(texto)}"

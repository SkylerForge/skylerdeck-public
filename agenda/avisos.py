"""Reminders by Telegram: a heads-up before each task with a time, and a morning summary.
Run every minute by a systemd timer (`python -m agenda.avisos`).

The panel only edits the settings (`avisos.json`) and asks for a test (`aviso-prueba`); this
process and the bot (agenda.bot_servicio) are the only parts that talk to the internet. Task
reminders carry a «Hecha» button, which the bot handles. Each reminder is sent once (state in
`avisos-estado.json`); after downtime, stale ones are skipped instead of arriving in a burst.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

from . import fechas, telegram, vistas
from .errores import AgendaError
from .escritura import write_atomic
from .fichas import Fichas, Tarea
from .proyectos import datos_dir

AJUSTES_POR_DEFECTO = {"tareas_hora": True, "antelacion": 15, "resumen": True, "hora_resumen": "08:00",
                       "noche": False, "hora_noche": "21:00", "repaso": False, "hora_repaso": "19:00"}
INTERRUPTORES = ("tareas_hora", "resumen", "noche", "repaso")
HORAS = {"hora_resumen": "del resumen", "hora_noche": "del resumen de la noche", "hora_repaso": "del repaso semanal"}
POSPONER = (10, 60)  # minutes offered by the snooze buttons
ANTELACIONES = (5, 10, 15, 30, 60)
TARDE_MIN = 10  # a reminder still goes out this long after the task started, never later
FIN_RESUMEN = "12:00"  # after this, a missed morning summary is skipped
DIAS_ESTADO = 3
MAX_LINEAS_RESUMEN = 12


def config_dir() -> Path:
    return Path(os.environ.get("AGENDA_CONFIG", "~/.config/skylerdeck")).expanduser()


# ---------- settings (the panel edits them) ----------

def leer_ajustes(config: Path | None = None) -> dict:
    path = (config or config_dir()) / "avisos.json"
    ajustes = dict(AJUSTES_POR_DEFECTO)
    try:
        guardados = json.loads(path.read_text("utf-8"))
        if isinstance(guardados, dict):
            ajustes.update({k: v for k, v in guardados.items() if k in AJUSTES_POR_DEFECTO})
    except (OSError, ValueError):
        pass
    return ajustes


def guardar_ajustes(cambios: dict, config: Path | None = None) -> dict:
    ajustes = leer_ajustes(config)
    for clave, valor in cambios.items():
        if clave in INTERRUPTORES:
            ajustes[clave] = bool(valor)
        elif clave == "antelacion":
            if int(valor) not in ANTELACIONES:
                raise AgendaError(f"La antelación debe ser {', '.join(map(str, ANTELACIONES))} minutos")
            ajustes[clave] = int(valor)
        elif clave in HORAS:
            if not fechas.TIME_RE.match(str(valor)):
                raise AgendaError(f"La hora {HORAS[clave]} debe ser HH:MM")
            ajustes[clave] = str(valor)
        else:
            raise AgendaError(f"Ajuste desconocido: {clave}")
    config = config or config_dir()
    config.mkdir(parents=True, exist_ok=True)
    write_atomic(config / "avisos.json", json.dumps(ajustes, ensure_ascii=False, indent=2))
    return ajustes


def pedir_prueba(config: Path | None = None) -> None:
    config = config or config_dir()
    config.mkdir(parents=True, exist_ok=True)
    (config / "aviso-prueba").write_text(fechas.sello())


def posponer(id_: str, minutos: int, config: Path | None = None, ahora: dt.datetime | None = None) -> dt.datetime:
    """Asks for one more reminder of that task in `minutos` (the bot's «+10 min» / «+1 h»)."""
    config = config or config_dir()
    cuando = (ahora or fechas.ahora()) + dt.timedelta(minutes=minutos)
    pospuestos = leer_pospuestos(config)
    pospuestos[id_] = cuando.strftime("%Y-%m-%d %H:%M")
    config.mkdir(parents=True, exist_ok=True)
    write_atomic(config / "avisos-pospuestos.json", json.dumps(pospuestos))
    return cuando


def leer_pospuestos(config: Path | None = None) -> dict[str, str]:
    try:
        datos = json.loads(((config or config_dir()) / "avisos-pospuestos.json").read_text("utf-8"))
        return {str(k): str(v) for k, v in datos.items()} if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def leer_copia(config: Path | None = None) -> dict | None:
    """Result of the last off-server copy (scripts/copia-datos.sh), or None if there is no remote copy."""
    try:
        estado = json.loads(((config or config_dir()) / "copia-estado.json").read_text("utf-8"))
        return estado if isinstance(estado, dict) else None
    except (OSError, ValueError):
        return None


def leer_estado(config: Path | None = None) -> dict:
    try:
        estado = json.loads(((config or config_dir()) / "avisos-estado.json").read_text("utf-8"))
        return estado if isinstance(estado, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------- what is due (pure: easy to test) ----------

def _inicio(t: Tarea) -> dt.datetime:
    return dt.datetime.combine(fechas.desde_iso(t.fecha), dt.time.fromisoformat(t.hora), tzinfo=fechas.TZ)


def pendientes(tareas: list[Tarea], ahora: dt.datetime, ajustes: dict, enviados: dict,
               nombres: dict[str, str] | None = None, pospuestos: dict[str, str] | None = None) -> list[dict]:
    """Messages due now that were not sent yet: [{clave, texto, enlace, tarea}]."""
    nombres = nombres or {}
    hoy = ahora.date()
    reloj = ahora.strftime("%H:%M")
    out = []

    def una_vez(clave: str, desde: str, hasta: str, texto) -> None:
        if clave not in enviados and desde <= reloj < hasta:
            out.append({"clave": clave, "texto": texto(), "enlace": "#/inicio", "tarea": None})

    if ajustes["resumen"]:
        una_vez(f"resumen:{hoy.isoformat()}", ajustes["hora_resumen"], FIN_RESUMEN, lambda: resumen(tareas, ahora, nombres))
    if ajustes["noche"]:
        una_vez(f"noche:{hoy.isoformat()}", ajustes["hora_noche"], "23:59", lambda: noche(tareas, ahora, nombres))
    if ajustes["repaso"] and hoy.weekday() == 6:
        una_vez(f"repaso:{hoy.isoformat()}", ajustes["hora_repaso"], "23:59", lambda: repaso(tareas, ahora, nombres))
    por_id = {t.id: t for t in tareas}
    for id_, cuando in (pospuestos or {}).items():
        t = por_id.get(id_)
        if cuando <= ahora.strftime("%Y-%m-%d %H:%M") and t and t.abierta and t.fecha and t.hora:
            out.append({"clave": f"pospuesto:{id_}:{cuando}", "texto": recordatorio(t, ahora, nombres), "enlace": f"#/t/{id_}",
                        "tarea": id_, "pospuesto": id_})
    if ajustes["tareas_hora"]:
        antes = dt.timedelta(minutes=int(ajustes["antelacion"]))
        for t in tareas:
            if not (t.fecha == hoy.isoformat() and t.hora and vistas.activa(t, hoy)):
                continue
            inicio = _inicio(t)
            clave = f"tarea:{t.id}:{t.fecha}:{t.hora}"
            if clave not in enviados and inicio - antes <= ahora < inicio + dt.timedelta(minutes=TARDE_MIN):
                out.append({"clave": clave, "texto": recordatorio(t, ahora, nombres), "enlace": f"#/t/{t.id}",
                            "tarea": t.id})
    return out


def recordatorio(t: Tarea, ahora: dt.datetime, nombres: dict[str, str]) -> str:
    minutos = round((_inicio(t) - ahora).total_seconds() / 60)
    cuando = "Ahora" if minutos <= 0 else f"En {minutos} min"
    linea2 = []
    if t.duracion:
        fin = (_inicio(t) + dt.timedelta(minutes=int(t.duracion))).strftime("%H:%M")
        linea2.append(f"Hasta las {fin}")
    if t.proyecto:
        linea2.append(nombres.get(t.proyecto, t.proyecto))
    linea2.append("Laboral" if t.ambito == "laboral" else "Personal")
    return f"{cuando} · {t.hora} {t.titulo}\n{' · '.join(linea2)}"


def resumen(tareas: list[Tarea], ahora: dt.datetime, nombres: dict[str, str]) -> str:
    hoy = ahora.date()
    del_dia = vistas.filtrar(tareas, "hoy", hoy)
    vencidas = [t for t in del_dia if t.fecha and fechas.desde_iso(t.fecha) < hoy]
    de_hoy = [t for t in del_dia if t not in vencidas]
    con_hora = sorted((t for t in de_hoy if t.hora), key=lambda t: t.hora)
    sin_hora = [t for t in de_hoy if not t.hora]
    nombre_dia = fechas.DIAS[hoy.weekday()]
    saludo = f"Buenos días, {nombre}." if (nombre := os.environ.get("AGENDA_NOMBRE", "").strip()) else "Buenos días."
    lineas = [f"{saludo} Hoy es {nombre_dia}, {hoy.day} de {fechas.MESES[hoy.month - 1]}."]
    if not del_dia:
        lineas.append("No tienes nada planificado para hoy.")
        return "\n".join(lineas)
    lineas.append(f"Tienes {len(de_hoy)} {'tarea' if len(de_hoy) == 1 else 'tareas'} para hoy.")
    filas = [f"{t.hora}  {t.titulo}" + (f" (hasta {_fin(t)})" if t.duracion else "") for t in con_hora]
    filas += [f"·  {t.titulo}" + (f"  [{t.prioridad}]" if t.prioridad in ("p1", "p2") else "") for t in sin_hora]
    if filas:
        lineas.append("")
        lineas += filas[:MAX_LINEAS_RESUMEN]
        if len(filas) > MAX_LINEAS_RESUMEN:
            lineas.append(f"… y {len(filas) - MAX_LINEAS_RESUMEN} más")
    if vencidas:
        lineas += ["", f"Vencidas: {len(vencidas)}"] + [f"·  {t.titulo} (desde el {fechas.corta(fechas.desde_iso(t.fecha))})" for t in vencidas[:5]]
    return "\n".join(lineas)


def _filas(tareas: list[Tarea]) -> list[str]:
    con_hora = sorted((t for t in tareas if t.hora), key=lambda t: t.hora)
    filas = [f"{t.hora}  {t.titulo}" + (f" (hasta {_fin(t)})" if t.duracion else "") for t in con_hora]
    filas += [f"·  {t.titulo}" + (f"  [{t.prioridad}]" if t.prioridad in ("p1", "p2") else "") for t in tareas if not t.hora]
    if len(filas) > MAX_LINEAS_RESUMEN:
        filas = filas[:MAX_LINEAS_RESUMEN] + [f"… y {len(filas) - MAX_LINEAS_RESUMEN} más"]
    return filas


def noche(tareas: list[Tarea], ahora: dt.datetime, nombres: dict[str, str]) -> str:
    """«Mañana tienes…»: tomorrow's tasks, the evening before."""
    manana = ahora.date() + dt.timedelta(days=1)
    de_manana = [t for t in vistas.filtrar(tareas, "abiertas", ahora.date()) if t.fecha == manana.isoformat()]
    cuando = f"{fechas.DIAS[manana.weekday()]}, {manana.day} de {fechas.MESES[manana.month - 1]}"
    if not de_manana:
        return f"Mañana, {cuando}, no tienes nada planificado."
    n = len(de_manana)
    return "\n".join([f"Mañana, {cuando}, tienes {n} {'tarea' if n == 1 else 'tareas'}.", ""] + _filas(de_manana))


def repaso(tareas: list[Tarea], ahora: dt.datetime, nombres: dict[str, str]) -> str:
    """Sunday: the week ahead day by day, what is overdue and what waits on someone else."""
    hoy = ahora.date()
    lineas = ["Repaso de la semana que viene."]
    semana = [t for t in vistas.filtrar(tareas, "proximo", hoy) if t.fecha > hoy.isoformat()]
    if not semana:
        lineas.append("No tienes nada planificado.")
    dia_actual = None
    for t in semana[:25]:
        if t.fecha != dia_actual:
            dia_actual = t.fecha
            dia = fechas.desde_iso(t.fecha)
            lineas += ["", f"{fechas.DIAS[dia.weekday()].capitalize()} {dia.day}"]
        lineas.append(f"{t.hora}  {t.titulo}" if t.hora else f"·  {t.titulo}")
    vencidas = [t for t in vistas.filtrar(tareas, "hoy", hoy) if t.fecha and t.fecha < hoy.isoformat()]
    if vencidas:
        lineas += ["", f"Vencidas: {len(vencidas)}"] + [f"·  {t.titulo}" for t in vencidas[:5]]
    esperando = [t for t in tareas if t.estado == "esperando"]
    if esperando:
        lineas += ["", "Esperando:"] + [f"·  {t.titulo}" + (f" (a {t.esperando_a})" if t.esperando_a else "") for t in esperando[:5]]
    return "\n".join(lineas)


def _fin(t: Tarea) -> str:
    return (_inicio(t) + dt.timedelta(minutes=int(t.duracion))).strftime("%H:%M")


# ---------- Telegram ----------

def credenciales(config: Path | None = None) -> telegram.Credenciales | None:
    return telegram.credenciales(config or config_dir())


def botones(enlace: str | None, tarea: str | None) -> list[list[dict]]:
    """For a task: «Hecha», «+10 min», «+1 h» and «→ Mañana» (the bot handles them); «Abrir en la agenda»."""
    filas = []
    if tarea:
        filas.append([{"text": "✓ Hecha", "callback_data": f"hecha:{tarea}"}]
                     + [{"text": f"+{m} min" if m < 60 else f"+{m // 60} h", "callback_data": f"mas:{tarea}:{m}"} for m in POSPONER])
        filas.append([{"text": "→ Mañana", "callback_data": f"manana:{tarea}"}])
    if enlace:
        abrir = {"text": "Abrir en la agenda", "url": enlace}
        if filas:
            filas[-1].append(abrir)
        else:
            filas.append([abrir])
    return filas


# ---------- one run (every minute) ----------

def ejecutar(fichas: Fichas, ahora: dt.datetime | None = None, config: Path | None = None, enviar=None,
             base_url: str | None = None) -> list[str]:
    """Sends whatever is due; returns the keys sent. `enviar(texto, enlace, tarea)` is injectable for tests."""
    config = config or config_dir()
    ahora = ahora or fechas.ahora()
    base_url = (base_url or os.environ.get("AGENDA_URL") or _url_guardada(config)).rstrip("/")
    if enviar is None:
        cred = credenciales(config)
        if not cred:
            _anotar(config, error="Falta el bot de Telegram (token o chat): configúralo con sudo scripts/instalar.sh telegram")
            return []
        enviar = lambda texto, enlace, tarea: telegram.enviar(  # noqa: E731
            cred.token, cred.chat, texto, botones(enlace, tarea))

    estado = leer_estado(config)
    enviados: dict = estado.get("enviados", {})
    limite = (ahora - dt.timedelta(days=DIAS_ESTADO)).isoformat()
    enviados = {k: v for k, v in enviados.items() if v >= limite}

    mensajes = []
    prueba = config / "aviso-prueba"
    if prueba.exists():
        mensajes.append({"clave": None, "texto": "Prueba de SkylerDeck: los avisos te llegarán por aquí.",
                         "enlace": "#/inicio", "tarea": None})
    nombres = {p.slug: p.nombre for p in fichas.proyectos.listar()}
    pospuestos = leer_pospuestos(config)
    mensajes += pendientes(fichas.listar(), ahora, leer_ajustes(config), enviados, nombres, pospuestos)
    copia = leer_copia(config)
    if copia and not copia.get("ok") and f"copia:{copia.get('cuando')}" not in enviados:
        mensajes.append({"clave": f"copia:{copia.get('cuando')}", "enlace": "#/ajustes", "tarea": None,
                         "texto": "La copia de seguridad no se ha podido subir a GitHub. Tienes el detalle en Ajustes."})

    hechos, error = [], None
    for m in mensajes:
        try:
            enviar(m["texto"], f"{base_url}/{m['enlace']}" if base_url.startswith("https://") else None, m["tarea"])
        except Exception as err:  # noqa: BLE001 - keep going, report in the panel
            error = str(err)[:300]
            continue
        if m["clave"]:
            enviados[m["clave"]] = ahora.isoformat()
            hechos.append(m["clave"])
        else:
            prueba.unlink(missing_ok=True)
            hechos.append("prueba")
    if pospuestos:
        _limpiar_pospuestos(config, {m["pospuesto"] for m in mensajes if m.get("pospuesto") and m["clave"] in hechos}, ahora)
    _anotar(config, enviados=enviados, error=error, enviado=bool(hechos), ahora=ahora)
    return hechos


def _limpiar_pospuestos(config: Path, enviados: set[str], ahora: dt.datetime) -> None:
    """Drops the snoozes just sent and any older than a day. Re-reads the file: the bot may have added one."""
    pospuestos = leer_pospuestos(config)
    limite = (ahora - dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    quedan = {k: v for k, v in pospuestos.items() if k not in enviados and v >= limite}
    if quedan != pospuestos:
        write_atomic(config / "avisos-pospuestos.json", json.dumps(quedan))


def _url_guardada(config: Path) -> str:
    try:
        return (config / "url").read_text().strip()
    except OSError:
        return ""


def _anotar(config: Path, *, enviados: dict | None = None, error: str | None = None, enviado: bool = False,
            ahora: dt.datetime | None = None) -> None:
    estado = leer_estado(config)
    if enviados is not None:
        estado["enviados"] = enviados
    momento = (ahora or fechas.ahora()).strftime("%Y-%m-%d %H:%M")
    estado["ultima_revision"] = momento
    if enviado:
        estado["ultimo_envio"] = momento
    if error:
        estado["ultimo_error"] = {"cuando": momento, "texto": error}
    elif enviado:
        estado.pop("ultimo_error", None)
    config.mkdir(parents=True, exist_ok=True)
    write_atomic(config / "avisos-estado.json", json.dumps(estado, ensure_ascii=False, indent=2))


def main() -> int:
    hechos = ejecutar(Fichas(datos_dir()))
    if hechos:
        print("Avisos enviados:", ", ".join(hechos), flush=True)
    error = leer_estado().get("ultimo_error")
    if error and error.get("cuando") == fechas.ahora().strftime("%Y-%m-%d %H:%M"):
        print("Error:", error["texto"], file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

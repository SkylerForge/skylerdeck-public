"""The agenda's Telegram bot: write to it and it organises the agenda.

Each line of a plain message becomes a task through the quick-add parser (rules, no LLM);
commands list tasks, close them, move them, take them off the agenda and write in today's note.
Tasks are named by a few of their words or by their number (encontrar.py); «borra la cita del
dentista» written as a message asks before taking it off, since it could also be a new task.
Taking a task off drops it (estado «soltada», as «Soltar tarea» in the panel), with «Deshacer». It serves only its owner
(the chat in telegram.env, linked first); anyone else is ignored without an answer. Every change goes through
fichas.py / notas.py, signed «telegram» in the card's log.

This module turns one update into Bot API calls through an injected `api(metodo, datos)`, so it
is tested offline; the polling loop and the setup live in bot_servicio.py.
"""
from __future__ import annotations

import datetime as dt
import secrets

from . import avisos, enlaces, fechas, quickadd, vistas
from .encontrar import encontrar, es_id
from .errores import AgendaError
from .fichas import ETIQUETAS_ESTADO, Fichas, Tarea, normalizar_id
from .bot_frases import Frases
from .bot_textos import AYUDA, MAX_BOTONES, Textos
from .notas import Notas

QUIEN = "telegram"
MAX_LINEAS = 20  # tasks from one message
MAX_SUELTAS = 4  # up to this many new tasks, each gets its own message with its buttons
MAX_PENDIENTES = 50  # texts waiting for «apúntalo como tarea nueva»
# «Borra la cita del dentista», «cancela la reunión del lunes», «quítame el gimnasio de mañana».

class Bot(Textos, Frases):
    def __init__(self, fichas: Fichas, chats, api, base_url: str = ""):
        self.fichas = fichas
        self.notas = Notas(fichas.datos)
        self.chats = {str(c) for c in chats}
        self.api = api
        self.base_url = base_url.rstrip("/") if base_url.startswith("https://") else ""
        self._pendientes: dict[str, str] = {}  # button token → text to write down as a new task

    # ---------- entry point ----------

    def atender(self, update: dict) -> str | None:
        """Handles one update. Returns what was done, for the log (never the text), or None if ignored."""
        if "callback_query" in update:
            return self._boton(update["callback_query"])
        msg = update.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat not in self.chats:
            return None
        texto = (msg.get("text") or "").strip()
        if not texto:
            self._decir(chat, "Solo entiendo texto. Escríbeme la tarea, o /ayuda.")
            return "mensaje sin texto"
        try:
            if texto.startswith("/"):
                return self._comando(chat, texto)
            hecho = self._frase(chat, texto) if "\n" not in texto else self._frase_lineas(chat, texto)
            if hecho:
                return hecho
            return self._apuntar(chat, texto)
        except AgendaError as err:
            self._decir(chat, str(err))
            return f"error: {err}"

    # ---------- commands ----------

    def _comando(self, chat: str, texto: str) -> str:
        cabeza, _, resto = texto.partition(" ")
        cmd = fechas.clave(cabeza[1:].split("@")[0])
        resto = resto.strip()
        ahora = fechas.ahora()
        hoy = ahora.date()
        if cmd in ("start", "ayuda", "help"):
            self._decir(chat, AYUDA)
        elif cmd == "hoy":
            self._lista(chat, "Hoy", vistas.filtrar(self.fichas.listar(), "hoy", hoy), ahora)
        elif cmd == "manana":
            manana = fechas.iso(hoy + dt.timedelta(days=1))
            tareas = [t for t in vistas.filtrar(self.fichas.listar(), "abiertas", hoy) if t.fecha == manana]
            self._lista(chat, "Mañana", sorted(tareas, key=vistas.orden_agenda), ahora)
        elif cmd in ("semana", "proximo"):
            self._lista(chat, "Próximos 7 días", vistas.filtrar(self.fichas.listar(), "proximo", hoy), ahora, por_dia=True)
        elif cmd == "bandeja":
            self._lista(chat, "Bandeja", vistas.filtrar(self.fichas.listar(), "bandeja", hoy), ahora)
        elif cmd in ("hecha", "hecho", "ok"):
            if not resto:
                raise AgendaError("Dime cuál: /hecha dentista, o /hecha T-12")
            ids = resto.replace(",", " ").split()
            if not all(es_id(i) for i in ids):
                return self._con_tarea(chat, resto, "hecha", "¿Cuál has hecho?")
            lineas = [self._completar(normalizar_id(i)) for i in ids]
            self._decir(chat, "\n".join(lineas))
            return f"{len(lineas)} hecha(s)"
        elif cmd == "posponer":
            if not resto:
                raise AgendaError("Dime cuál y a cuándo: /posponer dentista el lunes")
            id_, _, cuando = resto.partition(" ")
            if es_id(id_):
                cambios = self._cuando(cuando)
                t = self.fichas.editar(normalizar_id(id_), cambios, QUIEN)
                self._decir(chat, f"Pospuesta: {t.titulo}\n{vistas.cuando(t, fechas.ahora())}", self._botones(t))
                return f"pospuesta {t.id}"
            # «/posponer dentista el lunes a las 10»: the date is the new one, the words find the task.
            r = quickadd.parsear(resto)
            cambios = self._cuando(resto)
            extra = cambios["fecha"].replace("-", "") + (f":{cambios['hora'].replace(':', '')}" if "hora" in cambios else "")
            return self._con_tarea(chat, r.titulo, "pos", "¿Cuál cambio de fecha?", extra)
        elif cmd in ("borrar", "eliminar", "quitar", "cancelar", "anular"):
            if not resto:
                raise AgendaError("Dime cuál: /borrar dentista, o /borrar T-12")
            return self._pedir_quitar(chat, resto)
        elif cmd == "saltar":
            if not resto:
                raise AgendaError("Dime cuál: /saltar gimnasio")
            return self._con_tarea(chat, resto, "saltar", "¿Cuál te saltas?")
        elif cmd == "ver":
            if not resto:
                raise AgendaError("Dime cuál: /ver dentista, o /ver T-12")
            return self._con_tarea(chat, resto, "ver", "¿Cuál quieres ver?")
        elif cmd == "nota":
            if not resto:
                raise AgendaError("Escribe lo que quieres apuntar: /nota texto")
            self._nota_del_dia(resto)
            self._nota_apuntada(chat)
            return "nota del día"
        elif cmd == "buscar":
            self._decir(chat, self._buscar(resto))
        elif cmd == "probar":
            self._decir(chat, self._probar(resto))
        elif cmd == "proyectos":
            self._decir(chat, self._proyectos())
        else:
            self._decir(chat, f"No conozco /{cmd}. Mira /ayuda.")
            return "comando desconocido"
        return f"/{cmd}"

    # ---------- capture ----------

    def _apuntar(self, chat: str, texto: str) -> str:
        lineas = [l.strip().lstrip("-•*").strip() for l in texto.splitlines()]
        lineas = [l for l in lineas if l][:MAX_LINEAS]
        creadas, fallos = [], []
        for linea in lineas:
            try:
                tareas, avisos = self._crear(linea)
                creadas += [(t, avisos) for t in tareas]
            except AgendaError as err:
                fallos.append(f"«{linea[:60]}»: {err}")
        ahora = fechas.ahora()
        if creadas and len(creadas) <= MAX_SUELTAS:
            for t, avisos in creadas:  # each one as if it came alone, with its buttons
                self._apuntada(chat, t, avisos)
            if fallos:
                self._decir(chat, "\n".join(["No he podido apuntar:"] + fallos))
        else:
            partes, botones = [], None
            if creadas:
                tareas = [t for t, _ in creadas]
                partes.append(f"Apuntadas {len(creadas)}:")
                partes += [f"· {t.titulo}  ({t.id}{' · ' + vistas.cuando(t, ahora) if t.fecha else ''})" for t in tareas]
                botones = self._opciones(tareas, "ver:{}", [[self._boton_varias(tareas, f"🗑 Quitar estas {len(tareas)}")]])
            if fallos:
                partes += ["", "No he podido apuntar:"] + fallos
            self._decir(chat, "\n".join(partes), botones)
        return f"{len(creadas)} tarea(s) apuntada(s)" + (f", {len(fallos)} con error" if fallos else "")

    def _apuntada(self, chat: str, t: Tarea, avisos: list[str]) -> None:
        extra = "".join(f"\nOjo: {a}" for a in avisos)
        botones = self._botones(t)
        if t.hora and t.hora >= "13:00" and any("lo entiendo como" in a for a in avisos):
            botones.append([{"text": "Era por la mañana", "callback_data": f"am:{t.id}"}])
        self._decir(chat, f"Apuntada: {t.titulo}\n{self._meta(t, fechas.ahora()) or 'Sin fecha'}{extra}", botones)

    def _crear(self, linea: str) -> tuple[list[Tarea], list[str]]:
        """One task, or one per date for «el lunes y el miércoles» (never a recurrence)."""
        r = quickadd.parsear(linea[:500])
        if not r.titulo:
            raise AgendaError("No queda título después de leer fechas, proyecto y etiquetas")
        campos = r.campos()
        if r.proyecto:
            campos["proyecto"] = self.fichas.proyectos.obtener(r.proyecto).slug
        nota = f"Creada desde Telegram con «{linea}»"
        tareas = [self.fichas.crear({**campos, "fecha": dia}, QUIEN, nota=nota) for dia in [r.fecha, *r.otras_fechas]] \
            if r.otras_fechas else [self.fichas.crear(campos, QUIEN, nota=nota)]
        return tareas, r.avisos

    # ---------- changes ----------

    def _completar(self, id_: str) -> str:
        t = self.fichas.obtener(id_)
        if not t.abierta:
            return f"{t.titulo}: ya estaba {ETIQUETAS_ESTADO[t.estado].lower()}"
        t = self.fichas.completar(id_, QUIEN)
        if t.abierta:  # recurring: it moved on
            return f"Hecha: {t.titulo}. Vuelve {fechas.humana(fechas.desde_iso(t.fecha))}"
        return f"Hecha: {t.titulo}"

    def _cuando(self, texto: str) -> dict:
        r = quickadd.parsear(texto)
        if not r.fecha:
            raise AgendaError("No entiendo la nueva fecha. Prueba con «mañana», «el lunes», «30/10» o «en 3 días».")
        return {"fecha": r.fecha, **({"hora": r.hora} if r.hora else {})}

    def _quitar(self, id_: str) -> tuple[str, dict]:
        """Takes the task off the agenda (soltada, like «Soltar tarea» in the panel); returns the text and «Deshacer»."""
        t = self.fichas.obtener(id_)
        if not t.abierta:
            raise AgendaError(f"«{t.titulo}» ya no estaba en la agenda")
        antes = "en-curso" if t.estado == "en-curso" else "pendiente"
        t = self.fichas.mover(id_, "soltada", QUIEN, nota="Quitada desde Telegram")
        extra = f"\nSe repetía {t.repetir}: ya no volverá." if t.repetir else ""
        return f"Quitada de la agenda: {t.titulo}{extra}", {"text": "↩ Deshacer", "callback_data": f"recuperar:{t.id}:{antes}"}

    def _quitar_varias(self, ids: list[str]) -> tuple[str, dict]:
        """Several at once (the «Todas» button); «Deshacer» puts back every one."""
        quitadas, volver = [], []
        for id_ in ids:
            try:
                antes = self.fichas.obtener(id_)
                self._quitar(id_)
            except AgendaError:
                continue  # already gone: the rest still go
            quitadas.append(f"· {antes.titulo}" + (f" (se repetía {antes.repetir}: ya no volverá)" if antes.repetir else ""))
            volver.append(f"{antes.id}:{'en-curso' if antes.estado == 'en-curso' else 'pendiente'}")
        if not quitadas:
            raise AgendaError("Ya no estaban en la agenda")
        texto = f"Quitadas de la agenda {len(quitadas)}:\n" + "\n".join(quitadas)
        return texto, {"text": "↩ Deshacer", "callback_data": f"volver:{self._guardar(','.join(volver))}"}

    def _boton_varias(self, tareas: list[Tarea], texto: str) -> dict:
        return {"text": texto, "callback_data": f"varias:{self._guardar(','.join(t.id for t in tareas))}"}

    # ---------- naming tasks by their words ----------

    def _con_tarea(self, chat: str, texto: str, accion: str, pregunta: str, extra: str = "") -> str:
        """Runs `accion` on the one task the words name, or asks which one with a button each."""
        tareas = encontrar(self.fichas, texto)
        if not tareas:
            self._decir(chat, f"No encuentro nada pendiente con «{texto.strip()}». Mira /hoy o /semana, o búscalo con /buscar.")
            return f"{accion}: no encontrada"
        datos = f"{accion}:{{}}" + (f":{extra}" if extra else "")
        if len(tareas) == 1:
            return self._boton({"id": "", "data": datos.format(tareas[0].id), "message": {"chat": {"id": chat}}}, responder=chat)
        self._decir(chat, pregunta, self._opciones(tareas, datos, [[{"text": "Ninguna", "callback_data": "nada:0"}]]))
        return f"{accion}: {len(tareas)} posibles"

    def _pedir_quitar(self, chat: str, texto: str, nueva: str | None = None, o_nueva: bool = False) -> str | None:
        """Asks before taking a task off. With `nueva` (a plain message), the question also offers
        «apúntalo como tarea nueva», and so does the answer when nothing matches. With `o_nueva`, finding
        nothing returns None instead, so the message becomes a task («no hay leche»)."""
        if es_id(texto) and not self.fichas.obtener(normalizar_id(texto)).repetir:
            aviso, deshacer = self._quitar(normalizar_id(texto))
            self._decir(chat, aviso, [[deshacer]])
            return "quitada"
        tareas = encontrar(self.fichas, texto)
        if not tareas:
            if o_nueva:
                return None
            # Never a new task by itself: «borra las clases» that finds nothing must not add one.
            nuevo = [[{"text": "Apúntalo como tarea nueva", "callback_data": f"nueva:{self._guardar(nueva)}"}]] if nueva else None
            self._decir(chat, f"No encuentro nada pendiente con «{texto.strip()}». Mira /hoy o /semana, o búscalo con /buscar.", nuevo)
            return "quitar: no encontrada"
        no = [{"text": "No", "callback_data": "nada:0"}]
        if nueva:
            no = [{"text": "No: apúntalo como tarea nueva", "callback_data": f"nueva:{self._guardar(nueva)}"}]
        if len(tareas) == 1:
            self._decir(chat, *self._pregunta_quitar(tareas[0], no))
        else:
            todas = [self._boton_varias(tareas[:MAX_BOTONES], f"🗑 Todas ({min(len(tareas), MAX_BOTONES)})")]
            self._decir(chat, "¿Cuál quito de la agenda?", self._opciones(tareas, "quitar:{}", [todas, no], "🗑 "))
        return f"quitar: {len(tareas)} posible(s)"

    def _pregunta_quitar(self, t: Tarea, no: list[dict]) -> tuple[str, list[list[dict]]]:
        """A recurring task asks «only this time or all of them?»."""
        if t.repetir:
            dia = fechas.corta(fechas.desde_iso(t.fecha))
            return (f"«{t.titulo}» se repite {t.repetir}. ¿Quito solo la del {dia} o todas?",
                    [[{"text": f"⏭ Solo la del {dia}", "callback_data": f"saltar:{t.id}"}],
                     [{"text": "🗑 Todas", "callback_data": f"borrar:{t.id}"}], no])
        return (f"¿Quito de la agenda «{t.titulo}»?\n{self._meta(t, fechas.ahora()) or 'Sin fecha'}",
                [[{"text": "🗑 Sí, quítala", "callback_data": f"borrar:{t.id}"}], no])

    def _guardar(self, texto: str) -> str:
        """Keeps a text for a later button («apúntalo como tarea nueva», list items); returns its token."""
        if len(self._pendientes) >= MAX_PENDIENTES:
            self._pendientes.pop(next(iter(self._pendientes)))
        token = secrets.token_hex(4)
        self._pendientes[token] = texto
        return token

    def _deshacer_hecha(self, t: Tarea) -> dict:
        """Undo for ticking `t` (read before): a repeat goes back to its date, a closed task reopens."""
        if t.repetir:
            return {"text": "↩ Deshacer", "callback_data": f"pos:{t.id}:{t.fecha.replace('-', '')}"}
        return {"text": "↩ Deshacer", "callback_data": f"recuperar:{t.id}:{'en-curso' if t.estado == 'en-curso' else 'pendiente'}"}

    def _nota_del_dia(self, texto: str) -> None:
        slug = fechas.iso(fechas.hoy())
        actual = self.notas.obtener(slug)
        cuerpo = f"{actual.cuerpo}\n\n{texto.strip()}" if actual.cuerpo else texto.strip()
        enlaces.guardar_nota(self.fichas, self.notas, slug, cuerpo=cuerpo, quien=QUIEN)

    # ---------- buttons ----------

    def _botones(self, t: Tarea) -> list[list[dict]]:
        fila = []
        if t.abierta:
            fila.append({"text": "✓ Hecha", "callback_data": f"hecha:{t.id}"})
            fila.append({"text": "→ Mañana", "callback_data": f"manana:{t.id}"})
        if self.base_url:
            fila.append({"text": "Abrir", "url": f"{self.base_url}/#/t/{t.id}"})
        return [fila] if fila else []

    def _boton(self, cq: dict, responder: str | None = None) -> str | None:
        """A button press. `responder`: the same action asked by a command, answered with a message."""
        msg = cq.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat not in self.chats:
            return None
        accion, _, arg = str(cq.get("data", "")).partition(":")
        id_, _, extra = arg.partition(":")
        teclado = (msg.get("reply_markup") or {}).get("inline_keyboard") or []
        nuevo, texto_nuevo, botones = None, None, None  # None: drop this task's buttons
        try:
            if accion == "nueva":
                texto = self._pendientes.pop(arg, None)
                if texto is None:
                    aviso = "Este botón ya no sirve: escríbemelo otra vez"
                else:
                    self._apuntar(chat, texto)
                    aviso = "Apuntada como tarea nueva"
                nuevo = []
            elif accion == "nada":
                aviso, nuevo = "Vale, no toco nada", []
            elif accion == "varias":  # varias:<token of «T-015,T-016»>
                ids = self._pendientes.pop(arg, None)
                if ids is None:
                    aviso, nuevo = "Este botón ya no sirve: escríbemelo otra vez", []
                else:
                    aviso, deshacer = self._quitar_varias(ids.split(","))
                    nuevo, texto_nuevo = [[deshacer]], aviso
            elif accion == "volver":  # volver:<token of «T-015:pendiente,…»>, the undo of «varias»
                pares = self._pendientes.pop(arg, None)
                if pares is None:
                    aviso = "Este botón ya no sirve: recupéralas desde el panel"
                else:
                    for par in pares.split(","):
                        id_, _, estado = par.partition(":")
                        self.fichas.mover(id_, estado, QUIEN, nota="Recuperada desde Telegram")
                    aviso = f"Vuelven a estar en la agenda: {len(pares.split(','))}"
                    texto_nuevo = aviso
                nuevo = []
            else:
                id_ = normalizar_id(id_)
                if accion == "hecha":
                    antes = self.fichas.obtener(id_)
                    aviso = self._completar(id_)
                    if antes.abierta:
                        botones = [[self._deshacer_hecha(antes)]]
                elif accion == "mas":  # one more reminder later («+10 min», «+1 h»)
                    t = self.fichas.obtener(id_)
                    minutos = int(extra) if extra.isdigit() and int(extra) in avisos.POSPONER else avisos.POSPONER[0]
                    cuando = avisos.posponer(t.id, minutos)
                    aviso, nuevo = f"Te lo vuelvo a recordar a las {cuando:%H:%M}: {t.titulo}", teclado
                elif accion == "saltar":
                    antes = self.fichas.obtener(id_)
                    t = self.fichas.saltar(id_, QUIEN)
                    dia = fechas.corta(fechas.desde_iso(antes.fecha))
                    if t.abierta:
                        aviso = f"Saltada la del {dia}: {t.titulo}. La siguiente, {fechas.humana(fechas.desde_iso(t.fecha))}"
                        deshacer = {"text": "↩ Deshacer", "callback_data": f"pos:{t.id}:{antes.fecha.replace('-', '')}"}
                    else:
                        aviso = f"Saltada la del {dia}: {t.titulo}. Era la última"
                        deshacer = {"text": "↩ Deshacer", "callback_data": f"recuperar:{t.id}:pendiente"}
                    nuevo, texto_nuevo, botones = [[deshacer]], aviso, [[deshacer]]
                elif accion == "quitar":  # chosen from a list: a recurring one still asks
                    t = self.fichas.obtener(id_)
                    if t.repetir:
                        aviso, nuevo = self._pregunta_quitar(t, [{"text": "No", "callback_data": "nada:0"}])
                        texto_nuevo = aviso
                    else:
                        aviso, deshacer = self._quitar(id_)
                        nuevo, texto_nuevo, botones = [[deshacer]], aviso, [[deshacer]]
                elif accion == "prio":
                    t = self.fichas.editar(id_, {"prioridad": f"p{extra if extra in '1234' and extra else '1'}"}, QUIEN)
                    aviso = f"Prioridad {t.prioridad}: {t.titulo}"
                    nuevo, texto_nuevo = [], aviso
                elif accion == "lista":
                    cosas = self._pendientes.pop(extra, None)
                    if cosas is None:
                        aviso = "Este botón ya no sirve: escríbemelo otra vez"
                    else:
                        self._anadir_a(chat, id_, cosas.split("\n"))
                        aviso = "Añadido"
                    nuevo = []
                elif accion == "manana":
                    manana = fechas.iso(fechas.hoy() + dt.timedelta(days=1))
                    t = self.fichas.editar(id_, {"fecha": manana}, QUIEN)
                    aviso = f"Pasada a mañana: {t.titulo}"
                elif accion == "am":  # «a las 5» was 05:00 after all
                    t = self.fichas.obtener(id_)
                    if t.hora and t.hora >= "13:00":
                        t = self.fichas.editar(id_, {"hora": f"{int(t.hora[:2]) - 12:02d}{t.hora[2:]}"}, QUIEN)
                    aviso = f"Cambiada a las {t.hora}: {t.titulo}"
                elif accion == "pos":  # pos:T-012:20261029[:1730], «-» as the time clears it
                    fecha, _, hora = extra.partition(":")
                    antes = self.fichas.obtener(id_)
                    cambios = {"fecha": f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}"}
                    if hora:
                        cambios["hora"] = "" if hora == "-" else f"{hora[:2]}:{hora[2:]}"
                    t = self.fichas.editar(id_, cambios, QUIEN)
                    aviso = f"Cambiada: {t.titulo}\n{vistas.cuando(t, fechas.ahora())}"
                    previa = (antes.fecha or t.fecha).replace("-", "") + f":{antes.hora.replace(':', '') if antes.hora else '-'}"
                    deshacer = {"text": "↩ Deshacer", "callback_data": f"pos:{t.id}:{previa}"}
                    nuevo, texto_nuevo = [[deshacer]], aviso
                    botones = [[deshacer]] + self._botones(t)
                elif accion == "ver":
                    t = self.fichas.obtener(id_)
                    aviso, nuevo, botones = self._ficha(t, fechas.ahora()), teclado, self._botones(t)
                elif accion == "borrar":
                    aviso, deshacer = self._quitar(id_)
                    nuevo, texto_nuevo, botones = [[deshacer]], aviso, [[deshacer]]
                elif accion == "recuperar":
                    t = self.fichas.mover(id_, extra if extra in ("pendiente", "en-curso") else "pendiente", QUIEN,
                                          nota="Recuperada desde Telegram")
                    aviso = f"Vuelve a estar en la agenda: {t.titulo}"
                    nuevo, texto_nuevo = [], aviso
                else:
                    aviso = "Este botón ya no sirve"
        except AgendaError as err:
            aviso, botones = str(err), None
        if responder:  # asked by a command: the answer is a message, there is no button to update
            self._decir(chat, aviso, botones)
            return f"{accion} {id_}"
        self.api("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": aviso.split("\n")[0][:190]})
        if accion == "ver":
            self._decir(chat, aviso, botones)
        if nuevo is None:
            # Done or moved: that task's buttons go. Fixing the hour only removes that button.
            sobra = (lambda d: d == cq.get("data")) if accion == "am" else (lambda d: d.split(":")[1:2] == [id_])
            nuevo = [[b for b in fila if not sobra(str(b.get("callback_data", "")))] for fila in teclado]
            nuevo = [fila for fila in nuevo if fila]
        if msg.get("message_id") and texto_nuevo:
            self.api("editMessageText", {"chat_id": chat, "message_id": msg["message_id"], "text": texto_nuevo,
                                         "reply_markup": {"inline_keyboard": nuevo}})
        elif msg.get("message_id") and nuevo != teclado:
            self.api("editMessageReplyMarkup", {"chat_id": chat, "message_id": msg["message_id"],
                                                "reply_markup": {"inline_keyboard": nuevo}})
        return f"botón {accion} {id_}"

    # ---------- text ----------

    def _decir(self, chat: str, texto: str, botones: list[list[dict]] | None = None) -> None:
        datos = {"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": True}
        if botones:
            datos["reply_markup"] = {"inline_keyboard": botones}
        self.api("sendMessage", datos)

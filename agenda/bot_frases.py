"""Plain messages that talk about tasks already in the agenda instead of adding one.

«borra la cita del dentista», «hoy no hay gimnasio», «ya he ido al dentista», «pasa el dentista al
jueves», «ponle prioridad 1 al informe», «añade a la compra: leche, pan».

A rule only acts when some task matches the words (encontrar.py); otherwise the message is a new task,
as always, except an order like «borra…» / «elimina…», which answers that it found nothing (with a button
to add it after all); the infinitive («Cancelar el seguro») reads as a to-do and still becomes a task. Taking off and moving ask first and also offer «apúntalo como tarea nueva», because the same
sentence could be a task («Cancelar el seguro», «Cambiar el aceite»). Skipping and ticking act at once,
with «Deshacer». `Frases` is a mixin of `bot.Bot`.
"""
from __future__ import annotations

import re

from . import fechas, quickadd, vistas
from .bot_textos import MAX_BOTONES
from .encontrar import encontrar
from .fichas import Tarea, normalizar_id

_FIN = r"[.!\s]*$"
QUITAR_RE = re.compile(
    r"^(?:por\s+favor,?\s+)?(?:b[oó]rra|elim[ií]na|canc[eé]la|qu[ií]ta|an[uú]la)(?:r|me|la|lo|las|los|melo|mela)?"
    rf"\b[,:]?\s*(?P<resto>.*?)(?:\s+de\s+(?:la|mi)\s+agenda)?{_FIN}", re.IGNORECASE)
SALTAR_RE = re.compile(
    r"^(?:por\s+favor,?\s+)?(?:s[áa]lta(?:te|me|r)?|me\s+salto|no\s+(?:voy|ir[ée]|vamos)\s+(?:a\s+la\s+|al?\s+)?)"
    rf"(?P<resto>.+?){_FIN}", re.IGNORECASE)
NO_HAY_RE = re.compile(rf"^(?P<antes>.*?)\bno\s+(?:hay|tengo|tenemos)\s+(?P<resto>.+?){_FIN}", re.IGNORECASE)
HECHO_RE = re.compile(
    r"^(?:ya\s+)?(?:he\s+(?:ido\s+(?:a\s+la|al?)|hecho|terminado|acabado|llamado\s+(?:a\s+la|al?)|comprado|enviado|"
    r"mandado|pagado|entregado|recogido)|(?:hech[oa]s?|terminad[oa]s?|acabad[oa]s?|list[oa]s?)\b[:,]?|"
    rf"est[áa]\s+(?:hech[oa]|list[oa])\b)\s*(?P<resto>.+?){_FIN}", re.IGNORECASE)
MOVER_RE = re.compile(
    r"^(?:por\s+favor,?\s+)?(?:p[áa]sa|mu[ée]ve|c[áa]mbia|aplaza|retrasa|adelanta|traslada)(?:me|la|lo|las|los|melo|mela)?"
    rf"\s+(?P<resto>.+?){_FIN}", re.IGNORECASE)
SEPARA_RE = re.compile(r"\s+(?:a|al|para(?:\s+el)?|hasta\s+el)\s+", re.IGNORECASE)
PRIORIDAD_RE = re.compile(
    r"^(?:pon(?:le|me)?|marca|cambia)\s+(?:la\s+)?(?:prioridad\s+(?:a\s+)?|p)(?P<p>[1-4])\s+(?:a|al|a\s+la|en|para)\s+"
    rf"(?P<resto>.+?){_FIN}", re.IGNORECASE)
URGENTE_RE = re.compile(rf"^(?:marca|pon)\s+(?P<resto>.+?)\s+como\s+(?:urgente|importante|prioritari[oa]){_FIN}", re.IGNORECASE)
LISTA_DOS_PUNTOS_RE = re.compile(
    r"^(?:a[ñn][áa]de(?:me)?|mete|apunta)\s+(?:a|en)\s+(?:la\s+lista\s+de\s+)?(?P<lista>[^:]+?)\s*:\s*(?P<cosas>.+?)\s*$",
    re.IGNORECASE)
LISTA_RE = re.compile(
    r"^(?:a[ñn][áa]de(?:me)?|mete)\s+(?P<cosas>.+?)\s+(?:a|en)\s+(?:la\s+lista\s+de\s+)?"
    rf"(?P<lista>(?:(?:la|el|mi)\s+)?[^\W\d_]+(?:\s+de\s+[^\W\d_]+)?){_FIN}", re.IGNORECASE)
SEPARA_COSAS_RE = re.compile(r"\s*(?:,|;|\by\b|\be\b)\s*", re.IGNORECASE)
ARTICULO_RE = re.compile(r"^(?:la|el|los|las|mi|mis)\s+", re.IGNORECASE)
NUMERO_RE = re.compile(r"\bT-?(\d{1,6})\b", re.IGNORECASE)  # task numbers inside a text, like my own answers
MAX_COSAS = 30


class Frases:
    def _frase_lineas(self, chat: str, texto: str) -> str | None:
        """«elimina» and, below it, the tasks: one per line, or lines pasted from my own answer
        («· Clase de Crossfit (T-015 · Hoy, 21:00)»), where the numbers win. Any other message of
        several lines is new tasks, even if it starts with «Cancelar…»."""
        lineas = [l.strip().lstrip("-•*·").strip() for l in texto.splitlines()]
        lineas = [l for l in lineas if l]
        m = QUITAR_RE.match(lineas[0]) if lineas else None
        numeros = NUMERO_RE.findall(texto)
        if not m or (m["resto"] and not numeros):
            return None
        tareas = {}
        for buscar in [f"T-{n}" for n in numeros] or lineas[1:]:
            for t in encontrar(self.fichas, buscar):
                tareas.setdefault(t.id, t)
        if not tareas:
            self._decir(chat, "No encuentro esas tareas pendientes en la agenda. Mira /hoy o /semana.")
            return "quitar varias: no encontradas"
        tareas = list(tareas.values())
        if len(tareas) == 1:
            self._decir(chat, *self._pregunta_quitar(tareas[0], [{"text": "No", "callback_data": "nada:0"}]))
        else:
            ahora = fechas.ahora()
            lista = "\n".join(f"· {t.titulo}" + (f" ({vistas.cuando(t, ahora)})" if t.fecha else "") for t in tareas[:MAX_BOTONES])
            self._decir(chat, f"¿Quito de la agenda estas {min(len(tareas), MAX_BOTONES)}?\n{lista}",
                        [[self._boton_varias(tareas[:MAX_BOTONES], "🗑 Sí, quítalas")], [{"text": "No", "callback_data": "nada:0"}]])
        return f"quitar varias: {len(tareas)} posible(s)"

    def _frase(self, chat: str, texto: str) -> str | None:
        """Handles a one-line message that talks about existing tasks; None when it is a new task."""
        m = LISTA_DOS_PUNTOS_RE.match(texto)
        if m:
            return self._a_lista(chat, m["lista"], m["cosas"], crear=True)
        m = QUITAR_RE.match(texto)
        if m and not m["resto"]:
            self._decir(chat, "¿Qué quito? Dímelo así: «borra la cita del dentista».")
            return "quitar: sin texto"
        if m:
            infinitivo = texto.split()[0].lower().rstrip(",:").endswith("r")
            return self._pedir_quitar(chat, m["resto"], nueva=texto, o_nueva=infinitivo)
        m = PRIORIDAD_RE.match(texto) or URGENTE_RE.match(texto)
        if m:
            return self._actuar(chat, m["resto"], "prio", "¿A cuál le cambio la prioridad?", m.groupdict().get("p") or "1")
        m = SALTAR_RE.match(texto)
        if m:
            return self._saltar_frase(chat, texto, m["resto"])
        m = NO_HAY_RE.match(texto)
        if m:
            return self._saltar_frase(chat, texto, f"{m['resto']} {m['antes']}".strip())
        m = HECHO_RE.match(texto)
        if m:
            return self._actuar(chat, m["resto"], "hecha", "¿Cuál has hecho?")
        m = MOVER_RE.match(texto)
        if m:
            return self._mover_frase(chat, texto, m["resto"])
        m = LISTA_RE.match(texto)
        if m:
            return self._a_lista(chat, m["lista"], m["cosas"], crear=False)
        return None

    def _actuar(self, chat: str, consulta: str, accion: str, pregunta: str, extra: str = "") -> str | None:
        """One match: done at once (it can be undone). Several: a button each. None: it was a new task."""
        tareas = encontrar(self.fichas, consulta)
        if not tareas:
            return None
        datos = f"{accion}:{{}}" + (f":{extra}" if extra else "")
        if len(tareas) == 1:
            return self._boton({"id": "", "data": datos.format(tareas[0].id), "message": {"chat": {"id": chat}}}, responder=chat)
        self._decir(chat, pregunta, self._opciones(tareas, datos, [[{"text": "Ninguna", "callback_data": "nada:0"}]]))
        return f"{accion}: {len(tareas)} posibles"

    def _saltar_frase(self, chat: str, texto: str, consulta: str) -> str | None:
        """«hoy no hay gimnasio»: skips that repeat. A one-off task is offered to be taken off instead."""
        r = quickadd.parsear(consulta)
        repetidas = [t for t in encontrar(self.fichas, r.titulo) if t.repetir] if r.titulo else []
        if r.fecha and repetidas:
            exactas = [t for t in repetidas if t.fecha == r.fecha]
            if not exactas:
                t = repetidas[0]
                self._decir(chat, f"La próxima vez que toca «{t.titulo}» es el {fechas.corta(fechas.desde_iso(t.fecha))}, "
                                  "y solo puedo saltar la próxima. ¿Salto esa?",
                            [[{"text": "⏭ Sí, sáltala", "callback_data": f"saltar:{t.id}"}],
                             [{"text": "No", "callback_data": "nada:0"}]])
                return "saltar: no es la próxima"
            repetidas = exactas
        if not repetidas:
            return self._pedir_quitar(chat, consulta, nueva=texto, o_nueva=True)
        if len(repetidas) == 1:
            return self._boton({"id": "", "data": f"saltar:{repetidas[0].id}", "message": {"chat": {"id": chat}}}, responder=chat)
        self._decir(chat, "¿Cuál te saltas?", self._opciones(repetidas, "saltar:{}", [[{"text": "Ninguna", "callback_data": "nada:0"}]]))
        return f"saltar: {len(repetidas)} posibles"

    def _mover_frase(self, chat: str, texto: str, resto: str) -> str | None:
        """«pasa el dentista al jueves», «cambia el gimnasio a las 8»: asks before moving."""
        for sep in SEPARA_RE.finditer(resto):
            que, cuando = resto[:sep.start()], resto[sep.end():]
            if re.match(r"las?\s", cuando, re.IGNORECASE):
                cuando = f"a {cuando}"
            r = quickadd.parsear(cuando)
            tipos = {p["tipo"] for p in r.partes}
            if r.titulo or not tipos & {"fecha", "hora"}:
                continue  # that «a» belonged to the task's name: try the next one
            tareas = encontrar(self.fichas, que)
            if not tareas:
                return None
            ahora = fechas.ahora()

            def destino(t: Tarea) -> str:
                fecha = r.fecha if "fecha" in tipos else (t.fecha or r.fecha)
                hora = r.hora if "hora" in tipos else t.hora
                return f"pos:{t.id}:{fecha.replace('-', '')}" + (f":{hora.replace(':', '')}" if hora else "")

            no = [{"text": "No: apúntalo como tarea nueva", "callback_data": f"nueva:{self._guardar(texto)}"}]
            if len(tareas) == 1:
                t = tareas[0]
                datos = destino(t)
                fecha, _, hora = datos.split(":", 2)[2].partition(":")
                nueva = fechas.desde_iso(f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}")
                a_donde = fechas.humana(nueva, ahora.date()) + (f", {hora[:2]}:{hora[2:]}" if hora else "")
                self._decir(chat, f"¿Cambio «{t.titulo}» ({self._meta(t, ahora) or 'sin fecha'}) a {a_donde}?",
                            [[{"text": "Sí, cámbiala", "callback_data": datos}], no])
            else:
                self._decir(chat, "¿Cuál cambio?", self._opciones(tareas, destino, [no]))
            return f"mover: {len(tareas)} posible(s)"
        return None

    def _a_lista(self, chat: str, lista: str, cosas: str, crear: bool) -> str | None:
        """«añade a la compra: leche, pan»: subtasks of the task the list names (a new one with «:»)."""
        items = [c.strip()[:120] for c in SEPARA_COSAS_RE.split(cosas) if c.strip()][:MAX_COSAS]
        if not items:
            return None
        tareas = encontrar(self.fichas, lista)
        con_lista = [t for t in tareas if t.subtareas]
        if len(con_lista) == 1 or len(tareas) == 1:
            return self._anadir_a(chat, (con_lista or tareas)[0].id, items)
        if tareas:
            token = self._guardar("\n".join(items))
            self._decir(chat, "¿A qué lista lo añado?",
                        self._opciones(tareas, f"lista:{{}}:{token}", [[{"text": "Ninguna", "callback_data": "nada:0"}]]))
            return f"lista: {len(tareas)} posibles"
        if not crear:
            return None
        nombre = ARTICULO_RE.sub("", lista.strip())
        t = self.fichas.crear({"titulo": nombre[:1].upper() + nombre[1:], "subtareas": items}, "telegram",
                              nota="Lista creada desde Telegram")
        self._decir(chat, f"Nueva lista «{t.titulo}» con: {', '.join(items)}", [[{"text": "Ver la lista", "callback_data": f"ver:{t.id}"}]])
        return "lista nueva"

    def _anadir_a(self, chat: str, id_: str, items: list[str]) -> str:
        for item in items:
            t = self.fichas.subtarea(id_, "anadir", item, "telegram")
        pendientes = sum(not s.hecha for s in t.subtareas)
        self._decir(chat, f"Añadido a «{t.titulo}»: {', '.join(items)}\n{pendientes} por hacer en la lista.",
                    [[{"text": "Ver la lista", "callback_data": f"ver:{t.id}"}]])
        return f"lista: {len(items)} añadido(s)"

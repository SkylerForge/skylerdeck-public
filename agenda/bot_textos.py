"""What the bot says: lists, a task, search results, the parser preview, projects, the help.

`Textos` is a mixin of `bot.Bot`: these methods only read the agenda and build text and buttons;
everything that changes a task stays in bot.py.
"""
from __future__ import annotations

import datetime as dt

from . import enlaces, fechas, quickadd, vistas
from .fichas import ETIQUETAS_ESTADO, Tarea

MAX_LISTA = 25
MAX_BOTONES = 8

AYUDA = """Escríbeme lo que tengas que hacer, como se lo dirías a alguien, y lo apunto:

Tengo cita con el dentista el martes a las cinco y media
Recuérdame llamar a Ana pasado mañana por la tarde
Reunión con Marta el lunes 2 de 10 a 12
Dentro de 2 horas llamar al taller
Gimnasio todos los días a las 9 hasta el 15 de diciembre
Fisio el lunes y el miércoles a las 10

Solo se repite lo que dices que se repite («todos los días», «los martes», «cada 15 días»), y sin final salvo que digas hasta cuándo («hasta el 15 de diciembre», «hasta diciembre», «durante 2 meses»).
También entiendo #proyecto, @etiqueta y p1–p4 (prioridad). Varias líneas en un mismo mensaje son varias tareas.

/hoy · lo de hoy y lo vencido
/manana · lo de mañana
/semana · los próximos 7 días
/bandeja · tareas sin proyecto
/hecha dentista · marcarla como hecha
/posponer dentista el lunes · cambiarle la fecha
/borrar dentista · quitarla de la agenda (también vale «borra la cita del dentista»)
/saltar gimnasio · saltarte la próxima vez de una tarea que se repite
/ver dentista · ver la tarea
Las tareas se nombran con alguna de sus palabras («dentista», «reunión con Marta del lunes») o con su número (T-12).

Sin comandos también entiendo:
«ya he ido al dentista» · la marco como hecha
«pasa el dentista al jueves», «cambia el gimnasio a las 8» · la cambio, después de preguntarte
«hoy no hay gimnasio» · me salto esa vez
«ponle prioridad 1 al informe», «marca el informe como urgente»
«añade a la compra: leche, pan» · a la lista (si no existe, la creo)
/nota texto · apuntarlo en la nota de hoy
/buscar texto · buscar en tareas y notas
/probar texto · ver qué entiendo, sin apuntar nada
/proyectos · los nombres para usar con #"""

COMANDOS = [
    ("hoy", "Lo de hoy y lo vencido"), ("manana", "Lo de mañana"), ("semana", "Los próximos 7 días"),
    ("bandeja", "Tareas sin proyecto"), ("hecha", "Marcar como hecha: /hecha dentista"),
    ("posponer", "Cambiar la fecha: /posponer dentista el lunes"), ("borrar", "Quitar de la agenda: /borrar dentista"),
    ("saltar", "Saltar la próxima vez de una tarea que se repite"), ("ver", "Ver una tarea: /ver dentista"),
    ("nota", "Apuntar en la nota de hoy"), ("buscar", "Buscar en tareas y notas"),
    ("probar", "Ver qué entiendo, sin apuntar nada"), ("proyectos", "Proyectos para usar con #"),
    ("ayuda", "Cómo escribir las tareas"),
]


class Textos:
    def _nombres(self) -> dict[str, str]:
        return {p.slug: p.nombre for p in self.fichas.proyectos.listar()}

    def _meta(self, t: Tarea, ahora: dt.datetime, con_fecha: bool = True) -> str:
        bits = []
        if t.fecha and con_fecha:
            bits.append(vistas.cuando(t, ahora))
        elif t.hora:
            bits.append(t.hora + (f"–{_fin(t)}" if t.duracion else ""))
        if t.proyecto:
            bits.append(self._nombres().get(t.proyecto, t.proyecto))
        if t.prioridad in ("p1", "p2", "p3"):
            bits.append(t.prioridad)
        if t.repetir:
            bits.append(f"↻ {t.repetir}" + (f" hasta el {fechas.corta(fechas.desde_iso(t.hasta))}" if t.hasta else ", sin fecha de fin"))
        if t.estado not in ("pendiente", "hecha"):
            estado = ETIQUETAS_ESTADO.get(t.estado, t.estado)
            bits.append(f"{estado} a {t.esperando_a}" if t.esperando_a else estado)
        bits += [f"@{e}" for e in t.etiquetas]
        return " · ".join(bits)

    def _lista(self, chat: str, titulo: str, tareas: list[Tarea], ahora: dt.datetime, por_dia: bool = False) -> None:
        if not tareas:
            self._decir(chat, f"{titulo}: nada pendiente.")
            return
        lineas = [f"{titulo} · {len(tareas)}"]
        dia_actual = None
        for t in tareas[:MAX_LISTA]:
            if por_dia and t.fecha != dia_actual:
                dia_actual = t.fecha
                dia = fechas.desde_iso(t.fecha)
                lineas += ["", f"{fechas.DIAS[dia.weekday()].capitalize()} {dia.day}"]
            meta = self._meta(t, ahora, con_fecha=not por_dia)
            lineas.append(f"· {t.titulo}\n   {t.id}" + (f" · {meta}" if meta else ""))
        if len(tareas) > MAX_LISTA:
            lineas.append(f"… y {len(tareas) - MAX_LISTA} más")
        botones = [[{"text": f"✓ {t.titulo[:30]}", "callback_data": f"hecha:{t.id}"}] for t in tareas[:MAX_BOTONES]]
        self._decir(chat, "\n".join(lineas), botones)

    def _ficha(self, t: Tarea, ahora: dt.datetime) -> str:
        lineas = [f"{t.id} · {t.titulo}", self._meta(t, ahora) or "Sin fecha",
                  f"Estado: {ETIQUETAS_ESTADO.get(t.estado, t.estado)}"]
        if t.subtareas:
            lineas += ["", f"Subtareas {sum(s.hecha for s in t.subtareas)}/{len(t.subtareas)}"]
            lineas += [f"{'☑' if s.hecha else '☐'} {s.texto}" for s in t.subtareas[:15]]
        return "\n".join(lineas)

    def _buscar(self, consulta: str) -> str:
        if not consulta:
            return "Dime qué busco: /buscar texto"
        resultados = enlaces.Indice(self.fichas, self.notas).buscar(consulta[:120])
        if not resultados:
            return f"Nada con «{consulta}»."
        tipos = {"tarea": "Tarea", "nota": "Nota", "proyecto": "Proyecto", "etiqueta": "Etiqueta"}
        lineas = [f"Resultados de «{consulta}»:"]
        for r in resultados[:10]:
            ref = f" {r['ref']}" if r["tipo"] == "tarea" else ""
            lineas.append(f"· {tipos.get(r['tipo'], r['tipo'])}{ref}: {r['titulo']}")
        return "\n".join(lineas)

    def _probar(self, texto: str) -> str:
        if not texto:
            return "Escribe la tarea detrás: /probar Llamar a Ana mañana a las 10"
        r = quickadd.parsear(texto[:500])
        lineas = [f"Título: {r.titulo or '(vacío)'}"]
        for clave, valor in (("Fecha", r.fecha), ("Hora", r.hora), ("Duración", f"{r.duracion} min" if r.duracion else None),
                             ("Repetir", r.repetir and (r.repetir + (f" hasta el {r.hasta}" if r.hasta else ", sin fecha de fin"))),
                             ("Otras fechas", ", ".join(r.otras_fechas) if r.otras_fechas else None),
                             ("Proyecto", r.proyecto), ("Prioridad", r.prioridad),
                             ("Etiquetas", ", ".join(r.etiquetas) if r.etiquetas else None)):
            if valor:
                lineas.append(f"{clave}: {valor}")
        lineas += [f"Ojo: {a}" for a in r.avisos]
        lineas.append("(No he apuntado nada)")
        return "\n".join(lineas)

    def _proyectos(self) -> str:
        proyectos = self.fichas.proyectos.listar()
        if not proyectos:
            return "Aún no hay proyectos. Créalos en el panel."
        lineas = []
        for ambito, nombre in (("laboral", "Laboral"), ("personal", "Personal")):
            # A name with spaces is written by its slug (#mi-proyecto): # takes one word.
            de_ambito = [p.slug if " " in p.nombre else p.nombre for p in proyectos if p.ambito == ambito]
            if de_ambito:
                lineas.append(f"{nombre}: " + ", ".join(f"#{n}" for n in de_ambito))
        return "\n".join(lineas)

    def _opciones(self, tareas: list[Tarea], datos, fin: list[list[dict]], marca: str = "") -> list[list[dict]]:
        """A button per task; `datos` is a format string («hecha:{}») or a function of the task."""
        ahora = fechas.ahora()
        filas = []
        for t in tareas[:MAX_BOTONES]:
            cuando = vistas.cuando(t, ahora)
            filas.append([{"text": f"{marca}{t.titulo[:32]}" + (f" · {cuando}" if cuando else ""), "callback_data": datos.format(t.id) if isinstance(datos, str) else datos(t)}])
        return filas + fin


def _fin(t: Tarea) -> str:
    inicio = dt.datetime.combine(fechas.desde_iso(t.fecha), dt.time.fromisoformat(t.hora))
    return (inicio + dt.timedelta(minutes=int(t.duracion))).strftime("%H:%M")

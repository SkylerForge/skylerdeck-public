import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from agenda import bot_servicio, telegram
from agenda.bot import Bot
from agenda.notas import Notas
from tests.test_fichas import Base

YO, OTRO = "42", "666"


class TelegramBot(Base):
    def setUp(self):
        super().setUp()
        self.llamadas = []
        self.f.proyectos.crear("Casa", "personal")
        self.bot = Bot(self.f, [YO], lambda metodo, datos: self.llamadas.append((metodo, datos)) or {},
                       "https://agenda.example.ts.net:8443")

    def escribir(self, texto, chat=YO):
        return self.bot.atender({"update_id": 1, "message": {"chat": {"id": int(chat), "type": "private"}, "text": texto}})

    def respuesta(self):
        metodo, datos = self.llamadas[-1]
        self.assertEqual(metodo, "sendMessage")
        return datos

    def test_plain_text_becomes_a_task(self):
        self.escribir("Comprar bombillas mañana a las 18 #Casa p2 @recados")
        t = self.f.obtener("T-001")
        self.assertEqual((t.titulo, t.fecha, t.hora, t.proyecto, t.prioridad, t.etiquetas),
                         ("Comprar bombillas", "2026-10-27", "18:00", "casa", "p2", ["recados"]))
        self.assertIn("Telegram: Creada desde Telegram", t.cuerpo)
        r = self.respuesta()
        self.assertTrue(r["text"].startswith("Apuntada: Comprar bombillas\nMañana, 18:00 · Casa · p2"))
        botones = r["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([b.get("callback_data") for b in botones], ["hecha:T-001", "manana:T-001", None])
        self.assertEqual(botones[2]["url"], "https://agenda.example.ts.net:8443/#/t/T-001")

    def test_several_lines_and_errors(self):
        self.escribir("- Llamar a Ana el jueves\n\n• Regar las plantas cada 3 días\nAlgo #NoExiste")
        self.assertEqual([t.titulo for t in self.f.listar()], ["Llamar a Ana", "Regar las plantas"])
        textos = [d["text"] for m, d in self.llamadas if m == "sendMessage"]
        self.assertEqual([t.split("\n")[0] for t in textos], ["Apuntada: Llamar a Ana", "Apuntada: Regar las plantas", "No he podido apuntar:"])
        self.assertIn("No existe el proyecto «NoExiste»", textos[-1])

    def test_other_chats_are_ignored_silently(self):
        self.assertIsNone(self.escribir("Borrar todo", chat=OTRO))
        self.assertEqual((self.f.listar(), self.llamadas), ([], []))
        cq = {"id": "1", "data": "hecha:T-001", "message": {"chat": {"id": int(OTRO)}, "message_id": 5}}
        self.assertIsNone(self.bot.atender({"update_id": 2, "callback_query": cq}))

    def test_lists(self):
        self.f.crear({"titulo": "Vieja", "fecha": "2026-10-20"})
        self.f.crear({"titulo": "Reunión", "fecha": "2026-10-26", "hora": "10:30", "duracion": "60"})
        self.f.crear({"titulo": "Dentista", "fecha": "2026-10-27", "hora": "09:00"})
        self.f.crear({"titulo": "Sin fecha"})
        self.escribir("/hoy")
        r = self.respuesta()
        self.assertIn("Hoy · 2", r["text"])
        self.assertIn("Vencida el 20/10", r["text"])
        self.assertEqual(len(r["reply_markup"]["inline_keyboard"]), 2)
        self.escribir("/mañana@AgendaBot")
        self.assertIn("· Dentista\n   T-003 · Mañana, 09:00", self.respuesta()["text"])
        self.escribir("/semana")
        self.assertIn("Martes 27", self.respuesta()["text"])
        self.escribir("/bandeja")
        self.assertIn("Sin fecha", self.respuesta()["text"])

    def test_done_postpone_and_buttons(self):
        self.f.crear({"titulo": "Informe", "fecha": "2026-10-26"})
        self.f.crear({"titulo": "Pastilla", "fecha": "2026-10-26", "repetir": "cada día"})
        self.escribir("/hecha T-1 2")
        texto = self.respuesta()["text"]
        self.assertIn("Hecha: Informe", texto)
        self.assertIn("Hecha: Pastilla. Vuelve mañana", texto)
        self.assertEqual(self.f.obtener("T-001").estado, "hecha")
        self.escribir("/posponer T-2 el lunes a las 9")
        self.assertEqual((self.f.obtener("T-002").fecha, self.f.obtener("T-002").hora), ("2026-11-02", "09:00"))
        self.escribir("/posponer T-2 cuando pueda")
        self.assertIn("No entiendo la nueva fecha", self.respuesta()["text"])

        teclado = [[{"text": "✓ Hecha", "callback_data": "hecha:T-002"}, {"text": "Abrir", "url": "https://x"}]]
        cq = {"id": "9", "data": "hecha:T-002", "message": {"chat": {"id": int(YO)}, "message_id": 7,
                                                             "reply_markup": {"inline_keyboard": teclado}}}
        self.bot.atender({"update_id": 3, "callback_query": cq})
        (m1, d1), (m2, d2) = self.llamadas[-2:]
        self.assertEqual((m1, m2), ("answerCallbackQuery", "editMessageReplyMarkup"))
        self.assertIn("Vuelve", d1["text"])
        self.assertEqual(d2["reply_markup"]["inline_keyboard"], [[{"text": "Abrir", "url": "https://x"}]])

    def test_daily_note_search_and_preview(self):
        self.escribir("/nota Idea para el viernes @casa")
        self.escribir("/nota Otra más")
        self.assertEqual(Notas(self.datos).obtener("2026-10-26").cuerpo.strip(), "Idea para el viernes @casa\n\nOtra más")
        self.escribir("/buscar idea")
        self.assertIn("Nota: ", self.respuesta()["text"])
        self.escribir("/probar Llamar a Ana mañana a las 10 p1")
        texto = self.respuesta()["text"]
        self.assertIn("Fecha: 2026-10-27\nHora: 10:00", texto)
        self.assertEqual(self.f.listar(), [])
        self.escribir("/proyectos")
        self.assertEqual(self.respuesta()["text"], "Personal: #Casa")
        self.escribir("/borrartodo")
        self.assertIn("No conozco /borrartodo", self.respuesta()["text"])

    def test_natural_language_and_morning_fix(self):
        self.escribir("Recuérdame que tengo cita con el dentista el martes a las cinco y media")
        t = self.f.obtener("T-001")
        self.assertEqual((t.titulo, t.fecha, t.hora), ("Cita con el dentista", "2026-10-27", "17:30"))
        r = self.respuesta()
        self.assertIn("Ojo: «a las cinco y media» lo entiendo como 17:30", r["text"])
        teclado = r["reply_markup"]["inline_keyboard"]
        self.assertEqual(teclado[-1], [{"text": "Era por la mañana", "callback_data": "am:T-001"}])
        cq = {"id": "1", "data": "am:T-001", "message": {"chat": {"id": int(YO)}, "message_id": 4, "reply_markup": {"inline_keyboard": teclado}}}
        self.bot.atender({"update_id": 5, "callback_query": cq})
        self.assertEqual(self.f.obtener("T-001").hora, "05:30")
        (_, aviso), (_, editado) = self.llamadas[-2:]
        self.assertEqual(aviso["text"], "Cambiada a las 05:30: Cita con el dentista")
        self.assertEqual(editado["reply_markup"]["inline_keyboard"], teclado[:-1])  # Hecha and Mañana stay
        self.escribir("Reunión con Marta mañana a las 10")
        self.assertNotIn("Era por la mañana", str(self.respuesta()))

    def pulsar(self, datos, teclado=None):
        cq = {"id": "c", "data": datos, "message": {"chat": {"id": int(YO)}, "message_id": 9,
                                                   "reply_markup": {"inline_keyboard": teclado or []}}}
        self.bot.atender({"update_id": 7, "callback_query": cq})

    def test_take_off_by_words_with_undo(self):
        self.f.crear({"titulo": "Dentista", "fecha": "2026-10-27", "hora": "17:30"})
        self.f.crear({"titulo": "Reunión con Marta", "fecha": "2026-11-02", "hora": "10:00", "estado": "en-curso"})
        self.escribir("Borra la cita del dentista")
        r = self.respuesta()
        self.assertTrue(r["text"].startswith("¿Quito de la agenda «Dentista»?"))
        botones = r["reply_markup"]["inline_keyboard"]
        self.assertEqual(botones[0][0]["callback_data"], "borrar:T-001")
        self.assertEqual(botones[1][0]["text"], "No: apúntalo como tarea nueva")
        self.assertEqual(self.f.obtener("T-001").estado, "pendiente")  # nothing happens before the answer
        self.pulsar("borrar:T-001", botones)
        self.assertEqual(self.f.obtener("T-001").estado, "soltada")
        metodo, datos = self.llamadas[-1]
        self.assertEqual((metodo, datos["text"]), ("editMessageText", "Quitada de la agenda: Dentista"))
        self.assertEqual(datos["reply_markup"]["inline_keyboard"], [[{"text": "↩ Deshacer", "callback_data": "recuperar:T-001:pendiente"}]])
        self.pulsar("recuperar:T-001:pendiente")
        self.assertEqual(self.f.obtener("T-001").estado, "pendiente")
        self.escribir("/borrar marta lunes")
        self.assertIn("«Reunión con Marta»", self.respuesta()["text"])
        self.pulsar("borrar:T-002")
        self.assertEqual(self.llamadas[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "recuperar:T-002:en-curso")
        self.escribir("/borrar T-1")
        self.assertEqual((self.f.obtener("T-001").estado, self.respuesta()["text"]), ("soltada", "Quitada de la agenda: Dentista"))

    def test_take_off_asks_which_and_can_be_a_new_task(self):
        self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "hora": "19:00"})
        self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-28", "hora": "19:00"})
        self.escribir("Cancela el gimnasio")
        r = self.respuesta()
        self.assertEqual(r["text"], "¿Cuál quito de la agenda?")
        botones = r["reply_markup"]["inline_keyboard"]
        self.assertEqual([f[0]["callback_data"] for f in botones[:2]], ["quitar:T-001", "quitar:T-002"])
        self.assertEqual(botones[0][0]["text"], "🗑 Gimnasio · Hoy, 19:00")
        self.escribir("cancela el gimnasio del miércoles")
        self.assertTrue(self.respuesta()["text"].startswith("¿Quito de la agenda «Gimnasio»?\nMié 28/10, 19:00"))
        # Nothing with those words, said as a to-do (infinitive): it was a new task all along.
        self.escribir("Cancelar el seguro del coche el viernes")
        self.assertEqual(self.f.obtener("T-003").titulo, "Cancelar el seguro del coche")
        # Said as an order, it never adds a task by itself: it says so and offers to.
        self.escribir("Quita las ruedas de invierno al gimnasio")  # «gimnasio» alone would not do: «ruedas» does not match
        r = self.respuesta()
        self.assertTrue(r["text"].startswith("No encuentro nada pendiente con «las ruedas de invierno al gimnasio»"))
        self.assertEqual(len(self.f.listar()), 3)
        self.pulsar(r["reply_markup"]["inline_keyboard"][0][0]["callback_data"])
        self.assertEqual(self.f.obtener("T-004").titulo, "Quita las ruedas de invierno al gimnasio")
        self.escribir("Elimina gimnasio")
        token = self.respuesta()["reply_markup"]["inline_keyboard"][-1][0]["callback_data"]
        self.assertTrue(token.startswith("nueva:"))
        self.pulsar(token)
        self.assertEqual(self.f.obtener("T-005").titulo, "Elimina gimnasio")
        self.pulsar(token)
        self.assertEqual(self.llamadas[-1][1]["text"], "Este botón ya no sirve: escríbemelo otra vez")
        self.escribir("/borrar pádel")
        self.assertIn("No encuentro nada pendiente con «pádel»", self.respuesta()["text"])

    def test_several_new_tasks_keep_their_buttons(self):
        self.escribir("añademe la clase de Crossfit a las 21:00 mañana y hoy")
        enviados = [d for m, d in self.llamadas if m == "sendMessage"]
        self.assertEqual([d["text"] for d in enviados], ["Apuntada: Clase de Crossfit\nHoy, 21:00", "Apuntada: Clase de Crossfit\nMañana, 21:00"])
        self.assertEqual([[b.get("callback_data") for b in d["reply_markup"]["inline_keyboard"][0]] for d in enviados],
                         [["hecha:T-001", "manana:T-001", None], ["hecha:T-002", "manana:T-002", None]])
        # More than a few: one list, a button per task and one to take them all off again.
        self.escribir("\n".join(f"Tarea {n}" for n in range(1, 6)))
        r = self.respuesta()
        self.assertTrue(r["text"].startswith("Apuntadas 5:"))
        botones = r["reply_markup"]["inline_keyboard"]
        self.assertEqual([f[0]["callback_data"] for f in botones[:5]], [f"ver:T-00{n}" for n in range(3, 8)])
        self.assertEqual(botones[5][0]["text"], "🗑 Quitar estas 5")
        self.pulsar(botones[5][0]["callback_data"])
        self.assertEqual({self.f.obtener(f"T-00{n}").estado for n in range(3, 8)}, {"soltada"})
        deshacer = self.llamadas[-1][1]["reply_markup"]["inline_keyboard"][0][0]
        self.assertTrue(self.llamadas[-1][1]["text"].startswith("Quitadas de la agenda 5:"))
        self.pulsar(deshacer["callback_data"])
        self.assertEqual({self.f.obtener(f"T-00{n}").estado for n in range(3, 8)}, {"pendiente"})

    def test_take_off_several_at_once(self):
        self.escribir("añademe la clase de Crossfit a las 21:00 mañana y hoy")
        # «las dos» is how many, not part of the title.
        self.escribir("elimina las dos clases de crossfit")
        botones = self.respuesta()["reply_markup"]["inline_keyboard"]
        self.assertEqual([f[0]["callback_data"] for f in botones[:2]], ["quitar:T-001", "quitar:T-002"])
        self.assertEqual(botones[2][0]["text"], "🗑 Todas (2)")
        self.pulsar(botones[2][0]["callback_data"])
        self.assertEqual([self.f.obtener(i).estado for i in ("T-001", "T-002")], ["soltada", "soltada"])
        self.pulsar(self.llamadas[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"])
        # Lines pasted from my own answer, under «elimina»: the numbers say which, nothing new is added.
        self.escribir("elimina\n· Clase de Crossfit  (T-001 · Hoy, 21:00)\n· Clase de Crossfit  (T-002 · Mañana, 21:00)")
        r = self.respuesta()
        self.assertTrue(r["text"].startswith("¿Quito de la agenda estas 2?\n· Clase de Crossfit (Hoy, 21:00)"))
        self.assertEqual(len(self.f.listar()), 2)
        self.pulsar(r["reply_markup"]["inline_keyboard"][0][0]["callback_data"])
        self.assertEqual([self.f.obtener(i).estado for i in ("T-001", "T-002")], ["soltada", "soltada"])
        # «borra» with a task per line.
        self.f.crear({"titulo": "Dentista", "fecha": "2026-10-28"})
        self.f.crear({"titulo": "Llamar a Ana"})
        self.escribir("borra:\ndentista\nllamar a ana")
        self.assertTrue(self.respuesta()["text"].startswith("¿Quito de la agenda estas 2?"))
        # An order that finds nothing adds nothing; several lines that start with a to-do are still tasks.
        self.escribir("elimina las clases de yoga")
        self.assertTrue(self.respuesta()["text"].startswith("No encuentro nada pendiente con «las clases de yoga»"))
        self.escribir("Cancelar el seguro\nComprar pan")
        self.assertEqual([t.titulo for t in self.f.listar()][-2:], ["Cancelar el seguro", "Comprar pan"])

    def test_done_postpone_and_view_by_words(self):
        self.f.crear({"titulo": "Dentista", "fecha": "2026-10-27", "hora": "17:30"})
        self.f.crear({"titulo": "Llamar a Ana", "fecha": "2026-10-26"})
        self.f.crear({"titulo": "Llamar al taller", "fecha": "2026-10-26"})
        self.escribir("/hecha dentista")
        self.assertEqual((self.f.obtener("T-001").estado, self.respuesta()["text"]), ("hecha", "Hecha: Dentista"))
        self.escribir("/posponer llamar a ana el jueves a las 10")
        t = self.f.obtener("T-002")
        self.assertEqual((t.fecha, t.hora), ("2026-10-29", "10:00"))
        self.escribir("/posponer llamar el viernes")
        r = self.respuesta()
        self.assertEqual(r["text"], "¿Cuál cambio de fecha?")
        datos = r["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertEqual(datos, "pos:T-003:20261030")
        self.pulsar(datos)
        self.assertEqual(self.f.obtener("T-003").fecha, "2026-10-30")
        self.escribir("/ver taller")
        self.assertTrue(self.respuesta()["text"].startswith("T-003 · Llamar al taller"))

    def test_recurring_and_one_off_dates(self):
        self.escribir("Apúntame todos los días a las 9 el gimnasio hasta el 15 de diciembre")
        t = self.f.obtener("T-001")
        self.assertEqual((t.titulo, t.fecha, t.hora, t.repetir, t.hasta), ("Gimnasio", "2026-10-27", "09:00", "cada día", "2026-12-15"))  # 9:00 today has come
        self.assertIn("↻ cada día hasta el 15/12", self.respuesta()["text"])
        self.escribir("Inglés los martes a las 7 de la tarde")
        self.assertIn("↻ cada martes, sin fecha de fin", self.respuesta()["text"])
        self.escribir("Fisio el lunes y el miércoles a las 10")
        nuevas = [self.f.obtener(i) for i in ("T-003", "T-004")]
        self.assertEqual([(t.titulo, t.fecha, t.hora, t.repetir) for t in nuevas],
                         [("Fisio", "2026-10-28", "10:00", ""), ("Fisio", "2026-11-02", "10:00", "")])
        dos = [d for m, d in self.llamadas[-2:]]
        self.assertEqual([d["text"].split("\n")[0] for d in dos], ["Apuntada: Fisio", "Apuntada: Fisio"])
        self.assertEqual([d["reply_markup"]["inline_keyboard"][0][0]["callback_data"] for d in dos], ["hecha:T-003", "hecha:T-004"])

    def boton(self, n=0, fila=0):
        return self.respuesta()["reply_markup"]["inline_keyboard"][fila][n]["callback_data"]

    def test_skip_a_repeat(self):
        gym = self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "hora": "19:00", "repetir": "cada lunes y jueves"})
        self.escribir("Hoy no hay gimnasio")
        r = self.respuesta()
        self.assertEqual(r["text"], "Saltada la del 26/10: Gimnasio. La siguiente, jue 29/10")
        self.assertEqual(self.f.obtener(gym.id).fecha, "2026-10-29")
        self.pulsar(self.boton())  # ↩ Deshacer
        self.assertEqual(self.f.obtener(gym.id).fecha, "2026-10-26")
        self.escribir("sáltate el gimnasio del lunes que viene")
        self.assertIn("solo puedo saltar la próxima", self.respuesta()["text"])
        self.escribir("No voy al gimnasio hoy")
        self.assertEqual(self.f.obtener(gym.id).fecha, "2026-10-29")
        self.escribir("/saltar gimnasio")
        self.assertEqual(self.f.obtener(gym.id).fecha, "2026-11-02")
        # A one-off task: «no hay» offers to take it off instead.
        self.f.crear({"titulo": "Reunión de equipo", "fecha": "2026-10-26", "hora": "10:30"})
        self.escribir("Hoy no hay reunión de equipo")
        self.assertTrue(self.respuesta()["text"].startswith("¿Quito de la agenda «Reunión de equipo»?"))
        # Nothing matches: it is a new task, as always.
        self.escribir("No hay leche")
        self.assertEqual(self.f.listar()[-1].titulo, "No hay leche")

    def test_take_off_a_repeat_asks_this_time_or_all(self):
        gym = self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "repetir": "cada lunes"})
        self.escribir("Borra el gimnasio")
        r = self.respuesta()
        self.assertEqual(r["text"], "«Gimnasio» se repite cada lunes. ¿Quito solo la del 26/10 o todas?")
        self.assertEqual([f[0]["callback_data"] for f in r["reply_markup"]["inline_keyboard"][:2]], [f"saltar:{gym.id}", f"borrar:{gym.id}"])
        self.pulsar(f"borrar:{gym.id}")
        self.assertEqual(self.f.obtener(gym.id).estado, "soltada")

    def test_done_by_saying_it(self):
        dentista = self.f.crear({"titulo": "Dentista", "fecha": "2026-10-26", "hora": "17:30"})
        pastilla = self.f.crear({"titulo": "Pastilla", "fecha": "2026-10-26", "repetir": "cada día"})
        self.escribir("Ya he ido al dentista")
        self.assertEqual((self.f.obtener(dentista.id).estado, self.respuesta()["text"]), ("hecha", "Hecha: Dentista"))
        self.pulsar(self.boton())  # ↩ Deshacer
        self.assertEqual(self.f.obtener(dentista.id).estado, "pendiente")
        self.escribir("hecho: pastilla")
        self.assertEqual(self.f.obtener(pastilla.id).fecha, "2026-10-27")
        self.pulsar(self.boton())
        self.assertEqual(self.f.obtener(pastilla.id).fecha, "2026-10-26")
        self.escribir("Ya he llamado a Ana")  # no such task: a new one
        self.assertEqual(self.f.listar()[-1].titulo, "Ya he llamado a Ana")

    def test_move_by_saying_it(self):
        t = self.f.crear({"titulo": "Dentista", "fecha": "2026-10-27", "hora": "17:30"})
        self.escribir("Pasa el dentista al jueves")
        r = self.respuesta()
        self.assertEqual(r["text"], "¿Cambio «Dentista» (Mañana, 17:30) a jue 29/10, 17:30?")
        self.assertEqual(self.f.obtener(t.id).fecha, "2026-10-27")  # asks first
        self.pulsar(self.boton())
        self.assertEqual((self.f.obtener(t.id).fecha, self.f.obtener(t.id).hora), ("2026-10-29", "17:30"))
        self.escribir("cambia el dentista a las 6 de la tarde")
        self.pulsar(self.boton())
        self.assertEqual((self.f.obtener(t.id).fecha, self.f.obtener(t.id).hora), ("2026-10-29", "18:00"))
        self.pulsar(self.llamadas[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"])  # ↩ Deshacer
        self.assertEqual(self.f.obtener(t.id).hora, "17:30")
        self.escribir("Pasa llamar a Ana al lunes")  # «a Ana» is part of the name, «al lunes» the date
        self.assertEqual(self.f.listar()[-1].titulo, "Pasa llamar a Ana")  # no task called that: new task
        self.escribir("Cambia el aceite del coche el sábado")
        self.assertEqual(self.f.listar()[-1].titulo, "Cambia el aceite del coche")

    def test_priority_and_lists(self):
        t = self.f.crear({"titulo": "Informe anual"})
        self.escribir("Ponle prioridad 1 al informe")
        self.assertEqual((self.f.obtener(t.id).prioridad, self.respuesta()["text"]), ("p1", "Prioridad p1: Informe anual"))
        self.escribir("marca el informe como urgente")
        self.assertEqual(self.f.obtener(t.id).prioridad, "p1")
        self.escribir("Añade a la compra: leche, pan y huevos")
        compra = self.f.listar()[-1]
        self.assertEqual((compra.titulo, [x.texto for x in compra.subtareas]), ("Compra", ["leche", "pan", "huevos"]))
        self.escribir("añade pilas a la compra")
        self.assertEqual([x.texto for x in self.f.obtener(compra.id).subtareas], ["leche", "pan", "huevos", "pilas"])
        self.assertIn("4 por hacer en la lista", self.respuesta()["text"])
        self.escribir("Añade sal a la receta")  # no list called that: a new task
        self.assertEqual(self.f.listar()[-1].titulo, "Añade sal a la receta")

    def test_snooze_button(self):
        t = self.f.crear({"titulo": "Reunión", "fecha": "2026-10-26", "hora": "10:30"})
        with mock.patch.dict("os.environ", {"AGENDA_CONFIG": tempfile.mkdtemp()}):
            self.pulsar(f"mas:{t.id}:10", [[{"text": "+10 min", "callback_data": f"mas:{t.id}:10"}]])
            self.assertEqual(self.llamadas[-1][1]["text"], "Te lo vuelvo a recordar a las 09:10: Reunión")
            from agenda import avisos
            self.assertEqual(avisos.leer_pospuestos(), {t.id: "2026-10-26 09:10"})


class OneOwner(unittest.TestCase):
    """The bot talks only to whoever linked it first; a second person cannot add themselves."""

    def setUp(self):
        self.config = Path(tempfile.mkdtemp())
        telegram.guardar(self.config, token="123456:" + "A" * 35)
        self.cola = []

    def falso(self, token, metodo, datos=None, timeout=20):
        if metodo == "getMe":
            return {"username": "MiAgendaBot", "first_name": "Agenda"}
        if metodo == "getUpdates":
            return [] if datos.get("timeout") == 0 else (self.cola.pop(0) if self.cola else [])
        return {}

    def vincular(self, chat, cambiar=False):
        self.cola.append([{"update_id": int(chat), "message": {"chat": {"id": int(chat), "type": "private"},
                                                             "from": {"first_name": "X"}, "text": "/start 123456"}}])
        with mock.patch.object(telegram, "llamar", self.falso), mock.patch.object(bot_servicio.secrets, "randbelow", return_value=123456), \
                mock.patch.object(bot_servicio, "VINCULAR_MIN", 0.001), redirect_stdout(io.StringIO()):
            return bot_servicio.vincular(self.config, cambiar=cambiar)

    def test_second_person_cannot_link(self):
        self.assertEqual(self.vincular("42"), 0)
        with self.assertRaises(SystemExit) as err:
            self.vincular("666")
        self.assertIn("ya tiene dueño", str(err.exception))
        self.assertEqual(telegram.credenciales(self.config).chats, ("42",))

    def test_change_replaces_the_owner(self):
        self.vincular("42")
        self.assertEqual(self.vincular("7", cambiar=True), 0)
        self.assertEqual(telegram.credenciales(self.config).chats, ("7",))

    def test_only_the_first_chat_counts_in_an_old_file(self):
        telegram.guardar(self.config, chats=["42", "666"])
        self.assertEqual(telegram.credenciales(self.config).chats, ("42",))

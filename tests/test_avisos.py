import datetime as dt
import os
import tempfile
from pathlib import Path
from unittest import mock

from agenda import avisos, fechas, telegram
from agenda.errores import AgendaError
from tests.test_fichas import Base


def a(hora: str) -> dt.datetime:
    h, m = map(int, hora.split(":"))
    return dt.datetime(2026, 10, 26, h, m, tzinfo=fechas.TZ)


class Reminders(Base):
    def setUp(self):
        super().setUp()
        self.config = Path(tempfile.mkdtemp())
        self.enviados = []
        self.f.proyectos.crear("Equipo", "laboral")
        self.reunion = self.f.crear({"titulo": "Reunión de equipo", "fecha": "2026-10-26", "hora": "10:30",
                                     "duracion": "60", "proyecto": "equipo"}).id
        self.f.crear({"titulo": "Pedir cita ITV", "fecha": "2026-10-26", "prioridad": "p1"})
        self.f.crear({"titulo": "Vieja", "fecha": "2026-10-20"})
        self.f.crear({"titulo": "Mañana", "fecha": "2026-10-27", "hora": "09:00"})

    def correr(self, hora):
        return avisos.ejecutar(self.f, a(hora), self.config, lambda texto, enlace, tarea: self.enviados.append((texto, enlace)),
                               base_url="https://agenda.example.ts.net:8443")

    def test_task_reminder_once_and_in_window(self):
        avisos.guardar_ajustes({"resumen": False}, self.config)
        self.assertEqual(self.correr("10:00"), [])  # too early (15 min by default)
        self.assertEqual(self.correr("10:15"), [f"tarea:{self.reunion}:2026-10-26:10:30"])
        texto, enlace = self.enviados[-1]
        self.assertEqual(texto, "En 15 min · 10:30 Reunión de equipo\nHasta las 11:30 · Equipo · Laboral")
        self.assertEqual(enlace, f"https://agenda.example.ts.net:8443/#/t/{self.reunion}")
        self.assertEqual(self.correr("10:16"), [])  # never twice

    def test_late_reminders_are_skipped(self):
        avisos.guardar_ajustes({"resumen": False}, self.config)
        self.assertEqual(self.correr("10:45"), [])  # 15 min after it started: too late to be useful

    def test_morning_summary(self):
        self.assertEqual(self.correr("07:59"), [])
        self.assertEqual(self.correr("08:00"), ["resumen:2026-10-26"])
        texto, enlace = self.enviados[-1]
        self.assertIn("Hoy es lunes, 26 de octubre", texto)
        self.assertIn("10:30  Reunión de equipo (hasta 11:30)", texto)
        self.assertIn("·  Pedir cita ITV  [p1]", texto)
        self.assertIn("Vencidas: 1", texto)
        self.assertNotIn("Mañana", texto)
        self.assertTrue(enlace.endswith("/#/inicio"))
        self.assertEqual(self.correr("08:01"), [])
        # Down all morning: no summary after noon.
        otro = Path(tempfile.mkdtemp())
        self.assertEqual(avisos.ejecutar(self.f, a("12:30"), otro, lambda *x: None, base_url=""), [])

    def test_settings(self):
        avisos.guardar_ajustes({"antelacion": 5, "resumen": False}, self.config)
        self.assertEqual(self.correr("08:30"), [])
        self.assertEqual(self.correr("10:20"), [])
        self.assertEqual(self.correr("10:25"), [f"tarea:{self.reunion}:2026-10-26:10:30"])
        for malo in ({"antelacion": 7}, {"hora_resumen": "8"}, {"otra": 1}):
            with self.assertRaises(AgendaError):
                avisos.guardar_ajustes(malo, self.config)

    def test_test_message_and_errors(self):
        avisos.guardar_ajustes({"resumen": False}, self.config)
        avisos.pedir_prueba(self.config)
        self.assertEqual(self.correr("09:00"), ["prueba"])
        self.assertFalse((self.config / "aviso-prueba").exists())

        def falla(texto, enlace, tarea):
            raise RuntimeError("caído")
        avisos.pedir_prueba(self.config)
        avisos.ejecutar(self.f, a("09:01"), self.config, falla, base_url="")
        estado = avisos.leer_estado(self.config)
        self.assertEqual(estado["ultimo_error"]["texto"], "caído")
        self.assertTrue((self.config / "aviso-prueba").exists())  # retried next minute

    def test_token_never_in_errors(self):
        self.assertEqual(telegram.sin_token("fallo en https://api.telegram.org/bot123:ABC/sendMessage", "123:ABC"),
                         "fallo en https://api.telegram.org/bot***/sendMessage")

    def test_credentials_need_token_and_chat(self):
        self.assertIsNone(telegram.credenciales(self.config))
        telegram.guardar(self.config, token="999:XYZ")
        self.assertIsNone(telegram.credenciales(self.config))  # not linked yet
        telegram.guardar(self.config, chats=["42", "42", "7"])
        cred = telegram.credenciales(self.config)
        self.assertEqual((cred.token, cred.chats, cred.chat), ("999:XYZ", ("42",), "42"))  # the owner only
        self.assertEqual((self.config / "telegram.env").stat().st_mode & 0o777, 0o600)

    def test_buttons(self):
        self.assertEqual(avisos.botones("https://x/#/t/T-001", "T-001"), [
            [{"text": "✓ Hecha", "callback_data": "hecha:T-001"}, {"text": "+10 min", "callback_data": "mas:T-001:10"},
             {"text": "+1 h", "callback_data": "mas:T-001:60"}],
            [{"text": "→ Mañana", "callback_data": "manana:T-001"}, {"text": "Abrir en la agenda", "url": "https://x/#/t/T-001"}]])
        self.assertEqual(avisos.botones("https://x/#/inicio", None), [[{"text": "Abrir en la agenda", "url": "https://x/#/inicio"}]])
        self.assertEqual(avisos.botones(None, None), [])

    def test_evening_summary_and_sunday_review(self):
        avisos.guardar_ajustes({"resumen": False, "tareas_hora": False, "noche": True, "hora_noche": "21:30"}, self.config)
        self.assertEqual(self.correr("21:00"), [])
        self.assertEqual(self.correr("21:30"), ["noche:2026-10-26"])
        texto = self.enviados[-1][0]
        self.assertTrue(texto.startswith("Mañana, martes, 27 de octubre, tienes 1 tarea."))
        self.assertIn("09:00  Mañana", texto)
        self.assertEqual(self.correr("22:00"), [])
        avisos.guardar_ajustes({"noche": False, "repaso": True}, self.config)
        domingo = dt.datetime(2026, 11, 1, 19, 0, tzinfo=fechas.TZ)
        self.assertEqual(avisos.ejecutar(self.f, domingo, self.config, lambda *x: self.enviados.append(x), base_url=""),
                         ["repaso:2026-11-01"])
        texto = self.enviados[-1][0]
        self.assertIn("Repaso de la semana que viene.", texto)
        self.assertIn("Vencidas: 4", texto)  # everything from 26-27 October
        self.assertEqual(self.correr("19:00"), [])  # Monday: no review
        with self.assertRaises(AgendaError):
            avisos.guardar_ajustes({"hora_noche": "21h"}, self.config)

    def test_snoozed_reminder(self):
        avisos.guardar_ajustes({"resumen": False}, self.config)
        self.assertEqual(self.correr("10:15"), [f"tarea:{self.reunion}:2026-10-26:10:30"])
        cuando = avisos.posponer(self.reunion, 10, self.config, a("10:16"))
        self.assertEqual(cuando.strftime("%H:%M"), "10:26")
        self.assertEqual(self.correr("10:20"), [])
        self.assertEqual(self.correr("10:26"), [f"pospuesto:{self.reunion}:2026-10-26 10:26"])
        texto, enlace = self.enviados[-1]
        self.assertTrue(texto.startswith("En 4 min · 10:30 Reunión de equipo"))
        self.assertEqual(avisos.leer_pospuestos(self.config), {})  # sent once
        self.assertEqual(self.correr("10:27"), [])
        avisos.posponer(self.reunion, 60, self.config, a("10:30"))
        self.f.completar(self.reunion)
        self.assertEqual(self.correr("11:30"), [])  # done meanwhile: nothing

    def test_greeting_uses_the_configured_name(self):
        avisos.guardar_ajustes({"tareas_hora": False}, self.config)
        with mock.patch.dict(os.environ, {"AGENDA_NOMBRE": "Lucía"}):
            self.correr("08:00")
        self.assertTrue(self.enviados[-1][0].startswith("Buenos días, Lucía. Hoy es lunes"))

    def test_failed_backup_is_reported_once(self):
        avisos.guardar_ajustes({"resumen": False, "tareas_hora": False}, self.config)
        self.assertIsNone(avisos.leer_copia(self.config))
        (self.config / "copia-estado.json").write_text('{"cuando": "2026-10-26 03:30", "ok": true, "texto": ""}')
        self.assertEqual(self.correr("09:00"), [])
        (self.config / "copia-estado.json").write_text('{"cuando": "2026-10-27 03:30", "ok": false, "texto": "Permission denied"}')
        self.assertEqual(self.correr("09:01"), ["copia:2026-10-27 03:30"])
        self.assertIn("La copia de seguridad no se ha podido subir", self.enviados[-1][0])
        self.assertEqual(self.correr("09:02"), [])

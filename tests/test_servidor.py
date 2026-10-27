import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agenda import __version__
from agenda.servidor import crear_app

CLAVE = "k" * 40
HOST = "100.64.0.1:4850"


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = crear_app(Path(self.tmp.name), clave=CLAVE)
        self.c = self.app.test_client()
        self.c.set_cookie("agenda_clave", CLAVE, domain="100.64.0.1")

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path, **kw):
        return self.c.get(path, headers={"Host": HOST, **kw.pop("headers", {})}, **kw)

    def write(self, method, path, body, headers=None):
        base = {"Host": HOST, "X-Agenda": "1", "Origin": f"http://{HOST}"}
        return self.c.open(path, method=method, json=body, headers={**base, **(headers or {})})

    def test_needs_device_key(self):
        anon = self.app.test_client()
        self.assertEqual(anon.get("/", headers={"Host": HOST}).status_code, 401)
        self.assertEqual(anon.get("/api/panel", headers={"Host": HOST}).status_code, 401)
        self.assertEqual(anon.get("/?clave=mala", headers={"Host": HOST}).status_code, 401)
        r = anon.get(f"/?clave={CLAVE}", headers={"Host": HOST})
        self.assertEqual((r.status_code, r.headers["Location"]), (303, "/"))
        self.assertIn("HttpOnly", r.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", r.headers["Set-Cookie"])
        ts = anon.get(f"/?clave={CLAVE}", headers={"Host": "srv.tail1234.ts.net:8443"})
        self.assertIn("Secure", ts.headers["Set-Cookie"])
        self.assertEqual(anon.get("/", headers={"Host": HOST}).status_code, 200)

    def test_rejects_foreign_hosts(self):
        for host in ("evil.example.com", "192.168.1.10:4850", "8.8.8.8"):
            self.assertEqual(self.get("/", headers={"Host": host}).status_code, 421, host)
        for host in ("agenda.tail1234.ts.net", "127.0.0.1:4850", "localhost:4850"):
            self.assertNotEqual(self.get("/", headers={"Host": host}).status_code, 421, host)

    def test_write_guards(self):
        self.assertEqual(self.write("POST", "/api/tareas", {"texto": "x"}, {"X-Agenda": ""}).status_code, 400)
        self.assertEqual(self.write("POST", "/api/tareas", {"texto": "x"}, {"Origin": "http://evil.example.com"}).status_code, 403)

    def test_csp(self):
        r = self.get("/")
        self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", r.headers["Content-Security-Policy"])

    def test_flow(self):
        self.assertEqual(self.write("POST", "/api/proyectos", {"nombre": "Clientes", "ambito": "laboral"}).status_code, 201)
        r = self.write("POST", "/api/tareas", {"texto": "Llamar al dentista hoy a las 23:59 #Clientes p1 @teléfono"})
        self.assertEqual(r.status_code, 201, r.json)
        t = r.json["tarea"]
        self.assertEqual((t["id"], t["proyecto_nombre"], t["prioridad"]), ("T-001", "Clientes", "p1"))
        panel = self.get("/api/panel?ambito=laboral").json
        self.assertEqual(panel["vistas"]["hoy"], ["T-001"])
        self.assertEqual(panel["siguiente"]["id"], "T-001")
        self.assertEqual(self.get("/api/panel?ambito=personal").json["tareas"], [])

        r = self.write("PATCH", "/api/tareas/T-001", {"cambios": {"titulo": "Llamar al dentista otra vez"}, "version": t["version"]})
        self.assertEqual(r.status_code, 200)
        stale = self.write("PATCH", "/api/tareas/T-001", {"cambios": {"titulo": "Pisado"}, "version": t["version"]})
        self.assertEqual(stale.status_code, 409)

        v = r.json["version"]
        r = self.write("POST", "/api/tareas/T-001/estado", {"estado": "esperando", "esperando_a": "Dentista", "version": v})
        self.assertEqual((r.json["estado"], r.json["esperando_a"]), ("esperando", "Dentista"))
        r = self.write("POST", "/api/tareas/T-001/contexto", {"texto": "### Datos\nTeléfono en la ficha", "version": r.json["version"]})
        self.assertEqual(r.json["contexto"], "### Datos\nTeléfono en la ficha")
        self.assertTrue(any("Edita el contexto" in line for line in r.json["bitacora"]))

    def test_one_task_per_date(self):
        r = self.write("POST", "/api/tareas", {"texto": "Fisio el lunes y el miércoles a las 10"})
        self.assertEqual((r.status_code, r.json["otras"], r.json["tarea"]["fecha"]), (201, 1, "2026-10-28"))
        self.assertEqual(self.get("/api/tareas/T-002").json["fecha"], "2026-11-02")

    def test_skip_a_repeat(self):
        r = self.write("POST", "/api/tareas", {"texto": "Gimnasio los lunes y jueves a las 19"})
        t = r.json["tarea"]
        r = self.write("POST", f"/api/tareas/{t['id']}/saltar", {"version": t["version"]})
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json["fecha"], t["fecha"])  # the next Monday or Thursday after the first one
        self.assertEqual(self.write("POST", f"/api/tareas/{t['id']}/saltar", {"version": t["version"]}).status_code, 409)

    def test_unknown_project_is_an_error(self):
        r = self.write("POST", "/api/tareas", {"texto": "Algo #NoExiste"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("No existe el proyecto", r.json["error"])

    def test_demo_mode_needs_no_key_but_keeps_guards(self):
        demo = crear_app(Path(self.tmp.name), demo=True).test_client()
        r = demo.get("/", headers={"Host": "localhost:4852"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("X-Frame-Options", r.headers)
        self.assertEqual(demo.get("/", headers={"Host": "evil.example.com"}).status_code, 421)
        self.assertEqual(demo.post("/api/tareas", json={"texto": "x"}, headers={"Host": "localhost:4852"}).status_code, 400)
        # The normal panel still refuses to be framed.
        self.assertEqual(self.get("/").headers["X-Frame-Options"], "DENY")

    def test_version_changes_with_data(self):
        before = self.get("/api/version").json["datos"]
        self.write("POST", "/api/tareas", {"texto": "Algo"})
        self.assertNotEqual(self.get("/api/version").json["datos"], before)

    def test_settings_show_the_version(self):
        with mock.patch.dict(os.environ, {"AGENDA_CONFIG": self.tmp.name}):
            self.assertEqual(self.get("/api/avisos").json["version"], __version__)


if __name__ == "__main__":
    unittest.main()

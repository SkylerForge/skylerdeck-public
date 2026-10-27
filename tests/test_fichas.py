import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agenda import fechas, frontmatter, vistas
from agenda.errores import AgendaError
from agenda.fichas import Fichas

try:
    import yaml
except ImportError:  # the check of valid YAML needs PyYAML (requirements-dev.txt)
    yaml = None

AHORA = dt.datetime(2026, 10, 26, 9, 0, tzinfo=fechas.TZ)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.datos = Path(self.tmp.name)
        self.f = Fichas(self.datos)
        for target, value in (("hoy", AHORA.date()), ("ahora", AHORA)):
            patcher = mock.patch.object(fechas, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()


class Cards(Base):
    def test_create_writes_readable_card(self):
        self.f.proyectos.crear("Clientes", "laboral")
        t = self.f.crear({"titulo": "Llamar al dentista", "proyecto": "clientes", "prioridad": "p1",
                          "etiquetas": ["teléfono"], "fecha": "2026-10-27", "hora": "10:00"})
        self.assertEqual(t.id, "T-001")
        self.assertEqual(t.ambito, "laboral")  # from the project
        text = (self.datos / "tareas" / "T-001.md").read_text()
        self.assertIn('titulo: "Llamar al dentista"', text)
        self.assertIn("proyecto: clientes", text)
        self.assertIn('etiquetas: ["teléfono"]', text)
        self.assertIn('hora: "10:00"', text)
        self.assertIn("## Bitácora", text)

    def test_ids_increase(self):
        ids = [self.f.crear({"titulo": f"Tarea {i}"}).id for i in range(3)]
        self.assertEqual(ids, ["T-001", "T-002", "T-003"])

    @unittest.skipIf(yaml is None, "PyYAML no está instalado")
    def test_header_is_valid_yaml(self):
        nasty = ['a: b', '#no es comentario', '- guion', 'yes', 'null', '10:00', '@arroba', 'comillas "dobles"',
                 "comilla 'simple'", "barra \\ invertida", "[corchetes]", "{llaves}", "tab\tdentro", "ñandú 🦤"]
        self.f.proyectos.crear("Casa", "personal")
        for title in nasty:
            t = self.f.crear({"titulo": title, "proyecto": "casa", "etiquetas": ["no", "on"], "fecha": "2026-10-30",
                              "hora": "08:05", "repetir": "cada lunes", "caso": "2026/123", "esperando_a": "Sí: el dentista"})
            text = (self.datos / "tareas" / f"{t.id}.md").read_text()
            header = yaml.safe_load(frontmatter.FRONT_RE.match(text).group(1))
            with self.subTest(title=title):
                self.assertEqual(header["titulo"], " ".join(title.split()))
                self.assertEqual(header["hora"], "08:05")
                self.assertEqual(header["etiquetas"], ["no", "on"])
                self.assertEqual(header["esperando_a"], "Sí: el dentista")
                self.assertEqual(str(header["fecha"]), "2026-10-30")
                self.assertEqual(header["id"], t.id)

    def test_validation(self):
        bad = [{"titulo": ""}, {"titulo": "x", "fecha": "30/10"}, {"titulo": "x", "fecha": "2026-02-30"},
               {"titulo": "x", "hora": "10:00"}, {"titulo": "x", "prioridad": "p5"}, {"titulo": "x", "ambito": "otro"},
               {"titulo": "x", "caso": "Juan Pérez, víctima"}, {"titulo": "x", "proyecto": "inexistente"},
               {"titulo": "x", "repetir": "a veces"}, {"titulo": "x", "etiquetas": ["con espacio!"]}]
        for datos in bad:
            with self.subTest(datos=datos), self.assertRaises(AgendaError):
                self.f.crear(datos)

    def test_edit_and_conflict(self):
        t = self.f.crear({"titulo": "Original"})
        t2 = self.f.editar(t.id, {"titulo": "Nuevo", "prioridad": "p2"}, quien="claude", version=t.version)
        self.assertEqual((t2.titulo, t2.prioridad), ("Nuevo", "p2"))
        self.assertIn("Claude: Edita titulo, prioridad", t2.cuerpo)
        with self.assertRaises(AgendaError) as ctx:
            self.f.editar(t.id, {"titulo": "Otra vez"}, version=t.version)
        self.assertEqual(ctx.exception.status, 409)

    def test_hand_edited_card_survives(self):
        (self.datos / "tareas").mkdir()
        (self.datos / "tareas" / "T-007.md").write_text(
            "---\nid: T-007\ntitulo: 'A mano'\nestado: esperando\netiquetas: [casa, 'luz']\nextra: se conserva\n---\n\nTexto libre.\n")
        t = self.f.obtener("7")
        self.assertEqual((t.titulo, t.etiquetas, t.prioridad), ("A mano", ["casa", "luz"], "p4"))
        self.f.anotar("T-007", "Una nota")
        text = (self.datos / "tareas" / "T-007.md").read_text()
        self.assertIn("extra: \"se conserva\"", text)
        self.assertIn("Texto libre.", text)
        self.assertIn("Yo: Una nota", text)

    def test_states(self):
        t = self.f.crear({"titulo": "Esperar"})
        t = self.f.mover(t.id, "esperando", esperando_a="Despacho del gestor", revisar="2026-10-28")
        self.assertEqual((t.estado, t.esperando_a, t.revisar), ("esperando", "Despacho del gestor", "2026-10-28"))
        self.assertIn("Pendiente → Esperando (a Despacho del gestor)", t.cuerpo)
        t = self.f.mover(t.id, "en-curso")
        self.assertEqual((t.esperando_a, t.revisar), ("", ""))
        t = self.f.mover(t.id, "soltada")
        self.assertEqual((t.estado, t.cerrada), ("soltada", "2026-10-26"))

    def test_complete_plain_task(self):
        t = self.f.completar(self.f.crear({"titulo": "Una vez"}).id)
        self.assertEqual((t.estado, t.cerrada), ("hecha", "2026-10-26"))

    def test_complete_recurring_moves_to_next_date(self):
        t = self.f.crear({"titulo": "Regar", "fecha": "2026-10-20", "repetir": "cada 3 días", "subtareas": ["Salón", "Terraza"]})
        self.f.subtarea(t.id, "marcar", "1")
        t = self.f.completar(t.id)
        self.assertEqual((t.estado, t.fecha), ("pendiente", "2026-10-29"))
        self.assertEqual([s.hecha for s in t.subtareas], [False, False])
        self.assertIn("la siguiente, jue 29/10", t.cuerpo)

    def test_subtasks(self):
        t = self.f.crear({"titulo": "Informe", "subtareas": ["Hashes", "Capturas"]})
        t = self.f.subtarea(t.id, "anadir", "Firmar")
        t = self.f.subtarea(t.id, "marcar", "2")
        self.assertEqual([(s.texto, s.hecha) for s in t.subtareas], [("Hashes", False), ("Capturas", True), ("Firmar", False)])
        self.assertLess(t.cuerpo.index("## Subtareas"), t.cuerpo.index("## Bitácora"))
        with self.assertRaises(AgendaError):
            self.f.subtarea(t.id, "marcar", "9")

    def test_projects_rename_keeps_cards(self):
        self.f.proyectos.crear("Maker", "personal")
        t = self.f.crear({"titulo": "Batería", "proyecto": "Maker"})
        from agenda import enlaces
        from agenda.notas import Notas
        notas = Notas(self.datos)
        nota = notas.crear("Ideas", "Ver [[Maker]]", proyecto="maker")
        enlaces.renombrar_proyecto(self.f, notas, "maker", "Taller maker")
        self.assertEqual(self.f.proyectos.buscar("Taller maker").slug, "taller-maker")
        self.assertFalse((self.datos / "proyectos" / "maker.md").exists())
        self.assertEqual(self.f.obtener(t.id).proyecto, "taller-maker")
        self.assertEqual(notas.obtener(nota.slug).proyecto, "taller-maker")
        self.assertIn("[[Taller maker]]", notas.obtener(nota.slug).cuerpo)
        # The old name is free again.
        self.assertEqual(self.f.proyectos.crear("Maker", "personal").slug, "maker")
        with self.assertRaises(AgendaError):
            self.f.proyectos.crear("taller MAKER", "personal")


class RecurringUntil(Base):
    def test_the_last_one_closes_the_task(self):
        t = self.f.crear({"titulo": "Pastilla", "fecha": "2026-10-26", "repetir": "cada día", "hasta": "2026-10-27"})
        self.assertEqual(t.hasta, "2026-10-27")
        self.assertIn("hasta: 2026-10-27", (self.datos / "tareas" / "T-001.md").read_text())
        t = self.f.completar(t.id)
        self.assertEqual((t.estado, t.fecha), ("pendiente", "2026-10-27"))
        with mock.patch.object(fechas, "hoy", return_value=dt.date(2026, 10, 27)):
            t = self.f.completar(t.id)
        self.assertEqual(t.estado, "hecha")
        self.assertIn("era la última (cada día hasta el 27/10)", t.cuerpo)

    def test_until_needs_a_rule_and_comes_after_the_start(self):
        t = self.f.crear({"titulo": "Yoga", "fecha": "2026-10-27", "repetir": "cada martes", "hasta": "2026-12-15"})
        t = self.f.editar(t.id, {"repetir": ""})
        self.assertEqual((t.repetir, t.hasta), ("", ""))  # without a rule the end means nothing
        with self.assertRaises(AgendaError):
            self.f.crear({"titulo": "Yoga", "fecha": "2026-10-27", "repetir": "cada martes", "hasta": "2026-10-01"})
        with self.assertRaises(AgendaError):
            self.f.crear({"titulo": "Yoga", "fecha": "2026-10-27", "repetir": "cada martes", "hasta": "15/12"})


class Views(Base):
    def test_views(self):
        self.f.proyectos.crear("Clientes", "laboral")
        mk = lambda **kw: self.f.crear(kw).id
        vencida = mk(titulo="Vencida", fecha="2026-10-25", proyecto="clientes", prioridad="p1")
        hoy = mk(titulo="Hoy", fecha="2026-10-26", hora="13:00", prioridad="p3")
        futura = mk(titulo="Futura", fecha="2026-10-30")
        bandeja = mk(titulo="Sin nada")
        luego = mk(titulo="Luego", estado="mas-adelante", revisar="2026-11-20")
        todas = self.f.listar()
        ids = lambda vista, **kw: [t.id for t in vistas.filtrar(todas, vista, hoy=AHORA.date(), **kw)]
        self.assertEqual(ids("hoy"), [vencida, hoy])
        self.assertEqual(ids("hoy", ambito="personal"), [hoy])
        self.assertEqual(ids("proximo"), [hoy, futura])
        self.assertEqual(ids("bandeja"), [hoy, futura, bandeja])
        self.assertNotIn(luego, ids("hoy") + ids("bandeja"))
        t = self.f.obtener(vencida)
        self.assertEqual(vistas.cuando(t, AHORA), "Vencida ayer")
        self.assertEqual(vistas.cuando(self.f.obtener(hoy), AHORA), "Hoy, 13:00")


if __name__ == "__main__":
    unittest.main()


class Skip(Base):
    def test_skip_moves_on_without_doing_it(self):
        t = self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "repetir": "cada lunes y jueves", "hasta": "2026-11-02"})
        t = self.f.saltar(t.id)
        self.assertEqual((t.estado, t.fecha), ("pendiente", "2026-10-29"))
        self.assertIn("Saltada la del 26/10; la siguiente, jue 29/10", t.cuerpo)
        t = self.f.saltar(self.f.saltar(t.id).id)  # 29/10 → 2/11 → past the end
        self.assertEqual(t.estado, "soltada")
        with self.assertRaises(AgendaError):
            self.f.saltar(self.f.crear({"titulo": "Una vez", "fecha": "2026-10-27"}).id)

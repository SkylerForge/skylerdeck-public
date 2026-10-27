from agenda import enlaces, frontmatter
from agenda.errores import AgendaError
from agenda.notas import Notas
from tests.test_fichas import Base, yaml


class Notes(Base):
    def setUp(self):
        super().setUp()
        self.n = Notas(self.datos)

    def test_create_and_read(self):
        nota = self.n.crear("Reunión con el gestor", "Hablar de [[T-001]] @dentista @Dentista")
        self.assertEqual(nota.slug, "reunion-con-el-gestor")
        self.assertEqual(nota.etiquetas, ["dentista"])
        texto = (self.datos / "notas" / "reunion-con-el-gestor.md").read_text()
        self.assertIn('titulo: "Reunión con el gestor"', texto)
        if yaml:
            header = yaml.safe_load(frontmatter.FRONT_RE.match(texto).group(1))
            self.assertEqual(header["tipo"], "nota")
        with self.assertRaises(AgendaError):
            self.n.crear("reunión con el GESTOR")
        self.assertEqual(self.n.crear("Reunión: con el gestor").slug, "reunion-con-el-gestor-2")

    def test_daily_note_is_virtual_until_written(self):
        virtual = self.n.obtener("2026-10-26")
        self.assertEqual((virtual.existe, virtual.titulo), (False, "Lunes, 26 de octubre de 2026"))
        self.assertFalse((self.datos / "notas" / "2026-10-26.md").exists())
        nota, _ = self.n.guardar("2026-10-26", cuerpo="Primera línea")
        self.assertTrue(nota.existe)
        self.assertEqual(nota.tipo, "diario")
        with self.assertRaises(AgendaError) as ctx:
            self.n.obtener("no-existe")
        self.assertEqual(ctx.exception.status, 404)

    def test_conflict(self):
        nota = self.n.crear("Ideas")
        self.n.guardar(nota.slug, cuerpo="uno", version=nota.version)
        with self.assertRaises(AgendaError) as ctx:
            self.n.guardar(nota.slug, cuerpo="dos", version=nota.version)
        self.assertEqual(ctx.exception.status, 409)

    def test_delete_goes_to_bin_and_can_be_undone(self):
        nota = self.n.crear("Borrable", "texto")
        with self.assertRaises(AgendaError) as ctx:
            self.n.borrar(nota.slug, version="otra")
        self.assertEqual(ctx.exception.status, 409)
        nombre = self.n.borrar(nota.slug, version=nota.version)
        self.assertFalse((self.datos / "notas" / "borrable.md").exists())
        self.assertTrue((self.datos / "papelera" / "notas" / nombre).exists())
        with self.assertRaises(AgendaError):
            self.n.obtener("borrable")
        self.assertEqual(self.n.restaurar(nombre).cuerpo, "texto")
        for malo in ("../tareas/T-001.md", "borrable.md", nombre):
            with self.assertRaises(AgendaError):
                self.n.restaurar(malo)

    def test_bad_slugs(self):
        for slug in ("../tareas/T-001", "Mayúsculas", ""):
            with self.assertRaises(AgendaError):
                self.n.obtener(slug)


class Links(Base):
    def setUp(self):
        super().setUp()
        self.n = Notas(self.datos)
        self.f.proyectos.crear("Clientes", "laboral")
        self.t = self.f.crear({"titulo": "Entregar informe", "proyecto": "clientes"})
        self.nota = self.n.crear("Plantilla de informe", f"Usar en [[{self.t.id}]] y en [[clientes|el proyecto]]\n\nOtra línea")
        self.f.contexto(self.t.id, "Ver [[Plantilla de informe]] antes de empezar")

    def idx(self):
        return enlaces.Indice(self.f, self.n)

    def test_resolve(self):
        idx = self.idx()
        self.assertEqual(idx.resolver("t-1").ref, self.t.id)
        self.assertEqual(idx.resolver("plantilla DE informe").ref, self.nota.slug)
        self.assertEqual(idx.resolver("Clientes").tipo, "proyecto")
        self.assertEqual(idx.resolver("2026-10-26").tipo, "nota")
        self.assertIsNone(idx.resolver("Nada de esto"))

    def test_backlinks(self):
        idx = self.idx()
        a_tarea = idx.menciones("tarea", self.t.id)
        self.assertEqual([(m["tipo"], m["ref"]) for m in a_tarea], [("nota", self.nota.slug)])
        self.assertEqual(a_tarea[0]["fragmento"], "Usar en T-001 y en el proyecto")
        self.assertEqual([m["ref"] for m in idx.menciones("nota", self.nota.slug)], [self.t.id])
        self.assertEqual([m["ref"] for m in idx.menciones("proyecto", "clientes")], [self.nota.slug])

    def test_rename_rewrites_links(self):
        enlaces.guardar_nota(self.f, self.n, self.nota.slug, titulo="Plantilla de informe anual")
        self.assertIn("[[Plantilla de informe anual]]", self.f.obtener(self.t.id).cuerpo)
        self.assertIn("Enlaces a «Plantilla de informe anual» actualizados", self.f.obtener(self.t.id).cuerpo)
        enlaces.renombrar_proyecto(self.f, self.n, "clientes", "Clientes nuevos")
        self.assertIn("[[Clientes nuevos|el proyecto]]", self.n.obtener(self.nota.slug).cuerpo)
        self.assertEqual(self.n.obtener(self.nota.slug).slug, "plantilla-de-informe")  # the slug stays

    def test_suggest_search_tags(self):
        self.f.crear({"titulo": "Llamar al perito", "etiquetas": ["teléfono"]})
        self.n.crear("Lista de llamadas", "@teléfono pendientes")
        idx = self.idx()
        sugerencias = idx.sugerir("pla")
        self.assertEqual(sugerencias[0]["enlace"], "Plantilla de informe")
        self.assertEqual(idx.sugerir("T-00")[0]["tipo"], "tarea")
        tipos = {r["tipo"] for r in idx.buscar("llam")}
        self.assertEqual(tipos, {"tarea", "nota"})
        self.assertTrue(any(r["tipo"] == "nota" for r in idx.buscar("otra línea")))
        self.assertEqual(idx.etiquetas()[0], {"etiqueta": "teléfono", "tareas": 1, "notas": 1})

    def test_create_from_dangling_link(self):
        d = enlaces.crear_desde_enlace(self.f, self.n, "Idea nueva", proyecto="clientes")
        self.assertEqual((d.tipo, d.titulo), ("nota", "Idea nueva"))
        self.assertEqual(self.n.obtener(d.ref).proyecto, "clientes")
        self.assertEqual(enlaces.crear_desde_enlace(self.f, self.n, "Idea nueva").ref, d.ref)

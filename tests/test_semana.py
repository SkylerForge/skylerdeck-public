import datetime as dt

from agenda import semana
from tests.test_fichas import AHORA, Base


class Week(Base):
    def items(self, data, dia):
        return [(i["id"], i["tipo"]) for d in data["dias"] if d["fecha"] == dia for i in d["items"]]

    def test_week_sheet(self):
        f = self.f
        f.proyectos.crear("Clientes", "laboral")
        tarde = f.crear({"titulo": "Tarde", "fecha": "2026-10-27", "hora": "17:00"}).id
        sin_hora = f.crear({"titulo": "Sin hora p1", "fecha": "2026-10-27", "prioridad": "p1"}).id
        manana = f.crear({"titulo": "Mañana", "fecha": "2026-10-27", "hora": "09:00", "proyecto": "clientes"}).id
        gym = f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "repetir": "cada lunes y jueves"}).id
        hecha = f.completar(f.crear({"titulo": "Hecha", "fecha": "2026-10-28"}).id).id
        f.mover(f.crear({"titulo": "Soltada", "fecha": "2026-10-28"}).id, "soltada")
        espera = f.mover(f.crear({"titulo": "Espera"}).id, "esperando", esperando_a="Dentista", revisar="2026-10-30").id
        vieja = f.crear({"titulo": "Vieja", "fecha": "2026-10-20"}).id
        otra_semana = f.crear({"titulo": "Lejos", "fecha": "2026-11-10"}).id

        data = semana.construir(f, None, AHORA)
        self.assertEqual(data["lunes"], "2026-10-26")
        self.assertEqual([d["fecha"] for d in data["dias"]][-1], "2026-11-01")
        self.assertEqual(self.items(data, "2026-10-26"), [(gym, "tarea")])
        self.assertEqual(self.items(data, "2026-10-27"), [(manana, "tarea"), (tarde, "tarea"), (sin_hora, "tarea")])
        self.assertEqual(self.items(data, "2026-10-28"), [(hecha, "hecha")])
        self.assertEqual(self.items(data, "2026-10-29"), [(gym, "repeticion")])
        self.assertEqual(self.items(data, "2026-10-30"), [(espera, "revisar")])
        self.assertEqual(data["vencidas"], [vieja])
        self.assertNotIn(otra_semana, data["tareas"])
        self.assertEqual(data["pendientes"], 6)

        laboral = semana.construir(f, "laboral", AHORA)
        self.assertEqual(set(laboral["tareas"]), {manana})

    def test_other_weeks_and_projected_repeats(self):
        gym = self.f.crear({"titulo": "Gimnasio", "fecha": "2026-10-26", "repetir": "cada lunes y jueves"}).id
        data = semana.construir(self.f, None, AHORA, dt.date(2026, 11, 4))
        self.assertEqual(data["lunes"], "2026-11-02")
        self.assertEqual(self.items(data, "2026-11-02"), [(gym, "repeticion")])
        self.assertEqual(self.items(data, "2026-11-05"), [(gym, "repeticion")])
        self.assertEqual(data["vencidas"], [])  # only shown on the current week

    def test_month_grid(self):
        cita = self.f.crear({"titulo": "Cita", "fecha": "2026-10-01", "hora": "09:00"}).id
        fuera = self.f.crear({"titulo": "Noviembre", "fecha": "2026-11-02"}).id
        data = semana.construir_mes(self.f, None, AHORA)
        fechas_mes = [d["fecha"] for d in data["dias"]]
        self.assertEqual((data["mes"], fechas_mes[0], fechas_mes[-1], len(fechas_mes)), ("2026-10", "2026-09-28", "2026-11-01", 35))
        self.assertEqual(self.items(data, "2026-10-01"), [(cita, "tarea")])
        self.assertNotIn(fuera, data["tareas"])
        feb = semana.construir_mes(self.f, None, AHORA, "2027-02")  # starts on a Monday: four whole weeks
        self.assertEqual((feb["dias"][0]["fecha"], len(feb["dias"])), ("2027-02-01", 28))
        mar = semana.construir_mes(self.f, None, AHORA, "2026-03")  # 1 March 2026 is a Sunday: six weeks
        self.assertEqual(len(mar["dias"]), 42)

    def test_repeats_stop_at_the_end(self):
        pastilla = self.f.crear({"titulo": "Pastilla", "fecha": "2026-10-26", "hora": "22:00",
                                 "repetir": "cada día", "hasta": "2026-10-28"}).id
        data = semana.construir(self.f, None, AHORA)
        dias = [d["fecha"] for d in data["dias"] if (pastilla, "repeticion") in self.items(data, d["fecha"])]
        self.assertEqual(dias, ["2026-10-27", "2026-10-28"])

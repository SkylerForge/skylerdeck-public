import datetime as dt
import unittest

from agenda import fechas, quickadd, recurrencia

# Monday 26 October 2026, 09:00 in Madrid.
AHORA = dt.datetime(2026, 10, 26, 9, 0, tzinfo=fechas.TZ)


def p(text, ahora=AHORA):
    return quickadd.parsear(text, ahora)


class QuickAdd(unittest.TestCase):
    def test_brief_example(self):
        r = p("Llamar al dentista mañana 10:00 #Clientes p1 @teléfono")
        self.assertEqual(r.titulo, "Llamar al dentista")
        self.assertEqual((r.fecha, r.hora), ("2026-10-27", "10:00"))
        self.assertEqual((r.proyecto, r.prioridad, r.etiquetas), ("Clientes", "p1", ["teléfono"]))
        self.assertEqual([x["tipo"] for x in r.partes], ["fecha", "hora", "proyecto", "prioridad", "etiqueta"])

    def test_dates(self):
        cases = {
            "Algo hoy": "2026-10-26",
            "Algo mañana": "2026-10-27",
            "Algo manana": "2026-10-27",
            "Algo pasado mañana": "2026-10-28",
            "Algo el jueves": "2026-10-29",
            "Algo el próximo miércoles": "2026-10-28",
            "Algo el lunes": "2026-11-02",  # today is Monday: next week's
            "Algo 30/10": "2026-10-30",
            "Algo 30-10-2027": "2027-10-30",
            "Algo 1/3": "2027-03-01",
            "Algo 20/10": "2027-10-20",  # already gone this year
            "Algo el 3 de noviembre": "2026-11-03",
            "Algo en 3 días": "2026-10-29",
            "Algo dentro de dos semanas": "2026-11-09",
            "Algo la semana que viene": "2026-11-02",
            "Algo el finde": "2026-10-31",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                r = p(text)
                self.assertEqual(r.fecha, expected)
                self.assertEqual(r.titulo, "Algo")

    def test_times(self):
        self.assertEqual(p("Algo mañana a las 10").hora, "10:00")
        self.assertEqual(p("Algo mañana a las 10:30").hora, "10:30")
        self.assertEqual(p("Algo mañana 10h").hora, "10:00")
        self.assertEqual(p("Algo mañana a las 5 de la tarde").hora, "17:00")
        self.assertEqual(p("Algo mañana a las 10 de la mañana").fecha, "2026-10-27")
        r = p("Algo mañana a las 5")
        self.assertEqual(r.hora, "17:00")
        self.assertTrue(r.avisos)

    def test_time_alone_goes_today_or_tomorrow(self):
        self.assertEqual(p("Algo a las 11").fecha, "2026-10-26")
        r = p("Algo a las 8:00")
        self.assertEqual(r.fecha, "2026-10-27")
        self.assertTrue(r.avisos)

    def test_block_range(self):
        r = p("Bloque revisión hoy de 13 a 14:30 #Clientes")
        self.assertEqual((r.titulo, r.hora, r.duracion), ("Bloque revisión", "13:00", 90))
        self.assertEqual(p("Algo hoy 09:00-10:15").duracion, 75)

    def test_recurrence(self):
        r = p("Regar las plantas cada 3 días #Casa")
        self.assertEqual((r.titulo, r.repetir, r.fecha), ("Regar las plantas", "cada 3 días", "2026-10-26"))
        r = p("Gimnasio cada martes y jueves a las 19:00")
        self.assertEqual((r.repetir, r.fecha, r.hora), ("cada martes y jueves", "2026-10-27", "19:00"))
        self.assertEqual(p("Informe cada lunes").fecha, "2026-10-26")
        self.assertEqual(p("Revisar todos los sábados").repetir, "cada sábado")
        self.assertEqual(p("Fichar cada día laborable").repetir, "cada día laborable")
        r = p("Cada mes pagar alquiler")
        self.assertEqual((r.titulo, r.repetir), ("Pagar alquiler", "cada mes"))

    def test_leaves_unrelated_text_alone(self):
        self.assertEqual(p('Ver "los jueves de cine" pasado mañana').titulo, "Ver los jueves de cine")
        self.assertEqual(p("Escribir a ana@example.com").etiquetas, [])
        self.assertEqual(p("Escribir a ana@example.com").titulo, "Escribir a ana@example.com")
        self.assertIsNone(p("Comprar p5 tornillos").prioridad)
        r = p("Entregar 31/2")
        self.assertIsNone(r.fecha)
        self.assertTrue(r.avisos)

    def test_quotes_are_literal(self):
        r = p('Comprar "pan de mañana" mañana')
        self.assertEqual((r.titulo, r.fecha), ("Comprar pan de mañana", "2026-10-27"))
        self.assertEqual(p("Leer «Cada día #1» hoy").titulo, "Leer Cada día #1")

    def test_several_tags_once_each(self):
        self.assertEqual(p("Algo @casa @Casa @tienda").etiquetas, ["casa", "tienda"])

    def test_no_date(self):
        r = p("Pensar en el viaje")
        self.assertEqual((r.titulo, r.fecha, r.hora), ("Pensar en el viaje", None, None))


    def test_spoken_times(self):
        cases = {
            "Algo mañana a las nueve y cuarto": "09:15",
            "Algo mañana a las diez menos cuarto": "09:45",
            "Algo mañana a las 9 y media": "09:30",
            "Algo mañana a las ocho y veinte": "08:20",
            "Algo mañana a la una del mediodía": "13:00",
            "Algo mañana a las 8 de la tarde": "20:00",
            "Algo mañana a las 17 horas": "17:00",
            "Algo mañana sobre las 10": "10:00",
            "Algo esta tarde a las 6": "18:00",
            "Algo mañana por la mañana a las 7": "07:00",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                r = p(text)
                self.assertEqual((r.titulo, r.hora), ("Algo", expected))
        r = p("Algo mañana a las cinco y media")
        self.assertEqual(r.hora, "17:30")
        self.assertEqual(r.avisos, ["«a las cinco y media» lo entiendo como 17:30"])

    def test_parts_of_the_day(self):
        r = p("Llamar a Ana pasado mañana por la tarde")
        self.assertEqual((r.titulo, r.fecha, r.hora), ("Llamar a Ana", "2026-10-28", "17:00"))
        self.assertTrue(r.avisos)
        self.assertEqual((p("Cena esta noche").fecha, p("Cena esta noche").hora), ("2026-10-26", "21:00"))
        self.assertEqual(p("Comer con mamá el viernes a mediodía").hora, "14:00")
        self.assertEqual(p("Caldera el miércoles por la mañana").hora, "09:00")

    def test_from_now_and_durations(self):
        self.assertEqual((p("Dentro de 2 horas llamar").fecha, p("Dentro de 2 horas llamar").hora), ("2026-10-26", "11:00"))
        self.assertEqual(p("Llamar al seguro en media hora").hora, "09:30")
        self.assertEqual(p("Llamar en 7 minutos", AHORA.replace(minute=1)).hora, "09:10")  # rounded up to 5
        r = p("Cita en hacienda el 5/11 a las 12:30, durará una hora")
        self.assertEqual((r.titulo, r.duracion), ("Cita en hacienda", 60))
        self.assertEqual(p("Pádel mañana a las 20:00 durante hora y media").duracion, 90)
        self.assertEqual(p("Taller mañana a las 10 de dos horas").duracion, 120)
        self.assertIsNone(p("Paseo de dos horas").duracion)  # no time: the duration stays in the title
        r = p("Clase de 5 a 7 de la tarde")
        self.assertEqual((r.hora, r.duracion), ("17:00", 120))
        r = p("Comida de 1 a 3")
        self.assertEqual((r.hora, r.duracion), ("13:00", 120))
        self.assertTrue(r.avisos)
        self.assertEqual((p("Algo hoy de 11 a 1").hora, p("Algo hoy de 11 a 1").duracion), ("11:00", 120))

    def test_weekday_with_day_of_month(self):
        self.assertEqual(p("Revisión el lunes 2").fecha, "2026-11-02")
        self.assertEqual(p("Revisión el martes 3 de noviembre").fecha, "2026-11-03")
        self.assertEqual(p("Revisión el viernes 4").fecha, "2026-12-04")  # the next Friday the 4th
        r = p("Revisión el lunes 3 de noviembre")
        self.assertEqual(r.fecha, "2026-11-03")
        self.assertIn("es martes, no lunes", r.avisos[0])
        self.assertEqual(p("Pagar el día 14").fecha, "2026-11-14")
        self.assertEqual(p("Pagar el día 30").fecha, "2026-10-30")
        self.assertEqual(p("Pagar el día 14 de diciembre").fecha, "2026-12-14")

    def test_openings_stay_out_of_the_title(self):
        cases = {
            "Recuérdame que tengo cita con el dentista mañana": "Cita con el dentista",
            "Tengo que renovar el DNI": "Renovar el DNI",
            "Apunta que el viernes como con mi madre": "Como con mi madre",
            "Por favor apúntame la revisión de la caldera, por favor": "Revisión de la caldera",
            "tengo una reunión con Marta el lunes": "Reunión con Marta",
            "No olvides comprar pan": "Comprar pan",
            "Recuérdame llamar a Juan": "Llamar a Juan",
            "Apunta": "Apunta",
            "Reunión de equipo": "Reunión de equipo",
            "Tengo ganas de ir al cine": "Tengo ganas de ir al cine",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(p(text).titulo, expected)


    def test_recurring_only_when_said(self):
        # Tuesday 27 October 2026, 10:00
        martes = AHORA.replace(day=27, hour=10)
        cases = {
            "apúntame todos los días a las 9 el gimnasio": ("Gimnasio", "2026-10-28", "09:00", "cada día", None),
            "Gimnasio todos los días a las 9 hasta el 15 de diciembre": ("Gimnasio", "2026-10-28", "09:00", "cada día", "2026-12-15"),
            "inglés los lunes y los miércoles a las 7 de la tarde": ("Inglés", "2026-10-28", "19:00", "cada lunes y miércoles", None),
            "yoga cada martes a las 8 de la tarde hasta diciembre": ("Yoga", "2026-10-27", "20:00", "cada martes", "2026-12-31"),
            "pastilla cada día a las 22 hasta el 30/11": ("Pastilla", "2026-10-27", "22:00", "cada día", "2026-11-30"),
            "reunión de equipo cada dos semanas los lunes a las 10": ("Reunión de equipo", "2026-11-02", "10:00", "cada 2 semanas los lunes", None),
            "limpieza cada quince días": ("Limpieza", "2026-10-27", None, "cada 15 días", None),
            "pagar el alquiler el día 1 de cada mes": ("Pagar el alquiler", "2026-11-01", None, "cada mes", None),
            "paseo los fines de semana": ("Paseo", "2026-10-31", None, "cada sábado y domingo", None),
            "desde el 3 de noviembre todos los lunes a las 10 pilates": ("Pilates", "2026-11-09", "10:00", "cada lunes", None),
            "gimnasio cada lunes y jueves a las 19:00 durante 2 meses": ("Gimnasio", "2026-10-29", "19:00", "cada lunes y jueves", "2026-12-28"),
            "inglés a partir del lunes los martes y jueves a las 18 hasta final de año": ("Inglés", "2026-11-03", "18:00", "cada martes y jueves", "2026-12-31"),
            "revisión de la caldera semanalmente": ("Revisión de la caldera", "2026-10-27", None, "cada semana", None),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                r = p(text, martes)
                self.assertEqual((r.titulo, r.fecha, r.hora, r.repetir, r.hasta), expected)
        self.assertEqual(p("apúntame todos los días a las 9 el gimnasio", martes).avisos, ["Hoy ya han pasado las 09:00: empieza mañana"])
        self.assertEqual(p("gimnasio todos los días a las 11", martes).fecha, "2026-10-27")  # still to come today
        for once in ("Gimnasio mañana a las 9", "Dentista el lunes", "Entregar el informe hasta el viernes"):
            with self.subTest(text=once):
                r = p(once, martes)
                self.assertEqual((r.repetir, r.hasta, r.otras_fechas), (None, None, []))
        self.assertEqual(p("Entregar el informe hasta el viernes", martes).fecha, "2026-10-30")  # a deadline
        r = p("yoga cada lunes hasta el 1/10/2026", martes)
        self.assertEqual((r.hasta, r.avisos), (None, ["El final (01/10) es antes del primer día: la dejo sin final"]))

    def test_one_off_dates(self):
        martes = AHORA.replace(day=27, hour=10)
        r = p("fisio el lunes y el miércoles a las 10", martes)
        self.assertEqual((r.titulo, r.fecha, r.otras_fechas, r.hora, r.repetir), ("Fisio", "2026-10-28", ["2026-11-02"], "10:00", None))
        r = p("Dentista mañana, el jueves y el 5/11 a las 17:00", martes)
        self.assertEqual((r.titulo, r.fecha, r.otras_fechas), ("Dentista", "2026-10-28", ["2026-10-29", "2026-11-05"]))
        r = p("Comprar pan hoy y leche", martes)
        self.assertEqual((r.titulo, r.otras_fechas), ("Comprar pan y leche", []))


class Recurrence(unittest.TestCase):
    def test_next(self):
        lunes = dt.date(2026, 10, 26)
        self.assertEqual(recurrencia.parsear("cada 3 días").siguiente(lunes), dt.date(2026, 10, 29))
        self.assertEqual(recurrencia.parsear("cada lunes y jueves").siguiente(lunes), dt.date(2026, 10, 29))
        self.assertEqual(recurrencia.parsear("cada mes").siguiente(dt.date(2026, 1, 31)), dt.date(2026, 2, 28))
        self.assertEqual(recurrencia.parsear("cada día laborable").siguiente(dt.date(2026, 10, 30)), dt.date(2026, 11, 2))
        self.assertEqual(recurrencia.parsear("cada 2 semanas").siguiente(lunes), dt.date(2026, 11, 9))

    def test_skips_missed_dates(self):
        regla = recurrencia.parsear("cada 3 días")
        self.assertEqual(regla.siguiente(dt.date(2026, 10, 20), hasta_pasar=dt.date(2026, 10, 26)), dt.date(2026, 10, 29))

    def test_every_other_week_on_some_days(self):
        regla = recurrencia.parsear("cada 2 semanas los lunes y jueves")
        dia, fechas_ = dt.date(2026, 10, 26), []
        for _ in range(4):
            dia = regla.siguiente(dia)
            fechas_.append(dia)
        self.assertEqual(fechas_, [dt.date(2026, 10, 29), dt.date(2026, 11, 9), dt.date(2026, 11, 12), dt.date(2026, 11, 23)])

    def test_canonical_text_round_trips(self):
        for text in ("cada día", "cada 3 días", "cada lunes", "cada lunes y jueves", "cada mes", "cada 2 años", "cada día laborable",
                     "cada 2 semanas los lunes", "cada sábado y domingo"):
            self.assertEqual(recurrencia.parsear(text).texto(), text)

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            recurrencia.parsear("de vez en cuando")


if __name__ == "__main__":
    unittest.main()

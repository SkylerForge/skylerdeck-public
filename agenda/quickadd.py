"""Quick-add parser: one line of Spanish → task fields. No LLM, just rules.

    Llamar al dentista mañana 10:00 #Salud p1 @teléfono
    Recuérdame que tengo cita con el dentista el martes a las cinco y media

Understands dates (hoy, mañana, pasado mañana, el jueves, el lunes 3, el día 14, 30/10,
30 de octubre, en 3 días, la semana que viene), times in figures or words (a las 10, 10:00, 10h,
a las cinco y media, a las diez menos cuarto, a la una del mediodía, a las 5 de la tarde),
parts of the day (esta tarde, por la mañana, a mediodía: a usual hour, with a note), times from
now (dentro de 2 horas, en media hora), ranges and durations for work blocks (de 13 a 14,
durante hora y media), recurrences (cada lunes, los martes, todos los días, cada 15 días) with an
optional start and end (desde el 3 de noviembre, hasta el 15/12, hasta diciembre, durante 2
meses; no end unless one is given), several one-off dates (el lunes y el miércoles: one task
each, never a recurrence), #proyecto, @etiqueta and p1-p4.
Openings such as «Recuérdame que», «Apunta» or «Tengo que» stay out of the title.
Text "between quotes" is never parsed.

Each recognised piece is reported with its span, so the panel can highlight it while typing.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, field

from . import fechas, horas, recurrencia
from .horas import B, DURACION_RE, E, HORA_PERIODO, HORA_RE, NUM, PERIODO_RE, RANGO_RE, RELATIVO_RE

_DIA = r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)"
_MES = "|".join(fechas.MESES + ["setiembre"])
FECHA_RE = re.compile(
    rf"{B}(?:"
    rf"(?P<pasado>pasado\s+ma[ñn]ana)"
    rf"|(?P<hoy>hoy)"
    rf"|(?P<manana>ma[ñn]ana)"
    rf"|(?:(?:el|este)\s+)?(?P<wd2>{_DIA})\s+(?:d[íi]a\s+)?(?P<d3>\d{{1,2}})(?:[/-](?P<mo3>\d{{1,2}})|\s+de\s+(?P<mes3>{_MES}))?"
    rf"|(?:(?:el|este|el\s+pr[óo]ximo|pr[óo]ximo)\s+)?(?P<wd>{_DIA})(?:\s+que\s+viene)?"
    rf"|(?:el\s+)?(?P<d>\d{{1,2}})[/-](?P<mo>\d{{1,2}})(?:[/-](?P<y>\d{{4}}|\d{{2}}))?"
    rf"|(?:el\s+)?(?:d[íi]a\s+)?(?P<d2>\d{{1,2}})\s+de\s+(?P<mes>{_MES})(?:\s+(?:de\s+)?(?P<y2>\d{{4}}))?"
    rf"|(?:el\s+)?d[íi]a\s+(?P<d4>\d{{1,2}})"
    rf"|(?:en|dentro\s+de)\s+(?P<n>{NUM})\s+(?P<u>d[íi]as?|semanas?|mes(?:es)?)"
    rf"|(?:la\s+)?(?P<semana>semana\s+que\s+viene|pr[óo]xima\s+semana)"
    rf"|(?:el\s+)?(?P<finde>fin\s+de\s+semana|finde)"
    rf"){E}",
    re.IGNORECASE,
)
# «hasta el 15 de diciembre», «desde mañana», «a partir del lunes»: the date itself is read by FECHA_RE.
LIMITE_RE = re.compile(rf"{B}(?P<tipo>hasta|desde|a\s+partir\s+del?)\s+(?:el\s+)?", re.IGNORECASE)
HASTA_MES_RE = re.compile(
    rf"(?:(?:el\s+)?(?:fin(?:al)?|finales)\s+de\s+)?(?:(?P<mes>{_MES})|(?P<finmes>mes)|(?P<finano>a[ñn]o))(?:\s+(?:de\s+)?(?P<y>\d{{4}}))?{E}",
    re.IGNORECASE)
DURANTE_RE = re.compile(rf"{B}durante\s+(?P<n>{NUM})\s+(?P<u>d[íi]as?|semanas?|mes(?:es)?|a[ñn]os?){E}", re.IGNORECASE)
UNION_RE = re.compile(r"\s*(?:,|\by\b|\be\b)\s*", re.IGNORECASE)
PRIORIDAD_RE = re.compile(rf"{B}p(?P<p>[1-4]){E}", re.IGNORECASE)
PROYECTO_RE = re.compile(r"(?<!\S)#(?P<p>[^\W_][\w-]*)")
ETIQUETA_RE = re.compile(r"(?<!\S)@(?P<t>[^\W_][\w-]*)")
CITA_RE = re.compile(r"\"([^\"]+)\"|«([^»]+)»")
SOBRANTE_RE = re.compile(r"(?:^|\s+)(?:el|la|a|las|los|para|de|del|al|y|en|por|,|;|:|-|–)$", re.IGNORECASE)
# How people start a request to a bot: not part of the title.
RELLENO_RE = re.compile(
    r"^(?:(?:por\s+favor|oye|vale)[,\s]+)?"
    r"(?:recu[ée]rda(?:me|nos|le)?|ap[úu]nta(?:me|nos|lo)?|anota(?:me|lo)?|no\s+(?:me\s+)?olvides(?:\s+de)?"
    r"|que\s+no\s+se\s+me\s+olvide|tengo\s+que|tenemos\s+que|hay\s+que"
    r"|a[ñn][aá]de(?:me|nos)|agr[eé]ga(?:me|nos)|pon(?:me|nos)|m[eé]te(?:me|nos)"  # «añádeme…», not «pon la lavadora»
    r"|(?:a[ñn][aá]de|agr[eé]ga|pon|mete)(?=\s+(?:a|en)\s+(?:la|mi)\s+agenda\b))"
    r"(?:\s+(?:a|en)\s+(?:la|mi)\s+agenda\b)?(?:\s+que)?(?:[,:\s]+|$)",
    re.IGNORECASE,
)
# «Tengo cita con…» → «Cita con…»
TENGO_RE = re.compile(
    r"^(?:tengo|tenemos|hay)\s+(?:una?\s+)?(?=(?:cita|reuni[óo]n|consulta|llamada|videollamada|entrevista|clase|examen"
    r"|comida|cena|visita|revisi[óo]n|partido|vuelo|tutor[íi]a|m[ée]dico|dentista|fisio|peluquer[íi]a)\b)",
    re.IGNORECASE,
)
ARTICULO_RE = re.compile(r"^(?:el|la|los|las|un|una)\s+", re.IGNORECASE)
FINAL_RE = re.compile(r"(?:[,;\s]+por\s+favor)?[\s,;.!]*$", re.IGNORECASE)


@dataclass
class Resultado:
    titulo: str = ""
    fecha: str | None = None
    hora: str | None = None
    duracion: int | None = None
    repetir: str | None = None
    proyecto: str | None = None
    etiquetas: list[str] = field(default_factory=list)
    prioridad: str | None = None
    hasta: str | None = None  # last day of a recurring task
    otras_fechas: list[str] = field(default_factory=list)  # «el lunes y el miércoles»: one more task each
    partes: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def campos(self) -> dict:
        """Fields for Fichas.crear (the project is still the text typed; the caller resolves it)."""
        out = {"titulo": self.titulo}
        for key in ("fecha", "hora", "repetir", "hasta", "proyecto", "prioridad"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.duracion:
            out["duracion"] = str(self.duracion)
        if self.etiquetas:
            out["etiquetas"] = list(self.etiquetas)
        return out

    def to_dict(self) -> dict:
        return asdict(self)


class _Texto:
    """The line being parsed: pieces taken so far are blanked out so later rules skip them."""

    def __init__(self, text: str):
        self.original = text
        self.quitado = [False] * len(text)
        chars = list(text)
        for m in CITA_RE.finditer(text):
            inner = m.span(1) if m.group(1) is not None else m.span(2)
            for i in range(*inner):
                chars[i] = "\x00"  # quoted text never matches anything
            self.quitado[m.start()] = self.quitado[m.end() - 1] = True
        self.trabajo = "".join(chars)
        self.partes: list[dict] = []

    def tomar(self, m: re.Match, tipo: str) -> None:
        self.tomar_rango(*m.span(), tipo)

    def tomar_rango(self, start: int, end: int, tipo: str) -> None:
        self.trabajo = self.trabajo[:start] + " " * (end - start) + self.trabajo[end:]
        for i in range(start, end):
            self.quitado[i] = True
        self.partes.append({"tipo": tipo, "inicio": start, "fin": end, "texto": self.original[start:end]})

    def resto(self) -> str:
        return "".join(c if not q else " " for c, q in zip(self.original, self.quitado))


def _dia_del_mes(dia: int, hoy: dt.date, wd: int | None = None) -> dt.date | None:
    """The next date with that day of the month (and that weekday, when given)."""
    for n in range(14):
        primero = fechas.sumar_meses(hoy.replace(day=1), n)
        try:
            fecha = primero.replace(day=dia)
        except ValueError:
            continue
        if fecha >= hoy and (wd is None or fecha.weekday() == wd):
            return fecha
    return None


def _con_mes(dia: int, mes: int, year_text: str | None, hoy: dt.date) -> dt.date:
    year = (int(year_text) + (2000 if len(year_text) == 2 else 0)) if year_text else hoy.year
    fecha = dt.date(year, mes, dia)
    if not year_text and fecha < hoy:
        fecha = fecha.replace(year=hoy.year + 1)
    return fecha


def _mes(texto: str) -> int:
    return fechas.mes(texto if texto.lower() != "setiembre" else "septiembre")


def _fecha(m: re.Match, hoy: dt.date, avisos: list[str]) -> dt.date | None:
    g = m.groupdict()
    if g["pasado"]:
        return hoy + dt.timedelta(days=2)
    if g["hoy"]:
        return hoy
    if g["manana"]:
        return hoy + dt.timedelta(days=1)
    if g["wd2"]:
        wd, dia = fechas.dia_semana(g["wd2"]), int(g["d3"])
        nombre = fechas.DIAS[wd]
        if g["mo3"] or g["mes3"]:
            try:
                fecha = _con_mes(dia, int(g["mo3"]) if g["mo3"] else _mes(g["mes3"]), None, hoy)
            except ValueError:
                avisos.append(f"«{m.group(0).strip()}» no es una fecha válida")
                return None
            if fecha.weekday() != wd:
                avisos.append(f"El {fechas.corta(fecha)} es {fechas.DIAS[fecha.weekday()]}, no {nombre}")
            return fecha
        fecha = _dia_del_mes(dia, hoy, wd)
        if fecha:
            return fecha
        fecha = fechas.proximo_dia_semana(hoy, wd)
        avisos.append(f"No encuentro un {nombre} {dia} cercano: lo pongo el {nombre} {fechas.corta(fecha)}")
        return fecha
    if g["wd"]:
        return fechas.proximo_dia_semana(hoy, fechas.dia_semana(g["wd"]))
    if g["d4"]:
        fecha = _dia_del_mes(int(g["d4"]), hoy)
        if not fecha:
            avisos.append(f"«{m.group(0).strip()}» no es una fecha válida")
        return fecha
    if g["semana"]:
        return fechas.proximo_dia_semana(hoy, 0)
    if g["finde"]:
        return fechas.proximo_dia_semana(hoy, 5, incluir_hoy=True)
    if g["n"]:
        n = horas.numero(g["n"])
        u = fechas.clave(g["u"])
        if u.startswith("dia"):
            return hoy + dt.timedelta(days=n)
        if u.startswith("semana"):
            return hoy + dt.timedelta(weeks=n)
        return fechas.sumar_meses(hoy, n)
    day = int(g["d"] or g["d2"])
    month = int(g["mo"]) if g["mo"] else _mes(g["mes"])
    try:
        return _con_mes(day, month, g["y"] or g["y2"], hoy)
    except ValueError:
        avisos.append(f"«{m.group(0).strip()}» no es una fecha válida")
        return None


def _fin_de(m: re.Match, hoy: dt.date) -> dt.date:
    """«hasta diciembre», «hasta final de mes», «hasta fin de año» → the last day of it."""
    if m["finano"]:
        return dt.date(hoy.year, 12, 31)
    mes = hoy.month if m["finmes"] else _mes(m["mes"])
    year = int(m["y"]) if m["y"] else hoy.year
    ultimo = fechas.sumar_meses(dt.date(year, mes, 1), 1) - dt.timedelta(days=1)
    return ultimo.replace(year=year + 1) if not m["y"] and ultimo < hoy else ultimo


def _limites(texto: _Texto, hoy: dt.date, avisos: list[str]) -> tuple[dt.date | None, dt.date | None]:
    """Takes «desde …» and «hasta …» with their dates; returns (desde, hasta)."""
    desde = hasta = None
    for m in list(LIMITE_RE.finditer(texto.trabajo)):
        es_hasta = m["tipo"].lower() == "hasta"
        dm = FECHA_RE.match(texto.trabajo, m.end())
        if dm:
            dia = _fecha(dm, hoy, avisos)
        elif es_hasta and (dm := HASTA_MES_RE.match(texto.trabajo, m.end())):
            dia = _fin_de(dm, hoy)
        else:
            continue
        if dia:
            texto.tomar_rango(m.start(), dm.end(), "fecha")
            if es_hasta:
                hasta = hasta or dia
            else:
                desde = desde or dia
    return desde, hasta


def _titulo(texto: _Texto) -> str:
    titulo = " ".join(texto.resto().split())
    titulo = re.sub(r"\s+([,;.:!?])", r"\1", titulo)
    while True:
        limpio = SOBRANTE_RE.sub("", FINAL_RE.sub("", titulo)).strip()
        limpio = limpio.lstrip(",;:-– ").strip()
        sin_relleno = RELLENO_RE.sub("", limpio)
        if sin_relleno != limpio:  # «Apúntame la revisión…» → «Revisión…»
            sin_relleno = ARTICULO_RE.sub("", sin_relleno)
        sin_relleno = TENGO_RE.sub("", sin_relleno).strip()
        limpio = sin_relleno or limpio  # «Apunta» alone stays as it is
        if limpio == titulo:
            break
        titulo = limpio
    return titulo[:1].upper() + titulo[1:]


def parsear(linea: str, ahora: dt.datetime | None = None) -> Resultado:
    ahora = ahora or fechas.ahora()
    hoy = ahora.date()
    texto = _Texto(linea)
    r = Resultado()

    hallado = recurrencia.buscar(texto.trabajo)
    if hallado:
        regla, _ = hallado
        texto.tomar(recurrencia.REGEX.search(texto.trabajo), "repetir")
        r.repetir = regla.texto()

    m = RELATIVO_RE.search(texto.trabajo)
    if m and horas.lapso(m):
        # «dentro de 2 horas»: from now, rounded up to the next 5 minutes.
        momento = ahora + dt.timedelta(minutes=horas.lapso(m))
        momento += dt.timedelta(minutes=-momento.minute % 5)
        texto.tomar(m, "hora")
        r.fecha, r.hora = fechas.iso(momento.date()), momento.strftime("%H:%M")

    periodo, esta = "", False
    m = PERIODO_RE.search(texto.trabajo)
    if m:
        texto.tomar(m, "hora")
        periodo, esta = horas.periodo(m["p1"] or m["p2"] or m["p3"]), bool(m["esta"])

    m = RANGO_RE.search(texto.trabajo)
    if m and not r.hora:
        rango = horas.rango(m, horas.periodo(m["periodo"]) or periodo, r.avisos)
        if rango:
            texto.tomar(m, "hora")
            r.hora, r.duracion = rango
    if not r.hora:
        m = HORA_RE.search(texto.trabajo)
        if m:
            hora = horas.hora(m, horas.periodo(m["periodo"]) or periodo, r.avisos)
            if hora:
                texto.tomar(m, "hora")
                r.hora = hora

    m = DURACION_RE.search(texto.trabajo)
    if m and r.hora and not r.duracion and 0 < horas.lapso(m) <= 24 * 60:
        texto.tomar(m, "hora")
        r.duracion = horas.lapso(m)

    desde, hasta = _limites(texto, hoy, r.avisos)
    m = DURANTE_RE.search(texto.trabajo) if r.repetir else None
    durante = None
    if m:
        texto.tomar(m, "fecha")
        durante = m

    for m in FECHA_RE.finditer(texto.trabajo):
        if (m["wd"] or m["wd2"]) and re.search(r"(?:los|las|cada|todos)\s+$", texto.trabajo[: m.start()], re.IGNORECASE):
            continue
        dia = _fecha(m, hoy, r.avisos)
        if dia:
            texto.tomar(m, "fecha")
            r.fecha = fechas.iso(dia)
            # «el lunes y el miércoles»: the same appointment on other days, one task each.
            pos = m.end()
            while not r.repetir and (u := UNION_RE.match(texto.trabajo, pos)) and (otra := FECHA_RE.match(texto.trabajo, u.end())):
                dia = _fecha(otra, hoy, r.avisos)
                if not dia:
                    break
                texto.tomar_rango(pos, otra.end(), "fecha")
                if fechas.iso(dia) != r.fecha and fechas.iso(dia) not in r.otras_fechas:
                    r.otras_fechas.append(fechas.iso(dia))
                pos = otra.end()
            if r.otras_fechas:  # the first task is the soonest
                r.fecha, *r.otras_fechas = sorted({r.fecha, *r.otras_fechas})
        break

    m = PRIORIDAD_RE.search(texto.trabajo)
    if m:
        texto.tomar(m, "prioridad")
        r.prioridad = f"p{m['p']}"

    m = PROYECTO_RE.search(texto.trabajo)
    if m:
        texto.tomar(m, "proyecto")
        r.proyecto = m["p"]

    for m in list(ETIQUETA_RE.finditer(texto.trabajo)):
        texto.tomar(m, "etiqueta")
        tag = m["t"].lower()
        if tag not in r.etiquetas:
            r.etiquetas.append(tag)

    if periodo and not r.hora and periodo in HORA_PERIODO:
        r.hora = HORA_PERIODO[periodo]
        r.avisos.append(f"Sin hora concreta: la pongo a las {r.hora}")
    if esta and not r.fecha:
        r.fecha = fechas.iso(hoy)
    if desde and not r.fecha:
        r.fecha = fechas.iso(desde)
    if r.repetir:
        _repeticion(r, ahora, durante, hasta)
    elif hasta and not r.fecha:
        r.fecha = fechas.iso(hasta)  # «entregar el informe hasta el viernes»: a deadline
    if r.hora and not r.fecha:
        if r.hora <= ahora.strftime("%H:%M"):
            r.fecha = fechas.iso(hoy + dt.timedelta(days=1))
            r.avisos.append(f"Las {r.hora} de hoy ya han pasado: la pongo mañana")
        else:
            r.fecha = fechas.iso(hoy)

    r.titulo = _titulo(texto)
    r.partes = sorted(texto.partes, key=lambda p: p["inicio"])
    return r


def _repeticion(r: Resultado, ahora: dt.datetime, durante: re.Match | None, hasta: dt.date | None) -> None:
    """First date of a recurring task (never one already gone) and its last day, if one was given."""
    hoy = ahora.date()
    regla = recurrencia.parsear(r.repetir)
    dado = bool(r.fecha)
    inicio = regla.primera(fechas.desde_iso(r.fecha) if dado else hoy)
    if not dado and inicio == hoy and r.hora and r.hora <= ahora.strftime("%H:%M"):
        inicio = regla.siguiente(hoy)
        r.avisos.append(f"Hoy ya han pasado las {r.hora}: empieza {fechas.humana(inicio, hoy)}")
    r.fecha = fechas.iso(inicio)
    if durante:
        n, u = horas.numero(durante["n"]), fechas.clave(durante["u"])
        fin = (inicio + dt.timedelta(days=n) if u.startswith("dia") else inicio + dt.timedelta(weeks=n)
               if u.startswith("semana") else fechas.sumar_meses(inicio, n * (12 if u.startswith("ano") else 1)))
        hasta = hasta or fin - dt.timedelta(days=1)
    if hasta and hasta < inicio:
        r.avisos.append(f"El final ({fechas.corta(hasta)}) es antes del primer día: la dejo sin final")
    elif hasta:
        r.hasta = fechas.iso(hasta)

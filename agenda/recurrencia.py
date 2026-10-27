"""Recurrence rules written in Spanish: 'cada lunes', 'cada 3 días', 'cada día laborable'.

The card stores the canonical text (`repetir: "cada lunes y jueves"`), so the same
parser reads the quick-add and the card.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .fechas import DIAS, dia_semana, proximo_dia_semana, sumar_meses

UNIDADES = {
    "dia": "dia", "dias": "dia", "día": "dia", "días": "dia",
    "semana": "semana", "semanas": "semana",
    "mes": "mes", "meses": "mes",
    "año": "año", "años": "año", "ano": "año", "anos": "año",
}
NUMEROS = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20, "treinta": 30}
_N = r"(?:\d{1,3}|" + "|".join(NUMEROS) + ")"
_DIA = r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?)"
_LISTA_DIAS = rf"{_DIA}(?:\s*(?:,|\by\b|\be\b)\s*(?:los\s+)?{_DIA})*"
_SEPARA_DIAS = re.compile(r"\s*(?:,|\by\b|\be\b)\s*(?:los\s+)?", re.IGNORECASE)

# Order matters: longer forms first. «los lunes» (plural) is a habit; «el lunes» is one date (quickadd).
PATRONES = [
    r"(?P<laborable>cada\s+d[íi]a\s+laborable|todos\s+los\s+d[íi]as\s+laborables|entre\s+semana|de\s+lunes\s+a\s+viernes)",
    rf"cada\s+(?P<n2>{_N})\s+semanas\s+(?:los\s+|el\s+)?(?P<lista2>{_LISTA_DIAS})",
    r"(?:cada|todos\s+los|los)\s+(?P<finde>fines?\s+de\s+semana|findes?)",
    rf"(?:cada|todos\s+los|los)\s+(?P<lista>{_LISTA_DIAS})",
    rf"cada\s+(?P<n>{_N})\s+(?P<unidad_n>d[íi]as|semanas|meses|a[ñn]os)",
    r"(?:cada|todos\s+los|todas\s+las)\s+(?P<unidad>d[íi]as?|semanas?|mes(?:es)?|a[ñn]os?)",
    r"(?P<diario>a\s+diario|diariamente)",
    r"(?P<adverbio>semanalmente|mensualmente|anualmente)",
]
REGEX = re.compile(r"\b(?:" + "|".join(PATRONES) + r")\b", re.IGNORECASE)


@dataclass(frozen=True)
class Regla:
    unidad: str  # dia | semana | mes | año
    cada: int = 1
    dias: tuple[int, ...] = ()  # weekdays for weekly rules, 0 = lunes

    def texto(self) -> str:
        if self.dias == (0, 1, 2, 3, 4) and self.unidad == "semana" and self.cada == 1:
            return "cada día laborable"
        if self.dias:
            nombres = [DIAS[d] for d in self.dias]
            lista = nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"
            return f"cada {lista}" if self.cada == 1 else f"cada {self.cada} semanas los {lista}"
        singular = {"dia": "día", "semana": "semana", "mes": "mes", "año": "año"}[self.unidad]
        plural = {"dia": "días", "semana": "semanas", "mes": "meses", "año": "años"}[self.unidad]
        return f"cada {singular}" if self.cada == 1 else f"cada {self.cada} {plural}"

    def primera(self, desde: dt.date) -> dt.date:
        """First date on or after `desde` that fits the rule."""
        if self.dias:
            return min(proximo_dia_semana(desde, d, incluir_hoy=True) for d in self.dias)
        return desde

    def siguiente(self, despues_de: dt.date, hasta_pasar: dt.date | None = None) -> dt.date:
        """Next date after `despues_de`; with `hasta_pasar`, keeps going until it is later than that day."""
        dia = self._paso(despues_de)
        while hasta_pasar and dia <= hasta_pasar:
            dia = self._paso(dia)
        return dia

    def _paso(self, dia: dt.date) -> dt.date:
        if self.dias and self.cada > 1:
            # «cada 2 semanas los lunes y jueves»: the rest of this week, then skip ahead.
            despues = [d for d in self.dias if d > dia.weekday()]
            if despues:
                return dia + dt.timedelta(days=min(despues) - dia.weekday())
            return dia - dt.timedelta(days=dia.weekday()) + dt.timedelta(weeks=self.cada, days=min(self.dias))
        if self.dias:
            return min(proximo_dia_semana(dia, d) for d in self.dias)
        if self.unidad == "dia":
            return dia + dt.timedelta(days=self.cada)
        if self.unidad == "semana":
            return dia + dt.timedelta(weeks=self.cada)
        if self.unidad == "mes":
            return sumar_meses(dia, self.cada)
        return sumar_meses(dia, 12 * self.cada)


def _numero(texto: str) -> int:
    return int(texto) if texto.isdigit() else NUMEROS[texto.lower()]


def _dias(texto: str) -> tuple[int, ...]:
    nombres = [n for n in _SEPARA_DIAS.split(texto.strip()) if n]
    dias = {dia_semana(n.rstrip("s") if n.lower().endswith(("bados", "ngos")) else n) for n in nombres}
    return tuple(sorted(d for d in dias if d is not None))


def _desde_match(m: re.Match) -> Regla:
    if m.group("laborable"):
        return Regla("semana", 1, (0, 1, 2, 3, 4))
    if m.group("finde"):
        return Regla("semana", 1, (5, 6))
    if m.group("lista2"):
        return Regla("semana", max(1, _numero(m.group("n2"))), _dias(m.group("lista2")))
    if m.group("lista"):
        return Regla("semana", 1, _dias(m.group("lista")))
    if m.group("diario"):
        return Regla("dia")
    if m.group("adverbio"):
        return Regla({"semanalmente": "semana", "mensualmente": "mes", "anualmente": "año"}[m.group("adverbio").lower()])
    unidad = UNIDADES[(m.group("unidad") or m.group("unidad_n")).lower()]
    cada = _numero(m.group("n")) if m.group("n") else 1
    if cada < 1:
        raise ValueError("El intervalo tiene que ser al menos 1")
    return Regla(unidad, cada)


def buscar(text: str) -> tuple[Regla, tuple[int, int]] | None:
    """Finds a rule inside free text; returns it with its span."""
    m = REGEX.search(text)
    if not m:
        return None
    return _desde_match(m), m.span()


def parsear(text: str) -> Regla:
    """Parses a whole rule ('cada lunes'); raises ValueError otherwise."""
    m = REGEX.fullmatch(text.strip())
    if not m:
        raise ValueError(f"No entiendo la repetición «{text}». Ejemplos: cada lunes, cada 3 días, cada mes")
    return _desde_match(m)

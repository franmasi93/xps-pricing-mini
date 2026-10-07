"""Fecha de negocio de XPRESS (America/Guayaquil).

Ecuador no tiene horario de verano desde 1993: se usa un desfase fijo UTC−5, sin depender del
paquete tzdata (que Windows necesitaría para zoneinfo). Los tests sustituyen `hoy_ecuador`;
por eso los services lo llaman siempre como `fechas.hoy_ecuador()`.
"""
from datetime import date, datetime, timedelta, timezone

ZONA_ECUADOR = timezone(timedelta(hours=-5), "America/Guayaquil")


def hoy_ecuador() -> date:
    return datetime.now(ZONA_ECUADOR).date()

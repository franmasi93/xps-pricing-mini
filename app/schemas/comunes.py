"""Piezas compartidas por los schemas de catálogos."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


def rechazar_null(valor):
    """Para PATCH: un campo obligatorio se omite si no cambia; enviarlo en null es un error."""
    if valor is None:
        raise ValueError("no puede ser null; omita el campo si no quiere cambiarlo")
    return valor


def sin_null(*campos: str):
    return field_validator(*campos, mode="before")(lambda cls, valor: rechazar_null(valor))

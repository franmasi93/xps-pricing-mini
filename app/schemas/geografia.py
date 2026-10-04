"""Schemas de M2 Geografía. El formato de los códigos se valida en el service (códigos de error propios)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null

TipoPuerto = Literal["MARITIMO", "AEREO"]


class RegionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str


class PaisResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iso2: str
    nombre: str


class RegionSalida(CatalogoSalida):
    codigo: str
    nombre: str


class PaisSalida(CatalogoSalida):
    iso2: str
    nombre: str
    region_id: int
    region: RegionResumen


class PuertoSalida(CatalogoSalida):
    codigo: str
    nombre: str
    tipo: str
    pais_id: int
    pais: PaisResumen


class RegionCrear(Entrada):
    codigo: str = Field(max_length=40)
    nombre: str = Field(max_length=80)


class RegionActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=40)
    nombre: str | None = Field(default=None, max_length=80)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "activo")


class PaisCrear(Entrada):
    iso2: str = Field(max_length=10)
    nombre: str = Field(max_length=100)
    region_id: int


class PaisActualizar(Entrada):
    iso2: str | None = Field(default=None, max_length=10)
    nombre: str | None = Field(default=None, max_length=100)
    region_id: int | None = None
    activo: bool | None = None

    _sin_null = sin_null("iso2", "nombre", "region_id", "activo")


class PuertoCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=120)
    pais_id: int
    tipo: TipoPuerto


class PuertoActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=20)
    nombre: str | None = Field(default=None, max_length=120)
    pais_id: int | None = None
    tipo: TipoPuerto | None = None
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "pais_id", "tipo", "activo")

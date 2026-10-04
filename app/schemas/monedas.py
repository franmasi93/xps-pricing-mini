"""Schemas de M3 Monedas y tasas. Las tasas viajan como texto para no perder precisión (Decimal)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null


class MonedaSalida(CatalogoSalida):
    codigo: str
    nombre: str
    simbolo: str


class MonedaCrear(Entrada):
    codigo: str = Field(max_length=10)
    nombre: str = Field(max_length=80)
    simbolo: str = Field(max_length=8)


class MonedaActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=10)
    nombre: str | None = Field(default=None, max_length=80)
    simbolo: str | None = Field(default=None, max_length=8)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "simbolo", "activo")


class TasaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    moneda_id: int
    moneda: str
    tasa_a_usd: Decimal
    fecha_vigencia: date
    registrado_por: int
    creado_en: datetime
    actualizado_en: datetime

    @field_serializer("tasa_a_usd")
    def _texto(self, valor: Decimal) -> str:
        return str(valor)


class TasaCrear(Entrada):
    moneda: str = Field(max_length=10)
    tasa_a_usd: Decimal
    fecha_vigencia: date
    confirmar_desvio: bool = False


class TasaCorregir(Entrada):
    tasa_a_usd: Decimal
    confirmar_desvio: bool = False


class TasaVigenteSalida(BaseModel):
    moneda: str
    fecha: date
    tasa_a_usd: Decimal

    @field_serializer("tasa_a_usd")
    def _texto(self, valor: Decimal) -> str:
        return str(valor)

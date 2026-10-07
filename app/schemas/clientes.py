"""Schemas de M6 Clientes y contactos (sin datos de costo: no llevan gating)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import Entrada, sin_null
from app.schemas.geografia import PaisResumen

TipoIdentificacion = Literal["RUC", "CEDULA", "PASAPORTE", "EXTRANJERO"]


class ComercialRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class ContactoPrincipalRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: str | None


class ClienteSalida(BaseModel):
    id: int
    razon_social: str
    tipo_id: str
    ruc_o_id: str
    pais: PaisResumen
    direccion: str | None
    ciudad: str | None
    telefono: str | None
    notas: str | None
    comercial_asignado: ComercialRef
    contacto_principal: ContactoPrincipalRef | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


class ContactoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    nombre: str
    cargo: str | None
    email: str | None
    telefono: str | None
    principal: bool
    activo: bool
    creado_en: datetime
    actualizado_en: datetime
    # Indica si el cliente quedó con un contacto principal activo (p. ej. tras desactivar el principal).
    cliente_tiene_principal: bool


class ClienteCrear(Entrada):
    razon_social: str = Field(max_length=200)
    tipo_id: TipoIdentificacion
    ruc_o_id: str = Field(max_length=60)
    pais_id: int
    direccion: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)
    comercial_asignado_id: int | None = None


class ClienteActualizar(Entrada):
    razon_social: str | None = Field(default=None, max_length=200)
    tipo_id: TipoIdentificacion | None = None
    ruc_o_id: str | None = Field(default=None, max_length=60)
    pais_id: int | None = None
    direccion: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)
    comercial_asignado_id: int | None = None
    activo: bool | None = None

    _sin_null = sin_null("razon_social", "tipo_id", "ruc_o_id", "pais_id", "comercial_asignado_id", "activo")


class ContactoCrear(Entrada):
    nombre: str = Field(max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    principal: bool = False


class ContactoActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    principal: bool | None = None
    activo: bool | None = None

    _sin_null = sin_null("nombre", "principal", "activo")

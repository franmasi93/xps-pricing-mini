"""Schemas de M6 Clientes y contactos (sin datos de costo: no llevan gating)."""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import Entrada, sin_null
from app.schemas.geografia import PaisResumen



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
    # E1-B: perfil comercial, consentimiento y columnas calculadas de la lista.
    nombre_comercial: str | None = None
    tipo_cliente: str | None = None
    estado_comercial: str = "ACTIVO"
    sector: str | None = None
    servicios_interes: list[str] = []
    rutas_interes: list[str] = []
    tipos_carga: list[str] = []
    volumen_estimado: str | None = None
    frecuencia: str | None = None
    origen_cliente: str | None = None
    etiquetas: list[str] = []
    acepta_promociones: bool = True
    fecha_consentimiento: date | None = None
    medio_consentimiento: str | None = None
    ultimo_envio: datetime | None = None
    ultima_cotizacion: date | None = None


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
    # E1-B: área y consentimiento (recibe_cotizaciones = recibir_avisos de E3).
    area: str | None = None
    recibe_promociones: bool = True
    recibe_cotizaciones: bool = True


class ClienteCrear(Entrada):
    razon_social: str = Field(max_length=200)
    tipo_id: str = Field(max_length=10)  # E2: catálogo tipo_identificacion
    ruc_o_id: str = Field(max_length=60)
    pais_id: int
    direccion: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)
    comercial_asignado_id: int | None = None
    # E1-B: perfil comercial (códigos de los catálogos; listas como arreglos).
    nombre_comercial: str | None = Field(default=None, max_length=200)
    tipo_cliente: str | None = Field(default=None, max_length=120)
    estado_comercial: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    servicios_interes: list[str] | None = Field(default=None, max_length=50)
    rutas_interes: list[str] | None = Field(default=None, max_length=100)
    tipos_carga: list[str] | None = Field(default=None, max_length=50)
    volumen_estimado: str | None = Field(default=None, max_length=120)
    frecuencia: str | None = Field(default=None, max_length=120)
    origen_cliente: str | None = Field(default=None, max_length=120)
    etiquetas: list[str] | None = Field(default=None, max_length=50)
    acepta_promociones: bool | None = None
    fecha_consentimiento: date | None = None
    medio_consentimiento: str | None = Field(default=None, max_length=120)


class ClienteActualizar(Entrada):
    razon_social: str | None = Field(default=None, max_length=200)
    tipo_id: str | None = Field(default=None, max_length=10)
    ruc_o_id: str | None = Field(default=None, max_length=60)
    pais_id: int | None = None
    direccion: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)
    comercial_asignado_id: int | None = None
    activo: bool | None = None
    # E1-B: perfil comercial (códigos de los catálogos; listas como arreglos).
    nombre_comercial: str | None = Field(default=None, max_length=200)
    tipo_cliente: str | None = Field(default=None, max_length=120)
    estado_comercial: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    servicios_interes: list[str] | None = Field(default=None, max_length=50)
    rutas_interes: list[str] | None = Field(default=None, max_length=100)
    tipos_carga: list[str] | None = Field(default=None, max_length=50)
    volumen_estimado: str | None = Field(default=None, max_length=120)
    frecuencia: str | None = Field(default=None, max_length=120)
    origen_cliente: str | None = Field(default=None, max_length=120)
    etiquetas: list[str] | None = Field(default=None, max_length=50)
    acepta_promociones: bool | None = None
    fecha_consentimiento: date | None = None
    medio_consentimiento: str | None = Field(default=None, max_length=120)

    _sin_null = sin_null("razon_social", "tipo_id", "ruc_o_id", "pais_id", "comercial_asignado_id", "activo")


class ContactoCrear(Entrada):
    nombre: str = Field(max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    principal: bool = False
    area: str | None = Field(default=None, max_length=120)
    recibe_promociones: bool = True
    recibe_cotizaciones: bool = True


class ContactoActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    principal: bool | None = None
    activo: bool | None = None
    area: str | None = Field(default=None, max_length=120)
    recibe_promociones: bool | None = None
    recibe_cotizaciones: bool | None = None

    _sin_null = sin_null("nombre", "principal", "activo")

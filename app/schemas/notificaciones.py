"""Schemas de E3: configuración de avisos, eventos y reglas, bitácora, centro de notificaciones y preferencias."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import Entrada, sin_null


class ConfigAvisosSalida(BaseModel):
    modo_externo: str
    aplicar_desde: str | None
    tope_semanal_cliente: int
    dias_habiles: str
    hora_desde: int
    hora_hasta: int
    ultima_evaluacion: str | None


class ConfigAvisosActualizar(Entrada):
    modo_externo: Literal["SIMULACION", "ACTIVO", "APAGADO"] | None = None
    aplicar_desde: date | None = None
    tope_semanal_cliente: int | None = Field(default=None, ge=0, le=100)
    dias_habiles: str | None = Field(default=None, max_length=20)
    hora_desde: int | None = Field(default=None, ge=0, le=23)
    hora_hasta: int | None = Field(default=None, ge=0, le=23)

    _sin_null = sin_null("modo_externo", "tope_semanal_cliente", "dias_habiles", "hora_desde", "hora_hasta")


class Destinatarios(BaseModel):
    tipos: list[str] = Field(default_factory=list, max_length=5)
    roles: list[str] = Field(default_factory=list, max_length=20)
    usuarios: list[int] = Field(default_factory=list, max_length=50)
    correos: list[str] = Field(default_factory=list, max_length=20)


class ReglaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evento: str
    nombre: str
    canal_correo: bool
    canal_interno: bool
    destinatarios: dict[str, Any]
    parametros: dict[str, Any]
    plantilla_id: int | None
    agrupacion: str
    obligatoria: bool
    activo: bool


class ReglaCrear(Entrada):
    evento: str = Field(max_length=40)
    nombre: str = Field(max_length=120)
    canal_correo: bool = True
    canal_interno: bool = False
    destinatarios: Destinatarios
    parametros: dict[str, Any] = Field(default_factory=dict)
    plantilla_id: int | None = None
    agrupacion: Literal["INDIVIDUAL", "RESUMEN"] = "INDIVIDUAL"
    obligatoria: bool = False
    activo: bool = True


class ReglaActualizar(Entrada):
    evento: str | None = Field(default=None, max_length=40)
    nombre: str | None = Field(default=None, max_length=120)
    canal_correo: bool | None = None
    canal_interno: bool | None = None
    destinatarios: Destinatarios | None = None
    parametros: dict[str, Any] | None = None
    plantilla_id: int | None = None
    agrupacion: Literal["INDIVIDUAL", "RESUMEN"] | None = None
    obligatoria: bool | None = None
    activo: bool | None = None

    _sin_null = sin_null("evento", "nombre", "canal_correo", "canal_interno", "destinatarios", "parametros",
                         "agrupacion", "obligatoria", "activo")


class EventoSalida(BaseModel):
    codigo: str
    nombre: str
    audiencia: str
    tipo: str
    descripcion: str
    variables: list[str]
    comercial: bool
    reglas: list[ReglaSalida]


class NotificacionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evento: str
    regla_id: int | None
    audiencia: str
    entidad_tipo: str
    entidad_id: str
    cliente_id: int | None
    comercial_id: int | None
    usuario_id: int | None
    email: str | None
    canal: str
    estado: str
    motivo_omision: str | None
    titulo: str
    mensaje: str
    enlace: str | None
    asunto: str | None
    programada_para: datetime
    intentos: int
    message_id: str | None
    ultimo_error: str | None
    leida_en: datetime | None
    enviado_en: datetime | None
    creado_en: datetime


class NotificacionDetalle(NotificacionSalida):
    contenido: str
    plantilla: str | None


class Preferencia(BaseModel):
    evento: str
    nombre: str
    descripcion: str
    obligatoria: bool
    correo: bool


class PreferenciasActualizar(Entrada):
    correo: dict[str, bool]


class AvisosInterruptor(Entrada):
    activos: bool


class AvisosContacto(Entrada):
    recibir: bool


class AvisosCotizacion(BaseModel):
    activos: bool
    cliente_activos: bool
    avisos: list[NotificacionSalida]


class ContactoAvisos(BaseModel):
    id: int
    nombre: str
    email: str | None
    recibir_avisos: bool


class AvisosCliente(BaseModel):
    activos: bool
    contactos: list[ContactoAvisos]

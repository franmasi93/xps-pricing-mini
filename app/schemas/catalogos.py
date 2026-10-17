"""Schemas de Incoterms, configuración y auditoría."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.comunes import Entrada, sin_null


class IncotermSalida(BaseModel):
    id: int  # F3: el cotizador lo envía como incoterm_id
    codigo: str
    nombre: str
    solo_maritimo: bool  # E0: derivado de los servicios permitidos (compatibilidad con F1–F5)
    servicios: list[str]  # E0: códigos de los servicios permitidos (incoterm_servicio)
    activo: bool
    recogida_origen: bool
    despacho_export: bool
    gastos_origen: bool
    flete_principal: bool
    seguro: bool
    gastos_destino: bool
    despacho_import: bool
    entrega_final: bool
    # Calculados en el service (bloques_incluidos): el frontend no calcula nada.
    bloques_importacion: list[str]
    bloques_exportacion: list[str]
    advertencia_importacion: str | None
    advertencia_exportacion: str | None
    actualizado_en: datetime


class IncotermActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=60)
    servicios: list[str] | None = Field(default=None, max_length=50)  # E0: reemplaza a solo_maritimo
    recogida_origen: bool | None = None
    despacho_export: bool | None = None
    gastos_origen: bool | None = None
    flete_principal: bool | None = None
    seguro: bool | None = None
    gastos_destino: bool | None = None
    despacho_import: bool | None = None
    entrega_final: bool | None = None
    activo: bool | None = None

    _sin_null = sin_null(
        "nombre",
        "servicios",
        "recogida_origen",
        "despacho_export",
        "gastos_origen",
        "flete_principal",
        "seguro",
        "gastos_destino",
        "despacho_import",
        "entrega_final",
        "activo",
    )


class ConfiguracionSalida(BaseModel):
    clave: str
    valor: str
    tipo: str
    permiso_edicion: str
    editable: bool
    actualizado_en: datetime


class ConfiguracionActualizar(Entrada):
    valor: str | int | float = Field(union_mode="left_to_right")


class AuditoriaItem(BaseModel):
    id: int
    fecha: datetime
    usuario_id: int | None
    usuario_nombre: str | None
    entidad: str
    entidad_id: str
    accion: str
    valores_antes: dict[str, Any] | None
    valores_despues: dict[str, Any] | None
    nota: str | None


class AuditoriaPagina(BaseModel):
    items: list[AuditoriaItem]
    total: int
    limit: int
    offset: int


class EmpresaDatos(Entrada):
    """A4 de F4: datos de la empresa para el PDF; todos admiten vacío (H-F4-8)."""

    empresa_departamento: str | None = Field(default=None, max_length=2000)
    empresa_ciudad: str | None = Field(default=None, max_length=2000)
    empresa_telefono: str | None = Field(default=None, max_length=2000)
    empresa_celular: str | None = Field(default=None, max_length=2000)
    empresa_whatsapp: str | None = Field(default=None, max_length=2000)
    empresa_horario: str | None = Field(default=None, max_length=2000)
    empresa_direccion_matriz: str | None = Field(default=None, max_length=2000)
    pago_banco: str | None = Field(default=None, max_length=2000)
    pago_titular: str | None = Field(default=None, max_length=2000)
    pago_tipo_cuenta: str | None = Field(default=None, max_length=2000)
    pago_numero_cuenta: str | None = Field(default=None, max_length=2000)
    pago_ruc: str | None = Field(default=None, max_length=2000)
    clausula_fundamental: str | None = Field(default=None, max_length=2000)
    texto_legal_pie: str | None = Field(default=None, max_length=2000)

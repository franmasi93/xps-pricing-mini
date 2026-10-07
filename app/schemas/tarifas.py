"""Schemas de M5: tipos de equipo, tarifas, tramos aéreos y recargos.

Gating de costos (D-F2-5): tres esquemas de salida por recurso, elegidos en el SERVICE.
- *Venta*: sin costo.ver. Las claves de costo no existen (no van en null).
- *Costo*: con costo.ver.
- *CostoMargen*: con costo.ver y margen.ver.
Los montos salen como texto (Decimal serializado), nunca como float.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null

Modo = Literal["AEREO", "LCL", "FCL"]
RateUnit = Literal["KG", "CBM", "WM", "CONTENEDOR", "ENVIO"]
MetodoVenta = Literal["MANUAL", "MARKUP", "MARGEN", "FIJO"]
Lado = Literal["ORIGEN", "DESTINO"]
BloqueRecargo = Literal[
    "RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN", "SEGURO", "GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL"
]
RolIngreso = Literal["PRINCIPAL", "AGENTE"]
EstadoVigencia = Literal["FUTURA", "VIGENTE", "POR_VENCER", "VENCIDA"]

# Claves que el comercial (sin costo.ver) nunca recibe (D-F2-5).
CLAVES_DE_COSTO = (
    "costo",
    "costo_kg",
    "minimo",
    "metodo_venta",
    "parametro_venta",
    "precio_venta_manual",
    "minimo_venta_manual",
    "margen_unitario",
    "margen_pct",
    "notas",
)


# ---------- Referencias ----------


class Referencia(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class PuertoRef(Referencia):
    codigo: str


class TipoEquipoRef(Referencia):
    codigo: str


# ---------- Tipos de equipo ----------


class TipoEquipoSalida(CatalogoSalida):
    codigo: str
    nombre: str


class TipoEquipoCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=80)


class TipoEquipoActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=20)
    nombre: str | None = Field(default=None, max_length=80)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "activo")


# ---------- Salidas de tarifa ----------


class TarifaVenta(BaseModel):
    id: int
    proveedor: Referencia
    modo: str
    origen: PuertoRef
    destino: PuertoRef
    tipo_equipo: TipoEquipoRef | None
    rate_unit: str
    moneda: str
    precio_venta: Decimal
    precio_venta_minimo: Decimal
    transit_time_dias: int | None
    dias_libres: int | None
    valido_desde: date
    valido_hasta: date
    estado_vigencia: EstadoVigencia
    tiene_tramos: bool
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


class TarifaCosto(TarifaVenta):
    costo: Decimal
    minimo: Decimal
    metodo_venta: str
    parametro_venta: Decimal | None
    precio_venta_manual: Decimal | None
    minimo_venta_manual: Decimal | None
    notas: str | None


class TarifaCostoMargen(TarifaCosto):
    margen_unitario: Decimal
    margen_pct: Decimal


# ---------- Salidas de tramo ----------


class TramoVenta(BaseModel):
    desde_kg: int
    precio_venta_kg: Decimal


class TramoCosto(TramoVenta):
    costo_kg: Decimal


class TramoCostoMargen(TramoCosto):
    margen_unitario: Decimal
    margen_pct: Decimal


# ---------- Salidas de recargo ----------


class RecargoVenta(BaseModel):
    id: int
    proveedor: Referencia | None
    puerto: PuertoRef
    lado: str
    bloque_incoterm: str
    concepto: str
    modo: str | None
    tipo_equipo: TipoEquipoRef | None
    rate_unit: str
    moneda: str
    precio_venta: Decimal
    precio_venta_minimo: Decimal
    aplica_iva: bool
    rol_ingreso: str
    valido_desde: date
    valido_hasta: date
    estado_vigencia: EstadoVigencia
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


class RecargoCosto(RecargoVenta):
    costo: Decimal
    minimo: Decimal
    metodo_venta: str
    parametro_venta: Decimal | None
    precio_venta_manual: Decimal | None
    minimo_venta_manual: Decimal | None


class RecargoCostoMargen(RecargoCosto):
    margen_unitario: Decimal
    margen_pct: Decimal


# ---------- Entradas ----------


class _VentaEntrada(Entrada):
    costo: Decimal
    moneda_id: int
    minimo: Decimal = Decimal("0")
    metodo_venta: MetodoVenta
    parametro_venta: Decimal | None = None
    precio_venta_manual: Decimal | None = None
    minimo_venta_manual: Decimal | None = None
    valido_desde: date
    valido_hasta: date


class TarifaCrear(_VentaEntrada):
    proveedor_id: int
    modo: Modo
    origen_puerto_id: int
    destino_puerto_id: int
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit
    transit_time_dias: int | None = Field(default=None, ge=0, le=3650)
    dias_libres: int | None = Field(default=None, ge=0, le=3650)
    notas: str | None = Field(default=None, max_length=5000)


class TarifaActualizar(Entrada):
    """PATCH parcial. Los campos opcionales del modelo aceptan null; los obligatorios no."""

    proveedor_id: int | None = None
    modo: Modo | None = None
    origen_puerto_id: int | None = None
    destino_puerto_id: int | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit | None = None
    costo: Decimal | None = None
    moneda_id: int | None = None
    minimo: Decimal | None = None
    metodo_venta: MetodoVenta | None = None
    parametro_venta: Decimal | None = None
    precio_venta_manual: Decimal | None = None
    minimo_venta_manual: Decimal | None = None
    transit_time_dias: int | None = Field(default=None, ge=0, le=3650)
    dias_libres: int | None = Field(default=None, ge=0, le=3650)
    notas: str | None = Field(default=None, max_length=5000)
    valido_desde: date | None = None
    valido_hasta: date | None = None
    activo: bool | None = None

    _sin_null = sin_null(
        "proveedor_id",
        "modo",
        "origen_puerto_id",
        "destino_puerto_id",
        "rate_unit",
        "costo",
        "moneda_id",
        "minimo",
        "metodo_venta",
        "valido_desde",
        "valido_hasta",
        "activo",
    )


class TarifaDuplicar(Entrada):
    valido_desde: date
    valido_hasta: date


class TramoEntrada(Entrada):
    desde_kg: int
    costo_kg: Decimal
    precio_venta_kg: Decimal | None = None


class TramosEntrada(Entrada):
    tramos: list[TramoEntrada] = Field(max_length=6)


class RecargoCrear(_VentaEntrada):
    proveedor_id: int | None = None
    puerto_id: int
    lado: Lado
    bloque_incoterm: BloqueRecargo
    concepto: str = Field(max_length=200)
    modo: Modo | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit
    # Obligatorios y sin valor por defecto: Pricing debe decidirlos en cada recargo.
    aplica_iva: bool
    rol_ingreso: RolIngreso


class RecargoActualizar(Entrada):
    proveedor_id: int | None = None
    puerto_id: int | None = None
    lado: Lado | None = None
    bloque_incoterm: BloqueRecargo | None = None
    concepto: str | None = Field(default=None, max_length=200)
    modo: Modo | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit | None = None
    costo: Decimal | None = None
    moneda_id: int | None = None
    minimo: Decimal | None = None
    metodo_venta: MetodoVenta | None = None
    parametro_venta: Decimal | None = None
    precio_venta_manual: Decimal | None = None
    minimo_venta_manual: Decimal | None = None
    aplica_iva: bool | None = None
    rol_ingreso: RolIngreso | None = None
    valido_desde: date | None = None
    valido_hasta: date | None = None
    activo: bool | None = None

    _sin_null = sin_null(
        "puerto_id",
        "lado",
        "bloque_incoterm",
        "concepto",
        "rate_unit",
        "costo",
        "moneda_id",
        "minimo",
        "metodo_venta",
        "aplica_iva",
        "rol_ingreso",
        "valido_desde",
        "valido_hasta",
        "activo",
    )

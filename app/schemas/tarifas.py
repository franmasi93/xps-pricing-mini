"""Schemas de M5: tipos de equipo, tarifas, tramos aéreos y recargos.

Gating de costos (D-F2-5): tres esquemas de salida por recurso, elegidos en el SERVICE.
- *Venta*: sin costo.ver. Las claves de costo no existen (no van en null).
- *Costo*: con costo.ver.
- *CostoMargen*: con costo.ver y margen.ver.
Los montos salen como texto (Decimal serializado), nunca como float.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null

# E0: el código de un servicio del catálogo (antes Literal["AEREO", "LCL", "FCL"]); lo valida el service.
Modo = Annotated[str, Field(min_length=2, max_length=10)]


def _numero(valor: Decimal) -> int | float:
    return int(valor) if valor == valor.to_integral_value() else float(valor.normalize())


# Un "desde" de tramo: decimal (un courier usa 0,5 kg) que sale como número (0, 45, 0.5), igual que antes.
Desde = Annotated[Decimal, PlainSerializer(_numero, return_type=int | float)]
RateUnit = Literal["KG", "CBM", "WM", "CONTENEDOR", "ENVIO"]
# D-F3-3: PCT_VALOR (seguro como % del valor) solo existe en los recargos; D3 de F4: PCT_RECIBO también.
RateUnitRecargo = Literal["KG", "CBM", "WM", "CONTENEDOR", "ENVIO", "PCT_VALOR", "PCT_RECIBO"]
UnidadPeso = Literal["KG", "LB"]
BloqueFiscal = Literal["RECIBO_CAJA", "FACTURA"]
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
    servicio_id: int


class TipoEquipoCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=80)
    servicio_id: int | None = None  # sin indicar: el primer servicio activo con tipo de equipo


class TipoEquipoActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=20)
    nombre: str | None = Field(default=None, max_length=80)
    servicio_id: int | None = None
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "servicio_id", "activo")


# ---------- Salidas de tarifa ----------


class TarifaVenta(BaseModel):
    id: int
    tipos_carga: list[str] = ["GENERAL"]
    clases_imo_excluidas: list[str] = []
    proveedor: Referencia
    modo: str
    origen: PuertoRef
    destino: PuertoRef
    tipo_equipo: TipoEquipoRef | None
    rate_unit: str
    unidad_peso: str
    transportista: str | None
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
    desde_kg: Desde
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
    puerto: PuertoRef | None  # D-R2: sin puerto si está vinculado a tarifas
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
    bloque_fiscal: str
    tarifas_vinculadas: list[dict] = []
    servicios_vinculados: list[str] = []
    alcance: dict[str, list] = {}  # D-A1: nivel → valores ("Todos" = sin la clave)
    aplica_a: str = ""
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
    # D-T4: tipos de carga que acepta (por defecto solo GENERAL) y clases IMO excluidas.
    tipos_carga: list[str] = Field(default_factory=lambda: ["GENERAL"], max_length=20)
    clases_imo_excluidas: list[str] = Field(default_factory=list, max_length=9)
    proveedor_id: int
    modo: Modo
    origen_puerto_id: int
    destino_puerto_id: int
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit
    unidad_peso: UnidadPeso = "KG"
    transportista: str | None = Field(default=None, max_length=200)
    transit_time_dias: int | None = Field(default=None, ge=0, le=3650)
    dias_libres: int | None = Field(default=None, ge=0, le=3650)
    notas: str | None = Field(default=None, max_length=5000)


class TarifaActualizar(Entrada):
    """PATCH parcial. Los campos opcionales del modelo aceptan null; los obligatorios no."""

    tipos_carga: list[str] | None = Field(default=None, max_length=20)  # D-T4
    clases_imo_excluidas: list[str] | None = Field(default=None, max_length=9)

    proveedor_id: int | None = None
    modo: Modo | None = None
    origen_puerto_id: int | None = None
    destino_puerto_id: int | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnit | None = None
    unidad_peso: UnidadPeso | None = None
    transportista: str | None = Field(default=None, max_length=200)
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
        "unidad_peso",
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
    copiar_vinculos: bool = True  # D-R2: los recargos vinculados a la tarifa original también se vinculan a la copia


class TramoEntrada(Entrada):
    desde_kg: Decimal
    costo_kg: Decimal
    precio_venta_kg: Decimal | None = None


class TramosEntrada(Entrada):
    tramos: list[TramoEntrada] = Field(max_length=50)


class RecargoCrear(_VentaEntrada):
    proveedor_id: int | None = None
    puerto_id: int | None = None  # D-R2: opcional si se vincula a tarifas
    lado: Lado
    bloque_incoterm: BloqueRecargo
    concepto: str = Field(max_length=200)
    modo: Modo | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnitRecargo
    # Obligatorios y sin valor por defecto: Pricing debe decidirlos en cada recargo.
    aplica_iva: bool
    rol_ingreso: RolIngreso
    # D-R3: Recibo de Caja o Factura (sin indicarlo y con puerto: la regla por país de antes).
    bloque_fiscal: BloqueFiscal | None = None
    tarifas_ids: list[int] = Field(default=[], max_length=200)
    servicios: list[str] = Field(default=[], max_length=20)
    alcance: dict[str, list] | None = None  # D-A1: {"puertos": [..], "paises": [..], "regiones": [..], …}


class RecargoActualizar(Entrada):
    proveedor_id: int | None = None
    puerto_id: int | None = None
    lado: Lado | None = None
    bloque_incoterm: BloqueRecargo | None = None
    concepto: str | None = Field(default=None, max_length=200)
    modo: Modo | None = None
    tipo_equipo_id: int | None = None
    rate_unit: RateUnitRecargo | None = None
    costo: Decimal | None = None
    moneda_id: int | None = None
    minimo: Decimal | None = None
    metodo_venta: MetodoVenta | None = None
    parametro_venta: Decimal | None = None
    precio_venta_manual: Decimal | None = None
    minimo_venta_manual: Decimal | None = None
    aplica_iva: bool | None = None
    rol_ingreso: RolIngreso | None = None
    bloque_fiscal: BloqueFiscal | None = None
    tarifas_ids: list[int] | None = Field(default=None, max_length=200)
    servicios: list[str] | None = Field(default=None, max_length=20)
    alcance: dict[str, list] | None = None
    valido_desde: date | None = None
    valido_hasta: date | None = None
    activo: bool | None = None

    _sin_null = sin_null(
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

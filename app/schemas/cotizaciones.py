"""M7 Cotizaciones: esquemas de entrada.

La salida la arma el service como diccionario (gating de costos D-F2-5 y H10: las claves de costo y
margen se omiten, no van en null), igual que en tarifas.
"""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.comunes import Entrada, sin_null

Sentido = Literal["IMPORTACION", "EXPORTACION"]
Modo = Literal["AEREO", "LCL", "FCL"]
UnidadPeso = Literal["KG", "LB"]
MotivoRechazo = Literal["PRECIO", "TIEMPO", "COMPETENCIA", "OTRO"]


class BultoEntrada(Entrada):
    """Medidas en cm (unidad KG) o en pulgadas (unidad LB, D2); el service exige las de la unidad elegida."""

    cantidad: int = Field(ge=1, le=10000)
    largo_cm: Decimal | None = Field(default=None, gt=0, le=10000)
    ancho_cm: Decimal | None = Field(default=None, gt=0, le=10000)
    alto_cm: Decimal | None = Field(default=None, gt=0, le=10000)
    largo_in: Decimal | None = Field(default=None, gt=0, le=4000)
    ancho_in: Decimal | None = Field(default=None, gt=0, le=4000)
    alto_in: Decimal | None = Field(default=None, gt=0, le=4000)


class ContenedorEntrada(Entrada):
    tipo_equipo_id: int
    cantidad: int = Field(ge=1, le=999)


class CotizacionCrear(Entrada):
    cliente_id: int
    contacto_id: int | None = None
    sentido: Sentido
    incoterm_id: int
    modo: Modo
    origen_puerto_id: int
    destino_puerto_id: int
    proveedor_recargos_id: int | None = None
    unidad_peso: UnidadPeso = "KG"
    peso_kg: Decimal = Decimal("0")
    peso_lb: Decimal | None = None
    cbm: Decimal | None = None
    bultos: int | None = Field(default=None, ge=0, le=100000)
    dimensiones: list[BultoEntrada] | None = Field(default=None, max_length=50)
    valor_mercancia_usd: Decimal | None = None
    contenedores: list[ContenedorEntrada] = Field(default_factory=list, max_length=5)
    notas_cliente: str | None = Field(default=None, max_length=2000)
    notas_internas: str | None = Field(default=None, max_length=2000)
    transportista: str | None = Field(default=None, max_length=200)
    descripcion_carga: str | None = Field(default=None, max_length=2000)


class CotizacionActualizar(Entrada):
    cliente_id: int | None = None
    contacto_id: int | None = None
    sentido: Sentido | None = None
    incoterm_id: int | None = None
    modo: Modo | None = None
    origen_puerto_id: int | None = None
    destino_puerto_id: int | None = None
    proveedor_recargos_id: int | None = None
    unidad_peso: UnidadPeso | None = None
    peso_kg: Decimal | None = None
    peso_lb: Decimal | None = None
    cbm: Decimal | None = None
    bultos: int | None = Field(default=None, ge=0, le=100000)
    dimensiones: list[BultoEntrada] | None = Field(default=None, max_length=50)
    valor_mercancia_usd: Decimal | None = None
    contenedores: list[ContenedorEntrada] | None = Field(default=None, max_length=5)
    notas_cliente: str | None = Field(default=None, max_length=2000)
    notas_internas: str | None = Field(default=None, max_length=2000)
    transportista: str | None = Field(default=None, max_length=200)
    descripcion_carga: str | None = Field(default=None, max_length=2000)
    # D-F3-10: si el cambio borra líneas con ajuste manual, hay que confirmarlo.
    confirmar: bool = False

    _sin_null = sin_null(
        "cliente_id", "sentido", "incoterm_id", "modo", "origen_puerto_id", "destino_puerto_id", "peso_kg", "unidad_peso"
    )


class ProponerEntrada(Entrada):
    # Clave: tipo_equipo_id (FCL) o el modo ("AEREO" / "LCL"); valor: tarifa_id elegida.
    tarifas: dict[str, int] = Field(default_factory=dict, max_length=5)
    proveedor_id: int | None = None
    confirmar: bool = False


class LineaActualizar(Entrada):
    precio_venta_unit_usd: Decimal | None = None
    motivo: str | None = Field(default=None, max_length=300)
    incluida: bool | None = None
    quitar_ajuste: bool | None = None


class EmitirEntrada(Entrada):
    valida_hasta: date | None = None


class EstadoEntrada(Entrada):
    estado: str = Field(max_length=20)
    motivo_rechazo: MotivoRechazo | None = None
    detalle_rechazo: str | None = Field(default=None, max_length=1000)


class EnviarEntrada(Entrada):
    # B6: solo contactos activos del MISMO cliente (máximo 5); nunca correos escritos a mano.
    cc_contacto_ids: list[int] = Field(default_factory=list, max_length=5)

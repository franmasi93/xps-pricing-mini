"""M7 Cotizaciones: contador anual, cotización, contenedores y líneas. Tablas creadas por la migración 0004.

Los CHECK viven en la migración (escrita a mano); aquí solo el mapeo.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Integer, Numeric, SmallInteger, String, Text, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.clientes import Cliente, ContactoCliente
from app.models.geografia import Puerto
from app.models.incoterms import Incoterm
from app.models.monedas import Moneda
from app.models.proveedores import Proveedor
from app.models.seguridad import Usuario
from app.models.tarifas import Recargo, Tarifa, TipoEquipo

ESTADOS = ("BORRADOR", "EMITIDA", "ENVIADA", "ACEPTADA", "RECHAZADA")
MOTIVOS_RECHAZO = ("PRECIO", "TIEMPO", "COMPETENCIA", "OTRO")
BLOQUES_LINEA = (
    "RECOGIDA_ORIGEN",
    "DESPACHO_EXPORT",
    "GASTOS_ORIGEN",
    "FLETE_PRINCIPAL",
    "SEGURO",
    "GASTOS_DESTINO",
    "DESPACHO_IMPORT",
    "ENTREGA_FINAL",
)


class ContadorCotizacion(Base):
    __tablename__ = "contador_cotizacion"

    anio: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ultimo: Mapped[int] = mapped_column(Integer, default=0)


class Cotizacion(CatalogoMixin, Base):
    __tablename__ = "cotizacion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    numero: Mapped[str | None] = mapped_column(String(20), unique=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id", ondelete="RESTRICT"))
    contacto_id: Mapped[int | None] = mapped_column(ForeignKey("contacto_cliente.id", ondelete="RESTRICT"))
    comercial_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    sentido: Mapped[str] = mapped_column(String(11))
    incoterm_id: Mapped[int] = mapped_column(ForeignKey("incoterm.id", ondelete="RESTRICT"))
    modo: Mapped[str] = mapped_column(String(5))
    origen_puerto_id: Mapped[int] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    destino_puerto_id: Mapped[int] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    proveedor_recargos_id: Mapped[int | None] = mapped_column(ForeignKey("proveedor.id", ondelete="RESTRICT"))
    peso_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0"))
    cbm: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    bultos: Mapped[int | None]
    dimensiones: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    valor_mercancia_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(9), default="BORRADOR")
    fecha_emision: Mapped[date | None] = mapped_column(Date)
    valida_hasta: Mapped[date | None] = mapped_column(Date)
    moneda_cotizacion: Mapped[str] = mapped_column(String(3), default="USD")
    notas_cliente: Mapped[str | None] = mapped_column(Text)
    notas_internas: Mapped[str | None] = mapped_column(Text)
    subtotal_recibo_caja: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    subtotal_factura: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    iva: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_general: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    costo_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    margen_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    margen_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    iva_tasa_aplicada: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    snapshot_emision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(11))
    detalle_rechazo: Mapped[str | None] = mapped_column(Text)
    cotizacion_origen_id: Mapped[int | None] = mapped_column(ForeignKey("cotizacion.id", ondelete="RESTRICT"))
    transportista: Mapped[str | None] = mapped_column(Text)
    descripcion_carga: Mapped[str | None] = mapped_column(Text)
    unidad_peso: Mapped[str] = mapped_column(String(2), default="KG", server_default="KG")
    peso_lb: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))

    cliente: Mapped[Cliente] = relationship()
    contacto: Mapped[ContactoCliente | None] = relationship()
    comercial: Mapped[Usuario] = relationship(foreign_keys=[comercial_id])
    incoterm: Mapped[Incoterm] = relationship()
    origen: Mapped[Puerto] = relationship(foreign_keys=[origen_puerto_id])
    destino: Mapped[Puerto] = relationship(foreign_keys=[destino_puerto_id])
    proveedor_recargos: Mapped[Proveedor | None] = relationship()
    contenedores: Mapped[list["CotizacionContenedor"]] = relationship(
        order_by="CotizacionContenedor.id", cascade="all, delete-orphan"
    )
    lineas: Mapped[list["LineaCotizacion"]] = relationship(
        order_by="LineaCotizacion.orden", cascade="all, delete-orphan"
    )


class CotizacionContenedor(Base):
    __tablename__ = "cotizacion_contenedor"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizacion.id", ondelete="CASCADE"))
    tipo_equipo_id: Mapped[int] = mapped_column(ForeignKey("tipo_equipo.id", ondelete="RESTRICT"))
    cantidad: Mapped[int]

    tipo_equipo: Mapped[TipoEquipo] = relationship()


class LineaCotizacion(Base):
    __tablename__ = "linea_cotizacion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizacion.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(SmallInteger)
    concepto: Mapped[str] = mapped_column(String(160))
    bloque_incoterm: Mapped[str] = mapped_column(String(20))
    tarifa_id: Mapped[int | None] = mapped_column(ForeignKey("tarifa.id", ondelete="RESTRICT"))
    recargo_id: Mapped[int | None] = mapped_column(ForeignKey("recargo.id", ondelete="RESTRICT"))
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedor.id", ondelete="RESTRICT"))
    tipo_equipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_equipo.id", ondelete="RESTRICT"))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    rate_unit: Mapped[str] = mapped_column(String(10))
    costo_unit_original: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    minimo_original: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    moneda_original_id: Mapped[int] = mapped_column(ForeignKey("moneda.id", ondelete="RESTRICT"))
    tasa_aplicada: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    precio_venta_unit_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    minimo_venta_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    subtotal_venta_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    precio_calculado_unit_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    bloque_fiscal: Mapped[str] = mapped_column(String(11))
    aplica_iva: Mapped[bool]
    rol_ingreso: Mapped[str] = mapped_column(String(9))
    opcional: Mapped[bool] = mapped_column(default=False)
    incluida: Mapped[bool] = mapped_column(default=True, server_default=true())
    ajuste_manual: Mapped[bool] = mapped_column(default=False)
    motivo_ajuste: Mapped[str | None] = mapped_column(String(300))
    valido_hasta_origen: Mapped[date] = mapped_column(Date)
    unidad_peso: Mapped[str | None] = mapped_column(String(2))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tarifa: Mapped[Tarifa | None] = relationship()
    recargo: Mapped[Recargo | None] = relationship()
    proveedor: Mapped[Proveedor | None] = relationship()
    tipo_equipo: Mapped[TipoEquipo | None] = relationship()
    moneda_original: Mapped[Moneda] = relationship()

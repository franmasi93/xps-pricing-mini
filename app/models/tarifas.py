"""M5 Tarifas: tipos de equipo, tarifas, tramos aéreos y recargos. Tablas creadas por la migración 0003.

Los CHECK y las exclusiones de vigencia viven en la migración (escrita a mano); aquí solo el mapeo.
E0 (0007): "modo" es el código del servicio (FK a servicio.codigo); los tramos permitidos salen de servicio_tramo.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Numeric, SmallInteger, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.geografia import Puerto
from app.models.monedas import Moneda
from app.models.proveedores import Proveedor
from app.models.servicios import Servicio


def _servicio_por_defecto(contexto) -> int | None:
    """Sin servicio indicado: el primer servicio activo que usa tipo de equipo (por orden)."""
    return contexto.connection.scalar(
        select(Servicio.id)
        .where(Servicio.usa_tipo_equipo.is_(True), Servicio.activo.is_(True))
        .order_by(Servicio.orden, Servicio.id)
        .limit(1)
    )


class TipoEquipo(CatalogoMixin, Base):
    __tablename__ = "tipo_equipo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    servicio_id: Mapped[int] = mapped_column(
        ForeignKey("servicio.id", ondelete="RESTRICT"), index=True, default=_servicio_por_defecto
    )

    servicio: Mapped[Servicio] = relationship()


class VentaMixin:
    """Costo, mínimo, esquema de venta y vigencia (§7 M5, D-F2-3): comunes a tarifa y recargo."""

    costo: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    moneda_id: Mapped[int] = mapped_column(ForeignKey("moneda.id", ondelete="RESTRICT"))
    minimo: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    metodo_venta: Mapped[str] = mapped_column(String(7))
    parametro_venta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    precio_venta_manual: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    minimo_venta_manual: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    valido_desde: Mapped[date] = mapped_column(Date)
    valido_hasta: Mapped[date] = mapped_column(Date)


class Tarifa(VentaMixin, CatalogoMixin, Base):
    __tablename__ = "tarifa"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedor.id", ondelete="RESTRICT"))
    modo: Mapped[str] = mapped_column(ForeignKey("servicio.codigo", ondelete="RESTRICT"))
    origen_puerto_id: Mapped[int] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    destino_puerto_id: Mapped[int] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    tipo_equipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_equipo.id", ondelete="RESTRICT"))
    rate_unit: Mapped[str] = mapped_column(String(10))
    transit_time_dias: Mapped[int | None] = mapped_column(SmallInteger)
    dias_libres: Mapped[int | None] = mapped_column(SmallInteger)
    notas: Mapped[str | None] = mapped_column(Text)
    transportista: Mapped[str | None] = mapped_column(Text)
    unidad_peso: Mapped[str] = mapped_column(String(2), default="KG", server_default="KG")

    proveedor: Mapped[Proveedor] = relationship()
    moneda: Mapped[Moneda] = relationship()
    origen: Mapped[Puerto] = relationship(foreign_keys=[origen_puerto_id])
    destino: Mapped[Puerto] = relationship(foreign_keys=[destino_puerto_id])
    tipo_equipo: Mapped[TipoEquipo | None] = relationship()
    servicio: Mapped[Servicio] = relationship(foreign_keys=[modo], viewonly=True)
    tramos: Mapped[list["TramoAereo"]] = relationship(order_by="TramoAereo.desde_kg")


class TramoAereo(Base):
    __tablename__ = "tramo_aereo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    tarifa_id: Mapped[int] = mapped_column(ForeignKey("tarifa.id", ondelete="RESTRICT"))
    desde_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3))  # en lb si la tarifa es por libra (H-F4-2)
    costo_kg: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    precio_venta_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recargo(VentaMixin, CatalogoMixin, Base):
    __tablename__ = "recargo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedor.id", ondelete="RESTRICT"))
    puerto_id: Mapped[int] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    lado: Mapped[str] = mapped_column(String(7))
    bloque_incoterm: Mapped[str] = mapped_column(String(20))
    concepto: Mapped[str] = mapped_column(String(120))
    modo: Mapped[str | None] = mapped_column(ForeignKey("servicio.codigo", ondelete="RESTRICT"))
    tipo_equipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_equipo.id", ondelete="RESTRICT"))
    rate_unit: Mapped[str] = mapped_column(String(10))
    aplica_iva: Mapped[bool]
    rol_ingreso: Mapped[str] = mapped_column(String(9))

    proveedor: Mapped[Proveedor | None] = relationship()
    moneda: Mapped[Moneda] = relationship()
    puerto: Mapped[Puerto] = relationship()
    tipo_equipo: Mapped[TipoEquipo | None] = relationship()
    servicio: Mapped[Servicio | None] = relationship(foreign_keys=[modo], viewonly=True)

"""M5 Tarifas: tipos de equipo, tarifas, tramos aéreos y recargos. Tablas creadas por la migración 0003.

Los CHECK y las exclusiones de vigencia viven en la migración (escrita a mano); aquí solo el mapeo.
E0 (0007): "modo" es el código del servicio (FK a servicio.codigo); los tramos permitidos salen de servicio_tramo.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Identity, Numeric, SmallInteger, String, Text, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
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
    # D-T4 (0016): tipos de carga que acepta (por defecto solo GENERAL) y clases IMO excluidas.
    tipos_carga: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["GENERAL"])
    clases_imo_excluidas: Mapped[list[str]] = mapped_column(JSONB, default=list)
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
    # D-R2 (0015): opcional si el recargo está vinculado a tarifas (toma el puerto de la tarifa según su lado).
    puerto_id: Mapped[int | None] = mapped_column(ForeignKey("puerto.id", ondelete="RESTRICT"))
    lado: Mapped[str] = mapped_column(String(7))
    bloque_incoterm: Mapped[str] = mapped_column(String(20))
    concepto: Mapped[str] = mapped_column(String(120))
    modo: Mapped[str | None] = mapped_column(ForeignKey("servicio.codigo", ondelete="RESTRICT"))
    tipo_equipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_equipo.id", ondelete="RESTRICT"))
    rate_unit: Mapped[str] = mapped_column(String(10))
    aplica_iva: Mapped[bool]
    rol_ingreso: Mapped[str] = mapped_column(String(9))
    # D-R3 (0015): RECIBO_CAJA o FACTURA, elegido en el recargo (reemplaza la regla por país del puerto).
    bloque_fiscal: Mapped[str] = mapped_column(String(11))
    # D-A1 (0016): huella del alcance cuando no es el equivalente a las columnas (vacía en los recargos de antes);
    # entra en la exclusión de superposición para que alcances distintos del mismo concepto no choquen.
    alcance_firma: Mapped[str] = mapped_column(String(32), default="", server_default="")

    proveedor: Mapped[Proveedor | None] = relationship()
    moneda: Mapped[Moneda] = relationship()
    puerto: Mapped[Puerto | None] = relationship()
    vinculos_tarifa: Mapped[list["RecargoTarifa"]] = relationship(
        back_populates="recargo", cascade="all, delete-orphan", order_by="RecargoTarifa.tarifa_id"
    )
    # D-A1 (0016): alcance en cadena (un nivel sin filas = "Todos").
    alcance: Mapped[list["RecargoAlcance"]] = relationship(
        back_populates="recargo", cascade="all, delete-orphan", order_by="RecargoAlcance.id"
    )
    tipo_equipo: Mapped[TipoEquipo | None] = relationship()
    servicio: Mapped[Servicio | None] = relationship(foreign_keys=[modo], viewonly=True)


class RecargoTarifa(Base):
    """D-R2: un recargo vinculado a una tarifa sale primero al elegir esa tarifa en el cotizador."""

    __tablename__ = "recargo_tarifa"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    recargo_id: Mapped[int] = mapped_column(ForeignKey("recargo.id", ondelete="CASCADE"))
    tarifa_id: Mapped[int] = mapped_column(ForeignKey("tarifa.id", ondelete="CASCADE"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    recargo: Mapped[Recargo] = relationship(back_populates="vinculos_tarifa")
    tarifa: Mapped[Tarifa] = relationship()


class RecargoAlcance(Base):
    """D-A1 (0016): un valor de un nivel del alcance del recargo (servicio, modo, tipo de equipo, región, país,
    puerto, ruta, proveedor, tipo de carga o clase IMO). Los niveles por texto guardan el código."""

    __tablename__ = "recargo_alcance"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    recargo_id: Mapped[int] = mapped_column(ForeignKey("recargo.id", ondelete="CASCADE"))
    nivel: Mapped[str] = mapped_column(String(16))
    valor_id: Mapped[int | None]
    valor_texto: Mapped[str | None] = mapped_column(String(20))

    recargo: Mapped[Recargo] = relationship(back_populates="alcance")


class TipoCarga(CatalogoMixin, Base):
    """D-T2 (0016): atributo de la carga (IMO, refrigerada, OOG…), combinable con cualquier servicio."""

    __tablename__ = "tipo_carga"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    pide_imo: Mapped[bool] = mapped_column(default=False)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)


@event.listens_for(Recargo, "before_insert")
def _bloque_fiscal_por_defecto(mapper, connection, recargo: Recargo) -> None:
    """D-R3: un recargo insertado sin bloque fiscal (scripts y bancos de prueba) toma la regla de antes, la misma de la
    migración 0015: seguro → Recibo de Caja; puerto de Ecuador → Factura; exterior → Recibo de Caja. El service
    siempre lo envía explícito."""
    if recargo.bloque_fiscal is not None:
        return
    if recargo.bloque_incoterm == "SEGURO" or recargo.puerto_id is None:
        recargo.bloque_fiscal = "RECIBO_CAJA"
        return
    from app.models.geografia import Pais

    iso2 = connection.execute(select(Pais.iso2).join(Puerto, Puerto.pais_id == Pais.id).where(Puerto.id == recargo.puerto_id)).scalar()
    recargo.bloque_fiscal = "FACTURA" if iso2 == "EC" else "RECIBO_CAJA"


@event.listens_for(Recargo, "after_insert")
def _alcance_por_defecto(mapper, connection, recargo: Recargo) -> None:
    """D-A1: un recargo insertado sin alcance (scripts y bancos de prueba) recibe el equivalente a sus columnas, como
    en la migración 0016: su puerto → PUERTO, su servicio → SERVICIO, su tipo de equipo → TIPO_EQUIPO, su proveedor →
    PROVEEDOR. El service siempre lo arma explícito antes de insertar."""
    if recargo.alcance:
        return
    filas = []
    for nivel, valor in (("PUERTO", recargo.puerto_id), ("TIPO_EQUIPO", recargo.tipo_equipo_id),
                         ("PROVEEDOR", recargo.proveedor_id)):
        if valor is not None:
            filas.append({"recargo_id": recargo.id, "nivel": nivel, "valor_id": valor, "valor_texto": None})
    if recargo.modo is not None:
        filas.append({"recargo_id": recargo.id, "nivel": "SERVICIO", "valor_id": None, "valor_texto": recargo.modo})
    if filas:
        connection.execute(RecargoAlcance.__table__.insert(), filas)

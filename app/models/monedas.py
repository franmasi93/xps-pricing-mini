"""M3 Monedas y tasas de cambio (NIC 21). Tablas creadas por la migración 0002."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Identity, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin

MONEDA_BASE = "USD"


class Moneda(CatalogoMixin, Base):
    __tablename__ = "moneda"
    __table_args__ = (CheckConstraint("codigo ~ '^[A-Z]{3}$'", name="codigo_formato"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(3), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    simbolo: Mapped[str] = mapped_column(String(8))


class TasaCambio(Base):
    __tablename__ = "tasa_cambio"
    __table_args__ = (
        UniqueConstraint("moneda_id", "fecha_vigencia", name="uq_tasa_cambio_moneda_fecha"),
        CheckConstraint("tasa_a_usd > 0", name="tasa_positiva"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    moneda_id: Mapped[int] = mapped_column(ForeignKey("moneda.id", ondelete="RESTRICT"))
    # Cuántos USD vale 1 unidad de la moneda (EUR ≈ 1.08; CNY ≈ 0.14).
    tasa_a_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    fecha_vigencia: Mapped[date] = mapped_column(Date)
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    moneda: Mapped[Moneda] = relationship()

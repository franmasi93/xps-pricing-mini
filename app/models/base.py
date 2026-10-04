"""Base declarativa con convención de nombres de constraints (pk_, fk_, uq_, ck_, ix_)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONVENCION_NOMBRES = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


class CatalogoMixin:
    """Columnas comunes de los catálogos: borrado lógico y trazabilidad de creación."""

    activo: Mapped[bool] = mapped_column(default=True, server_default=true())
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

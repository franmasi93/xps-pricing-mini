"""M2 Geografía: Region → Pais → Puerto. Tablas creadas por la migración 0002.

E0 (0007): el tipo del puerto es un catálogo editable (tipo_ubicacion) con su regla de código.
"""
from sqlalchemy import CheckConstraint, ForeignKey, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin


class TipoUbicacion(CatalogoMixin, Base):
    """Puerto marítimo, aeropuerto, terminal terrestre… El código del puerto se valida con su regex (si tiene)."""

    __tablename__ = "tipo_ubicacion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    regex_codigo: Mapped[str | None] = mapped_column(Text)
    ayuda_codigo: Mapped[str | None] = mapped_column(String(200))
    prefijo_pais: Mapped[bool] = mapped_column(default=False)


class Region(CatalogoMixin, Base):
    __tablename__ = "region"
    __table_args__ = (CheckConstraint("codigo ~ '^[A-Z0-9_]{2,20}$'", name="codigo_formato"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))


class Pais(CatalogoMixin, Base):
    __tablename__ = "pais"
    __table_args__ = (CheckConstraint("iso2 ~ '^[A-Z]{2}$'", name="iso2_formato"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    iso2: Mapped[str] = mapped_column(String(2), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    region_id: Mapped[int] = mapped_column(ForeignKey("region.id", ondelete="RESTRICT"), index=True)

    region: Mapped[Region] = relationship()


class Puerto(CatalogoMixin, Base):
    __tablename__ = "puerto"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(ForeignKey("tipo_ubicacion.codigo", ondelete="RESTRICT"), index=True)

    pais: Mapped[Pais] = relationship()
    tipo_ubicacion: Mapped[TipoUbicacion] = relationship(viewonly=True)

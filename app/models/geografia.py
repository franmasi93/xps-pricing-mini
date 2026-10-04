"""M2 Geografía: Region → Pais → Puerto. Tablas creadas por la migración 0002."""
from sqlalchemy import CheckConstraint, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin

TIPOS_PUERTO = ("MARITIMO", "AEREO")


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
    __table_args__ = (
        CheckConstraint("tipo IN ('MARITIMO', 'AEREO')", name="tipo"),
        CheckConstraint(
            "(tipo = 'MARITIMO' AND codigo ~ '^[A-Z]{2}[A-Z0-9]{3}$') OR (tipo = 'AEREO' AND codigo ~ '^[A-Z]{3}$')",
            name="codigo_formato",
        ),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(5), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(String(10), index=True)

    pais: Mapped[Pais] = relationship()

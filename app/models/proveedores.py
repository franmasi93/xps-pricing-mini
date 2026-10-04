"""M4 Proveedores (agentes). Tabla creada por la migración 0002."""
from sqlalchemy import CheckConstraint, ForeignKey, Identity, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.geografia import Pais


class Proveedor(CatalogoMixin, Base):
    __tablename__ = "proveedor"
    __table_args__ = (
        Index("uq_proveedor_nombre_lower", func.lower(text("nombre")), unique=True),
        CheckConstraint("email IS NULL OR email = lower(email)", name="email_minusculas"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id", ondelete="RESTRICT"), index=True)
    contacto: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    telefono: Mapped[str | None] = mapped_column(String(40))
    notas: Mapped[str | None] = mapped_column(Text)

    pais: Mapped[Pais] = relationship()

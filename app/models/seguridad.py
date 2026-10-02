"""M1 Seguridad: Rol, Permiso, RolPermiso y Usuario.

Las tablas las crea la migración 0001 (escrita a mano); estos modelos reflejan
los mismos nombres de constraints.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Table,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

rol_permiso = Table(
    "rol_permiso",
    Base.metadata,
    Column("rol_id", Integer, ForeignKey("rol.id", ondelete="RESTRICT"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permiso.id", ondelete="RESTRICT"), primary_key=True),
)


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))

    permisos: Mapped[list["Permiso"]] = relationship(secondary=rol_permiso, order_by="Permiso.codigo")


class Permiso(Base):
    __tablename__ = "permiso"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str] = mapped_column(String(200))


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        Index("uq_usuario_email_lower", func.lower(text("email")), unique=True),
        CheckConstraint("email = lower(email)", name="email_minusculas"),
        CheckConstraint("token_version >= 0", name="token_version_no_negativo"),
        CheckConstraint("intentos_fallidos >= 0", name="intentos_fallidos_no_negativo"),
    )

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    nombre: Mapped[str] = mapped_column(String(120))
    hash_password: Mapped[str] = mapped_column(String(255))
    rol_id: Mapped[int] = mapped_column(ForeignKey("rol.id"), index=True)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())
    forzar_cambio_password: Mapped[bool] = mapped_column(default=False, server_default=false())
    token_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    intentos_fallidos: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    rol: Mapped[Rol] = relationship()

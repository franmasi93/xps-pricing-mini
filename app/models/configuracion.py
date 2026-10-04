"""Configuración editable por pantalla (§5.2) y auditoría de cambios (D-F1-4). Migración 0002."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

TIPOS_CONFIG = ("DECIMAL", "ENTERO", "TEXTO")
ACCIONES_AUDITORIA = ("CREAR", "EDITAR", "DESACTIVAR")


class Configuracion(Base):
    __tablename__ = "configuracion"
    __table_args__ = (CheckConstraint("tipo IN ('DECIMAL', 'ENTERO', 'TEXTO')", name="tipo"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    clave: Mapped[str] = mapped_column(String(60), unique=True)
    valor: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(10))
    permiso_edicion: Mapped[str] = mapped_column(
        String(50), ForeignKey("permiso.codigo", name="fk_configuracion_permiso_edicion_permiso")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class Auditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = (
        CheckConstraint("accion IN ('CREAR', 'EDITAR', 'DESACTIVAR')", name="accion"),
        Index("ix_auditoria_entidad_entidad_id", "entidad", "entidad_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[str] = mapped_column(String(40))
    accion: Mapped[str] = mapped_column(String(12))
    valores_antes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valores_despues: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    nota: Mapped[str | None] = mapped_column(String(300))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

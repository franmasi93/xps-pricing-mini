"""E3 Notificaciones y avisos: configuración, reglas, notificaciones (outbox y bitácora) y preferencias. Migración 0010.

Los eventos no son una tabla: viven en el código (services/eventos.py), porque los dispara el sistema.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Identity, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.boletines import PlantillaCorreo

MODOS_EXTERNOS = ("SIMULACION", "ACTIVO", "APAGADO")
ESTADOS_NOTIFICACION = ("PENDIENTE", "ENVIADO", "SIMULADO", "FALLIDO", "CANCELADO", "OMITIDO")


class ConfigAvisos(Base):
    """Una sola fila (id = 1): interruptor global de avisos externos, "aplicar desde", tope semanal y horario hábil."""

    __tablename__ = "config_avisos"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    modo_externo: Mapped[str] = mapped_column(String(10), default="SIMULACION")
    aplicar_desde: Mapped[date | None] = mapped_column(Date)
    tope_semanal_cliente: Mapped[int] = mapped_column(SmallInteger, default=3)
    dias_habiles: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5")
    hora_desde: Mapped[int] = mapped_column(SmallInteger, default=8)
    hora_hasta: Mapped[int] = mapped_column(SmallInteger, default=18)
    ultima_evaluacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class ReglaNotificacion(CatalogoMixin, Base):
    __tablename__ = "regla_notificacion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    evento: Mapped[str] = mapped_column(String(40), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    canal_correo: Mapped[bool] = mapped_column(default=True)
    canal_interno: Mapped[bool] = mapped_column(default=False)
    destinatarios: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    parametros: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantilla_correo.id", ondelete="RESTRICT"))
    agrupacion: Mapped[str] = mapped_column(String(10), default="INDIVIDUAL")
    obligatoria: Mapped[bool] = mapped_column(default=False)

    plantilla: Mapped[PlantillaCorreo | None] = relationship()


class Notificacion(Base):
    """Una notificación por destinatario y canal. clave_idempotencia = regla + entidad + ocurrencia + canal + destinatario."""

    __tablename__ = "notificacion"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    evento: Mapped[str] = mapped_column(String(40))
    regla_id: Mapped[int | None] = mapped_column(ForeignKey("regla_notificacion.id", ondelete="SET NULL"))
    audiencia: Mapped[str] = mapped_column(String(8))
    entidad_tipo: Mapped[str] = mapped_column(String(30))
    entidad_id: Mapped[str] = mapped_column(String(40))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id", ondelete="SET NULL"))
    comercial_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    email: Mapped[str | None] = mapped_column(String(254))
    canal: Mapped[str] = mapped_column(String(8))
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")
    motivo_omision: Mapped[str | None] = mapped_column(String(200))
    titulo: Mapped[str] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text, default="")
    enlace: Mapped[str | None] = mapped_column(String(300))
    asunto: Mapped[str | None] = mapped_column(String(300))
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantilla_correo.id", ondelete="SET NULL"))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    adjuntar_pdf: Mapped[bool] = mapped_column(default=False)
    programada_para: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    clave_idempotencia: Mapped[str] = mapped_column(String(250), unique=True)
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    message_id: Mapped[str | None] = mapped_column(String(120))
    ultimo_error: Mapped[str | None] = mapped_column(String(300))
    leida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plantilla: Mapped[PlantillaCorreo | None] = relationship()


class PreferenciaNotificacion(Base):
    """Si el usuario recibe por correo un evento interno (sin fila: lo que diga la regla). La campana siempre llega."""

    __tablename__ = "preferencia_notificacion"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    evento: Mapped[str] = mapped_column(String(40), primary_key=True)
    correo: Mapped[bool] = mapped_column()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


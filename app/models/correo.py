"""F4: datos de la empresa para el PDF, configuración del correo y bitácoras de envío. Migración 0005.

Los CHECK, el trigger de solo inserción y los valores iniciales viven en la migración; aquí solo el mapeo.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CLAVES_EMPRESA = (
    "empresa_departamento",
    "empresa_ciudad",
    "empresa_telefono",
    "empresa_celular",
    "empresa_whatsapp",
    "empresa_horario",
    "empresa_direccion_matriz",
    "pago_banco",
    "pago_titular",
    "pago_tipo_cuenta",
    "pago_numero_cuenta",
    "pago_ruc",
    "clausula_fundamental",
    "texto_legal_pie",
)


class ConfigEmpresa(Base):
    """Una sola fila (id = 1). Se copia a la foto de la cotización al emitir (A4)."""

    __tablename__ = "config_empresa"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    empresa_departamento: Mapped[str] = mapped_column(Text, default="")
    empresa_ciudad: Mapped[str] = mapped_column(Text, default="")
    empresa_telefono: Mapped[str] = mapped_column(Text, default="")
    empresa_celular: Mapped[str] = mapped_column(Text, default="")
    empresa_whatsapp: Mapped[str] = mapped_column(Text, default="")
    empresa_horario: Mapped[str] = mapped_column(Text, default="")
    empresa_direccion_matriz: Mapped[str] = mapped_column(Text, default="")
    pago_banco: Mapped[str] = mapped_column(Text, default="")
    pago_titular: Mapped[str] = mapped_column(Text, default="")
    pago_tipo_cuenta: Mapped[str] = mapped_column(Text, default="")
    pago_numero_cuenta: Mapped[str] = mapped_column(Text, default="")
    pago_ruc: Mapped[str] = mapped_column(Text, default="")
    clausula_fundamental: Mapped[str] = mapped_column(Text, default="")
    texto_legal_pie: Mapped[str] = mapped_column(Text, default="")
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfigCorreo(Base):
    """Una sola fila (id = 1). Las llaves van cifradas con Fernet (CONFIG_CIFRADO_KEY) y nunca salen en claro."""

    __tablename__ = "config_correo"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    habilitado: Mapped[bool] = mapped_column(default=False)
    region: Mapped[str] = mapped_column(String(40))
    endpoint: Mapped[str] = mapped_column(String(200))
    remitente: Mapped[str] = mapped_column(String(300))
    reply_to: Mapped[str] = mapped_column(String(254))
    bcc: Mapped[str | None] = mapped_column(String(254))
    plantilla_cotizacion_id: Mapped[int] = mapped_column(BigInteger)
    timeout_s: Mapped[int] = mapped_column(SmallInteger)
    adjunto_max_bytes: Mapped[int] = mapped_column(Integer)
    secret_id_cifrado: Mapped[str | None] = mapped_column(Text)
    secret_key_cifrado: Mapped[str | None] = mapped_column(Text)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class _EnvioMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    destinatario: Mapped[str] = mapped_column(String(254))
    asunto: Mapped[str] = mapped_column(String(300))
    adjunto_nombre: Mapped[str] = mapped_column(String(120))
    adjunto_bytes: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(8))
    message_id: Mapped[str | None] = mapped_column(String(120))
    request_id: Mapped[str | None] = mapped_column(String(120))
    codigo_error: Mapped[str | None] = mapped_column(String(60))
    reintentable: Mapped[bool] = mapped_column(default=False)
    respuesta_proveedor: Mapped[str | None] = mapped_column(Text)
    enviado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnvioCorreo(_EnvioMixin, Base):
    """Bitácora de envíos de cotizaciones (B7). Solo inserción: la base rechaza UPDATE y DELETE."""

    __tablename__ = "envio_correo"

    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizacion.id", ondelete="RESTRICT"))
    cc: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    bcc: Mapped[str | None] = mapped_column(String(254))


class EnvioCorreoPrueba(_EnvioMixin, Base):
    """Bitácora de los correos de prueba del administrador (B3), aparte de la de cotizaciones."""

    __tablename__ = "envio_correo_prueba"

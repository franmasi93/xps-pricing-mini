"""E2 Catálogos de administración: motivos de rechazo, tipos de identificación y textos del PDF. Migración 0009."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CatalogoMixin

# Las claves de config_textos_pdf, en el orden de la pantalla.
CLAVES_TEXTOS_PDF = (
    "aceptacion_titulo",
    "aceptacion_texto",
    "firma_fecha",
    "firma_firma",
    "firma_sello",
    "advertencia_ddp",
    "advertencia_exw",
)


class MotivoRechazo(CatalogoMixin, Base):
    """Por qué el cliente rechazó una cotización. El código no cambia (lo guardan las cotizaciones)."""

    __tablename__ = "motivo_rechazo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    exige_detalle: Mapped[bool] = mapped_column(default=False)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)


class TipoIdentificacion(CatalogoMixin, Base):
    """RUC, cédula, pasaporte… con la regla (regex) que valida el número y el formato que se muestra si no cumple."""

    __tablename__ = "tipo_identificacion"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    regex: Mapped[str] = mapped_column(String(300))
    formato: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)


class ConfigTextosPdf(Base):
    """Una sola fila (id = 1): textos fijos del PDF y de las advertencias de Incoterm. Se copian a la foto al emitir."""

    __tablename__ = "config_textos_pdf"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    aceptacion_titulo: Mapped[str] = mapped_column(Text)
    aceptacion_texto: Mapped[str] = mapped_column(Text)
    firma_fecha: Mapped[str] = mapped_column(Text)
    firma_firma: Mapped[str] = mapped_column(Text)
    firma_sello: Mapped[str] = mapped_column(Text)
    advertencia_ddp: Mapped[str] = mapped_column(Text)
    advertencia_exw: Mapped[str] = mapped_column(Text)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class ConfigSistema(Base):
    """E4 (0011): una sola fila. url_publica = dirección con la que se arman TODOS los enlaces (baja, avisos, botones de
    las plantillas). Hoy la de Cloud Run; con el dominio propio, https://pricing.xpress.ec."""

    __tablename__ = "config_sistema"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    url_publica: Mapped[str] = mapped_column(String(300))
    importacion_max_filas: Mapped[int] = mapped_column(Integer, default=2000)  # E1-B
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


# E1-B: tipos de catalogo_perfil. ESTADO_COMERCIAL es fijo (no se crean ni se editan sus códigos).
TIPOS_CATALOGO_PERFIL = ("TIPO_CLIENTE", "ESTADO_COMERCIAL", "SECTOR", "TIPO_CARGA", "FRECUENCIA", "VOLUMEN",
                         "ORIGEN_CLIENTE", "AREA_CONTACTO", "MEDIO_CONSENTIMIENTO")


class CatalogoPerfil(CatalogoMixin, Base):
    """E1-B (0012): los valores del perfil comercial (tipo de cliente, sector, tipo de carga…), por tipo."""

    __tablename__ = "catalogo_perfil"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))
    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    fijo: Mapped[bool] = mapped_column(default=False)


class TencentEvento(Base):
    """E1-B (0012): bitácora de eventos del callback de Tencent, vinculados por MessageId a su envío."""

    __tablename__ = "tencent_evento"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    message_id: Mapped[str | None] = mapped_column(String(120))
    evento: Mapped[str] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(254))
    origen: Mapped[str] = mapped_column(String(12))
    origen_id: Mapped[int | None] = mapped_column(BigInteger)
    datos: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PreferenciaPantalla(Base):
    """E1-B (0012): preferencias de pantalla por usuario (por ejemplo, las columnas visibles de Clientes)."""

    __tablename__ = "preferencia_pantalla"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[Any] = mapped_column(JSONB)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

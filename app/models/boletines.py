"""E1 Boletines de tarifas: configuración de masivos, plantillas, listas, bajas, campañas y destinatarios.

Tablas creadas por la migración 0008 (CHECK y valores iniciales allí). E3 reutiliza plantilla_correo, baja_correo y
el motor de envíos.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.clientes import ContactoCliente

ESTADOS_CAMPANA = ("BORRADOR", "PROGRAMADA", "ENVIANDO", "PAUSADA", "ENVIADA", "CANCELADA")
ESTADOS_DESTINATARIO = (
    "PENDIENTE", "ENVIADO", "REBOTADO", "FALLIDO", "OMITIDO_BAJA", "OMITIDO_DUPLICADO", "CANCELADO",
)
DISENOS_PLANTILLA = ("GENERAL", "PESO_TRAMOS", "VOLUMEN_WM", "UNIDAD_EQUIPO", "TARIFA_PLANA", "AVISO", "LIBRE")
USOS_PLANTILLA = ("COTIZACION", "BOLETIN", "AVISO")
ESTADOS_TENCENT = ("SIN_REGISTRAR", "EN_REVISION", "APROBADA", "RECHAZADA", "NO_ENCONTRADA")


class ConfigMasivos(Base):
    """Una sola fila (id = 1), en el espacio de Tencent: cómo salen los envíos masivos."""

    __tablename__ = "config_masivos"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    remitente: Mapped[str] = mapped_column(String(300), default="")
    reply_to: Mapped[str] = mapped_column(String(254), default="")
    tamano_lote: Mapped[int] = mapped_column(SmallInteger, default=50)
    pausa_segundos: Mapped[int] = mapped_column(Integer, default=60)
    tope_diario: Mapped[int] = mapped_column(Integer, default=500)
    tope_hora: Mapped[int] = mapped_column(Integer, default=200)
    reserva_pct: Mapped[int] = mapped_column(SmallInteger, default=20)
    adjuntar_pdf: Mapped[bool] = mapped_column(default=True)
    limite_filas: Mapped[int] = mapped_column(SmallInteger, default=8)
    texto_legal: Mapped[str] = mapped_column(Text, default="")
    correos_prueba: Mapped[str] = mapped_column(Text, default="")
    dias_envio: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5")
    hora_desde: Mapped[int] = mapped_column(SmallInteger, default=8)
    hora_hasta: Mapped[int] = mapped_column(SmallInteger, default=19)
    calentamiento: Mapped[bool] = mapped_column(default=False)
    calentamiento_inicio: Mapped[int] = mapped_column(Integer, default=100)
    calentamiento_incremento: Mapped[int] = mapped_column(Integer, default=50)
    calentamiento_desde: Mapped[date | None] = mapped_column(Date)
    url_publica: Mapped[str] = mapped_column(String(300), default="")
    ultimo_lote_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlantillaCorreo(CatalogoMixin, Base):
    __tablename__ = "plantilla_correo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    uso: Mapped[str] = mapped_column(String(10))
    diseno: Mapped[str] = mapped_column(String(20))
    evento_o_servicio: Mapped[str | None] = mapped_column(String(40))
    asunto_sugerido: Mapped[str | None] = mapped_column(String(200))
    html: Mapped[str | None] = mapped_column(Text)
    texto: Mapped[str | None] = mapped_column(Text)
    variables_esperadas: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tencent_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    estado_tencent: Mapped[str] = mapped_column(String(14), default="SIN_REGISTRAR")
    motivo_tencent: Mapped[str | None] = mapped_column(Text)
    sincronizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notas: Mapped[str | None] = mapped_column(Text)


lista_envio_miembro = Table(
    "lista_envio_miembro",
    Base.metadata,
    Column("lista_id", ForeignKey("lista_envio.id", ondelete="CASCADE"), primary_key=True),
    Column("contacto_id", ForeignKey("contacto_cliente.id", ondelete="RESTRICT"), primary_key=True),
)


class ListaEnvio(CatalogoMixin, Base):
    __tablename__ = "lista_envio"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(10))
    filtros: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    miembros: Mapped[list[ContactoCliente]] = relationship(secondary=lista_envio_miembro, order_by=ContactoCliente.id)


class BajaCorreo(Base):
    __tablename__ = "baja_correo"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    motivo: Mapped[str] = mapped_column(String(10))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revertida: Mapped[bool] = mapped_column(default=False)
    revertida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campana_id: Mapped[int | None] = mapped_column(ForeignKey("campana.id", ondelete="SET NULL"))
    registrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class Campana(Base):
    __tablename__ = "campana"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    asunto: Mapped[str] = mapped_column(String(200), default="")
    texto_intro: Mapped[str] = mapped_column(Text, default="")
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantilla_correo.id", ondelete="RESTRICT"))
    servicios: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tipos_equipo: Mapped[list[int]] = mapped_column(JSONB, default=list)
    tarifas_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    listas_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    adjuntar_pdf: Mapped[bool] = mapped_column(default=True)
    snapshot_tarifas: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    adjunto_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    estado: Mapped[str] = mapped_column(String(10), default="BORRADOR")
    programada_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_destinatarios: Mapped[int] = mapped_column(Integer, default=0)
    enviados: Mapped[int] = mapped_column(Integer, default=0)
    rebotados: Mapped[int] = mapped_column(Integer, default=0)
    fallidos: Mapped[int] = mapped_column(Integer, default=0)
    omitidos: Mapped[int] = mapped_column(Integer, default=0)
    creado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    enviado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plantilla: Mapped[PlantillaCorreo | None] = relationship()


class CampanaDestinatario(Base):
    __tablename__ = "campana_destinatario"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campana.id", ondelete="CASCADE"), index=True)
    contacto_id: Mapped[int | None] = mapped_column(ForeignKey("contacto_cliente.id", ondelete="SET NULL"))
    email: Mapped[str] = mapped_column(String(254))
    nombre: Mapped[str] = mapped_column(String(200), default="")
    empresa: Mapped[str] = mapped_column(String(200), default="")
    estado: Mapped[str] = mapped_column(String(18), default="PENDIENTE")
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(String(300))
    token_baja: Mapped[str] = mapped_column(String(80), unique=True)
    message_id: Mapped[str | None] = mapped_column(String(120))
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campana: Mapped[Campana] = relationship()

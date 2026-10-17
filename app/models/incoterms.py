"""Incoterms 2020: matriz de bloques para IMPORTACIÓN (§9.1). Tabla creada por la migración 0002.

E0 (0007): los servicios permitidos viven en incoterm_servicio (reemplaza a solo_maritimo).
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.servicios import Servicio

from app.models.base import Base

# Orden de los 8 bloques de la cotización (§9).
BLOQUES = (
    "recogida_origen",
    "despacho_export",
    "gastos_origen",
    "flete_principal",
    "seguro",
    "gastos_destino",
    "despacho_import",
    "entrega_final",
)


class Incoterm(Base):
    __tablename__ = "incoterm"
    __table_args__ = (CheckConstraint("codigo ~ '^[A-Z]{3}$'", name="codigo_formato"),)

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(3), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    recogida_origen: Mapped[bool]
    despacho_export: Mapped[bool]
    gastos_origen: Mapped[bool]
    flete_principal: Mapped[bool]
    seguro: Mapped[bool]
    gastos_destino: Mapped[bool]
    despacho_import: Mapped[bool]
    entrega_final: Mapped[bool]
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    servicios: Mapped[list["Servicio"]] = relationship(
        secondary="incoterm_servicio", order_by="(Servicio.orden, Servicio.id)"
    )

    @property
    def solo_maritimo(self) -> bool:
        """Compatibilidad con F1–F5: verdadero si todos sus servicios van de puerto marítimo a puerto marítimo."""
        return bool(self.servicios) and all(
            s.tipo_ubicacion_origen == s.tipo_ubicacion_destino == "MARITIMO" for s in self.servicios
        )

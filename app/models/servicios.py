"""E0 Servicios editables: servicio, sus tramos de peso e Incoterms permitidos. Tablas creadas por la migración 0007.

La forma de cobro es un catálogo cerrado en código (services/formas_cobro.py); el servicio la elige.
"""
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Identity, Numeric, SmallInteger, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.geografia import TipoUbicacion

incoterm_servicio = Table(
    "incoterm_servicio",
    Base.metadata,
    Column("incoterm_id", ForeignKey("incoterm.id", ondelete="CASCADE"), primary_key=True),
    Column("servicio_id", ForeignKey("servicio.id", ondelete="CASCADE"), primary_key=True),
)


class Servicio(CatalogoMixin, Base):
    __tablename__ = "servicio"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    forma_cobro: Mapped[str] = mapped_column(String(20))
    tipo_ubicacion_origen: Mapped[str] = mapped_column(ForeignKey("tipo_ubicacion.codigo", ondelete="RESTRICT"))
    tipo_ubicacion_destino: Mapped[str] = mapped_column(ForeignKey("tipo_ubicacion.codigo", ondelete="RESTRICT"))
    usa_tipo_equipo: Mapped[bool] = mapped_column(default=False)
    permite_libras: Mapped[bool] = mapped_column(default=False)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    descripcion_pdf: Mapped[str] = mapped_column(String(120))
    etiqueta_transportista: Mapped[str] = mapped_column(String(40))
    aviso_incoterm: Mapped[str | None] = mapped_column(String(200))

    origen: Mapped[TipoUbicacion] = relationship(foreign_keys=[tipo_ubicacion_origen], viewonly=True)
    destino: Mapped[TipoUbicacion] = relationship(foreign_keys=[tipo_ubicacion_destino], viewonly=True)
    tramos: Mapped[list["ServicioTramo"]] = relationship(
        back_populates="servicio", order_by="(ServicioTramo.unidad_peso, ServicioTramo.desde)"
    )


class ServicioTramo(CatalogoMixin, Base):
    """Un "desde" permitido para los tramos de las tarifas del servicio, en kg o en lb (admite decimales)."""

    __tablename__ = "servicio_tramo"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicio.id", ondelete="RESTRICT"), index=True)
    unidad_peso: Mapped[str] = mapped_column(String(2))
    desde: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)

    servicio: Mapped[Servicio] = relationship(back_populates="tramos")

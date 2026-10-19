"""M6 Clientes y contactos. Tablas creadas por la migración 0003 (CHECK e índice parcial del principal allí)."""
from sqlalchemy import Boolean, ForeignKey, Identity, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CatalogoMixin
from app.models.geografia import Pais
from app.models.seguridad import Usuario

class Cliente(CatalogoMixin, Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    tipo_id: Mapped[str] = mapped_column(ForeignKey("tipo_identificacion.codigo", ondelete="RESTRICT"))  # E2
    ruc_o_id: Mapped[str] = mapped_column(String(30))
    pais_id: Mapped[int] = mapped_column(ForeignKey("pais.id", ondelete="RESTRICT"))
    direccion: Mapped[str | None] = mapped_column(String(250))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(40))
    comercial_asignado_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    notas: Mapped[str | None] = mapped_column(Text)

    pais: Mapped[Pais] = relationship()
    comercial_asignado: Mapped[Usuario] = relationship(foreign_keys=[comercial_asignado_id])
    contactos: Mapped[list["ContactoCliente"]] = relationship(order_by="ContactoCliente.id")


class ContactoCliente(CatalogoMixin, Base):
    __tablename__ = "contacto_cliente"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(254))
    telefono: Mapped[str | None] = mapped_column(String(40))
    principal: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

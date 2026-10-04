"""Schemas de M4 Proveedores."""
from pydantic import Field

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null
from app.schemas.geografia import PaisResumen


class ProveedorSalida(CatalogoSalida):
    nombre: str
    pais_id: int
    pais: PaisResumen
    contacto: str | None
    email: str | None
    telefono: str | None
    notas: str | None


class ProveedorCrear(Entrada):
    nombre: str = Field(max_length=150)
    pais_id: int
    contacto: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)


class ProveedorActualizar(Entrada):
    """Los campos opcionales (contacto, email, telefono, notas) sí aceptan null para vaciarlos."""

    nombre: str | None = Field(default=None, max_length=150)
    pais_id: int | None = None
    contacto: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    telefono: str | None = Field(default=None, max_length=40)
    notas: str | None = Field(default=None, max_length=5000)
    activo: bool | None = None

    _sin_null = sin_null("nombre", "pais_id", "activo")

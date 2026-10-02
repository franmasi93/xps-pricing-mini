"""Schemas de usuarios y roles. Ningún schema de salida incluye hash_password."""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_MAX = 254
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Tope de entrada para contraseñas; la política (10-128) se valida en el service.
PASSWORD_ENTRADA_MAX = 1024


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def email_valido(email: str) -> bool:
    return len(email) <= EMAIL_MAX and EMAIL_REGEX.match(email) is not None


class RolResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str


class RolSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str
    permisos: list[str]

    @field_validator("permisos", mode="before")
    @classmethod
    def _codigos(cls, valor):
        return sorted(p if isinstance(p, str) else p.codigo for p in valor)


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: str
    rol: RolResumen
    activo: bool
    forzar_cambio_password: bool
    bloqueado_hasta: datetime | None
    ultimo_login: datetime | None
    creado_en: datetime
    actualizado_en: datetime


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UsuarioCrear(_Entrada):
    email: str
    nombre: str = Field(max_length=120)
    rol_codigo: str = Field(max_length=30)
    password_temporal: str = Field(max_length=PASSWORD_ENTRADA_MAX)

    @field_validator("email")
    @classmethod
    def _email(cls, valor: str) -> str:
        valor = normalizar_email(valor)
        if not email_valido(valor):
            raise ValueError("email inválido")
        return valor

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("el nombre no puede estar vacío")
        return valor


class UsuarioActualizar(_Entrada):
    nombre: str | None = Field(default=None, max_length=120)
    rol_codigo: str | None = Field(default=None, max_length=30)
    activo: bool | None = None

    @field_validator("nombre", "rol_codigo", "activo", mode="before")
    @classmethod
    def _sin_null(cls, valor):
        if valor is None:
            raise ValueError("no puede ser null; omita el campo si no quiere cambiarlo")
        return valor

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("el nombre no puede estar vacío")
        return valor


class RestablecerPassword(_Entrada):
    password_temporal: str = Field(max_length=PASSWORD_ENTRADA_MAX)

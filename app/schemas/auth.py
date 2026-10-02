"""Schemas de autenticación."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.usuarios import EMAIL_MAX, PASSWORD_ENTRADA_MAX, RolResumen


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_MAX)
    password: str = Field(max_length=PASSWORD_ENTRADA_MAX)


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    forzar_cambio_password: bool


class CambiarPasswordEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password_actual: str = Field(max_length=PASSWORD_ENTRADA_MAX)
    password_nueva: str = Field(max_length=PASSWORD_ENTRADA_MAX)


class YoSalida(BaseModel):
    id: int
    email: str
    nombre: str
    rol: RolResumen
    permisos: list[str]
    forzar_cambio_password: bool
    ultimo_login: datetime | None

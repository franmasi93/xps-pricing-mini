"""Entradas de la administración del correo (B3 de F4). La salida la arma el service (llaves enmascaradas)."""
from pydantic import Field

from app.schemas.comunes import Entrada, sin_null


class ConfigCorreoEntrada(Entrada):
    habilitado: bool | None = None
    region: str | None = Field(default=None, max_length=40)
    endpoint: str | None = Field(default=None, max_length=200)
    remitente: str | None = Field(default=None, max_length=300)
    reply_to: str | None = Field(default=None, max_length=254)
    bcc: str | None = Field(default=None, max_length=254)
    plantilla_cotizacion_id: int | None = Field(default=None, gt=0)
    timeout_s: int | None = Field(default=None, ge=5, le=120)
    adjunto_max_bytes: int | None = Field(default=None, ge=1, le=10_000_000)
    # Solo escritura: nunca se devuelven. Vacíos = conservar las guardadas.
    secret_id: str | None = Field(default=None, max_length=200)
    secret_key: str | None = Field(default=None, max_length=200)

    _sin_null = sin_null(
        "habilitado", "region", "endpoint", "remitente", "reply_to", "plantilla_cotizacion_id", "timeout_s",
        "adjunto_max_bytes",
    )


class EnviarPruebaEntrada(Entrada):
    email: str = Field(max_length=254)

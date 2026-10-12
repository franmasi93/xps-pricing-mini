"""Lectura de variables de entorno (sección 5.1 del documento rector).

Las variables obligatorias se validan al arrancar. Si falta alguna o es inválida,
se lanza ConfiguracionError con el NOMBRE de la variable y el motivo, nunca su valor.
"""
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent

PREFIJO_URL_BD = "postgresql+psycopg://"


class ConfiguracionError(RuntimeError):
    """Configuración faltante o inválida. El mensaje nunca incluye valores."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Obligatorias
    APP_ENV: Literal["dev", "test", "prod"]
    DATABASE_URL: SecretStr
    DATABASE_URL_TEST: SecretStr
    JWT_SECRET: SecretStr
    JWT_EXPIRA_MIN: int

    # Con valor por defecto
    # IVA_TASA NO se usa en ningún cálculo: la tasa de IVA se lee siempre de la tabla
    # configuracion (services/configuracion.leer_iva_tasa), regla de §5.2.
    IVA_TASA: Decimal = Decimal("15.00")
    COT_PREFIJO: str = "COT"
    MONEDA_BASE: str = "USD"
    # Navegador para el PDF (H12 de F3): chromium de Playwright o el Edge instalado (msedge).
    PDF_NAVEGADOR: Literal["chromium", "msedge"] = "chromium"

    # Opcionales hasta F4 (correo Tencent SES)
    TENCENT_SECRET_ID: SecretStr | None = None
    TENCENT_SECRET_KEY: SecretStr | None = None
    TENCENT_SES_REGION: str | None = None
    SES_FROM: str | None = None
    SES_REPLY_TO: str | None = None
    SES_TEMPLATE_ID: str | None = None
    SES_MAX_ADJUNTO_MB: Decimal | None = None

    @field_validator("DATABASE_URL", "DATABASE_URL_TEST")
    @classmethod
    def _validar_url_bd(cls, valor: SecretStr) -> SecretStr:
        crudo = valor.get_secret_value()
        if not crudo.startswith(PREFIJO_URL_BD):
            raise ValueError(f"debe comenzar con {PREFIJO_URL_BD} (driver psycopg v3)")
        if crudo[len(PREFIJO_URL_BD):].count("@") > 1:
            raise ValueError(
                "tiene más de un '@': la contraseña contiene caracteres sin codificar (use %40 para '@')"
            )
        try:
            host = make_url(crudo).host
        except ArgumentError:
            host = None
        if not host:
            raise ValueError("no se pudo leer el host; revise que la contraseña esté codificada en URL")
        return valor

    @field_validator("JWT_SECRET")
    @classmethod
    def _validar_jwt_secret(cls, valor: SecretStr) -> SecretStr:
        if len(valor.get_secret_value()) < 64:
            raise ValueError("debe tener al menos 64 caracteres")
        return valor

    @field_validator("JWT_EXPIRA_MIN")
    @classmethod
    def _validar_expiracion(cls, valor: int) -> int:
        if valor <= 0:
            raise ValueError("debe ser mayor que 0")
        return valor

    @model_validator(mode="after")
    def _bases_distintas(self) -> "Settings":
        if self.DATABASE_URL.get_secret_value() == self.DATABASE_URL_TEST.get_secret_value():
            raise ValueError("DATABASE_URL y DATABASE_URL_TEST deben apuntar a bases distintas")
        return self

    def url_bd(self) -> str:
        """Cadena de conexión según APP_ENV: la de tests cuando APP_ENV=test."""
        url = self.DATABASE_URL_TEST if self.APP_ENV == "test" else self.DATABASE_URL
        return url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        detalles = []
        for error in exc.errors():
            nombre = ".".join(str(parte) for parte in error["loc"]) or "configuración"
            motivo = "falta" if error["type"] == "missing" else error["msg"]
            detalles.append(f"{nombre}: {motivo}")
        raise ConfiguracionError(
            "Configuración inválida (.env o variables de entorno) -> " + "; ".join(detalles)
        ) from None

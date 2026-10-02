"""Validación de la configuración: errores claros y sin mostrar valores.

Se usan URLs ficticias en variables de entorno, que tienen prioridad sobre el .env.
"""
import pytest

from app.config import ConfiguracionError, get_settings

CLAVE_FICTICIA = "Clave@Ficticia"
URL_TEST_OK = "postgresql+psycopg://pricing_app:otra_clave@127.0.0.1:5432/xps_pricing_test"


@pytest.fixture
def entorno_ficticio(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    monkeypatch.setenv("JWT_EXPIRA_MIN", "480")
    monkeypatch.setenv("DATABASE_URL_TEST", URL_TEST_OK)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_url_con_arroba_sin_codificar_da_error_claro_sin_valores(entorno_ficticio):
    entorno_ficticio.setenv(
        "DATABASE_URL", f"postgresql+psycopg://pricing_app:{CLAVE_FICTICIA}@127.0.0.1:5432/xps_pricing"
    )
    with pytest.raises(ConfiguracionError) as error:
        get_settings()
    mensaje = str(error.value)
    assert "DATABASE_URL:" in mensaje
    assert "%40" in mensaje
    assert "Clave" not in mensaje
    assert "Ficticia" not in mensaje
    assert "127.0.0.1" not in mensaje


def test_url_con_arroba_codificada_es_valida(entorno_ficticio):
    entorno_ficticio.setenv(
        "DATABASE_URL", "postgresql+psycopg://pricing_app:Clave%40Ficticia@127.0.0.1:5432/xps_pricing"
    )
    assert get_settings().APP_ENV == "test"

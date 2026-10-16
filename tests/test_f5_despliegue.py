"""F5 (T304–T307): índices de trigramas, imagen sin secretos, configuración de producción y logs estructurados."""
import json
import logging
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import ConfiguracionError, Settings, get_settings
from app.core.registro import FormatoJSON

RAIZ = Path(__file__).resolve().parent.parent
URL_OK = "postgresql+psycopg://pricing_app:clave_ficticia@127.0.0.1:5432/xps_pricing"
URL_SOCKET = "postgresql+psycopg://pricing_app:clave_ficticia@/xps_pricing?host=/cloudsql/proyecto:us-central1:instancia"


def test_indices_de_trigramas_en_clientes(client, crear_usuario, headers_de, db_session):  # T304 (F5-A3)
    indices = set(db_session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'cliente'")).scalars())
    assert {"ix_cliente_razon_social_trgm", "ix_cliente_ruc_o_id_trgm"} <= indices
    from fabricas import crear_cliente

    comercial = crear_usuario("comercial")
    crear_cliente(db_session, comercial, razon_social="Importadora Trigrama Única S.A.")
    encontrados = client.get("/v1/clientes/buscar?q=rigrama", headers=headers_de(comercial)).json()
    assert [c["razon_social"] for c in encontrados] == ["Importadora Trigrama Única S.A."]


def test_la_imagen_no_lleva_secretos(client):  # T305 (F5-B1)
    ignorados = {linea.strip() for linea in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    assert {".env", ".env.*", ".venv/", "tests/", "salidas/", "docs/", ".git/", "*.pem", "*.key"} <= ignorados
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . " not in dockerfile and ".env" not in dockerfile.replace("sin .env", "")
    assert "USER xps" in dockerfile and "APP_ENV=prod" in dockerfile
    assert "pip install -r requirements.txt" in dockerfile and "playwright install --with-deps chromium" in dockerfile


@pytest.fixture
def entorno(monkeypatch):
    for variable in ("APP_ENV", "DATABASE_URL", "DATABASE_URL_TEST", "JWT_SECRET", "JWT_EXPIRA_MIN"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})  # sin el .env real
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _base(entorno, **variables):
    valores = {"JWT_SECRET": "x" * 64, "JWT_EXPIRA_MIN": "480", "DATABASE_URL": URL_OK} | variables
    for clave, valor in valores.items():
        if valor is None:
            entorno.delenv(clave, raising=False)
        else:
            entorno.setenv(clave, valor)


def test_configuracion_de_produccion(entorno):  # T306 (F5-B2, B3)
    _base(entorno, APP_ENV="prod", DATABASE_URL=URL_SOCKET)
    ajustes = get_settings()
    assert ajustes.DATABASE_URL_TEST is None and ajustes.url_bd() == URL_SOCKET  # socket de Cloud SQL aceptado
    get_settings.cache_clear()
    _base(entorno, APP_ENV="dev")
    with pytest.raises(ConfiguracionError, match="DATABASE_URL_TEST es obligatoria"):
        get_settings()
    get_settings.cache_clear()
    _base(entorno, APP_ENV="prod", JWT_SECRET=None)
    with pytest.raises(ConfiguracionError) as error:
        get_settings()
    assert "JWT_SECRET: falta" in str(error.value) and "clave_ficticia" not in str(error.value)


def test_logs_estructurados_sin_detalles():  # T307 (F5-B5)
    formato = FormatoJSON()
    try:
        raise RuntimeError("fallo de prueba")
    except RuntimeError:
        registro = logging.LogRecord("app", logging.ERROR, __file__, 1, "algo falló", None, sys.exc_info())
    linea = json.loads(formato.format(registro))
    assert (linea["severity"], linea["logger"], linea["message"]) == ("ERROR", "app", "algo falló")
    assert linea["error"] == "RuntimeError: fallo de prueba"  # solo la última línea, sin traza ni variables
    configuracion = json.loads((RAIZ / "app" / "core" / "log_config.json").read_text(encoding="utf-8"))
    assert configuracion["formatters"]["json"]["()"] == "app.core.registro.FormatoJSON"

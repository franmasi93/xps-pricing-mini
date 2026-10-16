"""F5 · D-AUT-7 (T301): si la base no responde (apagada fuera de horario), la API responde 503
SISTEMA_FUERA_DE_HORARIO con el horario, nunca un 500. Una base inalcanzable de verdad: un puerto local cerrado."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.errors import HORARIO_SISTEMA
from app.db import get_db
from app.main import app

BASE_APAGADA = "postgresql+psycopg://nadie:nada@127.0.0.1:1/apagada"


@pytest.fixture
def cliente_sin_base():
    motor = create_engine(BASE_APAGADA, connect_args={"connect_timeout": 2}, pool_pre_ping=False)

    def _sin_base():
        with Session(motor) as sesion:
            yield sesion

    app.dependency_overrides[get_db] = _sin_base
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()
        motor.dispose()


def test_base_apagada_responde_503_fuera_de_horario(cliente_sin_base):  # T301
    respuesta = cliente_sin_base.post("/v1/auth/login", json={"email": "x@xpress.ec", "password": "ClavePrueba2026"})
    assert respuesta.status_code == 503
    detalle = respuesta.json()["detail"]
    assert (detalle["codigo"], detalle["horario"]) == ("SISTEMA_FUERA_DE_HORARIO", HORARIO_SISTEMA)
    assert "07:00 a 20:00" in detalle["mensaje"]
    assert respuesta.headers["retry-after"] == "300"
    assert "psycopg" not in respuesta.text and "127.0.0.1" not in respuesta.text  # sin detalles internos
    # /v1/salud sigue respondiendo 200 (la app está viva) e informa la base caída: sirve al health check.
    salud = cliente_sin_base.get("/v1/salud")
    assert (salud.status_code, salud.json()) == (200, {"estado": "ok", "bd": "error"})

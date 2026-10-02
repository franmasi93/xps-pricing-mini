from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app


def test_salud_sin_token_200_bd_ok(client):  # T01
    respuesta = client.get("/v1/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "bd": "ok"}


class _SesionCaida:
    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexión rechazada en 10.0.0.1:5432"))


def test_salud_bd_caida_responde_error_sin_detalles(client):  # T02
    def _get_db_caida():
        yield _SesionCaida()

    app.dependency_overrides[get_db] = _get_db_caida
    respuesta = client.get("/v1/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "bd": "error"}
    assert "10.0.0.1" not in respuesta.text
    assert "SELECT" not in respuesta.text

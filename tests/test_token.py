"""Validez del token: firma, expiración, usuario activo y token_version vigente."""
import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Usuario
from conftest import PASSWORD_PRUEBA


def _yo(client, token):
    return client.get("/v1/auth/yo", headers={"Authorization": f"Bearer {token}"})


def _token_de(headers):
    return headers["Authorization"].removeprefix("Bearer ")


def _b64(datos: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()


def test_inactivo_no_puede_loguearse(client, crear_usuario):  # T19 (d)
    usuario = crear_usuario(activo=False)
    respuesta = client.post("/v1/auth/login", json={"email": usuario.email, "password": PASSWORD_PRUEBA})
    assert respuesta.status_code == 401
    assert respuesta.json()["detail"]["mensaje"] == "Credenciales inválidas"


def test_token_previo_a_desactivacion_401(client, crear_usuario, headers_de):  # T20 (d)
    admin = crear_usuario("admin")
    usuario = crear_usuario()
    token_previo = _token_de(headers_de(usuario))
    assert _yo(client, token_previo).status_code == 200

    respuesta = client.patch(f"/v1/usuarios/{usuario.id}", json={"activo": False}, headers=headers_de(admin))
    assert respuesta.status_code == 200
    assert _yo(client, token_previo).status_code == 401


def test_token_expirado_401(client, crear_usuario):  # T21 (f)
    usuario = crear_usuario()
    hace_un_rato = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode(
        {"sub": str(usuario.id), "tv": usuario.token_version, "iat": hace_un_rato,
         "exp": hace_un_rato + timedelta(minutes=30)},
        get_settings().JWT_SECRET.get_secret_value(),
        algorithm="HS256",
    )
    assert _yo(client, token).status_code == 401


def test_firma_alterada_401(client, crear_usuario, headers_de):  # T22 (f)
    usuario = crear_usuario()
    token = _token_de(headers_de(usuario))
    cabecera, cuerpo, firma = token.split(".")

    payload = jwt.decode(token, options={"verify_signature": False})
    payload["tv"] = usuario.token_version + 7
    token_cuerpo_alterado = f"{cabecera}.{_b64(payload)}.{firma}"
    assert _yo(client, token_cuerpo_alterado).status_code == 401

    token_otra_clave = jwt.encode(payload | {"tv": usuario.token_version}, "otra-clave-" * 8, algorithm="HS256")
    assert _yo(client, token_otra_clave).status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer basura.no.jwt", "Basic dXN1YXJpbzpjbGF2ZQ=="],
    ids=["sin_header", "bearer_basura", "esquema_basic"],
)
def test_sin_token_o_malformado_401(client, authorization):  # T23
    headers = {"Authorization": authorization} if authorization else {}
    respuesta = client.get("/v1/auth/yo", headers=headers)
    assert respuesta.status_code == 401
    assert respuesta.json()["detail"]["codigo"] == "TOKEN_INVALIDO"
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_token_usuario_inexistente_401(client, db_session):  # T24
    id_inexistente = (db_session.scalar(select(func.max(Usuario.id))) or 0) + 1000
    token = jwt.encode(
        {"sub": str(id_inexistente), "tv": 0, "iat": datetime.now(UTC),
         "exp": datetime.now(UTC) + timedelta(minutes=5)},
        get_settings().JWT_SECRET.get_secret_value(),
        algorithm="HS256",
    )
    assert _yo(client, token).status_code == 401


def test_token_alg_none_401(client, crear_usuario):  # T25
    usuario = crear_usuario()
    ahora = int(datetime.now(UTC).timestamp())
    cabecera = _b64({"alg": "none", "typ": "JWT"})
    cuerpo = _b64({"sub": str(usuario.id), "tv": usuario.token_version, "iat": ahora, "exp": ahora + 300})
    assert _yo(client, f"{cabecera}.{cuerpo}.").status_code == 401


def test_cambio_de_rol_invalida_token(client, crear_usuario, headers_de):  # T26
    admin = crear_usuario("admin")
    usuario = crear_usuario("comercial")
    token_previo = _token_de(headers_de(usuario))
    respuesta = client.patch(
        f"/v1/usuarios/{usuario.id}", json={"rol_codigo": "gerencia"}, headers=headers_de(admin)
    )
    assert respuesta.status_code == 200
    assert _yo(client, token_previo).status_code == 401


def test_restablecer_password_invalida_token(client, crear_usuario, headers_de):  # T27
    admin = crear_usuario("admin")
    usuario = crear_usuario()
    token_previo = _token_de(headers_de(usuario))
    respuesta = client.post(
        f"/v1/usuarios/{usuario.id}/restablecer-password",
        json={"password_temporal": "Temporal2026x"},
        headers=headers_de(admin),
    )
    assert respuesta.status_code == 200
    assert _yo(client, token_previo).status_code == 401

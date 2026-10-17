"""/auth/yo y /auth/cambiar-password."""
import pytest

from conftest import PASSWORD_PRUEBA
from matriz_rbac import MATRIZ_6_2, PERMISOS_EXTENSIONES

CLAVE_NUEVA = "NuevaClave2026"


def _cambiar(client, headers, actual=PASSWORD_PRUEBA, nueva=CLAVE_NUEVA):
    return client.post(
        "/v1/auth/cambiar-password",
        json={"password_actual": actual, "password_nueva": nueva},
        headers=headers,
    )


@pytest.mark.parametrize("rol", ["admin", "pricing", "comercial", "gerencia"])
def test_yo_permisos_exactos_por_rol(client, crear_usuario, headers_de, rol):  # T28 (g)
    usuario = crear_usuario(rol)
    respuesta = client.get("/v1/auth/yo", headers=headers_de(usuario))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["rol"]["codigo"] == rol
    # D-E0-1: sin los permisos de las extensiones (se verifican en test_e0_servicios).
    assert [p for p in cuerpo["permisos"] if p not in PERMISOS_EXTENSIONES] == sorted(MATRIZ_6_2[rol])


def test_cambiar_password_invalida_token_anterior(client, crear_usuario, headers_de):  # T29 (e)
    usuario = crear_usuario()
    headers_previos = headers_de(usuario)
    respuesta = _cambiar(client, headers_previos)
    assert respuesta.status_code == 200
    token_nuevo = respuesta.json()["access_token"]

    assert client.get("/v1/auth/yo", headers=headers_previos).status_code == 401
    assert client.get("/v1/auth/yo", headers={"Authorization": f"Bearer {token_nuevo}"}).status_code == 200
    login = client.post("/v1/auth/login", json={"email": usuario.email, "password": CLAVE_NUEVA})
    assert login.status_code == 200


def test_cambiar_password_pone_forzar_false(client, crear_usuario, headers_de, db_session):  # T30
    usuario = crear_usuario(forzar=True)
    tv_previa = usuario.token_version
    respuesta = _cambiar(client, headers_de(usuario))
    assert respuesta.status_code == 200
    assert respuesta.json()["forzar_cambio_password"] is False
    db_session.refresh(usuario)
    assert usuario.forzar_cambio_password is False
    assert usuario.token_version == tv_previa + 1


def test_cambiar_password_actual_incorrecta_422(client, crear_usuario, headers_de):  # T31
    usuario = crear_usuario()
    respuesta = _cambiar(client, headers_de(usuario), actual="NoEsLaActual123")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "PASSWORD_ACTUAL_INCORRECTA"


def test_cambiar_password_debil_422(client, crear_usuario, headers_de):  # T32 (m)
    usuario = crear_usuario()
    respuesta = _cambiar(client, headers_de(usuario), nueva="corta1")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "PASSWORD_DEBIL"


def test_cambiar_password_igual_a_actual_422(client, crear_usuario, headers_de):  # T33
    usuario = crear_usuario()
    respuesta = _cambiar(client, headers_de(usuario), nueva=PASSWORD_PRUEBA)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "PASSWORD_REPETIDA"

"""forzar_cambio_password=true: solo /auth/yo y /auth/cambiar-password."""
from conftest import PASSWORD_PRUEBA


def test_forzar_cambio_403_en_usuarios_y_roles(client, crear_usuario, headers_de):  # T34 (l)
    admin = crear_usuario("admin", forzar=True)
    for ruta in ("/v1/usuarios", "/v1/roles", f"/v1/usuarios/{admin.id}"):
        respuesta = client.get(ruta, headers=headers_de(admin))
        assert respuesta.status_code == 403, ruta
        assert respuesta.json()["detail"]["codigo"] == "PASSWORD_CAMBIO_REQUERIDO"


def test_forzar_cambio_permite_yo(client, crear_usuario, headers_de):  # T35 (l)
    admin = crear_usuario("admin", forzar=True)
    respuesta = client.get("/v1/auth/yo", headers=headers_de(admin))
    assert respuesta.status_code == 200
    assert respuesta.json()["forzar_cambio_password"] is True


def test_forzar_cambio_permite_cambiar_y_luego_accede(client, crear_usuario, headers_de):  # T36 (l)
    admin = crear_usuario("admin", forzar=True)
    cambio = client.post(
        "/v1/auth/cambiar-password",
        json={"password_actual": PASSWORD_PRUEBA, "password_nueva": "Definitiva2026"},
        headers=headers_de(admin),
    )
    assert cambio.status_code == 200
    token = cambio.json()["access_token"]
    respuesta = client.get("/v1/usuarios", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 200

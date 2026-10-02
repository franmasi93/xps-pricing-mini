"""Bloqueo: 5 fallos seguidos -> 429 por 15 minutos; un login exitoso reinicia el contador."""
from datetime import UTC, datetime, timedelta

from conftest import PASSWORD_PRUEBA

CLAVE_MALA = "Equivocada123"


def _login(client, email, password):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def test_cuatro_fallos_401_quinto_429(client, crear_usuario):  # T14 (c)
    usuario = crear_usuario()
    codigos = [_login(client, usuario.email, CLAVE_MALA).status_code for _ in range(5)]
    assert codigos == [401, 401, 401, 401, 429]


def test_sexto_con_password_correcta_429(client, crear_usuario):  # T15 (c)
    usuario = crear_usuario()
    for _ in range(5):
        _login(client, usuario.email, CLAVE_MALA)
    respuesta = _login(client, usuario.email, PASSWORD_PRUEBA)
    assert respuesta.status_code == 429
    assert respuesta.json()["detail"]["codigo"] == "CUENTA_BLOQUEADA"


def test_bloqueo_vencido_login_ok(client, crear_usuario, db_session):  # T16 (c)
    usuario = crear_usuario()
    for _ in range(5):
        _login(client, usuario.email, CLAVE_MALA)
    db_session.refresh(usuario)
    assert usuario.bloqueado_hasta is not None

    usuario.bloqueado_hasta = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    assert _login(client, usuario.email, PASSWORD_PRUEBA).status_code == 200
    db_session.refresh(usuario)
    assert usuario.bloqueado_hasta is None


def test_429_indica_minutos_y_retry_after(client, crear_usuario):  # T17
    usuario = crear_usuario()
    for _ in range(4):
        _login(client, usuario.email, CLAVE_MALA)
    respuesta = _login(client, usuario.email, CLAVE_MALA)
    assert respuesta.status_code == 429
    assert respuesta.json()["detail"]["mensaje"] == "Cuenta bloqueada temporalmente, intente en 15 minutos"
    assert 1 <= int(respuesta.headers["Retry-After"]) <= 15 * 60


def test_fallos_no_consecutivos_no_bloquean(client, crear_usuario):  # T18
    usuario = crear_usuario()
    for _ in range(4):
        assert _login(client, usuario.email, CLAVE_MALA).status_code == 401
    assert _login(client, usuario.email, PASSWORD_PRUEBA).status_code == 200
    for _ in range(4):
        assert _login(client, usuario.email, CLAVE_MALA).status_code == 401

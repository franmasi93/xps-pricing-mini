from conftest import PASSWORD_PRUEBA


def _login(client, email, password=PASSWORD_PRUEBA):
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def test_login_correcto_token_valido(client, crear_usuario):  # T09 (a)
    usuario = crear_usuario("pricing")
    respuesta = _login(client, usuario.email)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["forzar_cambio_password"] is False
    yo = client.get("/v1/auth/yo", headers={"Authorization": f"Bearer {cuerpo['access_token']}"})
    assert yo.status_code == 200
    assert yo.json()["id"] == usuario.id


def test_password_incorrecta_y_email_inexistente_mismo_401(client, crear_usuario):  # T10 (b)
    usuario = crear_usuario()
    mala_clave = _login(client, usuario.email, "OtraClave999")
    sin_email = _login(client, "nadie-aqui@prueba.xps", "OtraClave999")
    assert mala_clave.status_code == sin_email.status_code == 401
    assert mala_clave.json() == sin_email.json()
    assert mala_clave.json()["detail"]["mensaje"] == "Credenciales inválidas"


def test_email_inexistente_verifica_hash_ficticio(client, monkeypatch):  # T11
    llamadas = []
    monkeypatch.setattr(
        "app.services.auth.verificar_contra_ficticio", lambda password: llamadas.append(password)
    )
    respuesta = _login(client, "fantasma@prueba.xps", "AlgunaClave123")
    assert respuesta.status_code == 401
    assert llamadas == ["AlgunaClave123"]


def test_login_normaliza_email(client, crear_usuario):  # T12
    usuario = crear_usuario()
    respuesta = _login(client, f"  {usuario.email.upper()}  ")
    assert respuesta.status_code == 200


def test_login_exitoso_reinicia_contador_y_ultimo_login(client, crear_usuario, db_session):  # T13
    usuario = crear_usuario()
    for _ in range(3):
        assert _login(client, usuario.email, "Equivocada123").status_code == 401
    db_session.refresh(usuario)
    assert usuario.intentos_fallidos == 3
    assert usuario.ultimo_login is None

    assert _login(client, usuario.email).status_code == 200
    db_session.refresh(usuario)
    assert usuario.intentos_fallidos == 0
    assert usuario.ultimo_login is not None

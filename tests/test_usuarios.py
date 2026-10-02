"""Administración de usuarios por API y reglas de negocio del service."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.errors import ErrorNegocio
from app.models import Rol, Usuario
from app.services.usuarios import actualizar_usuario
from conftest import PASSWORD_PRUEBA

TEMPORAL = "Temporal2026x"


def _email() -> str:
    return f"n{uuid4().hex[:12]}@prueba.xps"


def _crear(client, headers, email=None, rol="comercial", password=TEMPORAL, nombre="Nombre Prueba"):
    return client.post(
        "/v1/usuarios",
        json={"email": email or _email(), "nombre": nombre, "rol_codigo": rol, "password_temporal": password},
        headers=headers,
    )


def _dejar_un_solo_admin(db_session, admin_que_queda: Usuario) -> None:
    """Desactiva, dentro de la transacción del test, a todos los demás admins activos."""
    admin_rol_id = db_session.scalar(select(Rol.id).where(Rol.codigo == "admin"))
    db_session.execute(
        update(Usuario)
        .where(Usuario.rol_id == admin_rol_id, Usuario.activo.is_(True), Usuario.id != admin_que_queda.id)
        .values(activo=False)
    )
    db_session.commit()


def test_crear_201_forzar_true_y_creado_por(client, crear_usuario, headers_de, db_session):  # T41
    admin = crear_usuario("admin")
    respuesta = _crear(client, headers_de(admin), rol="pricing")
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["forzar_cambio_password"] is True
    assert cuerpo["activo"] is True
    assert cuerpo["rol"] == {"codigo": "pricing", "nombre": "Pricing"}
    creado = db_session.get(Usuario, cuerpo["id"])
    assert creado.creado_por == admin.id


def test_crear_guarda_email_minusculas(client, crear_usuario, headers_de, db_session):  # T42
    admin = crear_usuario("admin")
    base = uuid4().hex[:10]
    respuesta = _crear(client, headers_de(admin), email=f"  Ana.{base}@Prueba.XPS ")
    assert respuesta.status_code == 201
    assert respuesta.json()["email"] == f"ana.{base}@prueba.xps"
    assert db_session.get(Usuario, respuesta.json()["id"]).email == f"ana.{base}@prueba.xps"


def test_email_duplicado_distinta_capitalizacion_409(client, crear_usuario, headers_de):  # T43 (j)
    admin = crear_usuario("admin")
    base = uuid4().hex[:10]
    assert _crear(client, headers_de(admin), email=f"pedro.{base}@prueba.xps").status_code == 201
    respuesta = _crear(client, headers_de(admin), email=f"PEDRO.{base}@Prueba.Xps")
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {
        "codigo": "EMAIL_DUPLICADO",
        "mensaje": "Ya existe un usuario con ese email",
    }


def test_crear_rol_inexistente_422(client, crear_usuario, headers_de):  # T44
    admin = crear_usuario("admin")
    respuesta = _crear(client, headers_de(admin), rol="supervisor")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "ROL_INEXISTENTE"


def test_crear_password_temporal_debil_422(client, crear_usuario, headers_de):  # T45 (m)
    admin = crear_usuario("admin")
    for debil in ("Corta1", "SinNumerosNunca", "12345678901"):
        respuesta = _crear(client, headers_de(admin), password=debil)
        assert respuesta.status_code == 422, debil
        assert respuesta.json()["detail"]["codigo"] == "PASSWORD_DEBIL"


def test_crear_email_invalido_422(client, crear_usuario, headers_de):  # T46
    admin = crear_usuario("admin")
    for invalido in ("no-es-email", "sin@dominio", "con espacio@prueba.xps"):
        assert _crear(client, headers_de(admin), email=invalido).status_code == 422, invalido


def test_listar_filtro_activo(client, crear_usuario, headers_de):  # T47
    admin = crear_usuario("admin")
    activo = crear_usuario("comercial")
    inactivo = crear_usuario("comercial", activo=False)

    inactivos = client.get("/v1/usuarios", params={"activo": "false"}, headers=headers_de(admin)).json()
    ids_inactivos = {u["id"] for u in inactivos}
    assert inactivo.id in ids_inactivos and activo.id not in ids_inactivos
    assert all(u["activo"] is False for u in inactivos)

    activos = client.get("/v1/usuarios", params={"activo": "true"}, headers=headers_de(admin)).json()
    ids_activos = {u["id"] for u in activos}
    assert activo.id in ids_activos and inactivo.id not in ids_activos


def test_listar_filtro_rol(client, crear_usuario, headers_de):  # T48
    admin = crear_usuario("admin")
    gerente = crear_usuario("gerencia")
    comercial = crear_usuario("comercial")
    lista = client.get("/v1/usuarios", params={"rol": "gerencia"}, headers=headers_de(admin)).json()
    ids = {u["id"] for u in lista}
    assert gerente.id in ids and comercial.id not in ids
    assert all(u["rol"]["codigo"] == "gerencia" for u in lista)


def test_detalle_404(client, crear_usuario, headers_de, db_session):  # T49
    admin = crear_usuario("admin")
    id_inexistente = db_session.scalar(select(func.max(Usuario.id))) + 1000
    respuesta = client.get(f"/v1/usuarios/{id_inexistente}", headers=headers_de(admin))
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["codigo"] == "USUARIO_NO_ENCONTRADO"


def test_patch_parcial_no_pisa_campos(client, crear_usuario, headers_de):  # T50 (n)
    admin = crear_usuario("admin")
    usuario = crear_usuario("pricing", nombre="Nombre Original")
    ruta = f"/v1/usuarios/{usuario.id}"

    solo_nombre = client.patch(ruta, json={"nombre": "Nombre Nuevo"}, headers=headers_de(admin)).json()
    assert solo_nombre["nombre"] == "Nombre Nuevo"
    assert solo_nombre["rol"]["codigo"] == "pricing"
    assert solo_nombre["activo"] is True

    solo_activo = client.patch(ruta, json={"activo": False}, headers=headers_de(admin)).json()
    assert solo_activo["activo"] is False
    assert solo_activo["nombre"] == "Nombre Nuevo"
    assert solo_activo["rol"]["codigo"] == "pricing"


def test_patch_cambiar_rol_ok(client, crear_usuario, headers_de, db_session):  # T51
    admin = crear_usuario("admin")
    usuario = crear_usuario("comercial")
    tv_previa = usuario.token_version
    respuesta = client.patch(f"/v1/usuarios/{usuario.id}", json={"rol_codigo": "gerencia"}, headers=headers_de(admin))
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"]["codigo"] == "gerencia"
    db_session.refresh(usuario)
    assert usuario.token_version == tv_previa + 1


def test_patch_nombre_null_422(client, crear_usuario, headers_de):  # T52
    admin = crear_usuario("admin")
    usuario = crear_usuario()
    for cuerpo in ({"nombre": None}, {"activo": None}, {"rol_codigo": None}):
        respuesta = client.patch(f"/v1/usuarios/{usuario.id}", json=cuerpo, headers=headers_de(admin))
        assert respuesta.status_code == 422, cuerpo


def test_admin_no_puede_desactivarse_409(client, crear_usuario, headers_de):  # T53 (k)
    admin = crear_usuario("admin")
    respuesta = client.patch(f"/v1/usuarios/{admin.id}", json={"activo": False}, headers=headers_de(admin))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["codigo"] == "OPERACION_SOBRE_SI_MISMO"


def test_admin_no_puede_quitarse_rol_409(client, crear_usuario, headers_de):  # T54 (k)
    admin = crear_usuario("admin")
    respuesta = client.patch(f"/v1/usuarios/{admin.id}", json={"rol_codigo": "comercial"}, headers=headers_de(admin))
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["codigo"] == "OPERACION_SOBRE_SI_MISMO"


def test_no_desactivar_ultimo_admin_409(crear_usuario, db_session):  # T55 (k) nivel service
    ultimo = crear_usuario("admin")
    _dejar_un_solo_admin(db_session, ultimo)
    actor = crear_usuario("pricing")
    with pytest.raises(ErrorNegocio) as error:
        actualizar_usuario(db_session, actor, ultimo.id, {"activo": False})
    assert (error.value.status_code, error.value.codigo) == (409, "ULTIMO_ADMIN")
    db_session.refresh(ultimo)
    assert ultimo.activo is True


def test_no_quitar_rol_ultimo_admin_409(crear_usuario, db_session):  # T56 (k) nivel service
    ultimo = crear_usuario("admin")
    _dejar_un_solo_admin(db_session, ultimo)
    actor = crear_usuario("pricing")
    with pytest.raises(ErrorNegocio) as error:
        actualizar_usuario(db_session, actor, ultimo.id, {"rol_codigo": "comercial"})
    assert (error.value.status_code, error.value.codigo) == (409, "ULTIMO_ADMIN")
    db_session.refresh(ultimo)
    assert ultimo.rol.codigo == "admin"


def test_desactivar_otro_admin_si_quedan_ok(client, crear_usuario, headers_de, db_session):  # T57
    admin_a = crear_usuario("admin")
    admin_b = crear_usuario("admin")
    tv_previa = admin_b.token_version
    respuesta = client.patch(f"/v1/usuarios/{admin_b.id}", json={"activo": False}, headers=headers_de(admin_a))
    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
    db_session.refresh(admin_b)
    assert admin_b.token_version == tv_previa + 1


def test_restablecer_password_efectos(client, crear_usuario, headers_de, db_session):  # T58
    admin = crear_usuario("admin")
    usuario = crear_usuario()
    usuario.intentos_fallidos = 3
    usuario.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=10)
    db_session.commit()
    tv_previa = usuario.token_version

    respuesta = client.post(
        f"/v1/usuarios/{usuario.id}/restablecer-password",
        json={"password_temporal": "Restablecida2026"},
        headers=headers_de(admin),
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["forzar_cambio_password"] is True
    db_session.refresh(usuario)
    assert usuario.intentos_fallidos == 0
    assert usuario.bloqueado_hasta is None
    assert usuario.token_version == tv_previa + 1

    login = client.post("/v1/auth/login", json={"email": usuario.email, "password": "Restablecida2026"})
    assert login.status_code == 200
    assert login.json()["forzar_cambio_password"] is True


def test_sin_delete_405(client, crear_usuario, headers_de):  # T59
    admin = crear_usuario("admin")
    usuario = crear_usuario()
    respuesta = client.delete(f"/v1/usuarios/{usuario.id}", headers=headers_de(admin))
    assert respuesta.status_code == 405


def test_hash_password_nunca_en_respuestas(client, crear_usuario, headers_de):  # T60 (i)
    admin = crear_usuario("admin")
    otro = crear_usuario()
    h = headers_de(admin)

    respuestas = {
        "login": client.post("/v1/auth/login", json={"email": admin.email, "password": PASSWORD_PRUEBA}),
        "yo": client.get("/v1/auth/yo", headers=h),
        "listar": client.get("/v1/usuarios", headers=h),
        "detalle": client.get(f"/v1/usuarios/{otro.id}", headers=h),
        "crear": _crear(client, h),
        "patch": client.patch(f"/v1/usuarios/{otro.id}", json={"nombre": "Renombrado"}, headers=h),
        "restablecer": client.post(
            f"/v1/usuarios/{otro.id}/restablecer-password", json={"password_temporal": TEMPORAL}, headers=h
        ),
        "roles": client.get("/v1/roles", headers=h),
    }
    otro_login = client.post("/v1/auth/login", json={"email": otro.email, "password": TEMPORAL})
    respuestas["cambiar_password"] = client.post(
        "/v1/auth/cambiar-password",
        json={"password_actual": TEMPORAL, "password_nueva": "OtraDistinta2026"},
        headers={"Authorization": f"Bearer {otro_login.json()['access_token']}"},
    )

    for nombre, respuesta in respuestas.items():
        assert respuesta.status_code in (200, 201), nombre
        assert "hash_password" not in respuesta.text, nombre
        assert "$argon2" not in respuesta.text, nombre

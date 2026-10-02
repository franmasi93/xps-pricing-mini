"""crear_admin_inicial y restablecer_password_admin (lógica de los scripts de consola)."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.errors import ErrorNegocio
from app.core.security import verificar_password
from app.models import Rol, Usuario
from app.services.usuarios import crear_admin_inicial, restablecer_password_admin

CLAVE_ADMIN = "AdminSeguro2026"


def _sin_admins_activos(db_session) -> None:
    """Desactiva, dentro de la transacción del test, a los admins activos existentes."""
    admin_rol_id = db_session.scalar(select(Rol.id).where(Rol.codigo == "admin"))
    db_session.execute(
        update(Usuario).where(Usuario.rol_id == admin_rol_id, Usuario.activo.is_(True)).values(activo=False)
    )
    db_session.commit()


def test_crea_admin_activo_sin_forzar(db_session):  # T61
    _sin_admins_activos(db_session)
    base = uuid4().hex[:10]
    admin = crear_admin_inicial(db_session, f"  Jefe.{base}@Prueba.XPS ", "  Jefe de TI  ", CLAVE_ADMIN)
    assert admin.email == f"jefe.{base}@prueba.xps"
    assert admin.nombre == "Jefe de TI"
    assert admin.rol.codigo == "admin"
    assert admin.activo is True
    assert admin.forzar_cambio_password is False
    assert admin.creado_por is None


def test_aborta_si_existe_admin_activo(db_session, crear_usuario):  # T62
    crear_usuario("admin")
    with pytest.raises(ErrorNegocio) as error:
        crear_admin_inicial(db_session, f"x{uuid4().hex[:8]}@prueba.xps", "Otro Admin", CLAVE_ADMIN)
    assert (error.value.status_code, error.value.codigo) == (409, "ADMIN_YA_EXISTE")


def test_valida_politica_y_email_duplicado(db_session, crear_usuario):  # T63
    _sin_admins_activos(db_session)
    existente = crear_usuario("comercial")

    casos = [
        (f"a{uuid4().hex[:8]}@prueba.xps", "Admin", "debil", 422, "PASSWORD_DEBIL"),
        ("no-es-email", "Admin", CLAVE_ADMIN, 422, "EMAIL_INVALIDO"),
        (f"a{uuid4().hex[:8]}@prueba.xps", "   ", CLAVE_ADMIN, 422, "NOMBRE_INVALIDO"),
        (existente.email.upper(), "Admin", CLAVE_ADMIN, 409, "EMAIL_DUPLICADO"),
    ]
    for email, nombre, password, status_esperado, codigo_esperado in casos:
        with pytest.raises(ErrorNegocio) as error:
            crear_admin_inicial(db_session, email, nombre, password)
        assert (error.value.status_code, error.value.codigo) == (status_esperado, codigo_esperado)


def test_restablecer_admin_efectos(db_session, crear_usuario):  # T70
    admin = crear_usuario("admin", forzar=True)
    admin.intentos_fallidos = 4
    admin.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=10)
    db_session.commit()
    tv_previa = admin.token_version

    restablecer_password_admin(db_session, f"  {admin.email.upper()} ", "Recuperada2026")
    db_session.refresh(admin)
    assert verificar_password(admin.hash_password, "Recuperada2026")
    assert admin.forzar_cambio_password is False
    assert admin.intentos_fallidos == 0
    assert admin.bloqueado_hasta is None
    assert admin.token_version == tv_previa + 1


def test_restablecer_admin_solo_admins_activos(db_session, crear_usuario):  # T71
    comercial = crear_usuario("comercial")
    admin_inactivo = crear_usuario("admin", activo=False)
    casos = [
        ("nadie@prueba.xps", 404, "ADMIN_NO_ENCONTRADO"),
        (comercial.email, 404, "ADMIN_NO_ENCONTRADO"),
        (admin_inactivo.email, 409, "ADMIN_INACTIVO"),
    ]
    antes = {u.id: (u.hash_password, u.token_version) for u in (comercial, admin_inactivo)}
    for email, status_esperado, codigo_esperado in casos:
        with pytest.raises(ErrorNegocio) as error:
            restablecer_password_admin(db_session, email, "Recuperada2026")
        assert (error.value.status_code, error.value.codigo) == (status_esperado, codigo_esperado)
        for usuario in (comercial, admin_inactivo):
            db_session.refresh(usuario)
            assert (usuario.hash_password, usuario.token_version) == antes[usuario.id], email


def test_restablecer_admin_valida_politica(db_session, crear_usuario):  # T72
    admin = crear_usuario("admin")
    hash_previo = admin.hash_password
    with pytest.raises(ErrorNegocio) as error:
        restablecer_password_admin(db_session, admin.email, "debil")
    assert (error.value.status_code, error.value.codigo) == (422, "PASSWORD_DEBIL")
    db_session.refresh(admin)
    assert admin.hash_password == hash_previo

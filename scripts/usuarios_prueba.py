"""Lógica común de los usuarios de prueba de la verificación final (F5-C2): uno por rol.

La usan scripts/crear_usuarios_prueba.py y scripts/desactivar_usuarios_prueba.py. Nunca borra: desactivar es
activo=false. Cada alta, reactivación o baja queda en Auditoria (entidad "usuario", actor del sistema).
"""
import secrets
import string
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hashear_password, password_cumple_politica
from app.models import Rol, Usuario
from app.services import auditoria

ROLES = ("admin", "pricing", "comercial", "gerencia")
DOMINIO = "xpress.ec"


def email_de(rol: str) -> str:
    return f"prueba.{rol}@{DOMINIO}"


def password_aleatoria() -> str:
    """16 caracteres con letras y números (cumple la política: 10–128, al menos una letra y un número)."""
    alfabeto = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alfabeto) for _ in range(16))
        if password_cumple_politica(password) and any(c.isdigit() for c in password) and any(c.isalpha() for c in password):
            return password


def crear_o_reactivar(db: Session) -> list[dict[str, Any]]:
    """Crea (o reactiva) un usuario por rol con contraseña nueva y cambio obligatorio al primer ingreso."""
    salida = []
    for rol_codigo in ROLES:
        rol = db.scalars(select(Rol).where(Rol.codigo == rol_codigo)).one()
        email = email_de(rol_codigo)
        password = password_aleatoria()
        usuario = db.scalars(select(Usuario).where(Usuario.email == email)).one_or_none()
        if usuario is None:
            usuario = Usuario(email=email, nombre=f"Prueba {rol_codigo}", rol=rol, hash_password=hashear_password(password),
                              activo=True, forzar_cambio_password=True)
            db.add(usuario)
            db.flush()
            accion, nota = "CREAR", "USUARIO DE PRUEBA F5-C2"
        else:
            usuario.rol = rol
            usuario.hash_password = hashear_password(password)
            usuario.activo = True
            usuario.forzar_cambio_password = True
            usuario.token_version += 1  # invalida sesiones anteriores
            accion, nota = "EDITAR", "USUARIO DE PRUEBA F5-C2 REACTIVADO"
        auditoria.registrar(db, None, "usuario", usuario.id, accion, despues={"email": email, "rol": rol_codigo,
                                                                             "activo": True}, nota=nota)
        salida.append({"rol": rol_codigo, "email": email, "password": password})
    db.commit()
    return salida


def desactivar(db: Session) -> list[str]:
    """activo=false para los usuarios de prueba que existan y estén activos (sin borrar nada)."""
    desactivados = []
    for rol_codigo in ROLES:
        usuario = db.scalars(select(Usuario).where(Usuario.email == email_de(rol_codigo))).one_or_none()
        if usuario is None or not usuario.activo:
            continue
        usuario.activo = False
        usuario.token_version += 1
        auditoria.registrar(db, None, "usuario", usuario.id, "DESACTIVAR", antes={"activo": True},
                            despues={"activo": False}, nota="USUARIO DE PRUEBA F5-C2 DESACTIVADO")
        desactivados.append(usuario.email)
    db.commit()
    return desactivados

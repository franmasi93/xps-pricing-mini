"""Login con bloqueo por intentos fallidos y cambio de contraseña."""
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.security import (
    crear_token,
    hashear_password,
    necesita_rehash,
    validar_politica_password,
    verificar_contra_ficticio,
    verificar_password,
)
from app.models import Usuario
from app.schemas.usuarios import normalizar_email

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15


def _credenciales_invalidas() -> ErrorNegocio:
    return ErrorNegocio(401, "CREDENCIALES_INVALIDAS", "Credenciales inválidas")


def _cuenta_bloqueada(restante: timedelta) -> ErrorNegocio:
    segundos = max(1, math.ceil(restante.total_seconds()))
    minutos = math.ceil(segundos / 60)
    unidad = "minuto" if minutos == 1 else "minutos"
    return ErrorNegocio(
        429,
        "CUENTA_BLOQUEADA",
        f"Cuenta bloqueada temporalmente, intente en {minutos} {unidad}",
        headers={"Retry-After": str(segundos)},
    )


def login(db: Session, email: str, password: str) -> tuple[str, bool]:
    """Devuelve (token, forzar_cambio_password) o lanza 401 / 429."""
    usuario = db.scalars(
        select(Usuario).where(Usuario.email == normalizar_email(email)).with_for_update()
    ).one_or_none()
    if usuario is None:
        verificar_contra_ficticio(password)
        raise _credenciales_invalidas()

    ahora = datetime.now(UTC)
    if usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > ahora:
        raise _cuenta_bloqueada(usuario.bloqueado_hasta - ahora)

    if not verificar_password(usuario.hash_password, password):
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= MAX_INTENTOS:
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
            from app.services import notificaciones  # E3: aviso al administrador (outbox)

            notificaciones.usuario_bloqueado(db, usuario)
            confirmar(db)
            raise _cuenta_bloqueada(timedelta(minutes=MINUTOS_BLOQUEO))
        confirmar(db)
        raise _credenciales_invalidas()

    if not usuario.activo:
        raise _credenciales_invalidas()

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_login = ahora
    if necesita_rehash(usuario.hash_password):
        usuario.hash_password = hashear_password(password)
    confirmar(db)
    return crear_token(usuario.id, usuario.token_version), usuario.forzar_cambio_password


def cambiar_password(db: Session, usuario: Usuario, password_actual: str, password_nueva: str) -> str:
    """Cambia la contraseña del propio usuario, invalida sus tokens y devuelve uno nuevo."""
    if not verificar_password(usuario.hash_password, password_actual):
        raise ErrorNegocio(422, "PASSWORD_ACTUAL_INCORRECTA", "La contraseña actual es incorrecta")
    if password_nueva == password_actual:
        raise ErrorNegocio(422, "PASSWORD_REPETIDA", "La nueva contraseña debe ser distinta de la actual")
    validar_politica_password(password_nueva)
    usuario.hash_password = hashear_password(password_nueva)
    usuario.forzar_cambio_password = False
    usuario.token_version += 1
    confirmar(db)
    return crear_token(usuario.id, usuario.token_version)

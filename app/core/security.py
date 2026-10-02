"""Hash de contraseñas (argon2), política de contraseña y JWT (HS256)."""
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.core.errors import ErrorNegocio

ALGORITMO_JWT = "HS256"
CLAIMS_OBLIGATORIOS = ["sub", "tv", "iat", "exp"]

PASSWORD_MIN = 10
PASSWORD_MAX = 128
MENSAJE_POLITICA = (
    f"La contraseña debe tener entre {PASSWORD_MIN} y {PASSWORD_MAX} caracteres, "
    "con al menos una letra y un número"
)

_hasher = PasswordHasher()
# Hash de una clave aleatoria: se verifica contra él cuando el email no existe,
# para que el tiempo de respuesta del login sea el mismo.
_HASH_FICTICIO = _hasher.hash(secrets.token_urlsafe(32))


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(hash_password: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_password, password)
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_password: str) -> bool:
    return _hasher.check_needs_rehash(hash_password)


def verificar_contra_ficticio(password: str) -> None:
    verificar_password(_HASH_FICTICIO, password)


def password_cumple_politica(password: str) -> bool:
    return (
        PASSWORD_MIN <= len(password) <= PASSWORD_MAX
        and any(c.isalpha() for c in password)
        and any(c.isdigit() for c in password)
    )


def validar_politica_password(password: str) -> None:
    if not password_cumple_politica(password):
        raise ErrorNegocio(422, "PASSWORD_DEBIL", MENSAJE_POLITICA)


def crear_token(usuario_id: int, token_version: int) -> str:
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(usuario_id),
        "tv": token_version,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=get_settings().JWT_EXPIRA_MIN),
    }
    return jwt.encode(payload, get_settings().JWT_SECRET.get_secret_value(), algorithm=ALGORITMO_JWT)


def decodificar_token(token: str) -> dict:
    """Devuelve el payload o lanza jwt.InvalidTokenError (firma, expiración, claims)."""
    return jwt.decode(
        token,
        get_settings().JWT_SECRET.get_secret_value(),
        algorithms=[ALGORITMO_JWT],
        options={"require": CLAIMS_OBLIGATORIOS},
    )

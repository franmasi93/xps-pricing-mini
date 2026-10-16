"""Cifrado de las llaves de correo con Fernet (B2 de F4) usando CONFIG_CIFRADO_KEY.

Sin esa llave, o si no descifra, nada falla al arrancar: `descifrar` devuelve None y el correo queda
"No configurado". Ninguna función imprime ni registra valores en claro.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet | None:
    llave = get_settings().CONFIG_CIFRADO_KEY
    if llave is None:
        return None
    try:
        return Fernet(llave.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None


def disponible() -> bool:
    return _fernet() is not None


def cifrar(texto: str) -> str | None:
    fernet = _fernet()
    if fernet is None:
        return None
    return fernet.encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token: str | None) -> str | None:
    fernet = _fernet()
    if fernet is None or not token:
        return None
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def enmascarar(texto: str | None) -> str | None:
    """IKIDabcdef…XZQ3 → IKID****ZQ3: nunca más de 4 al inicio y 3 al final."""
    if not texto:
        return None
    if len(texto) <= 8:
        return "****"
    return f"{texto[:4]}****{texto[-3:]}"

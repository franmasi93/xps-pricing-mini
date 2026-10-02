import jwt
import pytest

from app.config import get_settings
from app.core.errors import ErrorNegocio
from app.core.security import (
    ALGORITMO_JWT,
    crear_token,
    hashear_password,
    validar_politica_password,
    verificar_password,
)


def test_hash_argon2_verifica_y_rechaza():  # T06
    hash_password = hashear_password("ClaveCorrecta123")
    assert hash_password.startswith("$argon2")
    assert verificar_password(hash_password, "ClaveCorrecta123") is True
    assert verificar_password(hash_password, "ClaveIncorrecta123") is False
    assert verificar_password("no-es-un-hash", "ClaveCorrecta123") is False


@pytest.mark.parametrize(
    ("password", "valida"),
    [
        ("Corta1", False),
        ("SoloLetrasSinNumero", False),
        ("1234567890123", False),
        ("a1" * 64 + "x", False),
        ("ClaveValida2026", True),
    ],
    ids=["menos_de_10", "sin_numero", "sin_letra", "mas_de_128", "valida"],
)
def test_politica_password(password, valida):  # T07
    if valida:
        validar_politica_password(password)
    else:
        with pytest.raises(ErrorNegocio) as error:
            validar_politica_password(password)
        assert error.value.status_code == 422
        assert error.value.codigo == "PASSWORD_DEBIL"


def test_jwt_claims_y_expiracion():  # T08
    token = crear_token(42, 3)
    payload = jwt.decode(
        token, get_settings().JWT_SECRET.get_secret_value(), algorithms=[ALGORITMO_JWT]
    )
    assert set(payload) == {"sub", "tv", "iat", "exp"}
    assert payload["sub"] == "42"
    assert payload["tv"] == 3
    assert payload["exp"] - payload["iat"] == get_settings().JWT_EXPIRA_MIN * 60
    assert jwt.get_unverified_header(token)["alg"] == "HS256"

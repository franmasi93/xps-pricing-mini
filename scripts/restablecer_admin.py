"""Restablece la contraseña de un administrador activo pidiendo los datos por teclado.

Uso:  .venv\\Scripts\\python.exe scripts\\restablecer_admin.py

Sirve para recuperar el acceso cuando el administrador olvidó su contraseña y no hay
otro admin que la restablezca desde la pantalla. Nada hardcodeado: la base de datos
sale de .env (DATABASE_URL, o DATABASE_URL_TEST si APP_ENV=test).
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.errors import ErrorNegocio  # noqa: E402
from app.core.security import MENSAJE_POLITICA  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.schemas.usuarios import normalizar_email  # noqa: E402
from app.services.usuarios import restablecer_password_admin  # noqa: E402


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    print(f"Restablecer contraseña de un administrador de XPS Pricing Mini (base de datos: {base})")
    print(MENSAJE_POLITICA)
    email = input("Email del administrador: ").strip()
    password = getpass.getpass("Nueva contraseña: ")
    if password != getpass.getpass("Confirme la nueva contraseña: "):
        print("Las contraseñas no coinciden. No se cambió nada.")
        return 1
    respuesta = input(
        f"Se cambiará la contraseña de {normalizar_email(email)} en la base {base}. ¿Confirma? (s/N): "
    )
    if respuesta.strip().lower() != "s":
        print("Operación cancelada. No se cambió nada.")
        return 1
    with SessionLocal() as db:
        try:
            admin = restablecer_password_admin(db, email, password)
        except ErrorNegocio as error:
            print(f"No se restableció la contraseña: {error.mensaje}")
            return 1
        resumen = admin.email
    print(f"Contraseña restablecida para {resumen}. Las sesiones abiertas quedaron cerradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Crea el administrador inicial pidiendo los datos por teclado.

Uso:  .venv\\Scripts\\python.exe scripts\\crear_admin.py

Aborta si ya existe un administrador activo. Nada hardcodeado: la base de datos
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
from app.services.usuarios import crear_admin_inicial  # noqa: E402


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    print(f"Crear administrador inicial de XPS Pricing Mini (base de datos: {base})")
    print(MENSAJE_POLITICA)
    email = input("Email: ").strip()
    nombre = input("Nombre: ").strip()
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Confirme la contraseña: "):
        print("Las contraseñas no coinciden. No se creó nada.")
        return 1
    respuesta = input(
        f"Se creará el administrador {normalizar_email(email)} en la base {base}. ¿Confirma? (s/N): "
    )
    if respuesta.strip().lower() != "s":
        print("Operación cancelada. No se cambió nada.")
        return 1
    with SessionLocal() as db:
        try:
            admin = crear_admin_inicial(db, email, nombre, password)
        except ErrorNegocio as error:
            print(f"No se creó el administrador: {error.mensaje}")
            return 1
        resumen = f"{admin.email} (id {admin.id})"
    print(f"Administrador creado: {resumen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

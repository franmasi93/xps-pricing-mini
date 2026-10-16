"""Crea (o reactiva) un usuario de prueba por rol para recorrer docs/CHECKLIST-FINAL.md (F5-C2).

Uso:  .venv\\Scripts\\python.exe scripts\\crear_usuarios_prueba.py test|trabajo

Muestra cada contraseña UNA sola vez en la consola (no se guarda en ningún archivo); al primer ingreso el sistema
exige cambiarla. Al terminar la verificación: scripts\\desactivar_usuarios_prueba.py.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2 or sys.argv[1] not in ("test", "trabajo"):
    raise SystemExit("Uso: python scripts/crear_usuarios_prueba.py test|trabajo")
os.environ["APP_ENV"] = "test" if sys.argv[1] == "test" else "dev"
sys.path[:0] = [str(RAIZ), str(RAIZ / "scripts")]

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from usuarios_prueba import crear_o_reactivar  # noqa: E402


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    if base.endswith("_test") != (sys.argv[1] == "test"):
        raise SystemExit(f"La base conectada ({base}) no corresponde a '{sys.argv[1]}'. No se cambió nada.")
    if input(f"Se crearán o reactivarán 4 usuarios de prueba en la base {base}. ¿Confirma? (s/N): ").strip().lower() != "s":
        print("Operación cancelada. No se cambió nada.")
        return 1
    with SessionLocal() as db:
        usuarios = crear_o_reactivar(db)
    print("Anote estas contraseñas ahora: no se vuelven a mostrar (el primer ingreso exige cambiarlas).")
    for usuario in usuarios:
        print(f"  {usuario['rol']:<10} {usuario['email']:<28} {usuario['password']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

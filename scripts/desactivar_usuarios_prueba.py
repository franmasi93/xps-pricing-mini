"""Da de baja (activo=false, sin borrar) los usuarios de prueba de la verificación final (F5-C2).

Uso:  .venv\\Scripts\\python.exe scripts\\desactivar_usuarios_prueba.py test|trabajo
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2 or sys.argv[1] not in ("test", "trabajo"):
    raise SystemExit("Uso: python scripts/desactivar_usuarios_prueba.py test|trabajo")
os.environ["APP_ENV"] = "test" if sys.argv[1] == "test" else "dev"
sys.path[:0] = [str(RAIZ), str(RAIZ / "scripts")]

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from usuarios_prueba import desactivar  # noqa: E402


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    if base.endswith("_test") != (sys.argv[1] == "test"):
        raise SystemExit(f"La base conectada ({base}) no corresponde a '{sys.argv[1]}'. No se cambió nada.")
    with SessionLocal() as db:
        desactivados = desactivar(db)
    print(f"Base {base}: {len(desactivados)} usuarios de prueba desactivados: {', '.join(desactivados) or 'ninguno'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Guarda cifradas en config_correo las llaves de Tencent tomadas del .env (TENCENT_SEED_SECRET_ID y _KEY).

Uso:  .venv\\Scripts\\python.exe scripts\\sembrar_correo.py test|trabajo

- test → DATABASE_URL_TEST; trabajo → DATABASE_URL. Se niega si la base no coincide con lo pedido.
- Cifra con CONFIG_CIFRADO_KEY (app/core/cifrado) a través del service del correo, con auditoría EDITAR y las
  llaves enmascaradas. No cambia el interruptor: guardar con habilitado=false no consulta a Tencent.
- Actor de la auditoría: el primer administrador activo. Solo en la base de pruebas, si no hay ninguno, se crea un
  administrador INACTIVO "semilla" (no puede iniciar sesión).
- Nunca imprime las llaves: solo su forma enmascarada. Después de sembrar las dos bases, borre del .env las líneas
  TENCENT_SEED_*.
"""
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if __name__ == "__main__":  # importado (p. ej. por cargar_configuracion_inicial.py) no toca argv ni APP_ENV
    if len(sys.argv) != 2 or sys.argv[1] not in ("test", "trabajo"):
        raise SystemExit("Uso: python scripts/sembrar_correo.py test|trabajo")
    os.environ["APP_ENV"] = "test" if sys.argv[1] == "test" else "dev"
sys.path.insert(0, str(RAIZ))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core import cifrado  # noqa: E402
from app.core.security import hashear_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Rol, Usuario  # noqa: E402
from app.services import correo  # noqa: E402

CLAVES = ("TENCENT_SEED_SECRET_ID", "TENCENT_SEED_SECRET_KEY")


def leer_semillas() -> dict[str, str]:
    valores = {}
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            clave, valor = linea.split("=", 1)
            if clave.strip() in CLAVES:
                valores[clave.strip()] = valor.strip()
    faltan = [clave for clave in CLAVES if not valores.get(clave)]
    if faltan:
        raise SystemExit(f"Faltan en el .env: {', '.join(faltan)}. No se cambió nada.")
    return valores


def actor(db, base_pruebas: bool) -> Usuario:
    admin = db.scalars(
        select(Usuario).join(Rol, Usuario.rol_id == Rol.id).where(Rol.codigo == "admin", Usuario.activo.is_(True)).order_by(Usuario.id)
    ).first()
    if admin is not None:
        return admin
    if not base_pruebas:
        raise SystemExit("La base de trabajo no tiene un administrador activo. No se cambió nada.")
    semilla = db.scalars(select(Usuario).where(Usuario.email == "semilla@prueba.xps")).one_or_none()
    if semilla is None:
        rol = db.scalars(select(Rol).where(Rol.codigo == "admin")).one()
        semilla = Usuario(email="semilla@prueba.xps", nombre="Semilla de pruebas (inactivo)", rol=rol, activo=False,
                          hash_password=hashear_password(secrets.token_urlsafe(32)))
        db.add(semilla)
        db.commit()
    return semilla


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    pruebas = sys.argv[1] == "test"
    if base.endswith("_test") != pruebas:
        raise SystemExit(f"La base conectada ({base}) no corresponde a '{sys.argv[1]}'. No se cambió nada.")
    if not cifrado.disponible():
        raise SystemExit("Falta CONFIG_CIFRADO_KEY (o no es válida) en el .env. No se cambió nada.")
    semillas = leer_semillas()
    with SessionLocal() as db:
        quien = actor(db, pruebas)
        datos = correo.actualizar_config(
            db, quien, {"secret_id": semillas[CLAVES[0]], "secret_key": semillas[CLAVES[1]]}
        )
    print(f"Base {base}: llaves guardadas cifradas · SecretId {datos['secret_id']} · estado {datos['estado']} "
          f"· auditoría a nombre de {quien.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Sube a Secret Manager los tres secretos del servicio de Cloud Run SIN mostrarlos (F5-B2). Lo ejecuta François.

Uso:  .venv\\Scripts\\python.exe scripts\\subir_secretos.py <proyecto> <conexion_cloud_sql>
      ej.: ... subir_secretos.py xps-reborn-v2 xps-reborn-v2:us-central1:xpress-db-reborn-v2

Lee del .env: DATABASE_URL (la de la base de trabajo, con la contraseña YA rotada), JWT_SECRET y CONFIG_CIFRADO_KEY.
- xps-pricing-database-url: la misma URL pero por el socket de Cloud SQL
  (postgresql+psycopg://usuario:clave@/base?host=/cloudsql/<conexion>), sin IP pública.
- xps-pricing-jwt-secret y xps-pricing-config-cifrado-key: el valor tal cual (CONFIG_CIFRADO_KEY, el MISMO del .env:
  si cambia, las llaves de Tencent guardadas en la base dejan de descifrarse).
Crea el secreto si no existe y agrega una versión nueva. Los valores viajan a gcloud por la entrada estándar, sin
salto de línea final; en pantalla solo aparecen los nombres.
"""
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402

if len(sys.argv) != 3:
    raise SystemExit("Uso: python scripts/subir_secretos.py <proyecto> <conexion_cloud_sql>")
proyecto, conexion = sys.argv[1], sys.argv[2]
gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
if gcloud is None:
    raise SystemExit("No se encontró gcloud en el PATH. Instale Google Cloud SDK y vuelva a intentar.")

ajustes = get_settings()
if ajustes.CONFIG_CIFRADO_KEY is None:
    raise SystemExit("Falta CONFIG_CIFRADO_KEY en el .env. No se subió nada.")
url = make_url(ajustes.DATABASE_URL.get_secret_value())
if url.database.endswith("_test"):
    raise SystemExit("DATABASE_URL apunta a una base _test. No se subió nada.")
url_socket = url.set(host=None, port=None, query={"host": f"/cloudsql/{conexion}"})
secretos = {
    "xps-pricing-database-url": url_socket.render_as_string(hide_password=False),
    "xps-pricing-jwt-secret": ajustes.JWT_SECRET.get_secret_value(),
    "xps-pricing-config-cifrado-key": ajustes.CONFIG_CIFRADO_KEY.get_secret_value(),
}

for nombre, valor in secretos.items():
    existe = subprocess.run([gcloud, "secrets", "describe", nombre, f"--project={proyecto}"],
                            capture_output=True, text=True).returncode == 0
    if not existe:
        creado = subprocess.run([gcloud, "secrets", "create", nombre, f"--project={proyecto}",
                                 "--replication-policy=automatic"], capture_output=True, text=True)
        if creado.returncode != 0:
            raise SystemExit(f"No se pudo crear {nombre}: {creado.stderr.strip().splitlines()[-1]}")
    version = subprocess.run([gcloud, "secrets", "versions", "add", nombre, f"--project={proyecto}", "--data-file=-"],
                             input=valor.encode("utf-8"), capture_output=True)
    if version.returncode != 0:
        raise SystemExit(f"No se pudo agregar la versión de {nombre}: "
                         f"{version.stderr.decode('utf-8', 'replace').strip().splitlines()[-1]}")
    print(f"{nombre}: {'creado y ' if not existe else ''}versión nueva agregada")
print("Listo. Ningún valor se mostró en pantalla.")

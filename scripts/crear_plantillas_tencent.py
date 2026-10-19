"""Crea en Tencent SES las plantillas de boletines (E1) y avisos (E3), y el remitente de masivos, si todavía no existen.

Uso:  .venv\\Scripts\\python.exe scripts\\crear_plantillas_tencent.py [--remitente tarifas@notificaciones.xpress.ec]

- Lee la configuración de correo de la base de trabajo (APP_ENV=dev, xps_pricing): las llaves se descifran en memoria y
  NUNCA se imprimen.
- Las plantillas se generan con app/services/plantillas_diseno.py, con los datos de la empresa (config_empresa).
- Es idempotente: si ya existe una plantilla con el mismo nombre, no se vuelve a crear. Nunca toca la 72669 (la de
  cotizaciones de F4) ni ninguna plantilla sin el prefijo "XPS-".
- Deja la lista (nombre, ID, estado) en salidas/e1/plantillas_tencent.json, sin secretos.
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("APP_ENV", "dev")

from app.db import SessionLocal  # noqa: E402
from app.models import ConfigEmpresa  # noqa: E402
from app.models.correo import CLAVES_EMPRESA  # noqa: E402
from app.services import correo, plantillas_diseno  # noqa: E402
from app.services.proveedor_correo import ErrorProveedor  # noqa: E402

TEXTO_LEGAL = (
    "Recibe este correo porque es cliente o contacto comercial de XPRESS LOGISTICS XPS S.A. Las tarifas están "
    "sujetas a la vigencia indicada, a disponibilidad de espacio y a los recargos locales que correspondan."
)
ESTADOS = {0: "aprobada", 1: "en revisión", 2: "rechazada"}


def exportar(empresa: dict[str, str]) -> None:
    carpeta = RAIZ / "docs" / "extensiones" / "plantillas"
    carpeta.mkdir(parents=True, exist_ok=True)
    for plantilla in plantillas_diseno.catalogo(empresa, TEXTO_LEGAL):
        (carpeta / f"{plantilla['nombre']}.html").write_text(plantilla["html"], encoding="utf-8")
        (carpeta / f"{plantilla['nombre']}.txt").write_text(plantillas_diseno.texto_plano(plantilla["html"]), encoding="utf-8")
        print(f"{plantilla['nombre']}: {', '.join(plantilla['variables'])}")


def main() -> None:
    remitente = sys.argv[sys.argv.index("--remitente") + 1] if "--remitente" in sys.argv else None
    with SessionLocal() as db:
        vigente = correo.config_vigente(db)
        fila = db.get(ConfigEmpresa, 1)
        empresa = {clave: getattr(fila, clave) or "" for clave in CLAVES_EMPRESA}
    if "--exportar" in sys.argv:
        exportar(empresa)
        return
    if not vigente.configurado:
        raise SystemExit("El correo no está configurado (faltan las llaves): no se creó nada.")
    proveedor = correo.fabrica_proveedor(vigente.proveedor())
    existentes = {p.nombre: p for p in proveedor.plantillas()}  # todas, aprobadas o no
    resultado = []
    for plantilla in plantillas_diseno.catalogo(empresa, TEXTO_LEGAL):
        nombre = plantilla["nombre"]
        if nombre in existentes:
            p = existentes[nombre]
            resultado.append({"nombre": nombre, "id": p.id, "estado": ESTADOS.get(p.estado, str(p.estado)), "accion": "ya existía"})
            continue
        try:
            nuevo = proveedor.crear_plantilla(nombre, plantilla["html"], plantillas_diseno.texto_plano(plantilla["html"]))
            resultado.append({"nombre": nombre, "id": nuevo, "estado": "en revisión", "accion": "creada"})
        except ErrorProveedor as error:
            resultado.append({"nombre": nombre, "id": None, "estado": None, "accion": f"ERROR {error.codigo}: {error.mensaje[:150]}"})
    if remitente:
        try:
            actuales = [r.lower() for r in proveedor.remitentes()]
            if remitente.lower() in actuales:
                resultado.append({"remitente": remitente, "accion": "ya existía"})
            else:
                proveedor.crear_remitente(remitente, "XPRESS LOGISTICS")
                resultado.append({"remitente": remitente, "accion": "creado"})
        except ErrorProveedor as error:
            resultado.append({"remitente": remitente, "accion": f"ERROR {error.codigo}: {error.mensaje[:150]}"})
    salida = RAIZ / "salidas" / "e1" / "plantillas_tencent.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    for fila_resultado in resultado:
        print(fila_resultado)


if __name__ == "__main__":
    main()

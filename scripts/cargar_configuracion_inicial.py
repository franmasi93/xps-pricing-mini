"""Carga las condiciones generales del PDF y los datos de la empresa (A4) aprobados por François el 2026-10-15.

Uso:  .venv\\Scripts\\python.exe scripts\\cargar_configuracion_inicial.py test|trabajo

Pasa por los services (configuracion.actualizar_config y empresa.actualizar_empresa): mismas validaciones y la
misma auditoría que la pantalla. Actor: el primer administrador activo (en la base de pruebas, el administrador
"semilla" de scripts/sembrar_correo.py si no hay otro). Volver a correrlo no cambia nada si los valores ya están.
Textos pendientes de revisión legal (no bloquea).
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2 or sys.argv[1] not in ("test", "trabajo"):
    raise SystemExit("Uso: python scripts/cargar_configuracion_inicial.py test|trabajo")
os.environ["APP_ENV"] = "test" if sys.argv[1] == "test" else "dev"
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.services import configuracion, empresa  # noqa: E402
from sembrar_correo import actor  # noqa: E402

CONDICIONES = """1. La presente cotización es válida hasta la fecha indicada en este documento.
2. Los valores no incluyen aranceles, tributos ni impuestos de importación, salvo los expresamente detallados. El IVA se aplica solo a los rubros del bloque Factura.
3. Para aceptar la cotización, el cliente deberá enviar su confirmación por escrito (correo electrónico o documento firmado).
4. Cambios en fletes, recargos, tasas de cambio, peso o volumen facturable podrán modificar los valores cotizados.
5. El pago deberá realizarse según las condiciones acordadas; de lo contrario, la cotización quedará sin efecto.
6. Peso facturable: se cobra sobre el mayor entre el peso real y el volumétrico. Si al recibir la carga el peso o las medidas difieren de lo declarado, el flete se reliquidará.
7. La aceptación de esta cotización implica el conocimiento y la aceptación de todos los términos aquí descritos."""

EMPRESA = {
    "empresa_departamento": "Departamento Comercial",
    "empresa_ciudad": "Guayaquil",
    "empresa_telefono": "2630102",
    "empresa_celular": "+593 98 915 4770",
    "empresa_whatsapp": "+593 98 159 3438",
    "empresa_horario": "08h30 – 13h30 / 14h30 – 17h30",
    "empresa_direccion_matriz": "Edif. Brickell Tower, PB · Av. León F. Cordero Km 11.5, Daule",
    "pago_banco": "Banco Guayaquil",
    "pago_titular": "XPRESS LOGISTICS XPS S.A.",
    "pago_tipo_cuenta": "Cta. Cte.",
    "pago_numero_cuenta": "49216238",
    "pago_ruc": "0993380090001",
    "clausula_fundamental": (
        "XPRESS LOGISTICS XPS S.A. no se responsabiliza por la carga que no ha sido asegurada; esta viaja por cuenta "
        "y riesgo del consignatario."
    ),
    "texto_legal_pie": "Las tarifas están sujetas a la vigencia indicada. Confirme su aceptación por escrito.",
}


def main() -> int:
    base = make_url(get_settings().url_bd()).database
    pruebas = sys.argv[1] == "test"
    if base.endswith("_test") != pruebas:
        raise SystemExit(f"La base conectada ({base}) no corresponde a '{sys.argv[1]}'. No se cambió nada.")
    with SessionLocal() as db:
        quien = actor(db, pruebas)
        correo_actor = quien.email
        configuracion.actualizar_config(db, quien, "condiciones_generales_pdf", CONDICIONES)
        guardado = empresa.actualizar_empresa(db, quien, EMPRESA)
    distintos = [clave for clave, valor in EMPRESA.items() if guardado[clave] != valor]
    print(f"Base {base}: condiciones generales cargadas ({len(CONDICIONES.splitlines())} puntos) · datos de la empresa "
          f"{len(EMPRESA) - len(distintos)}/{len(EMPRESA)} iguales a lo aprobado · auditoría a nombre de {correo_actor}")
    return 0 if not distintos else 1


if __name__ == "__main__":
    sys.exit(main())

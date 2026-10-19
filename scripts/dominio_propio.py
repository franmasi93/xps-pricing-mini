"""E4: mapeo del dominio propio en Cloud Run (pricing.xpress.ec y www.pricing.xpress.ec) y su estado.

Usa la API REST de Cloud Run (el componente "beta" de gcloud no es necesario) con el token de la cuenta de gcloud.
No imprime credenciales.

    python scripts/dominio_propio.py crear     # crea los dos mapeos (si no existen) y muestra los registros DNS
    python scripts/dominio_propio.py estado    # estado de los mapeos y del certificado
    python scripts/dominio_propio.py borrar    # borra los dos mapeos (la URL de Cloud Run sigue funcionando)

Requisito: la cuenta de gcloud debe haber verificado xpress.ec en Google Search Console (si no, el estado dice
PermissionDenied: ver docs/extensiones/E4-DOMINIO.md).
"""
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PROYECTO = "xps-reborn-v2"
REGION = "us-central1"
SERVICIO = "xps-pricing"
DOMINIOS = ("pricing.xpress.ec", "www.pricing.xpress.ec")
BASE = f"https://{REGION}-run.googleapis.com/apis/domains.cloudrun.com/v1/namespaces/{PROYECTO}/domainmappings"


def _token() -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    return subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True, check=True).stdout.strip()


def _pedir(metodo: str, url: str, cuerpo: dict | None = None) -> tuple[int, dict]:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    pedido = urllib.request.Request(url, data=datos, method=metodo, headers={
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as respuesta:
            return respuesta.status, json.loads(respuesta.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def crear() -> None:
    for dominio in DOMINIOS:
        codigo, respuesta = _pedir("POST", BASE, {
            "apiVersion": "domains.cloudrun.com/v1", "kind": "DomainMapping",
            "metadata": {"name": dominio, "namespace": PROYECTO},
            "spec": {"routeName": SERVICIO, "certificateMode": "AUTOMATIC"},
        })
        print(f"{dominio}: {'creado' if codigo in (200, 201) else 'ya existía' if codigo == 409 else respuesta.get('message', codigo)}")
    estado()


def estado() -> None:
    for dominio in DOMINIOS:
        codigo, respuesta = _pedir("GET", f"{BASE}/{dominio}")
        if codigo == 404:
            print(f"{dominio}: no existe el mapeo")
            continue
        status = respuesta.get("status", {})
        condiciones = {c["type"]: (c["status"], c.get("reason", "")) for c in status.get("conditions", [])}
        print(f"{dominio}: listo={condiciones.get('Ready')} certificado={condiciones.get('CertificateProvisioned')}")
        for registro in status.get("resourceRecords", []):
            print(f"   DNS → tipo {registro.get('type')} · nombre {registro.get('name') or '@'} · valor {registro.get('rrdata')}")


def borrar() -> None:
    for dominio in DOMINIOS:
        codigo, _ = _pedir("DELETE", f"{BASE}/{dominio}")
        print(f"{dominio}: {'borrado' if codigo == 200 else codigo}")


if __name__ == "__main__":
    {"crear": crear, "estado": estado, "borrar": borrar}[sys.argv[1] if len(sys.argv) > 1 else "estado"]()

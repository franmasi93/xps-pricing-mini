"""PDF de cotización (§12, D-F3-13): HTML con Jinja2 (autoescape) → PDF con Playwright síncrono.

- Fuentes y logo se incrustan en base64: nada se carga de internet al generar.
- El PDF nunca muestra costo, margen, proveedor ni tasa de cambio: la plantilla solo recibe el
  snapshot de venta (emitida) o su equivalente en vivo (vista previa del borrador).
- Navegador: PDF_NAVEGADOR = chromium (por defecto) o msedge (H12). La función es síncrona y se
  llama desde un endpoint "def" (threadpool), compatible con Windows.
"""
import base64
import re
import unicodedata
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_PLANTILLAS = RAIZ / "app" / "templates"
LOGO = RAIZ / "frontend" / "img" / "xpress-logo.png"  # H1: logo oficial a color
FUENTE_INTER = DIR_PLANTILLAS / "fonts" / "Inter.ttf"
FUENTE_MONO = DIR_PLANTILLAS / "fonts" / "JetBrainsMono.ttf"
UNIDADES = {"KG": "kg", "CBM": "m³", "WM": "W/M", "CONTENEDOR": "contenedor", "ENVIO": "envío", "PCT_VALOR": "% valor"}


def _dinero(valor: Any) -> str:
    return f"{Decimal(str(valor)):,.2f}" if valor is not None else "—"


def _unitario(valor: Any) -> str:
    """Hasta 4 decimales, con al menos 2 (los unitarios se manejan a 4)."""
    numero = Decimal(str(valor))
    texto = f"{numero:,.4f}"
    entero, decimales = texto.split(".")
    return f"{entero}.{decimales.rstrip('0').ljust(2, '0')}"


def _cantidad(valor: Any) -> str:
    numero = Decimal(str(valor))
    return f"{numero:,.4f}".rstrip("0").rstrip(".")


def _porcentaje(valor: Any) -> str:
    return f"{Decimal(str(valor)).normalize():f}"


@lru_cache(maxsize=1)
def _entorno() -> Environment:
    entorno = Environment(loader=FileSystemLoader(DIR_PLANTILLAS), autoescape=select_autoescape(["html"]))
    entorno.filters |= {
        "dinero": _dinero,
        "unitario": _unitario,
        "cantidad": _cantidad,
        "porcentaje": _porcentaje,
        "unidad": lambda codigo: UNIDADES.get(codigo, codigo),
    }
    return entorno


@lru_cache(maxsize=3)
def _base64(ruta: Path) -> str:
    return base64.b64encode(ruta.read_bytes()).decode("ascii")


def bloques_fiscales(datos: dict[str, Any]) -> list[dict[str, Any]]:
    """Líneas incluidas en dos bloques: Recibo de Caja (IVA 0%) y Factura (IVA X%)."""
    tasa = _porcentaje(datos["totales"]["iva_tasa"])
    salida = []
    for codigo, titulo in (("RECIBO_CAJA", "Recibo de Caja (IVA 0%)"), ("FACTURA", f"Factura (IVA {tasa}%)")):
        lineas = [linea for linea in datos["lineas"] if linea["bloque_fiscal"] == codigo]
        subtotal = sum((Decimal(linea["subtotal_venta_usd"]) for linea in lineas), Decimal(0))
        salida.append({"titulo": titulo, "lineas": lineas, "subtotal": subtotal})
    return salida


def renderizar_html(datos: dict[str, Any], borrador: bool) -> str:
    return _entorno().get_template("cotizacion.html").render(
        d=datos,
        borrador=borrador,
        bloques=bloques_fiscales(datos),
        logo=_base64(LOGO),
        fuente_inter=_base64(FUENTE_INTER),
        fuente_mono=_base64(FUENTE_MONO),
    )


def generar_pdf(html: str) -> bytes:
    """A4 con márgenes. Se importa aquí para que la app arranque aunque falte el navegador."""
    from playwright.sync_api import sync_playwright

    canal = get_settings().PDF_NAVEGADOR
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(channel="msedge") if canal == "msedge" else playwright.chromium.launch()
        try:
            pagina = navegador.new_page()
            pagina.set_content(html, wait_until="load")
            return pagina.pdf(
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            navegador.close()


def nombre_archivo(numero: str | None, cotizacion_id: int, razon_social: str) -> str:
    """COT-AAAA-NNNNN_<cliente-sin-caracteres-raros>.pdf (borrador: BORRADOR-<id>_...)."""
    sin_tildes = unicodedata.normalize("NFKD", razon_social).encode("ascii", "ignore").decode("ascii")
    cliente = re.sub(r"[^A-Za-z0-9]+", "-", sin_tildes).strip("-")[:60] or "cliente"
    return f"{numero or f'BORRADOR-{cotizacion_id}'}_{cliente}.pdf"

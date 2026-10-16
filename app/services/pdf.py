"""PDF de cotización (§12, D-F3-13; formato oficial de F4): HTML con Jinja2 (autoescape) → PDF con Playwright.

- Fuentes y logo se incrustan en base64 al renderizar, leídos de archivos del repo: nada se carga de internet.
- El PDF nunca muestra costo, margen, proveedor ni tasa de cambio: la plantilla solo recibe el snapshot de
  venta (emitida) o su equivalente en vivo (vista previa del borrador).
- F4 (A1): el contenido fluye a las hojas necesarias; las filas no se parten y el encabezado de la tabla se
  repite; el pie "Hoja X de Y" es el pie nativo de Chromium (pageNumber / totalPages).
- Una emitida antes de F4 no trae en su foto los datos nuevos: su PDF los omite o muestra "—" (H-F4-7).
- Navegador: PDF_NAVEGADOR = chromium (por defecto) o msedge (H12). La función es síncrona y se
  llama desde un endpoint "def" (threadpool), compatible con Windows.
"""
import base64
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.config import get_settings
from app.core.unidades import kg_a_lb, lb_a_kg

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_PLANTILLAS = RAIZ / "app" / "templates"
LOGO = RAIZ / "frontend" / "img" / "xpress-logo.png"  # H1: logo oficial a color (el mismo del modelo, F4-1)
FUENTE_INTER = DIR_PLANTILLAS / "fonts" / "Inter.ttf"
FUENTE_MONO = DIR_PLANTILLAS / "fonts" / "JetBrainsMono.ttf"
RAZON_SOCIAL = "XPRESS LOGISTICS XPS S.A."
BASE_POR_UNIDAD = {"CBM": "m³", "WM": "W/M", "ENVIO": "Envío", "PCT_VALOR": "% s/ valor", "PCT_RECIBO": "% s/ recibo"}
MODO_TEXTO = {
    "AEREO": "vía aérea",
    "LCL": "vía marítima · carga consolidada (LCL)",
    "FCL": "vía marítima · contenedor completo (FCL)",
}
INCOTERMS_EN_ORIGEN = ("EXW", "FCA", "FAS", "FOB")  # grupos E y F: el lugar es el de origen (H-F4-18)
MARCAS = {"borrador": "BORRADOR — SIN VALIDEZ", "prueba": "PRUEBA — SIN VALIDEZ"}
MARGENES = {"top": "12mm", "bottom": "16mm", "left": "11mm", "right": "11mm"}


# ---------- Formatos (A5: separador de miles, fechas dd/mm/aaaa) ----------


def _numero(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    return Decimal(str(valor))


def _dinero(valor: Any) -> str:
    """A 2 decimales con ROUND_HALF_UP (regla del proyecto); el formato de Python solo redondearía al par."""
    numero = _numero(valor)
    return f"{numero.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}" if numero is not None else "—"


def _decimales(numero: Decimal, maximo: int, minimo: int) -> str:
    """Con separador de miles, hasta `maximo` decimales y al menos `minimo`."""
    entero, decimales = f"{numero:,.{maximo}f}".split(".")
    decimales = decimales.rstrip("0").ljust(minimo, "0")
    return f"{entero}.{decimales}" if decimales else entero


def _unitario(valor: Any) -> str:
    """Hasta 4 decimales, con al menos 2 (los unitarios se manejan a 4)."""
    numero = _numero(valor)
    return _decimales(numero, 4, 2) if numero is not None else "—"


def _cantidad(valor: Any) -> str:
    numero = _numero(valor)
    return _decimales(numero, 4, 0) if numero is not None else "—"


def _peso(valor: Any) -> str:
    """Pesos y volúmenes: hasta 3 decimales (4 en m³), al menos 2."""
    numero = _numero(valor)
    return _decimales(numero, 4, 2) if numero is not None else "—"


def _porcentaje(valor: Any) -> str:
    return f"{Decimal(str(valor)).normalize():f}"


def _fecha(valor: Any) -> str:
    if not valor:
        return "—"
    dia = valor if isinstance(valor, date) else date.fromisoformat(str(valor))
    return dia.strftime("%d/%m/%Y")


fecha_corta = _fecha


def _texto(valor: Any) -> str:
    return valor if valor not in (None, "") else "—"


def _parrafos(valor: Any) -> Markup:
    """Texto con saltos de línea, escapado."""
    return Markup("<br>").join(escape(linea) for linea in str(valor or "").splitlines())


@lru_cache(maxsize=1)
def _entorno() -> Environment:
    entorno = Environment(loader=FileSystemLoader(DIR_PLANTILLAS), autoescape=select_autoescape(["html"]))
    entorno.filters |= {
        "dinero": _dinero,
        "unitario": _unitario,
        "cantidad": _cantidad,
        "peso": _peso,
        "porcentaje": _porcentaje,
        "fecha": _fecha,
        "texto": _texto,
        "parrafos": _parrafos,
    }
    return entorno


@lru_cache(maxsize=3)
def _base64(ruta: Path) -> str:
    return base64.b64encode(ruta.read_bytes()).decode("ascii")


# ---------- Datos que la plantilla presenta ----------


def _fila_linea(linea: dict[str, Any]) -> dict[str, Any]:
    """Cant., Base, P. Unit., Mínimo y Total de una línea (H-F4-6)."""
    unidad = linea["rate_unit"]
    cantidad = Decimal(linea["cantidad"])
    if unidad in ("PCT_VALOR", "PCT_RECIBO"):
        cant, unitario = _dinero(cantidad * 100), f"{_porcentaje(linea['precio_venta_unit_usd'])} %"
    elif unidad in ("KG", "CBM", "WM"):
        cant, unitario = _peso(cantidad), _unitario(linea["precio_venta_unit_usd"])
    else:
        cant, unitario = _cantidad(cantidad), _unitario(linea["precio_venta_unit_usd"])
    if unidad == "KG":
        base = linea.get("unidad_peso") or "KG"
    elif unidad == "CONTENEDOR":
        base = linea.get("tipo_equipo") or "Contenedor"
    else:
        base = BASE_POR_UNIDAD.get(unidad, unidad)
    minimo = _numero(linea.get("minimo_venta_usd"))
    total = _dinero(linea["subtotal_venta_usd"]) + (" (mín.)" if linea.get("cobro_minimo") else "")
    return {
        "concepto": linea["concepto"],
        "cant": cant,
        "base": base,
        "unitario": unitario,
        "minimo": _dinero(minimo) if minimo else "—",
        "total": total,
    }


def bloques_fiscales(datos: dict[str, Any]) -> list[dict[str, Any]]:
    """Líneas incluidas en dos bloques: Recibo de Caja (IVA 0%) y Factura (IVA X%); siempre los dos, como en F3."""
    tasa = _porcentaje(datos["totales"]["iva_tasa"])
    salida = []
    for codigo, titulo in (("RECIBO_CAJA", "Recibo de Caja (IVA 0%)"), ("FACTURA", f"Factura (IVA {tasa}%)")):
        lineas = [linea for linea in datos["lineas"] if linea["bloque_fiscal"] == codigo]
        subtotal = sum((Decimal(linea["subtotal_venta_usd"]) for linea in lineas), Decimal(0))
        salida.append({"codigo": codigo, "titulo": titulo, "filas": [_fila_linea(l) for l in lineas],
                       "subtotal": subtotal})
    return salida


def _equivalente(kilos: Any, libras: Any, unidad: str) -> tuple[str, str]:
    """(peso en la unidad elegida, equivalente en la otra), con su unidad."""
    kg = _numero(kilos)
    lb = _numero(libras)
    if kg is None and lb is None:
        return "—", ""
    if lb is None:
        lb = kg_a_lb(kg)
    if kg is None:
        kg = lb_a_kg(lb)
    if unidad == "LB":
        return f"{_peso(lb)} LB", f"{_peso(kg)} kg"
    return f"{_peso(kg)} kg", f"{_peso(lb)} LB"


def _carga(datos: dict[str, Any]) -> dict[str, Any]:
    carga = datos.get("carga") or {}
    unidad = carga.get("unidad_peso") or "KG"
    medida, sufijo = ("in", "in") if unidad == "LB" else ("cm", "cm")
    medidas = []
    for bulto in carga.get("dimensiones") or []:
        lados = [bulto.get(f"{lado}_{medida}") or bulto.get(f"{lado}_cm") for lado in ("largo", "ancho", "alto")]
        medidas.append(f"{bulto['cantidad']} × " + " × ".join(_peso(lado) for lado in lados) + f" {sufijo}")
    real, real_eq = _equivalente(carga.get("peso_kg"), carga.get("peso_lb"), unidad)
    salida = {
        "unidad": unidad,
        "medidas": medidas,
        "peso_real": real,
        "peso_real_eq": real_eq,
        "volumen": f"{_peso(carga['cbm'])} m³" if carga.get("cbm") else None,
        "contenedores": [f"{c['cantidad']} × {c['codigo']}" for c in carga.get("contenedores") or []],
    }
    if carga.get("peso_cobrable_kg"):
        cobrable, cobrable_eq = _equivalente(carga["peso_cobrable_kg"], carga.get("peso_cobrable_lb"), unidad)
        volumetrico = _numero(carga.get("peso_volumetrico_kg")) or Decimal(0)
        base = carga.get("base_cobro") or ("VOLUMETRICO" if volumetrico > (_numero(carga.get("peso_kg")) or 0) else "REAL")
        salida |= {
            "cobrable": cobrable,
            "cobrable_eq": cobrable_eq,
            "base_cobro": "Peso volumétrico" if base == "VOLUMETRICO" else "Peso real",
        }
    if carga.get("peso_medida"):
        salida["peso_medida"] = _peso(carga["peso_medida"])
    return salida


def _lugar_incoterm(datos: dict[str, Any]) -> str:
    puerto = datos["origen"] if datos["incoterm"]["codigo"] in INCOTERMS_EN_ORIGEN else datos["destino"]
    return puerto["nombre"]


def renderizar_html(datos: dict[str, Any], borrador: bool, *, marca: str | None = None) -> str:
    """marca: None (emitida), "borrador" o "prueba" (correo de prueba del administrador)."""
    if borrador and marca is None:
        marca = "borrador"
    empresa = datos.get("datos_empresa") or {}
    return _entorno().get_template("cotizacion.html").render(
        d=datos,
        e=empresa,
        razon_social=RAZON_SOCIAL,
        marca=MARCAS.get(marca) if marca else None,
        bloques=bloques_fiscales(datos),
        total_factura=Decimal(datos["totales"]["subtotal_factura"]) + Decimal(datos["totales"]["iva"]),
        carga=_carga(datos),
        modo_texto=MODO_TEXTO.get(datos["modo"], datos["modo"]),
        etiqueta_transportista="Aerolínea" if datos["modo"] == "AEREO" else "Naviera / Motonave",
        lugar_incoterm=_lugar_incoterm(datos),
        logo=_base64(LOGO),
        fuente_inter=_base64(FUENTE_INTER),
        fuente_mono=_base64(FUENTE_MONO),
    )


def pie_de_pagina(datos: dict[str, Any]) -> str:
    """Pie nativo de Chromium: razón social a la izquierda y "Hoja X de Y · fecha" a la derecha."""
    fecha = _fecha(datos.get("fecha_emision")) if datos.get("fecha_emision") else ""
    return (
        '<div style="width:100%;margin:0 11mm;border-top:1px solid #e0e1ee;padding-top:4px;display:flex;'
        'justify-content:space-between;font-family:Arial,Helvetica,sans-serif;font-size:7.4pt;color:#9997b6;">'
        f"<span>{escape(RAZON_SOCIAL)} · Cotización de servicios logísticos</span>"
        '<span>Hoja <span class="pageNumber"></span> de <span class="totalPages"></span>'
        f"{' · ' + fecha if fecha else ''}</span></div>"
    )


def generar_pdf(html: str, pie: str = "") -> bytes:
    """A4 con márgenes y pie nativo. Se importa aquí para que la app arranque aunque falte el navegador."""
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
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=pie or pie_de_pagina({}),
                margin=MARGENES,
            )
        finally:
            navegador.close()


def generar_pdf_de(datos: dict[str, Any], borrador: bool, *, marca: str | None = None) -> bytes:
    """La única función que arma el PDF (B5: el adjunto del correo sale de aquí, desde la foto congelada)."""
    return generar_pdf(renderizar_html(datos, borrador, marca=marca), pie_de_pagina(datos))


def nombre_archivo(numero: str | None, cotizacion_id: int, razon_social: str) -> str:
    """COT-AAAA-NNNNN_<cliente>.pdf (borrador: BORRADOR-<id>_...). B5: el cliente en ASCII (sin tildes, ñ→n);
    todo lo que no sea letra o número se vuelve guion, sin guiones repetidos ni al final, máximo 60 caracteres.
    """
    sin_tildes = unicodedata.normalize("NFKD", razon_social).encode("ascii", "ignore").decode("ascii")
    cliente = re.sub(r"[^A-Za-z0-9]+", "-", sin_tildes).strip("-")[:60].rstrip("-") or "cliente"
    return f"{numero or f'BORRADOR-{cotizacion_id}'}_{cliente}.pdf"

"""Diseños de las plantillas de correo de Tencent (boletines de E1 y avisos de E3), con el estilo del correo aprobado
de F4 (docs/referencias/Cotizacion_Pricing.html): estilos en línea, ancho máximo 650 px y nada de CSS externo.

Límite de Tencent (SDK oficial, Template.TemplateData): "参数值不能是html等复杂类型的数据。TemplateData (整个 JSON 结构)
总长度限制为 800 bytes". Las variables son texto plano y TODO el JSON cabe en 800 bytes. Por eso:
- los datos fijos de la empresa (dirección, teléfonos, WhatsApp, horario y texto legal) se escriben en el HTML al
  generar la plantilla, desde config_empresa y config_masivos (al cambiarlos, se regenera y Tencent la revisa de nuevo);
- las variables tienen nombres cortos y las filas de tarifas son UNA variable de texto ya formateada cada una;
- el motor llena tantas filas como quepan en los 800 bytes, y el resto va en el PDF adjunto ({{mas}}).
"""
import re
from html import escape
from typing import Any

LIMITE_TEMPLATE_DATA = 800  # bytes del JSON completo (SDK oficial de Tencent SES)
MAXIMO_VARIABLES = 40
FILAS_POR_PLANTILLA = 8
PATRON_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

AZUL, NARANJA, TINTA, SUAVE, LINEA, FONDO = "#000771", "#ED4C01", "#131235", "#6b6a8c", "#e7e7f1", "#eef0f8"
MONO = "'JetBrains Mono',Consolas,monospace"
LOGO = "https://xpress.ec/xpress-color-blanco-logo-sin-lema.png"

# Leyenda de las filas según la forma de cobro (el texto de cada fila lo arma su formateador: formas_cobro.py).
LEYENDAS = {
    "GENERAL": "Ruta · servicio · tarifa · tránsito · vigencia · aerolínea o naviera",
    "PESO_TRAMOS": "Ruta · tarifa por kg o lb según el peso · tránsito · vigencia · aerolínea",
    "VOLUMEN_WM": "Ruta · tarifa por W/M o m³ · mínimo · tránsito · vigencia · naviera",
    "UNIDAD_EQUIPO": "Ruta · tarifa por equipo · tránsito · días libres · vigencia · naviera",
    "TARIFA_PLANA": "Ruta · tarifa por envío · tránsito · vigencia · transportista",
}
TITULOS_FORMA = {
    "GENERAL": "Boletín de tarifas",
    "PESO_TRAMOS": "Tarifas por peso",
    "VOLUMEN_WM": "Tarifas de carga consolidada",
    "UNIDAD_EQUIPO": "Tarifas por contenedor o equipo",
    "TARIFA_PLANA": "Tarifas por envío",
}
NOMBRES_TENCENT = {
    "GENERAL": "XPS-Boletin-General",
    "PESO_TRAMOS": "XPS-Boletin-Peso",
    "VOLUMEN_WM": "XPS-Boletin-Volumen",
    "UNIDAD_EQUIPO": "XPS-Boletin-Equipo",
    "TARIFA_PLANA": "XPS-Boletin-Plana",
}
# Avisos de E3: (nombre en Tencent, evento, título, párrafo con variables, filas de datos [(etiqueta, variable)], comercial).
AVISOS: dict[str, tuple[str, str, str, list[tuple[str, str]], bool]] = {
    "COT_SEGUIMIENTO": (
        "XPS-Aviso-Seguimiento", "¿Pudo revisar su cotización?",
        "Le escribimos para saber si pudo revisar la cotización que le enviamos. Si tiene preguntas o desea ajustar "
        "algún dato, responda este correo y la actualizamos.",
        [("Cotización", "numero"), ("Ruta", "ruta"), ("Válida hasta", "valida_hasta")], True,
    ),
    "COT_POR_VENCER": (
        "XPS-Aviso-Por-Vencer", "Su cotización está por vencer",
        "La cotización que le enviamos vence pronto. Si desea confirmarla, responda este correo antes de la fecha "
        "indicada para mantener las tarifas.",
        [("Cotización", "numero"), ("Ruta", "ruta"), ("Vence el", "valida_hasta")], True,
    ),
    "COT_VENCIDA": (
        "XPS-Aviso-Vencida", "Su cotización venció",
        "La cotización que le enviamos ya no está vigente. Si todavía necesita el servicio, responda este correo y "
        "se la actualizamos con las tarifas de hoy.",
        [("Cotización", "numero"), ("Ruta", "ruta"), ("Venció el", "valida_hasta")], True,
    ),
    "COT_ACEPTADA_CLIENTE": (
        "XPS-Aviso-Aceptada", "Gracias por aceptar nuestra cotización",
        "Recibimos la aceptación de su cotización. Nuestro equipo le escribirá para coordinar la reserva y los "
        "documentos del embarque. Si necesita algo antes, responda este correo.",
        [("Cotización", "numero"), ("Ruta", "ruta")], True,
    ),
    "TARIFA_RUTA_INTERES": (
        "XPS-Aviso-Tarifa-Ruta", "Nueva tarifa en una ruta de su interés",
        "Tenemos una tarifa nueva o un mejor precio en una ruta que usted cotizó con nosotros.",
        [("Tarifa", "tarifa"), ("Vigente hasta", "vigencia")], True,
    ),
    "INTERNO": (
        "XPS-Aviso-Interno", "{{titulo}}", "{{mensaje}}", [("Detalle", "detalle"), ("Ver en el sistema", "enlace")],
        False,
    ),
    "RESUMEN": (
        "XPS-Resumen", "{{titulo}}", "Periodo: {{periodo}}",
        [(f"·", f"l{n}") for n in range(1, 9)] + [("Ver en el sistema", "enlace")], False,
    ),
}


def variables_de(html: str) -> list[str]:
    """Las variables {{...}} del HTML, en orden de aparición y sin repetir."""
    vistas: list[str] = []
    for nombre in PATRON_VARIABLE.findall(html or ""):
        if nombre not in vistas:
            vistas.append(nombre)
    return vistas


def _t(valor: Any) -> str:
    return escape(str(valor or "").strip())


def _cabecera(kicker: str, titulo: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
</head>
<body style="margin:0;padding:0;background-color:{FONDO};font-family:Inter,Helvetica,Arial,sans-serif;color:{TINTA};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{FONDO};">
<tr><td align="center" style="padding:20px 10px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:650px;background-color:#ffffff;border:1px solid {LINEA};border-radius:16px;">
  <tr><td align="center" style="padding:35px 20px;background-color:{AZUL};border-radius:16px 16px 0 0;">
    <img src="{LOGO}" alt="XPRESS LOGISTICS" width="160" style="display:block;border:0;max-width:60%;height:auto;">
  </td></tr>
  <tr><td style="padding:32px 28px 8px;">
    <p style="margin:0 0 10px;font-family:{MONO};font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;color:{NARANJA};">{kicker}</p>
    <h1 style="margin:0;font-size:26px;font-weight:800;line-height:1.2;letter-spacing:-0.5px;color:{AZUL};">{titulo}</h1>"""


def _pie(empresa: dict[str, str], legal: str, con_baja: bool) -> str:
    contacto = []
    if empresa.get("empresa_direccion_matriz"):
        contacto.append(f"Matriz: {_t(empresa['empresa_direccion_matriz'])}")
    telefonos = " · ".join(
        _t(empresa[c]) for c in ("empresa_telefono", "empresa_celular") if empresa.get(c)
    )
    if telefonos:
        contacto.append(f"Teléfonos: {telefonos}")
    if empresa.get("empresa_whatsapp"):
        contacto.append(f"WhatsApp: {_t(empresa['empresa_whatsapp'])}")
    if empresa.get("empresa_horario"):
        contacto.append(f"Horario: {_t(empresa['empresa_horario'])}")
    lineas = "<br>".join(contacto)
    baja = (
        f'<p style="margin:12px 0 0;font-size:11px;line-height:1.5;color:#9997b6;">Si no desea recibir más boletines, '
        f'<a href="{{{{baja}}}}" style="color:{AZUL};text-decoration:underline;">dese de baja aquí</a>.</p>'
        if con_baja else ""
    )
    return f"""
  <tr><td align="center" style="padding:26px 28px;background-color:#f6f6fb;border-top:1px solid {LINEA};border-radius:0 0 16px 16px;">
    <p style="margin:0 0 12px;font-family:{MONO};font-size:11px;letter-spacing:0.05em;text-transform:uppercase;color:{SUAVE};">XPRESS LOGISTICS XPS S.A.<br>Empresa autorizada por SENAE y MINTEL</p>
    <p style="margin:0 0 10px;font-size:12px;line-height:1.6;color:{SUAVE};">{lineas}</p>
    <p style="margin:0;font-size:11px;line-height:1.5;color:#9997b6;">{_t(legal)}</p>{baja}
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def _caja_respuesta(texto: str) -> str:
    return f"""
  <tr><td style="padding:10px 28px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#e8f0fe;border:1px solid #d5e2fb;border-radius:12px;">
      <tr><td style="padding:16px 18px;font-size:14px;line-height:1.5;color:#2563eb;">{texto}</td></tr>
    </table>
  </td></tr>"""


def html_boletin(diseno: str, empresa: dict[str, str], legal: str) -> str:
    """Plantilla de boletín: general o por forma de cobro. Variables: contacto, empresa, titulo, intro, vigencia,
    comercial, baja, f1…f8 y mas."""
    filas = "\n".join(
        f'      <p style="margin:0 0 8px;font-size:14px;line-height:1.45;color:{TINTA};word-break:break-word;">{{{{f{n}}}}}</p>'
        for n in range(1, FILAS_POR_PLANTILLA + 1)
    )
    cuerpo = f"""
    <p style="margin:18px 0 0;font-size:16px;line-height:1.6;color:{TINTA};">Estimado/a <strong>{{{{contacto}}}}</strong> ({{{{empresa}}}}):</p>
    <p style="margin:10px 0 0;font-size:15px;line-height:1.6;color:{SUAVE};">{{{{intro}}}}</p>
  </td></tr>
  <tr><td style="padding:14px 28px 6px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINEA};border-radius:16px;">
      <tr><td style="padding:14px 18px;border-bottom:1px solid {LINEA};">
        <p style="margin:0;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#9997b6;">Tarifas vigentes al {{{{vigencia}}}}</p>
        <p style="margin:4px 0 0;font-size:11px;color:#9997b6;">{_t(LEYENDAS[diseno])}</p>
      </td></tr>
      <tr><td style="padding:14px 18px 6px;">
{filas}
      </td></tr>
      <tr><td style="padding:0 18px 14px;">
        <p style="margin:0;font-family:{MONO};font-size:12px;color:{NARANJA};">{{{{mas}}}}</p>
      </td></tr>
    </table>
  </td></tr>"""
    caja = _caja_respuesta(
        "<strong>¿Desea reservar o cotizar un embarque?</strong> Responda este correo y su mensaje llegará a "
        "nuestro equipo de Pricing. Le atiende {{comercial}}."
    )
    return _cabecera("Departamento de Pricing · " + TITULOS_FORMA[diseno], "{{titulo}}") + cuerpo + caja + _pie(
        empresa, legal, con_baja=True
    )


def html_aviso(evento: str, empresa: dict[str, str], legal: str) -> str:
    """Plantilla de un aviso de E3 (externo, interno o resumen)."""
    _, titulo, parrafo, datos, externo = AVISOS[evento]
    saludo = (
        f'<p style="margin:18px 0 0;font-size:16px;line-height:1.6;color:{TINTA};">Estimado/a <strong>{{{{contacto}}}}</strong>:</p>'
        if externo else ""
    )
    filas = "\n".join(
        f'      <tr><td style="padding:12px 18px;border-bottom:1px solid {LINEA};font-size:11px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.05em;color:#9997b6;">{_t(etiqueta)}</td>'
        f'<td align="right" style="padding:12px 18px;border-bottom:1px solid {LINEA};font-size:14px;font-weight:600;'
        f'color:{AZUL};word-break:break-word;">{{{{{variable}}}}}</td></tr>'
        for etiqueta, variable in datos
    )
    cuerpo = f"""
    {saludo}
    <p style="margin:12px 0 0;font-size:15px;line-height:1.6;color:{SUAVE};">{parrafo}</p>
  </td></tr>
  <tr><td style="padding:14px 28px 6px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINEA};border-radius:16px;">
{filas}
    </table>
  </td></tr>"""
    caja = _caja_respuesta(
        "<strong>¿Preguntas?</strong> Responda este correo. Le atiende {{comercial}}." if externo
        else "Aviso automático de XPS Pricing para el equipo de XPRESS LOGISTICS."
    )
    kicker = "Departamento de Pricing" if externo else "XPS Pricing · aviso interno"
    return _cabecera(kicker, titulo) + cuerpo + caja + _pie(empresa, legal, con_baja=evento == "TARIFA_RUTA_INTERES")


def texto_plano(html: str) -> str:
    """Versión de texto de la plantilla (Tencent la pide junto con el HTML), conservando las variables."""
    texto = re.sub(r"<br\s*/?>", "\n", html)
    texto = re.sub(r"</(p|tr|h1|table)>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return "\n".join(linea.strip() for linea in texto.splitlines() if linea.strip())


def catalogo(empresa: dict[str, str], legal: str) -> list[dict[str, Any]]:
    """Todas las plantillas del sistema: (nombre en Tencent, uso, diseño, evento o forma, html, variables)."""
    salida = []
    for diseno, nombre in NOMBRES_TENCENT.items():
        html = html_boletin(diseno, empresa, legal)
        salida.append({"nombre": nombre, "uso": "BOLETIN", "diseno": diseno,
                       "evento_o_servicio": None if diseno == "GENERAL" else diseno, "html": html,
                       "variables": variables_de(html)})
    for evento, (nombre, *_resto) in AVISOS.items():
        html = html_aviso(evento, empresa, legal)
        salida.append({"nombre": nombre, "uso": "AVISO", "diseno": "AVISO", "evento_o_servicio": evento,
                       "html": html, "variables": variables_de(html)})
    return salida

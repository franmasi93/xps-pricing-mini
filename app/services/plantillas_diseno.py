"""Reglas de las plantillas de Tencent SES y utilidades para sus variables.

Las plantillas las diseña el gerente y las sube a Tencent (72746 boletín y 72747–72753 avisos, 2026-10-19). El sistema
las importa por ID y lee sus variables reales del HTML (GetEmailTemplate): esas variables mandan, y nunca se envía una
variable que la plantilla no tenga.

Límites de Tencent: el SDK oficial (Template.TemplateData) dice "参数值不能是html等复杂类型的数据。TemplateData (整个 JSON
结构) 总长度限制为 800 bytes": los valores son texto plano (sin HTML). El límite de 800 bytes NO se aplica en la cuenta:
el 2026-10-19 Tencent aceptó un envío real de la 72746 con 2.406 bytes de variables (15 filas llenas, message_id
qcloudses-30-1420342617-…). Se usa un tope técnico de 4.000 bytes: el boletín llena tantas filas como quepan (hasta 15) y
el resto va en el PDF adjunto (mas_tarifas).
"""
import re

LIMITE_TEMPLATE_DATA = 4000  # bytes del JSON completo; verificado con un envío real de 2.406 bytes (ver arriba)
MAXIMO_VARIABLES = 40
PATRON_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def variables_de(html: str) -> list[str]:
    """Las variables {{...}} del HTML, en orden de aparición y sin repetir."""
    vistas: list[str] = []
    for nombre in PATRON_VARIABLE.findall(html or ""):
        if nombre not in vistas:
            vistas.append(nombre)
    return vistas


def texto_plano(html: str) -> str:
    """Versión de texto de una plantilla (Tencent la pide junto con el HTML), conservando las variables."""
    texto = re.sub(r"(?is)<(style|head)[^>]*>.*?</\1>", "", html or "")
    texto = re.sub(r"<br\s*/?>", "\n", texto)
    texto = re.sub(r"</(p|tr|h1|h2|table|div)>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return "\n".join(linea.strip() for linea in texto.splitlines() if linea.strip())

"""Constantes únicas de conversión de unidades (D2 de F4). Siempre Decimal, nunca float.

1 lb = 0.45359237 kg y 1 in = 2.54 cm, exactos por definición. El motor trabaja en kg a 3 decimales y en cm;
lo capturado en libras o pulgadas se guarda tal cual y de ahí se derivan kg y cm (H-F4-1).
"""
from decimal import ROUND_HALF_UP, Decimal

KG_POR_LB = Decimal("0.45359237")
CM_POR_IN = Decimal("2.54")
UNIDADES_PESO = ("KG", "LB")
TRES_DECIMALES = Decimal("0.001")


def _a_3(valor: Decimal) -> Decimal:
    return valor.quantize(TRES_DECIMALES, rounding=ROUND_HALF_UP)


def lb_a_kg(libras: Decimal) -> Decimal:
    return _a_3(libras * KG_POR_LB)


def kg_a_lb(kilos: Decimal) -> Decimal:
    return _a_3(kilos / KG_POR_LB)


def in_a_cm(pulgadas: Decimal) -> Decimal:
    """Exacto: con 2 decimales en pulgadas, el resultado tiene a lo más 4 decimales en cm."""
    return pulgadas * CM_POR_IN

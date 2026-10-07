"""Precio de venta (§10.4, D-F2-3): ÚNICA fuente de cálculo de venta de tarifas, tramos y recargos.

Métodos: MANUAL (valor fijado), MARKUP costo × (1 + p/100), MARGEN costo / (1 − p/100) con p < 100,
FIJO costo + p. Decimal a 4 decimales con ROUND_HALF_UP, siempre en la moneda original.
El mínimo de venta aplica la misma fórmula al mínimo de costo; si el mínimo es 0, la venta mínima es 0.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.errors import ErrorNegocio

METODOS = ("MANUAL", "MARKUP", "MARGEN", "FIJO")
ESCALA_MONTO = 4
CUATRO_DECIMALES = Decimal("0.0001")
DOS_DECIMALES = Decimal("0.01")
CIEN = Decimal("100")
CERO = Decimal("0")


def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def validar_monto(valor: Any, campo: str, *, positivo: bool, enteros_maximos: int = 10) -> Decimal:
    """Más de 4 decimales → 422: nunca se redondea en silencio."""
    try:
        monto = Decimal(str(valor))
    except Exception:
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} debe ser un número") from None
    if not monto.is_finite():
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} debe ser un número")
    if positivo and monto <= 0:
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} debe ser mayor que 0")
    if not positivo and monto < 0:
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} no puede ser negativo")
    normalizado = monto.normalize()
    if normalizado != 0 and normalizado.as_tuple().exponent < -ESCALA_MONTO:
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} admite como máximo {ESCALA_MONTO} decimales")
    if normalizado != 0 and normalizado.adjusted() >= enteros_maximos:
        raise ErrorNegocio(422, "MONTO_INVALIDO", f"{campo} es demasiado grande")
    return monto


def validar_esquema(
    metodo: str,
    parametro: Decimal | None,
    precio_manual: Decimal | None,
    minimo: Decimal,
    minimo_manual: Decimal | None,
) -> None:
    """D-F2-3: coherencia entre el método de venta y sus campos."""
    if metodo not in METODOS:
        raise ErrorNegocio(422, "ESQUEMA_VENTA_INVALIDO", "Método de venta desconocido")
    if metodo == "MANUAL":
        if parametro is not None:
            raise ErrorNegocio(422, "ESQUEMA_VENTA_INVALIDO", "Con MANUAL el parámetro de venta debe ir vacío")
        if precio_manual is None:
            raise ErrorNegocio(422, "ESQUEMA_VENTA_INVALIDO", "Con MANUAL el precio de venta es obligatorio")
        if minimo > 0 and minimo_manual is None:
            raise ErrorNegocio(
                422, "ESQUEMA_VENTA_INVALIDO", "Con MANUAL y mínimo de costo, el mínimo de venta es obligatorio"
            )
        return
    if parametro is None:
        raise ErrorNegocio(422, "ESQUEMA_VENTA_INVALIDO", f"Con {metodo} el parámetro de venta es obligatorio")
    if precio_manual is not None or minimo_manual is not None:
        raise ErrorNegocio(
            422, "ESQUEMA_VENTA_INVALIDO", f"Con {metodo} el precio y el mínimo manuales deben ir vacíos"
        )
    if metodo == "MARGEN" and parametro >= CIEN:
        raise ErrorNegocio(422, "MARGEN_INVALIDO", "Con MARGEN el parámetro debe ser menor que 100")


def aplicar_metodo(metodo: str, base: Decimal, parametro: Decimal) -> Decimal:
    """Aplica MARKUP, MARGEN o FIJO a una base (costo, mínimo o costo por kg)."""
    if metodo == "MARKUP":
        return redondear(base * (1 + parametro / CIEN))
    if metodo == "MARGEN":
        if parametro >= CIEN:
            raise ErrorNegocio(422, "MARGEN_INVALIDO", "Con MARGEN el parámetro debe ser menor que 100")
        return redondear(base / (1 - parametro / CIEN))
    if metodo == "FIJO":
        return redondear(base + parametro)
    raise ErrorNegocio(422, "ESQUEMA_VENTA_INVALIDO", f"El método {metodo} no se calcula con fórmula")


def precio_venta(metodo: str, costo: Decimal, parametro: Decimal | None, precio_manual: Decimal | None) -> Decimal:
    if metodo == "MANUAL":
        return redondear(precio_manual)
    return aplicar_metodo(metodo, costo, parametro)


def precio_venta_minimo(
    metodo: str, minimo: Decimal, parametro: Decimal | None, minimo_manual: Decimal | None
) -> Decimal:
    if minimo == 0:
        return redondear(CERO)
    if metodo == "MANUAL":
        return redondear(minimo_manual)
    return aplicar_metodo(metodo, minimo, parametro)


def margen(venta: Decimal, costo: Decimal) -> tuple[Decimal, Decimal]:
    """(margen_unitario a 4 decimales, margen_pct a 2) sobre la venta, en la moneda original."""
    unitario = redondear(venta - costo)
    pct = (unitario / venta * CIEN).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    return unitario, pct

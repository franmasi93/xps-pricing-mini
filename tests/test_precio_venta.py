"""Fórmulas de venta (T140 a T143): services/precio_venta.py es la única fuente de cálculo."""
from decimal import Decimal

import pytest

from app.core.errors import ErrorNegocio
from app.services.precio_venta import precio_venta, precio_venta_minimo, redondear, validar_esquema

CIEN, VEINTE = Decimal("100"), Decimal("20")


@pytest.mark.parametrize(
    ("metodo", "parametro", "manual", "esperado"),
    [
        ("MARKUP", VEINTE, None, "120.0000"),
        ("MARGEN", VEINTE, None, "125.0000"),
        ("FIJO", VEINTE, None, "120.0000"),
        ("MANUAL", None, Decimal("133.5"), "133.5000"),
    ],
)
def test_formulas_costo_100_p_20(metodo, parametro, manual, esperado):  # T140
    assert str(precio_venta(metodo, CIEN, parametro, manual)) == esperado


@pytest.mark.parametrize(("parametro", "acepta"), [(Decimal("100"), False), (Decimal("99.99"), True)])
def test_margen_limite(parametro, acepta):  # T141
    if acepta:
        validar_esquema("MARGEN", parametro, None, Decimal("0"), None)
        assert precio_venta("MARGEN", CIEN, parametro, None) == Decimal("1000000.0000")
    else:
        with pytest.raises(ErrorNegocio) as error:
            validar_esquema("MARGEN", parametro, None, Decimal("0"), None)
        assert (error.value.status_code, error.value.codigo) == (422, "MARGEN_INVALIDO")


@pytest.mark.parametrize(
    ("metodo", "parametro", "minimo_manual", "esperado"),
    [
        ("MANUAL", None, Decimal("80"), "80.0000"),
        ("MARKUP", VEINTE, None, "60.0000"),
        ("MARGEN", VEINTE, None, "62.5000"),
        ("FIJO", VEINTE, None, "70.0000"),
    ],
)
def test_minimo_de_venta_por_metodo(metodo, parametro, minimo_manual, esperado):  # T142
    assert str(precio_venta_minimo(metodo, Decimal("50"), parametro, minimo_manual)) == esperado
    # Sin mínimo de costo no hay mínimo de venta, en ningún método (hueco 1 de la Parada 1).
    assert precio_venta_minimo(metodo, Decimal("0"), parametro, None) == Decimal("0")


def test_redondeo_half_up_cuatro_decimales():  # T143
    assert str(redondear(Decimal("1.00005"))) == "1.0001"
    assert str(redondear(Decimal("1.00004999"))) == "1.0000"
    assert str(precio_venta("MARKUP", Decimal("0.0001"), Decimal("50"), None)) == "0.0002"

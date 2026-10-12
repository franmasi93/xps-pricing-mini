"""Motor de cálculo (T215–T227): valores exactos calculados a mano en cada test."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.errors import ErrorNegocio
from app.services import cotizador
from app.services.cotizador import Bulto, Carga, Precios, calcular_linea, cantidad_por_unidad, totales
from fabricas import crear_moneda, crear_tasa

D = Decimal


def _bultos(*medidas) -> tuple[Bulto, ...]:
    return tuple(Bulto(cantidad, D(largo), D(ancho), D(alto)) for cantidad, largo, ancho, alto in medidas)


@pytest.mark.parametrize(
    ("peso", "medidas", "esperado"),
    [
        # 1×50×40×30 = 60 000 cm³ / 6000 = 10,000 kg < 120 kg reales → gana el real.
        ("120", [(1, 50, 40, 30)], D("120.000")),
        # 2×100×80×60 = 960 000 cm³ / 6000 = 160,000 kg > 50 kg reales → gana el volumétrico.
        ("50", [(2, 100, 80, 60)], D("160.000")),
        # 1×33×33×33 = 35 937 / 6000 = 5,9895 → 5,990 (3 decimales, ROUND_HALF_UP, sin redondeo IATA).
        ("5", [(1, 33, 33, 33)], D("5.990")),
    ],
    ids=["real_gana", "volumetrico_gana", "volumetrico_tres_decimales"],
)
def test_peso_cobrable(peso, medidas, esperado):  # T215
    carga = Carga("AEREO", peso_kg=D(peso), dimensiones=_bultos(*medidas))
    assert cotizador.peso_cobrable(carga) == esperado
    assert cotizador.cantidad_cobrable(carga) == esperado


@pytest.mark.parametrize(
    ("cbm", "peso", "medidas", "esperado"),
    [
        ("2.5", "1800", [], D("2.5000")),  # max(2,5 m³; 1,8 t) → gana el volumen
        ("1.2", "3000", [], D("3.0000")),  # max(1,2 m³; 3,0 t) → gana el peso
        (None, "500", [(3, 120, 80, 100)], D("2.8800")),  # 3×120×80×100 = 2 880 000 cm³ = 2,88 m³ > 0,5 t
        (None, "10", [(1, 33, 33, 33)], D("0.0359")),  # 35 937 cm³ = 0,035937 → 0,0359 (4 decimales) > 0,01 t
    ],
    ids=["volumen_gana", "peso_gana", "cbm_desde_dimensiones", "cbm_derivado_cuatro_decimales"],
)
def test_peso_medida_lcl(cbm, peso, medidas, esperado):  # T216
    carga = Carga("LCL", peso_kg=D(peso), cbm=D(cbm) if cbm else None, dimensiones=_bultos(*medidas))
    assert cotizador.peso_medida(carga) == esperado
    assert cotizador.cantidad_cobrable(carga) == esperado


def test_lcl_sin_cbm_ni_dimensiones_422():  # T216 (carga incompleta)
    with pytest.raises(ErrorNegocio) as error:
        cotizador.peso_medida(Carga("LCL", peso_kg=D("100")))
    assert (error.value.status_code, error.value.codigo) == (422, "CARGA_INCOMPLETA")


def test_cantidades_por_unidad_y_fcl():  # T217
    carga = Carga("FCL", peso_kg=D("20000"), cbm=D("60"), contenedores={1: 2, 2: 1}, valor_mercancia_usd=D("12345.67"))
    assert cotizador.cantidad_cobrable(carga) == D("3")
    assert cantidad_por_unidad("CONTENEDOR", carga, tipo_equipo_id=1) == D("2")
    assert cantidad_por_unidad("CONTENEDOR", carga, tipos=[2]) == D("1")
    assert cantidad_por_unidad("CONTENEDOR", carga) == D("3")
    assert cantidad_por_unidad("ENVIO", carga) == D("1")
    assert cantidad_por_unidad("CBM", carga) == D("60.0000")
    assert cantidad_por_unidad("WM", carga) == D("60.0000")  # max(60 m³; 20 t)
    assert cantidad_por_unidad("PCT_VALOR", carga) == D("123.4567")  # 12 345,67 / 100


def test_minimo_aplicado_en_costo_y_venta():  # T218
    # 2 unidades × costo 30 = 60 < mínimo 75 → costo 75. MARKUP 20 %: venta 36 × 2 = 72 < mínimo de venta 90 → 90.
    precios = Precios(costo_unit=D("30"), minimo=D("75"), venta_unit=D("36.0000"), venta_minimo=D("90.0000"))
    calculo = calcular_linea(D("2"), precios, D("1"))
    assert (calculo.costo_usd, calculo.subtotal_venta_usd) == (D("75.0000"), D("90.0000"))
    assert (calculo.precio_venta_unit_usd, calculo.minimo_venta_usd) == (D("36.0000"), D("90.0000"))
    # Sin mínimo que gane: 5 × 30 = 150; 5 × 36 = 180.
    calculo = calcular_linea(D("5"), precios, D("1"))
    assert (calculo.costo_usd, calculo.subtotal_venta_usd) == (D("150.0000"), D("180.0000"))


@pytest.mark.parametrize(
    ("peso", "desde"),
    [("44.999", 0), ("45", 45), ("99.999", 45), ("100", 100), ("999.999", 500), ("1000", 1000)],
)
def test_tramo_aereo_en_sus_bordes(peso, desde):  # T219
    tramos = [SimpleNamespace(desde_kg=d) for d in (1000, 0, 300, 45, 500, 100)]
    assert cotizador.tramo_aplicable(tramos, D(peso)).desde_kg == desde


def test_eur_y_cny_con_la_tasa_del_dia_anterior(crear_usuario, db_session):  # T220
    admin = crear_usuario("admin")
    eur, cny = crear_moneda(db_session, codigo="EUR"), crear_moneda(db_session, codigo="CNY")
    crear_tasa(db_session, eur, "1.080000", date(2026, 10, 6), admin)
    crear_tasa(db_session, eur, "1.100000", date(2026, 10, 8), admin)  # posterior: no cuenta
    crear_tasa(db_session, cny, "0.140000", date(2026, 10, 6), admin)
    dia = date(2026, 10, 7)
    tasa_eur = cotizador.tasa_vigente(db_session, "EUR", dia)
    tasa_cny = cotizador.tasa_vigente(db_session, "CNY", dia)
    assert (tasa_eur, tasa_cny) == (D("1.080000"), D("0.140000"))
    assert cotizador.tasa_vigente(db_session, "USD", dia) == D("1")
    # 10 kg a 2 EUR, MARKUP 20 % (2,40 EUR): costo 2 × 1,08 = 2,1600 USD/kg → 21,6000; venta 2,4 × 1,08 = 2,5920 → 25,9200.
    precios = Precios(costo_unit=D("2"), minimo=D("0"), venta_unit=D("2.4000"), venta_minimo=D("0"))
    calculo = calcular_linea(D("10"), precios, tasa_eur)
    assert (calculo.costo_usd, calculo.precio_venta_unit_usd, calculo.subtotal_venta_usd) == (
        D("21.6000"), D("2.5920"), D("25.9200")
    )
    # 1000 CNY × 0,14 = 140,0000 USD.
    assert cotizador.a_usd(D("1000"), tasa_cny) == D("140.0000")


def test_sin_tasa_422_sin_tasa(crear_usuario, db_session):  # T221
    gbp = crear_moneda(db_session)
    crear_tasa(db_session, gbp, "1.250000", date(2026, 10, 8), crear_usuario("admin"))  # solo una posterior
    with pytest.raises(ErrorNegocio) as error:
        cotizador.tasa_vigente(db_session, gbp.codigo, date(2026, 10, 7))
    assert (error.value.status_code, error.value.codigo) == (422, "SIN_TASA")
    assert error.value.extra == {"moneda": gbp.codigo, "fecha": "2026-10-07"}


def _linea(subtotal: str, costo: str, bloque_fiscal: str, aplica_iva: bool) -> SimpleNamespace:
    return SimpleNamespace(
        subtotal_venta_usd=D(subtotal), costo_usd=D(costo), bloque_fiscal=bloque_fiscal, aplica_iva=aplica_iva
    )


def test_iva_solo_factura_con_iva_y_margen_sin_iva():  # T222
    lineas = [
        _linea("100.0000", "80.0000", "RECIBO_CAJA", True),  # recibo de caja: nunca lleva IVA
        _linea("50.0000", "40.0000", "FACTURA", True),
        _linea("20.0000", "10.0000", "FACTURA", False),
    ]
    resultado = totales(lineas, D("15.00"))
    # Base IVA 50 × 15 % = 7,50. Total 100 + 70 + 7,50. Margen (170 − 130) / 170 = 23,529 % → 23,53.
    assert (resultado.subtotal_recibo_caja, resultado.subtotal_factura, resultado.base_iva) == (
        D("100.00"), D("70.00"), D("50.00")
    )
    assert (resultado.iva, resultado.total_general) == (D("7.50"), D("177.50"))
    assert (resultado.costo_total, resultado.margen_total, resultado.margen_pct) == (D("130.00"), D("40.00"), D("23.53"))
    # La tasa de IVA es un parámetro (se lee de la configuración), no está fija.
    assert totales(lineas, D("12.00")).iva == D("6.00")


def test_margen_cero_sin_venta():  # T222 (sin división por cero)
    resultado = totales([], D("15.00"))
    assert (resultado.total_general, resultado.margen_pct) == (D("0.00"), D("0.00"))


def test_redondeo_una_vez_sobre_la_suma():  # T223 (H8)
    # Tres líneas de 0,3350: sobre la suma 1,0050 → 1,01; redondeando cada línea serían 0,34 × 3 = 1,02.
    lineas = [_linea("0.3350", "0.1000", "RECIBO_CAJA", False) for _ in range(3)]
    assert totales(lineas, D("15.00")).subtotal_recibo_caja == D("1.01")
    # El IVA va sobre la base ya redondeada: 3 × 0,3350 = 1,0050 → 1,01 × 15 % = 0,1515 → 0,15.
    lineas = [_linea("0.3350", "0.1000", "FACTURA", True) for _ in range(3)]
    resultado = totales(lineas, D("15.00"))
    assert (resultado.base_iva, resultado.iva) == (D("1.01"), D("0.15"))


@pytest.mark.parametrize(
    ("valor", "costo_usd", "venta_usd"),
    [
        # 10 000 USD: cantidad 100; 0,35 × 100 = 35 < mínimo 50 → 50. Venta 0,42 × 100 = 42 < mínimo de venta 60 → 60.
        ("10000", D("50.0000"), D("60.0000")),
        # 50 000 USD: cantidad 500; 0,35 × 500 = 175; venta 0,42 × 500 = 210.
        ("50000", D("175.0000"), D("210.0000")),
    ],
    ids=["minimo_aplica", "sin_minimo"],
)
def test_seguro_pct_valor_con_minimo(valor, costo_usd, venta_usd):  # T224
    carga = Carga("LCL", peso_kg=D("100"), cbm=D("1"), valor_mercancia_usd=D(valor))
    precios = Precios(costo_unit=D("0.35"), minimo=D("50"), venta_unit=D("0.4200"), venta_minimo=D("60.0000"))
    calculo = calcular_linea(cantidad_por_unidad("PCT_VALOR", carga), precios, D("1"))
    assert (calculo.costo_usd, calculo.subtotal_venta_usd) == (costo_usd, venta_usd)


def test_pct_valor_sin_valor_422():  # T224 (sin valor de la mercancía)
    with pytest.raises(ErrorNegocio) as error:
        cantidad_por_unidad("PCT_VALOR", Carga("LCL", peso_kg=D("1"), cbm=D("1")))
    assert (error.value.status_code, error.value.codigo) == (422, "VALOR_MERCANCIA_REQUERIDO")


def test_prioridad_del_ajuste_manual():  # T225 (§10.4 y H9)
    precios = Precios(costo_unit=D("10"), minimo=D("0"), venta_unit=D("12.0000"), venta_minimo=D("150.0000"))
    sin_ajuste = calcular_linea(D("10"), precios, D("1"))
    assert sin_ajuste.subtotal_venta_usd == D("150.0000")  # 10 × 12 = 120 < mínimo de venta 150
    # Ajuste 9,50: 10 × 9,50 = 95, sin mínimo de venta; queda bajo el mínimo (150) y bajo el costo (100).
    ajustada = calcular_linea(D("10"), precios, D("1"), ajuste_unit_usd=D("9.5"))
    assert (ajustada.precio_venta_unit_usd, ajustada.subtotal_venta_usd) == (D("9.5000"), D("95.0000"))
    assert ajustada.precio_calculado_unit_usd == D("12.0000")
    assert (ajustada.bajo_minimo_venta, ajustada.bajo_costo) == (True, True)
    assert (sin_ajuste.bajo_minimo_venta, sin_ajuste.bajo_costo) == (False, False)


@pytest.mark.parametrize(
    ("bloque", "iso2", "esperado"),
    [
        ("FLETE_PRINCIPAL", "EC", "RECIBO_CAJA"),
        ("SEGURO", "EC", "RECIBO_CAJA"),
        ("GASTOS_DESTINO", "EC", "FACTURA"),
        ("DESPACHO_IMPORT", "EC", "FACTURA"),
        ("GASTOS_ORIGEN", "CN", "RECIBO_CAJA"),
    ],
)
def test_bloque_fiscal(bloque, iso2, esperado):  # T226 (D-F3-4)
    assert cotizador.bloque_fiscal(bloque, iso2) == esperado


def _recargo(ident, concepto, proveedor_id=None, modo=None, tipo_equipo_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=ident, concepto=concepto, proveedor_id=proveedor_id, modo=modo, tipo_equipo_id=tipo_equipo_id
    )


def test_fcl_mas_especifico_por_concepto_y_tipo():  # T227 (H6)
    hc, gp = 10, 20  # 40HC × 2 y 20GP × 1
    recargos = [
        _recargo(1, "THC", modo="FCL", tipo_equipo_id=hc),
        _recargo(2, "thc ", modo="FCL"),  # mismo concepto, genérico FCL
        _recargo(3, "BL", modo=None),
        _recargo(4, "THC", proveedor_id=99, modo="FCL", tipo_equipo_id=gp),  # otro proveedor: no entra
    ]
    elegidos = {r.id: cubre for r, cubre in cotizador.elegir_mas_especifico(recargos, 7, "FCL", [hc, gp])}
    assert elegidos == {1: (hc,), 2: (gp,), 3: (hc, gp)}
    carga = Carga("FCL", contenedores={hc: 2, gp: 1})
    assert cantidad_por_unidad("CONTENEDOR", carga, tipo_equipo_id=hc) == D("2")  # THC 40HC × 2
    assert cantidad_por_unidad("CONTENEDOR", carga, tipos=elegidos[2]) == D("1")  # THC genérico solo para el 20GP
    assert cantidad_por_unidad("ENVIO", carga) == D("1")  # BL una sola vez


def test_proveedor_antes_que_null_y_modo_antes_que_todos():  # T227 (D-F3-7)
    recargos = [
        _recargo(1, "Handling", proveedor_id=None, modo="AEREO"),
        _recargo(2, "Handling", proveedor_id=7, modo=None),  # del proveedor del flete: gana aunque sea genérico
        _recargo(3, "Seguridad", proveedor_id=None, modo=None),
        _recargo(4, "Seguridad", proveedor_id=None, modo="AEREO"),  # modo gana a todos
        _recargo(5, "Fuel", proveedor_id=8, modo="AEREO"),  # otro proveedor: no entra
    ]
    elegidos = [r.id for r, _ in cotizador.elegir_mas_especifico(recargos, 7, "AEREO")]
    assert sorted(elegidos) == [2, 4]
    # Sin proveedor de flete (D-F3-9 sin proveedor indicado): solo los propios.
    sin_flete = [r.id for r, _ in cotizador.elegir_mas_especifico(recargos, None, "AEREO")]
    assert sorted(sin_flete) == [1, 4]

"""F4 bloque D (T264–T273): kilos y libras, recargo sobre el Recibo de Caja, transportista y descripción.

Los valores esperados se calcularon a mano con Decimal (ROUND_HALF_UP), no con el motor.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.unidades import CM_POR_IN, KG_POR_LB, in_a_cm, kg_a_lb, lb_a_kg
from app.models import Cotizacion, Recargo, TramoAereo
from app.services import cotizador
from app.services.cotizaciones import _transportista
from app.services.cotizador import AVISO_SIN_BASE, Bulto, Carga
from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import payload_tarifa

D = Decimal


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _crear(client, h, payload):
    respuesta = client.post("/v1/cotizaciones", json=payload, headers=h)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _proponer(client, h, cotizacion_id):
    respuesta = client.post(f"/v1/cotizaciones/{cotizacion_id}/proponer-lineas", json={}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _flete(datos):
    return next(l for l in datos["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")


# ---------- Constantes y conversiones (T264, T265) ----------


def test_constantes_exactas_en_decimal():  # T264
    assert (KG_POR_LB, CM_POR_IN) == (D("0.45359237"), D("2.54"))
    assert isinstance(KG_POR_LB, Decimal) and isinstance(CM_POR_IN, Decimal)
    assert lb_a_kg(D("225")) == D("102.058")  # 225 × 0.45359237 = 102.05828325
    assert kg_a_lb(D("120")) == D("264.555")  # 120 / 0.45359237 = 264.5547…
    assert kg_a_lb(D("102.058")) == D("224.999")  # la ida y vuelta pierde: por eso se guarda lo capturado
    assert in_a_cm(D("40")) == D("101.60")


def test_peso_cobrable_en_libras():  # T265
    capturada = Carga(modo="AEREO", peso_kg=D("102.058"), peso_lb=D("225"))
    assert cotizador.peso_cobrable_en(capturada, "LB") == D("225.000")  # gana el real: lo capturado tal cual
    assert cotizador.peso_cobrable_en(capturada, "KG") == D("102.058")
    sin_captura = Carga(modo="AEREO", peso_kg=D("102.058"))
    assert cotizador.peso_cobrable_en(sin_captura, "LB") == D("224.999")
    # Gana el volumétrico (1 × 100 × 100 × 100 cm / 6000 = 166.667 kg): se convierte a libras.
    volumetrica = Carga(modo="AEREO", peso_kg=D("45.359"), peso_lb=D("100"),
                        dimensiones=(Bulto(1, D("100"), D("100"), D("100")),))
    assert cotizador.peso_cobrable_en(volumetrica, "LB") == D("367.438")


# ---------- Tarifas por libra (T266, T267, T270) ----------


def _escenario_lb(db_session, comercial) -> Escenario:
    """Tarifa AEREO por LB con tramos 0 / 100 / 220 lb: 2.00 / 1.80 / 1.50 USD por lb, MARKUP 20 %."""
    esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
    esc.tarifa = esc.nueva_tarifa(rate_unit="KG", unidad_peso="LB", costo="2.00", transportista="LATAM Cargo")
    for desde, costo in ((0, "2.00"), (100, "1.80"), (220, "1.50")):
        db_session.add(TramoAereo(tarifa_id=esc.tarifa.id, desde_kg=desde, costo_kg=D(costo)))
    db_session.commit()
    return esc


def test_tarifa_lb_con_tramos_carga_en_kg(client, crear_usuario, headers_de, db_session):  # T266
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario_lb(db_session, comercial)
    cotizacion = _crear(client, h, esc.payload("FCA", peso_kg="120", cbm=None))
    linea = _flete(_proponer(client, h, cotizacion["id"]))
    # 120 kg = 264.555 lb → tramo +220 (1.50 → venta 1.80) → 264.555 × 1.80 = 476.1990
    assert (linea["cantidad"], linea["unidad_peso"], linea["subtotal_venta_usd"]) == ("264.5550", "LB", "476.1990")


def test_tarifa_lb_con_carga_en_lb_usa_lo_capturado(client, crear_usuario, headers_de, db_session):  # T266
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario_lb(db_session, comercial)
    payload = esc.payload("FCA", cbm=None, unidad_peso="LB", peso_lb="225")
    payload.pop("peso_kg")
    cotizacion = _crear(client, h, payload)
    assert (cotizacion["carga"]["peso_kg"], cotizacion["carga"]["peso_lb"]) == ("102.058", "225.000")
    linea = _flete(_proponer(client, h, cotizacion["id"]))
    # 225.000 lb (no 224.999) → tramo +220 → 225 × 1.80 = 405.0000
    assert (linea["cantidad"], linea["subtotal_venta_usd"]) == ("225.0000", "405.0000")


def test_tramos_segun_la_unidad(client, crear_usuario, headers_de, db_session):  # T267
    admin = crear_usuario("admin")
    h = headers_de(admin)
    esc = Escenario(db_session, admin, modo="AEREO", con_tarifa=False)
    por_lb = esc.nueva_tarifa(rate_unit="KG", unidad_peso="LB")
    por_kg = esc.nueva_tarifa(rate_unit="KG", valido_desde=date(2027, 1, 1), valido_hasta=date(2027, 12, 31))

    def tramos(tarifa, desdes):
        cuerpo = {"tramos": [{"desde_kg": d, "costo_kg": "2"} for d in desdes]}
        return client.put(f"/v1/tarifas/{tarifa.id}/tramos", json=cuerpo, headers=h)

    assert tramos(por_lb, [0, 100, 220, 660, 1100, 2200]).status_code == 200
    malo = tramos(por_lb, [0, 45])
    assert (malo.status_code, malo.json()["detail"]["codigo"]) == (422, "TRAMOS_INVALIDOS")
    assert "desde lb" in malo.json()["detail"]["mensaje"]
    malo = tramos(por_kg, [0, 220])
    assert (malo.status_code, malo.json()["detail"]["codigo"]) == (422, "TRAMOS_INVALIDOS")
    assert tramos(por_kg, [0, 45, 100]).status_code == 200


def test_unidad_lb_solo_aereo_por_peso(client, crear_usuario, headers_de, db_session):  # T270
    h = headers_de(crear_usuario("admin"))
    respuesta = client.post("/v1/tarifas", json=payload_tarifa(db_session, "LCL", unidad_peso="LB"), headers=h)
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (422, "UNIDAD_PESO_INCOMPATIBLE")
    respuesta = client.post("/v1/tarifas", json=payload_tarifa(db_session, "AEREO", rate_unit="ENVIO", unidad_peso="LB"),
                            headers=h)
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (422, "UNIDAD_PESO_INCOMPATIBLE")
    creada = client.post("/v1/tarifas", json=payload_tarifa(db_session, "AEREO"), headers=h).json()
    assert (creada["unidad_peso"], creada["transportista"]) == ("KG", None)  # por defecto, KG


# ---------- Carga en libras con tarifa por kg (T268, T269) ----------


def test_carga_en_lb_con_tarifa_por_kg(client, crear_usuario, headers_de, db_session):  # T268
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="AEREO", rate_unit="KG", costo="2")  # venta 2.40 por kg
    payload = esc.payload("FCA", cbm=None, unidad_peso="LB", peso_lb="225")
    payload.pop("peso_kg")
    linea = _flete(_proponer(client, h, _crear(client, h, payload)["id"]))
    # 225 lb = 102.058 kg × 2.40 = 244.9392
    assert (linea["cantidad"], linea["unidad_peso"], linea["subtotal_venta_usd"]) == ("102.0580", "KG", "244.9392")


def test_medidas_en_pulgadas(client, crear_usuario, headers_de, db_session):  # T269
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="AEREO", rate_unit="KG", costo="2")
    payload = esc.payload("FCA", cbm=None, unidad_peso="LB", peso_lb="100", bultos=1,
                          dimensiones=[{"cantidad": 1, "largo_in": "40", "ancho_in": "40", "alto_in": "40"}])
    payload.pop("peso_kg")
    cotizacion = _crear(client, h, payload)
    bulto = cotizacion["carga"]["dimensiones"][0]
    assert (bulto["largo_in"], bulto["largo_cm"]) == ("40", "101.60")
    # 101.60³ cm³ / 6000 = 174.795 kg > 45.359 kg reales → gana el volumétrico
    assert (cotizacion["carga"]["peso_cobrable_kg"], cotizacion["carga"]["base_cobro"]) == ("174.795", "VOLUMETRICO")
    linea = _flete(_proponer(client, h, cotizacion["id"]))
    assert (linea["cantidad"], linea["subtotal_venta_usd"]) == ("174.7950", "419.5080")  # × 2.40
    sin_pulgadas = esc.payload("FCA", cbm=None, unidad_peso="LB", peso_lb="100",
                               dimensiones=[{"cantidad": 1, "largo_cm": "40", "ancho_cm": "40", "alto_cm": "40"}])
    sin_pulgadas.pop("peso_kg")
    respuesta = client.post("/v1/cotizaciones", json=sin_pulgadas, headers=h)
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (422, "CARGA_INVALIDA")


# ---------- Recargo porcentual sobre el Recibo de Caja (T271) ----------


def _escenario_pct(db_session, comercial) -> Escenario:
    """LCL: flete 120 por W/M (recibo de caja); en destino (Ecuador, factura) "Manejo local" 6 % con mínimo 30
    USD y un seguro de 1 % del valor (recibo de caja, se propone apagado)."""
    esc = Escenario(db_session, comercial)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="Manejo local", rate_unit="PCT_RECIBO",
                  costo="5", minimo="25", metodo_venta="MANUAL", parametro_venta=None, precio_venta_manual="6",
                  minimo_venta_manual="30")
    crear_recargo(db_session, esc.destino, "SEGURO", "DESTINO", concepto="Seguro", rate_unit="PCT_VALOR", costo="1",
                  metodo_venta="MANUAL", parametro_venta=None, precio_venta_manual="1", aplica_iva=False)
    return esc


def _linea(datos, concepto):
    return next(l for l in datos["lineas"] if l["concepto"] == concepto)


def test_pct_recibo_minimo_porcentaje_y_seguro(client, crear_usuario, headers_de, db_session):  # T271
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario_pct(db_session, comercial)

    # Debajo del mínimo: base 2.5 W/M × 120 = 300 → 6 % = 18 < 30 → se cobra 30.
    chica = _proponer(client, h, _crear(client, h, esc.payload("FOB", valor_mercancia_usd="10000"))["id"])
    manejo = _linea(chica, "Manejo local")
    assert (manejo["cantidad"], manejo["subtotal_venta_usd"], manejo["bloque_fiscal"]) == ("3.0000", "30.0000", "FACTURA")

    # Encima del mínimo: base 10 W/M × 120 = 1 200 → 6 % = 72.
    grande = _crear(client, h, esc.payload("FOB", cbm="10", valor_mercancia_usd="10000"))
    datos = _proponer(client, h, grande["id"])
    assert _linea(datos, "Manejo local")["subtotal_venta_usd"] == "72.0000"
    # Seguro encendido (1 % de 10 000 = 100, recibo de caja): base 1 300 → 78; apagado, vuelve a 72.
    seguro = _linea(datos, "Seguro")
    encendido = client.patch(f"/v1/cotizaciones/{grande['id']}/lineas/{seguro['id']}", json={"incluida": True}, headers=h)
    assert _linea(encendido.json(), "Manejo local")["subtotal_venta_usd"] == "78.0000"
    fila = db_session.scalars(select(Cotizacion).where(Cotizacion.id == grande["id"])).one()
    db_session.refresh(fila)
    guardada = next(l for l in fila.lineas if l.concepto == "Manejo local")
    db_session.refresh(guardada)
    assert (guardada.cantidad, guardada.subtotal_venta_usd) == (D("13.0000"), D("78.0000"))  # también guardada
    apagado = client.patch(f"/v1/cotizaciones/{grande['id']}/lineas/{seguro['id']}", json={"incluida": False}, headers=h)
    assert _linea(apagado.json(), "Manejo local")["subtotal_venta_usd"] == "72.0000"


def test_pct_recibo_sin_base_vale_cero(client, crear_usuario, headers_de, db_session):  # T271 (H-F4-4)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario_pct(db_session, comercial)
    # CIF importación: sin flete; los gastos en Ecuador van a factura → la base del recibo es 0.
    datos = _proponer(client, h, _crear(client, h, esc.payload("CIF"))["id"])
    manejo = _linea(datos, "Manejo local")
    assert (manejo["cantidad"], manejo["subtotal_venta_usd"]) == ("0.0000", "0.0000")  # sin mínimo
    assert AVISO_SIN_BASE in datos["avisos"]
    vista = client.get(f"/v1/cotizaciones/{datos['id']}", headers=h).json()
    assert AVISO_SIN_BASE in vista["avisos"]


def test_pct_recibo_solo_usd_y_fuera_del_seguro(client, crear_usuario, headers_de, db_session):  # T271
    from fabricas import crear_moneda, payload_recargo

    h = headers_de(crear_usuario("admin"))
    eur = crear_moneda(db_session)
    otra = client.post("/v1/recargos", json=payload_recargo(db_session, rate_unit="PCT_RECIBO", moneda_id=eur.id), headers=h)
    assert (otra.status_code, otra.json()["detail"]["codigo"]) == (422, "PCT_RECIBO_SOLO_USD")
    seguro = client.post(
        "/v1/recargos", json=payload_recargo(db_session, rate_unit="PCT_RECIBO", bloque_incoterm="SEGURO"), headers=h
    )
    assert (seguro.status_code, seguro.json()["detail"]["codigo"]) == (422, "SEGURO_UNIDAD_INVALIDA")
    bien = client.post("/v1/recargos", json=payload_recargo(db_session, rate_unit="PCT_RECIBO", costo="6"), headers=h)
    assert (bien.status_code, bien.json()["rate_unit"]) == (201, "PCT_RECIBO")
    assert db_session.get(Recargo, bien.json()["id"]).rate_unit == "PCT_RECIBO"


# ---------- Transportista y descripción (T272, T273) ----------


def test_transportista_copiado_editado_y_congelado(client, crear_usuario, headers_de, db_session):  # T272
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    esc = _escenario_lb(db_session, comercial)
    cotizacion = _crear(client, h, esc.payload("FCA", peso_kg="120", cbm=None))
    _proponer(client, h, cotizacion["id"])
    vista = client.get(f"/v1/cotizaciones/{cotizacion['id']}", headers=h).json()
    fila = db_session.get(Cotizacion, cotizacion["id"])
    db_session.refresh(fila)
    assert fila.transportista == "LATAM Cargo"
    assert (vista["estado"], vista["transportista"]) == ("BORRADOR", "LATAM Cargo")
    editada = client.patch(f"/v1/cotizaciones/{cotizacion['id']}", json={"transportista": "Avianca Cargo"}, headers=h)
    assert editada.status_code == 200
    assert editada.json()["lineas"]  # cambiar el transportista no borra las líneas
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h).status_code == 200
    db_session.refresh(fila)
    assert fila.snapshot_emision["transportista"] == "Avianca Cargo"
    tarde = client.patch(f"/v1/cotizaciones/{cotizacion['id']}", json={"transportista": "Otro"}, headers=h)
    assert (tarde.status_code, tarde.json()["detail"]["codigo"]) == (409, "COTIZACION_NO_EDITABLE")


def test_transportistas_distintos_unidos():  # T272 (H-F4-5)
    tarifas = [SimpleNamespace(transportista=t) for t in ("MSC", None, "Maersk", "MSC", " ")]
    assert _transportista(tarifas) == "MSC / Maersk"
    assert _transportista([SimpleNamespace(transportista=None)]) is None


def test_descripcion_de_la_carga_congelada(client, crear_usuario, headers_de, db_session):  # T273
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    esc = Escenario(db_session, comercial)
    cotizacion = _crear(client, h, esc.payload("FOB", descripcion_carga="  Repuestos automotrices  "))
    assert db_session.get(Cotizacion, cotizacion["id"]).descripcion_carga == "Repuestos automotrices"
    _proponer(client, h, cotizacion["id"])
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h).status_code == 200
    fila = db_session.get(Cotizacion, cotizacion["id"])
    db_session.refresh(fila)
    assert fila.snapshot_emision["descripcion_carga"] == "Repuestos automotrices"
    tarde = client.patch(f"/v1/cotizaciones/{cotizacion['id']}", json={"descripcion_carga": "Otra"}, headers=h)
    assert tarde.status_code == 409

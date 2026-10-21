"""FIX cotizador (TFX-01 a TFX-10): al elegir la tarifa aparecen los recargos del proveedor y los propios de XPRESS,
en Recibo de Caja y Factura; los de fuera del Incoterm y las alternativas (D-F3-7) llegan desmarcados y se pueden
marcar; "¿Por qué no aparece?" explica cada recargo que quedó fuera. Los precios no cambian (F3 al centavo en
test_regresion_f3.py)."""
from decimal import Decimal

import pytest

from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_proveedor, crear_puerto, tipo_equipo

INCOTERM = {"LCL": "FOB", "FCL": "FOB", "AEREO": "FCA"}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _escenario(db_session, comercial, modo):
    extra = {"tipo_equipo_id": tipo_equipo(db_session, "40HC").id} if modo == "FCL" else {}
    return Escenario(db_session, comercial, modo=modo, **extra)


def _cotizacion(client, h, esc, modo):
    creada = client.post("/v1/cotizaciones", json=esc.payload(INCOTERM[modo]), headers=h)
    assert creada.status_code == 201, creada.text
    propuesta = client.post(f"/v1/cotizaciones/{creada.json()['id']}/proponer-lineas", json={}, headers=h)
    assert propuesta.status_code == 200, propuesta.text
    return propuesta.json()


def _linea(cotizacion, recargo):
    return next(l for l in cotizacion["lineas"] if l["recargo_id"] == recargo.id)


def _marcar(client, h, cotizacion, linea, incluida: bool):
    return client.patch(f"/v1/cotizaciones/{cotizacion['id']}/lineas/{linea['id']}", json={"incluida": incluida}, headers=h)


@pytest.mark.parametrize("modo", ["FCL", "LCL", "AEREO"])
def test_caso_real_recargos_del_proveedor_y_propios_aparecen(client, crear_usuario, headers_de, db_session, modo):  # TFX-01
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, modo)
    del_proveedor = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="Servicio Logístico",
                                  proveedor_id=esc.proveedor.id, modo=modo)
    propio = crear_recargo(db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO", concepto="Agenciamiento")
    fuera = crear_recargo(db_session, esc.origen, "RECOGIDA_ORIGEN", "ORIGEN", concepto="Recogida en origen",
                          proveedor_id=esc.proveedor.id)
    cotizacion = _cotizacion(client, h, esc, modo)
    a, b, c = _linea(cotizacion, del_proveedor), _linea(cotizacion, propio), _linea(cotizacion, fuera)
    assert (a["seleccion"], a["incluida"], a["bloque_fiscal"]) == ("INCOTERM", True, "FACTURA")  # Ecuador → Factura
    assert (b["seleccion"], b["incluida"], b["bloque_fiscal"]) == ("INCOTERM", True, "FACTURA")
    assert "proveedor_propio" not in b and "proveedor" not in b  # D-R1: el comercial no recibe el proveedor
    assert (c["seleccion"], c["incluida"], c["bloque_fiscal"]) == ("FUERA_INCOTERM", False, "RECIBO_CAJA")  # exterior
    assert cotizacion["sin_recargos"] is False
    flete = next(l for l in cotizacion["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")
    t = cotizacion["totales"]
    assert Decimal(t["subtotal_factura"]) == Decimal(a["subtotal_venta_usd"]) + Decimal(b["subtotal_venta_usd"])
    assert Decimal(t["subtotal_recibo_caja"]) == Decimal(flete["subtotal_venta_usd"])  # lo desmarcado no se cobra


def test_fuera_del_incoterm_marcar_suma_y_desmarcar_resta(client, crear_usuario, headers_de, db_session):  # TFX-02
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    fuera = crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN", proveedor_id=esc.proveedor.id)
    cotizacion = _cotizacion(client, h, esc, "LCL")
    total = Decimal(cotizacion["totales"]["total_general"])
    linea = _linea(cotizacion, fuera)
    marcada = _marcar(client, h, cotizacion, linea, True)
    assert marcada.status_code == 200, marcada.text
    assert Decimal(marcada.json()["totales"]["total_general"]) == total + Decimal(linea["subtotal_venta_usd"])
    desmarcada = _marcar(client, h, cotizacion, linea, False).json()
    assert Decimal(desmarcada["totales"]["total_general"]) == total


def test_recargo_del_incoterm_se_puede_desmarcar_y_el_flete_no(client, crear_usuario, headers_de, db_session):  # TFX-03
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    recargo = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", aplica_iva=False)
    cotizacion = _cotizacion(client, h, esc, "LCL")
    linea = _linea(cotizacion, recargo)
    sin = _marcar(client, h, cotizacion, linea, False)
    assert sin.status_code == 200, sin.text
    sin = sin.json()
    assert Decimal(sin["totales"]["total_general"]) == Decimal(cotizacion["totales"]["total_general"]) - Decimal(linea["subtotal_venta_usd"])
    flete = next(l for l in cotizacion["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")
    respuesta = _marcar(client, h, cotizacion, flete, False)
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (422, "LINEA_NO_OPCIONAL")


def test_alternativa_d_f3_7_se_elige_en_lugar_del_ganador(client, crear_usuario, headers_de, db_session):  # TFX-04
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    ganador = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC", proveedor_id=esc.proveedor.id)
    alternativa = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="thc", costo="80")
    cotizacion = _cotizacion(client, h, esc, "LCL")
    g, alt = _linea(cotizacion, ganador), _linea(cotizacion, alternativa)
    assert (g["incluida"], alt["incluida"], alt["seleccion"]) == (True, False, "ALTERNATIVA")
    elegida = _marcar(client, h, cotizacion, alt, True)
    assert elegida.status_code == 200, elegida.text
    elegida = elegida.json()
    assert (_linea(elegida, ganador)["incluida"], _linea(elegida, alternativa)["incluida"]) == (False, True)  # uno por concepto
    esperado = Decimal(cotizacion["totales"]["total_general"]) - Decimal(g["subtotal_venta_usd"]) * Decimal("1.15") \
        + Decimal(alt["subtotal_venta_usd"]) * Decimal("1.15")
    assert abs(Decimal(elegida["totales"]["total_general"]) - esperado) <= Decimal("0.02")


def test_filtros_de_correlacion_y_por_que_no_aparece(client, crear_usuario, headers_de, db_session):  # TFX-05
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "FCL")
    gp = tipo_equipo(db_session, "20GP")
    otro_puerto = crear_puerto(db_session, pais=esc.destino.pais, tipo="MARITIMO")
    descartes = {
        "otro proveedor": crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO",
                                        proveedor_id=crear_proveedor(db_session).id),
        "otro puerto": crear_recargo(db_session, otro_puerto, "GASTOS_DESTINO", "DESTINO", proveedor_id=esc.proveedor.id),
        "otro tipo de contenedor": crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", modo="FCL",
                                                 tipo_equipo_id=gp.id, rate_unit="CONTENEDOR"),
        "vencido el 31/05/2026": crear_recargo(db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO",
                                               valido_hasta="2026-05-31"),
        "inactivo": crear_recargo(db_session, esc.destino, "ENTREGA_FINAL", "DESTINO", activo=False),
        "es el ORIGEN de esta cotización": crear_recargo(db_session, esc.origen, "GASTOS_DESTINO", "DESTINO",
                                                         proveedor_id=esc.proveedor.id),  # el caso real de producción
        "otro servicio": crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", modo="LCL"),
    }
    cotizacion = _cotizacion(client, h, esc, "FCL")
    en_panel = {l["recargo_id"] for l in cotizacion["lineas"] if l["recargo_id"]}
    assert en_panel.isdisjoint({r.id for r in descartes.values()})
    respuesta = client.get(f"/v1/cotizaciones/{cotizacion['id']}/recargos-descartados", headers=h)
    assert respuesta.status_code == 200, respuesta.text
    motivos = {r["recargo_id"]: " · ".join(r["motivos"]) for r in respuesta.json()["recargos"]}
    for clave, recargo in descartes.items():
        assert clave in motivos[recargo.id], (clave, motivos.get(recargo.id))
    cruzado = motivos[descartes["es el ORIGEN de esta cotización"].id]
    assert esc.destino.codigo in cruzado and "debería estar en" in cruzado


def test_sin_recargos_avisa(client, crear_usuario, headers_de, db_session):  # TFX-06
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    cotizacion = _cotizacion(client, h, esc, "LCL")
    assert cotizacion["sin_recargos"] is True
    assert "Esta tarifa no tiene recargos cargados para este puerto y servicio" in cotizacion["avisos"]


def test_comercial_sin_costo_ni_margen_y_gerencia_ve_margen(client, crear_usuario, headers_de, db_session):  # TFX-07
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", proveedor_id=esc.proveedor.id)
    crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN")
    cotizacion = _cotizacion(client, h, esc, "LCL")
    prohibidas = {"costo_usd", "costo_unit_original", "minimo_original", "precio_calculado_unit_usd", "margen_usd"}
    assert all(prohibidas.isdisjoint(linea) for linea in cotizacion["lineas"])
    assert {"costo_total", "margen_total", "margen_pct"}.isdisjoint(cotizacion["totales"])
    assert client.get(f"/v1/cotizaciones/{cotizacion['id']}/recargos-descartados", headers=h).status_code == 403
    gerencia = headers_de(crear_usuario("gerencia"))
    vista = client.get(f"/v1/cotizaciones/{cotizacion['id']}", headers=gerencia).json()
    for linea in vista["lineas"]:
        assert Decimal(linea["margen_usd"]) == Decimal(linea["subtotal_venta_usd"]) - Decimal(linea["costo_usd"])
    assert {"costo_total", "margen_total", "margen_pct"} <= set(vista["totales"])
    linea = vista["lineas"][-1]
    assert client.patch(f"/v1/cotizaciones/{cotizacion['id']}/lineas/{linea['id']}", json={"incluida": True},
                        headers=gerencia).status_code == 403  # gerencia ve, no edita
    assert client.get(f"/v1/cotizaciones/{cotizacion['id']}/recargos-descartados", headers=gerencia).status_code == 403


def test_pdf_solo_lineas_activas(client, crear_usuario, headers_de, db_session):  # TFX-08
    from app.models import Cotizacion
    from app.services import pdf

    cargar_condiciones(db_session)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN", concepto="Handling NO COBRADO")
    cobrado = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="Handling COBRADO")
    cotizacion = _cotizacion(client, h, esc, "LCL")
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    db_session.expire_all()
    html = pdf.renderizar_html(db_session.get(Cotizacion, cotizacion["id"]).snapshot_emision, False)
    assert cobrado.concepto in html and "Handling NO COBRADO" not in html  # el PDF solo lleva las líneas activas
    assert esc.proveedor.nombre not in html and "costo" not in html.lower()


def test_pantallas_del_cotizador(client):  # TFX-09
    from test_frontend import PATRONES_PROHIBIDOS_JS

    pagina = client.get("/app/cotizador.html").text
    assert 'id="paso-cargos"' in pagina and "js/cargos.js" in pagina and "btn-proponer" not in pagina
    for script in ("cargos.js", "cotizador.js", "cotizacion.js"):
        texto = client.get(f"/app/js/{script}").text
        assert [p for p in PATRONES_PROHIBIDOS_JS if p in texto] == []
    assert "recargos-descartados" in client.get("/app/js/cotizador.js").text


def test_migracion_seleccion_no_toca_lineas_viejas(db_session, crear_usuario):  # TFX-10
    from sqlalchemy import text

    columnas = db_session.execute(text(
        "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'linea_cotizacion' AND column_name = 'seleccion'"
    )).scalar_one()
    assert columnas == "YES"

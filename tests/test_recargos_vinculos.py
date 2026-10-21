"""Recargos vinculados a tarifas, bloque fiscal en el recargo y proveedor solo interno (TRV-01 a TRV-12).

D-R1: el proveedor nunca llega al cliente (PDF, correo) ni al comercial (JSON); sí a admin, pricing y gerencia.
D-R2: un recargo vinculado a una tarifa sale primero al elegirla, con el puerto de la tarifa según su lado, y le gana a
uno general del mismo concepto. D-R3: el recargo dice si va en Recibo de Caja o en Factura.
Los precios de F3 al centavo los vigila test_regresion_f3.py.
"""
import io
import json
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Auditoria, Recargo, RecargoTarifa
from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_proveedor, payload_recargo
from test_f4_correo import _con_llaves, _sin_red, falso, llave  # noqa: F401 - fixtures de F4

SECRETO = "PROVEEDOR-SECRETO-RX"


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _cotizacion(client, h, esc, incoterm="FOB", tarifas=None):
    creada = client.post("/v1/cotizaciones", json=esc.payload(incoterm), headers=h)
    assert creada.status_code == 201, creada.text
    cuerpo = {"tarifas": tarifas} if tarifas else {}
    propuesta = client.post(f"/v1/cotizaciones/{creada.json()['id']}/proponer-lineas", json=cuerpo, headers=h)
    assert propuesta.status_code == 200, propuesta.text
    return propuesta.json()


def _linea(cotizacion, recargo):
    return next((l for l in cotizacion["lineas"] if l["recargo_id"] == recargo.id), None)


def _vinculado(db_session, puerto_lado, tarifa, **cambios) -> Recargo:
    """Recargo SIN puerto, vinculado a la tarifa (D-R2)."""
    recargo = crear_recargo(db_session, puerto_lado, cambios.pop("bloque", "GASTOS_DESTINO"), cambios.pop("lado", "DESTINO"),
                            **cambios)
    recargo.puerto_id = None
    db_session.add(RecargoTarifa(recargo_id=recargo.id, tarifa_id=tarifa.id))
    db_session.commit()
    return recargo


# ---------- D-R1: proveedor solo interno ----------


def test_proveedor_no_llega_al_cliente_ni_al_comercial(client, crear_usuario, headers_de, db_session, falso):  # TRV-01
    cargar_condiciones(db_session)
    _con_llaves(db_session)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="LCL")
    esc.proveedor.nombre = SECRETO
    esc.contacto.email = "compras@cliente-prueba.ec"
    db_session.commit()
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="Servicio Logístico", proveedor_id=esc.proveedor.id)
    cotizacion = _cotizacion(client, h, esc)
    assert SECRETO not in json.dumps(cotizacion, ensure_ascii=False)
    assert all("proveedor" not in l and "proveedor_id" not in l for l in cotizacion["lineas"])
    opciones = client.get(f"/v1/cotizaciones/{cotizacion['id']}/opciones-flete", headers=h).json()
    assert SECRETO not in json.dumps(opciones, ensure_ascii=False)
    pricing = headers_de(crear_usuario("pricing"))
    interna = client.get(f"/v1/cotizaciones/{cotizacion['id']}", headers=pricing).json()
    assert {l["proveedor"] for l in interna["lineas"]} == {SECRETO}  # internamente sí se ve
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    pdf = client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h)
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Servicio Logístico" in texto and SECRETO not in texto
    envio = client.post(f"/v1/cotizaciones/{cotizacion['id']}/enviar", json={"cc_contacto_ids": []}, headers=h)
    assert envio.status_code == 200, envio.text
    mensaje = falso.enviados[-1]
    crudo = json.dumps(mensaje.datos_plantilla, ensure_ascii=False) + mensaje.asunto + mensaje.adjunto_nombre
    assert SECRETO not in crudo


# ---------- D-R2: vínculos ----------


def test_vinculado_sin_puerto_aparece_con_su_tarifa_y_no_con_otra(client, crear_usuario, headers_de, db_session):  # TRV-02
    comercial = crear_usuario("pricing")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="LCL")
    otra = esc.nueva_tarifa(proveedor_id=crear_proveedor(db_session).id)
    destino = _vinculado(db_session, esc.destino, esc.tarifa, concepto="Servicio Logístico", proveedor_id=esc.proveedor.id)
    origen = _vinculado(db_session, esc.origen, esc.tarifa, concepto="Handling origen", bloque="GASTOS_ORIGEN", lado="ORIGEN",
                        bloque_fiscal="RECIBO_CAJA")
    con_su_tarifa = _cotizacion(client, h, esc, tarifas={"LCL": esc.tarifa.id})
    d, o = _linea(con_su_tarifa, destino), _linea(con_su_tarifa, origen)
    assert (d["vinculado"], d["seleccion"], d["incluida"], d["bloque_incoterm"]) == (True, "INCOTERM", True, "GASTOS_DESTINO")
    assert (o["vinculado"], o["seleccion"], o["bloque_fiscal"]) == (True, "FUERA_INCOTERM", "RECIBO_CAJA")  # FOB: origen fuera
    con_otra = _cotizacion(client, h, esc, tarifas={"LCL": otra.id})
    assert _linea(con_otra, destino) is None and _linea(con_otra, origen) is None
    motivos = {r["recargo_id"]: " ".join(r["motivos"]) for r in
               client.get(f"/v1/cotizaciones/{con_otra['id']}/recargos-descartados", headers=h).json()["recargos"]}
    assert f"vinculado a otra tarifa (#{esc.tarifa.id})" in motivos[destino.id]


def test_vinculado_le_gana_al_general_del_mismo_concepto(client, crear_usuario, headers_de, db_session):  # TRV-03
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="LCL")
    general = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC", proveedor_id=esc.proveedor.id,
                            tipo_equipo_id=None, modo="LCL")
    vinculado = _vinculado(db_session, esc.destino, esc.tarifa, concepto="thc")
    cotizacion = _cotizacion(client, h, esc)
    v, g = _linea(cotizacion, vinculado), _linea(cotizacion, general)
    assert (v["incluida"], v["vinculado"], g["incluida"], g["seleccion"]) == (True, True, False, "ALTERNATIVA")


def test_vinculo_por_servicio(client, crear_usuario, headers_de, db_session):  # TRV-04
    admin = headers_de(crear_usuario("admin"))
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial, modo="LCL")
    solo_fcl = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino, servicios=["FCL"]), headers=admin)
    solo_lcl = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino, servicios=["LCL"]), headers=admin)
    assert solo_fcl.status_code == 201 and solo_lcl.status_code == 201, solo_fcl.text
    lineas = {l["recargo_id"]: l for l in _cotizacion(client, headers_de(comercial), esc)["lineas"] if l["recargo_id"]}
    assert solo_fcl.json()["id"] not in lineas and lineas[solo_lcl.json()["id"]]["vinculado"] is True


def test_api_vinculos_validaciones_y_auditoria(client, crear_usuario, headers_de, db_session):  # TRV-05
    admin = crear_usuario("admin")
    h = headers_de(admin)
    esc = Escenario(db_session, admin, modo="LCL")
    sin_nada = payload_recargo(db_session, esc.destino) | {"puerto_id": None}
    respuesta = client.post("/v1/recargos", json=sin_nada, headers=h)
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (422, "PUERTO_REQUERIDO")
    otro = payload_recargo(db_session, esc.destino) | {"puerto_id": None, "tarifas_ids": [esc.tarifa.id],
                                                        "proveedor_id": Escenario(db_session, admin).proveedor.id}
    assert client.post("/v1/recargos", json=otro, headers=h).json()["detail"]["codigo"] == "VINCULO_OTRO_PROVEEDOR"
    creado = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino) | {
        "puerto_id": None, "tarifas_ids": [esc.tarifa.id], "bloque_fiscal": "FACTURA"}, headers=h)
    assert creado.status_code == 201, creado.text
    datos = creado.json()
    assert (datos["puerto"], [t["id"] for t in datos["tarifas_vinculadas"]], datos["bloque_fiscal"]) == (None, [esc.tarifa.id], "FACTURA")
    en_ficha = client.get(f"/v1/tarifas/{esc.tarifa.id}/recargos", headers=h).json()
    assert [r["id"] for r in en_ficha] == [datos["id"]]
    unico = client.delete(f"/v1/tarifas/{esc.tarifa.id}/recargos/{datos['id']}", headers=h)
    assert unico.json()["detail"]["codigo"] == "PUERTO_REQUERIDO"  # sin puerto no puede quedar sin tarifa
    general = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino), headers=h).json()
    assert client.post(f"/v1/tarifas/{esc.tarifa.id}/recargos/{general['id']}", headers=h).status_code == 200
    assert client.delete(f"/v1/tarifas/{esc.tarifa.id}/recargos/{general['id']}", headers=h).status_code == 200
    notas = [a.nota for a in db_session.scalars(select(Auditoria).where(Auditoria.entidad == "recargo",
                                                                         Auditoria.entidad_id == str(general["id"])))]
    assert f"VINCULAR TARIFA {esc.tarifa.id}" in notas and f"DESVINCULAR TARIFA {esc.tarifa.id}" in notas
    comercial = headers_de(crear_usuario("comercial"))
    assert client.post(f"/v1/tarifas/{esc.tarifa.id}/recargos/{general['id']}", headers=comercial).status_code == 403


def test_duplicar_tarifa_copia_vinculos(client, crear_usuario, headers_de, db_session):  # TRV-06
    admin = crear_usuario("admin")
    h = headers_de(admin)
    esc = Escenario(db_session, admin, modo="LCL")
    vinculado = _vinculado(db_session, esc.destino, esc.tarifa)
    fechas = {"valido_desde": "2027-01-01", "valido_hasta": "2027-01-31"}
    copia = client.post(f"/v1/tarifas/{esc.tarifa.id}/duplicar", json=fechas, headers=h)
    assert copia.status_code == 201, copia.text
    assert [r["id"] for r in client.get(f"/v1/tarifas/{copia.json()['id']}/recargos", headers=h).json()] == [vinculado.id]
    sin = client.post(f"/v1/tarifas/{esc.tarifa.id}/duplicar", json={"valido_desde": "2027-02-01", "valido_hasta": "2027-02-28",
                                                                     "copiar_vinculos": False}, headers=h)
    assert client.get(f"/v1/tarifas/{sin.json()['id']}/recargos", headers=h).json() == []


def test_advertencia_de_coherencia(client, crear_usuario, headers_de, db_session):  # TRV-07
    h = headers_de(crear_usuario("pricing"))
    esc = Escenario(db_session, crear_usuario("comercial"))
    ecuador, exterior = esc.destino, esc.origen

    def avisos(puerto, lado):
        return client.post("/v1/recargos/validar", json={"puerto_id": puerto.id, "lado": lado}, headers=h).json()["advertencias"]

    assert "gasto de destino" in avisos(exterior, "DESTINO")[0]
    assert "gasto de origen" in avisos(ecuador, "ORIGEN")[0]
    assert avisos(ecuador, "DESTINO") == [] and avisos(exterior, "ORIGEN") == []


# ---------- D-R3: bloque fiscal en el recargo ----------


def test_bloque_fiscal_lo_decide_el_recargo(client, crear_usuario, headers_de, db_session):  # TRV-08
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, modo="LCL")
    # en el exterior pero marcado Factura con IVA; en Ecuador pero marcado Recibo de Caja
    factura = crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN", bloque_fiscal="FACTURA", aplica_iva=True)
    recibo = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", bloque_fiscal="RECIBO_CAJA", aplica_iva=False)
    cotizacion = _cotizacion(client, h, esc, incoterm="EXW")  # EXW: todo es de XPRESS
    f, r = _linea(cotizacion, factura), _linea(cotizacion, recibo)
    assert (f["bloque_fiscal"], r["bloque_fiscal"]) == ("FACTURA", "RECIBO_CAJA")
    t = cotizacion["totales"]
    assert Decimal(t["subtotal_factura"]) == Decimal(f["subtotal_venta_usd"])
    assert Decimal(t["iva"]) == (Decimal(f["subtotal_venta_usd"]) * Decimal(t["iva_tasa_aplicada"]) / 100).quantize(Decimal("0.01"))


def test_regla_por_defecto_igual_a_la_migracion(db_session, crear_usuario):  # TRV-09
    """Sin bloque fiscal explícito (scripts, bancos de prueba) vale la regla de la migración 0015."""
    from app.services.recargos import bloque_fiscal_por_regla

    esc = Escenario(db_session, crear_usuario("comercial"), con_tarifa=False)
    en_ecuador = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO")
    en_exterior = crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN")
    seguro = crear_recargo(db_session, esc.destino, "SEGURO", "DESTINO")
    assert (en_ecuador.bloque_fiscal, en_exterior.bloque_fiscal, seguro.bloque_fiscal) == ("FACTURA", "RECIBO_CAJA", "RECIBO_CAJA")
    assert bloque_fiscal_por_regla(esc.destino, "GASTOS_DESTINO") == "FACTURA"


def test_seguro_siempre_en_recibo_y_recibo_sin_iva(client, crear_usuario, headers_de, db_session):  # TRV-10
    h = headers_de(crear_usuario("admin"))
    esc = Escenario(db_session, crear_usuario("comercial"), modo="LCL")
    seguro = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino, bloque_incoterm="SEGURO",
                                                              bloque_fiscal="FACTURA"), headers=h).json()
    assert seguro["bloque_fiscal"] == "RECIBO_CAJA"
    recibo = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino, bloque_fiscal="RECIBO_CAJA",
                                                              aplica_iva=True), headers=h).json()
    assert (recibo["bloque_fiscal"], recibo["aplica_iva"]) == ("RECIBO_CAJA", False)
    sin_indicar = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino), headers=h).json()
    assert sin_indicar["bloque_fiscal"] == "FACTURA"  # puerto de Ecuador: la regla de antes


def test_gerencia_ve_proveedor_y_comercial_no_en_opciones(client, crear_usuario, headers_de, db_session):  # TRV-11
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial, modo="LCL")
    cotizacion = _cotizacion(client, headers_de(comercial), esc)
    gerencia = client.get(f"/v1/cotizaciones/{cotizacion['id']}/opciones-flete", headers=headers_de(crear_usuario("gerencia"))).json()
    assert gerencia["grupos"][0]["opciones"][0]["proveedor"]["nombre"] == esc.proveedor.nombre


def test_pantallas_recargos_y_tarifas(client):  # TRV-12
    from test_frontend import PATRONES_PROHIBIDOS_JS

    for pagina in ("recargos", "tarifas", "cotizador"):
        html = client.get(f"/app/{pagina}.html").text
        assert "<style" not in html and "style=" not in html
        assert [p for p in PATRONES_PROHIBIDOS_JS if p in client.get(f"/app/js/{pagina}.js").text] == []
    assert 'name="bloque_fiscal"' in client.get("/app/recargos.html").text
    assert 'id="tabla-vinculos"' in client.get("/app/tarifas.html").text
    assert "/recargos/validar" in client.get("/app/js/recargos.js").text

"""M7 Cotización en borrador y líneas por Incoterm (T228–T241 y T260)."""
import io
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Auditoria
from cotizacion_escenarios import Escenario, crear_recargo, fijar_hoy
from fabricas import crear_cliente, crear_contacto, crear_proveedor, tipo_equipo

CLAVES_COSTO_LINEA = {"costo_unit_original", "minimo_original", "costo_usd", "precio_calculado_unit_usd", "bajo_costo"}
CLAVES_COSTO_TOTALES = {"costo_total", "margen_total", "margen_pct"}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _crear(client, headers, datos):
    return client.post("/v1/cotizaciones", json=datos, headers=headers)


def _proponer(client, headers, cotizacion_id, **cuerpo):
    return client.post(f"/v1/cotizaciones/{cotizacion_id}/proponer-lineas", json=cuerpo, headers=headers)


def _bloques(respuesta) -> set[str]:
    return {linea["bloque_incoterm"] for linea in respuesta.json()["lineas"]}


# ---------- Crear el borrador ----------


def test_crear_borrador_sin_numero(client, crear_usuario, headers_de, db_session):  # T228
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial)
    respuesta = _crear(client, headers_de(comercial), esc.payload())
    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert (datos["numero"], datos["estado"], datos["etiqueta"]) == (None, "BORRADOR", f"Borrador #{datos['id']}")
    assert datos["contacto"]["id"] == esc.contacto.id  # el principal, si no se indica
    assert (datos["comercial"]["id"], datos["requiere_proponer"]) == (comercial.id, True)
    registro = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(datos["id"]))
    ).one()
    assert registro.accion == "CREAR"


@pytest.mark.parametrize(
    ("caso", "estado", "codigo"),
    [
        ("cliente_ajeno", 404, "CLIENTE_NO_ENCONTRADO"),
        ("contacto_de_otro_cliente", 422, "CONTACTO_INVALIDO"),
        ("puerto_aereo_en_lcl", 422, "PUERTO_MODO_INCONSISTENTE"),
        ("origen_igual_destino", 422, "ORIGEN_IGUAL_DESTINO"),
        ("lcl_sin_cbm_ni_dimensiones", 422, "CARGA_INCOMPLETA"),
        ("peso_con_cuatro_decimales", 422, "CARGA_INVALIDA"),
        ("contenedores_en_lcl", 422, "CONTENEDORES_NO_PERMITIDOS"),
    ],
)
def test_crear_validaciones(client, crear_usuario, headers_de, db_session, caso, estado, codigo):  # T228
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial)
    datos = esc.payload()
    if caso == "cliente_ajeno":
        datos["cliente_id"] = crear_cliente(db_session, crear_usuario("comercial")).id
    elif caso == "contacto_de_otro_cliente":
        datos["contacto_id"] = crear_contacto(db_session, crear_cliente(db_session, comercial)).id
    elif caso == "puerto_aereo_en_lcl":
        datos["origen_puerto_id"] = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False).origen.id
    elif caso == "origen_igual_destino":
        datos["destino_puerto_id"] = datos["origen_puerto_id"]
    elif caso == "lcl_sin_cbm_ni_dimensiones":
        datos["cbm"] = None
    elif caso == "peso_con_cuatro_decimales":
        datos["peso_kg"] = "10.1234"
    else:
        datos["contenedores"] = [{"tipo_equipo_id": tipo_equipo(db_session).id, "cantidad": 1}]
    respuesta = _crear(client, headers_de(comercial), datos)
    assert (respuesta.status_code, _codigo(respuesta)) == (estado, codigo)


@pytest.mark.parametrize(("caso", "codigo"), [("fcl_sin_contenedores", "CARGA_INCOMPLETA"), ("aereo_peso_cero", "CARGA_INVALIDA")])
def test_carga_minima_por_modo(client, crear_usuario, headers_de, db_session, caso, codigo):  # T228 (H20)
    comercial = crear_usuario("comercial")
    if caso == "fcl_sin_contenedores":
        esc = Escenario(db_session, comercial, modo="FCL", con_tarifa=False)
        datos = esc.payload(contenedores=[])
    else:
        esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
        datos = esc.payload("FCA", peso_kg="0")
    respuesta = _crear(client, headers_de(comercial), datos)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, codigo)


# ---------- Reglas de Incoterm (§9.3) ----------


@pytest.mark.parametrize(
    ("modo", "codigo", "sentido", "esperado"),
    [
        ("AEREO", "FOB", "IMPORTACION", "Para aéreo use FCA, CPT o CIP"),
        ("LCL", "DDP", "IMPORTACION", "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación"),
        ("LCL", "EXW", "EXPORTACION", "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación"),
    ],
    ids=["fob_aereo", "ddp_importacion", "exw_exportacion"],
)
def test_reglas_de_incoterm(client, crear_usuario, headers_de, db_session, modo, codigo, sentido, esperado):  # T229
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial, modo=modo, con_tarifa=False)
    respuesta = _crear(client, headers_de(comercial), esc.payload(codigo, sentido))
    assert respuesta.status_code == 422
    if modo == "AEREO":
        assert _codigo(respuesta) == "INCOTERM_MODO_INVALIDO"
        assert esperado in respuesta.json()["detail"]["mensaje"]
    else:
        assert (_codigo(respuesta), respuesta.json()["detail"]["mensaje"]) == ("NADA_QUE_COTIZAR", esperado)


# ---------- Líneas por Incoterm (§9.1, §9.2) ----------


def _recargos_en_todos_los_bloques(db_session, esc) -> None:
    for bloque in ("RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN"):
        crear_recargo(db_session, esc.origen, bloque, "ORIGEN")
    for bloque in ("GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL"):
        crear_recargo(db_session, esc.destino, bloque, "DESTINO")
    crear_recargo(db_session, esc.destino, "SEGURO", "DESTINO")
    crear_recargo(db_session, esc.origen, "SEGURO", "ORIGEN")


@pytest.mark.parametrize(
    ("codigo", "sentido", "bloques"),
    [
        ("FOB", "IMPORTACION", {"FLETE_PRINCIPAL", "SEGURO", "GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL"}),
        ("EXW", "IMPORTACION", {"RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN", "FLETE_PRINCIPAL", "SEGURO",
                                "GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL"}),
        ("DAP", "IMPORTACION", {"DESPACHO_IMPORT"}),
        ("FOB", "EXPORTACION", {"RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN"}),
    ],
    ids=["fob_importacion", "exw_importacion", "dap_importacion", "fob_exportacion_complemento"],
)
def test_bloques_segun_incoterm_y_sentido(client, crear_usuario, headers_de, db_session, codigo, sentido, bloques):  # T230
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    _recargos_en_todos_los_bloques(db_session, esc)
    cotizacion = _crear(client, h, esc.payload(codigo, sentido)).json()
    respuesta = _proponer(client, h, cotizacion["id"])
    assert respuesta.status_code == 200, respuesta.text
    assert _bloques(respuesta) == bloques
    seguro = [l for l in respuesta.json()["lineas"] if l["bloque_incoterm"] == "SEGURO"]
    if sentido == "IMPORTACION" and seguro:
        assert seguro[0]["recargo_id"] is not None


def test_recargos_en_su_puerto_y_bloque_fiscal(client, crear_usuario, headers_de, db_session):  # T230 (D-F3-4)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    origen = crear_recargo(db_session, esc.origen, "GASTOS_ORIGEN", "ORIGEN", aplica_iva=False)
    destino = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO")
    cotizacion = _crear(client, h, esc.payload("EXW")).json()
    lineas = {l["recargo_id"]: l for l in _proponer(client, h, cotizacion["id"]).json()["lineas"] if l["recargo_id"]}
    assert lineas[origen.id]["bloque_fiscal"] == "RECIBO_CAJA"  # puerto en el exterior
    assert lineas[destino.id]["bloque_fiscal"] == "FACTURA"  # puerto en Ecuador
    flete = next(l for l in _proponer(client, h, cotizacion["id"]).json()["lineas"] if l["tarifa_id"])
    assert (flete["bloque_fiscal"], flete["rol_ingreso"], flete["aplica_iva"]) == ("RECIBO_CAJA", "PRINCIPAL", False)


def test_aviso_si_un_bloque_no_tiene_recargo(client, crear_usuario, headers_de, db_session):  # T231
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    respuesta = _proponer(client, h, cotizacion["id"])
    assert respuesta.status_code == 200
    assert f"Sin recargo cargado para GASTOS_DESTINO en {esc.destino.codigo}" in respuesta.json()["avisos"]
    assert _bloques(respuesta) == {"FLETE_PRINCIPAL"}


# ---------- Recargo más específico (D-F3-7, H6) ----------


def test_mas_especifico_gana_en_lcl(client, crear_usuario, headers_de, db_session):  # T232
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC")
    lcl = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="thc", modo="LCL")
    crear_recargo(db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO", concepto="Aduana", modo="LCL")
    del_proveedor = crear_recargo(
        db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO", concepto="ADUANA", proveedor_id=esc.proveedor.id
    )
    crear_recargo(db_session, esc.destino, "ENTREGA_FINAL", "DESTINO", proveedor_id=crear_proveedor(db_session).id)
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    lineas = _proponer(client, h, cotizacion["id"]).json()["lineas"]
    recargos = {l["recargo_id"] for l in lineas if l["recargo_id"]}
    assert recargos == {lcl.id, del_proveedor.id}  # modo > todos; proveedor del flete > NULL; otro proveedor no entra


def test_fcl_40hc_x2_y_20gp_x1(client, crear_usuario, headers_de, db_session):  # T232 (H6 obligatorio)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    hc, gp = tipo_equipo(db_session, "40HC"), tipo_equipo(db_session, "20GP")
    esc = Escenario(db_session, comercial, modo="FCL", tipo_equipo_id=hc.id)
    esc.nueva_tarifa(tipo_equipo_id=gp.id)
    especifico = crear_recargo(
        db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC", modo="FCL", tipo_equipo_id=hc.id,
        rate_unit="CONTENEDOR",
    )
    generico = crear_recargo(
        db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC", modo="FCL", rate_unit="CONTENEDOR"
    )
    bl = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="BL", rate_unit="ENVIO")
    datos = esc.payload(contenedores=[{"tipo_equipo_id": hc.id, "cantidad": 2}, {"tipo_equipo_id": gp.id, "cantidad": 1}])
    cotizacion = _crear(client, h, datos).json()
    respuesta = _proponer(client, h, cotizacion["id"])
    assert respuesta.status_code == 200, respuesta.text
    lineas = respuesta.json()["lineas"]
    cantidades = {l["recargo_id"]: l["cantidad"] for l in lineas if l["recargo_id"]}
    assert cantidades == {especifico.id: "2.0000", generico.id: "1.0000", bl.id: "1.0000"}
    fletes = sorted((l["tipo_equipo"], l["cantidad"]) for l in lineas if l["tarifa_id"])
    assert fletes == [("20GP", "1.0000"), ("40HC", "2.0000")]


def test_fcl_proveedores_distintos_422(client, crear_usuario, headers_de, db_session):  # T233
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    hc, gp = tipo_equipo(db_session, "40HC"), tipo_equipo(db_session, "20GP")
    esc = Escenario(db_session, comercial, modo="FCL", tipo_equipo_id=hc.id)
    esc.nueva_tarifa(tipo_equipo_id=gp.id, proveedor_id=crear_proveedor(db_session).id)
    datos = esc.payload(contenedores=[{"tipo_equipo_id": hc.id, "cantidad": 1}, {"tipo_equipo_id": gp.id, "cantidad": 1}])
    respuesta = _proponer(client, h, _crear(client, h, datos).json()["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "PROVEEDORES_DISTINTOS")


# ---------- Elegibilidad y elección de tarifa (§10.2) ----------


@pytest.mark.parametrize(
    "vigencia",
    [(date(2026, 1, 1), date(2026, 6, 14)), (date(2026, 6, 16), date(2026, 12, 31))],
    ids=["vencida", "futura"],
)
def test_tarifa_vencida_o_futura_no_es_elegible(client, crear_usuario, headers_de, db_session, vigencia):  # T234
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, valido_desde=vigencia[0], valido_hasta=vigencia[1])
    cotizacion = _crear(client, h, esc.payload()).json()
    opciones = client.get(f"/v1/cotizaciones/{cotizacion['id']}/opciones-flete", headers=h).json()
    assert opciones["grupos"][0]["opciones"] == []
    respuesta = _proponer(client, h, cotizacion["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "SIN_TARIFA")


def test_varias_tarifas_ordenadas_y_elegir(client, crear_usuario, headers_de, db_session):  # T235
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, costo="100")
    barata = esc.nueva_tarifa(proveedor_id=crear_proveedor(db_session).id, costo="80")
    cotizacion = _crear(client, h, esc.payload()).json()
    opciones = client.get(f"/v1/cotizaciones/{cotizacion['id']}/opciones-flete", headers=h).json()["grupos"][0]
    assert opciones["clave"] == "LCL"
    assert [o["tarifa_id"] for o in opciones["opciones"]] == [barata.id, esc.tarifa.id]
    assert all("costo_usd" not in o for o in opciones["opciones"])
    respuesta = _proponer(client, h, cotizacion["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "ELEGIR_TARIFA")
    respuesta = _proponer(client, h, cotizacion["id"], tarifas={"LCL": barata.id})
    assert respuesta.status_code == 200
    assert next(l for l in respuesta.json()["lineas"] if l["tarifa_id"])["tarifa_id"] == barata.id


# ---------- Seguro (D-F3-6) y valores ----------


def test_seguro_propuesto_apagado_y_se_activa(client, crear_usuario, headers_de, db_session):  # T236
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    seguro = crear_recargo(
        db_session, esc.destino, "SEGURO", "DESTINO", rate_unit="PCT_VALOR", costo="0.35", minimo="0"
    )
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    datos = _proponer(client, h, cotizacion["id"]).json()
    linea = next(l for l in datos["lineas"] if l["recargo_id"] == seguro.id)
    assert (linea["opcional"], linea["incluida"]) == (True, False)
    total_sin_seguro = Decimal(datos["totales"]["total_general"])
    url = f"/v1/cotizaciones/{cotizacion['id']}/lineas/{linea['id']}"
    sin_valor = client.patch(url, json={"incluida": True}, headers=h)
    assert (sin_valor.status_code, _codigo(sin_valor)) == (422, "VALOR_MERCANCIA_REQUERIDO")
    client.patch(f"/v1/cotizaciones/{cotizacion['id']}", json={"valor_mercancia_usd": "20000"}, headers=h)
    activado = client.patch(url, json={"incluida": True}, headers=h)
    assert activado.status_code == 200, activado.text
    linea = next(l for l in activado.json()["lineas"] if l["recargo_id"] == seguro.id)
    # 20 000 / 100 = 200 × 0,35 % = 70 de costo; MARKUP 10 % → 0,385 × 200 = 77,0000 de venta.
    assert (linea["cantidad"], linea["subtotal_venta_usd"]) == ("200.0000", "77.0000")
    assert Decimal(activado.json()["totales"]["total_general"]) == total_sin_seguro + Decimal("77.00")


# ---------- Gating y alcance (§6.3, D-F2-5) ----------


def test_gating_del_json_de_cotizacion(client, crear_usuario, headers_de, db_session):  # T237
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO")
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    del_comercial = _proponer(client, h, cotizacion["id"]).json()
    for linea in del_comercial["lineas"]:
        assert CLAVES_COSTO_LINEA.isdisjoint(linea)
    assert CLAVES_COSTO_TOTALES.isdisjoint(del_comercial["totales"])
    de_gerencia = client.get(f"/v1/cotizaciones/{cotizacion['id']}", headers=headers_de(crear_usuario("gerencia"))).json()
    assert {"costo_unit_original", "costo_usd"} <= set(de_gerencia["lineas"][0])
    assert CLAVES_COSTO_TOTALES <= set(de_gerencia["totales"])
    # Flete 2,5 W/M × 100 = 250 de costo y 300 de venta (MARKUP 20 %); recargo 50 → 55 (MARKUP 10 %).
    assert (de_gerencia["totales"]["costo_total"], de_gerencia["totales"]["margen_total"]) == ("300.00", "55.00")


@pytest.mark.parametrize("operacion", ["get", "patch", "proponer", "opciones", "linea", "listado"])
def test_cotizacion_ajena_404(client, crear_usuario, headers_de, db_session, operacion):  # T238
    duenio, otro = crear_usuario("comercial"), crear_usuario("comercial")
    esc = Escenario(db_session, duenio)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO")
    h_duenio, h_otro = headers_de(duenio), headers_de(otro)
    cotizacion = _crear(client, h_duenio, esc.payload()).json()
    lineas = _proponer(client, h_duenio, cotizacion["id"]).json()["lineas"]
    base = f"/v1/cotizaciones/{cotizacion['id']}"
    if operacion == "listado":
        assert client.get("/v1/cotizaciones", headers=h_otro).json()["items"] == []
        return
    respuesta = {
        "get": lambda: client.get(base, headers=h_otro),
        "patch": lambda: client.patch(base, json={"notas_cliente": "x"}, headers=h_otro),
        "proponer": lambda: _proponer(client, h_otro, cotizacion["id"]),
        "opciones": lambda: client.get(f"{base}/opciones-flete", headers=h_otro),
        "linea": lambda: client.patch(f"{base}/lineas/{lineas[0]['id']}", json={"incluida": True}, headers=h_otro),
    }[operacion]()
    assert (respuesta.status_code, _codigo(respuesta)) == (404, "COTIZACION_NO_ENCONTRADA")


# ---------- Ajuste manual (§10.4, H9) ----------


def test_ajuste_manual_auditado_y_quitar(client, crear_usuario, headers_de, db_session):  # T239
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, minimo="300", minimo_venta_manual=None)
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    flete = next(l for l in _proponer(client, h, cotizacion["id"]).json()["lineas"] if l["tarifa_id"])
    url = f"/v1/cotizaciones/{cotizacion['id']}/lineas/{flete['id']}"
    corto = client.patch(url, json={"precio_venta_unit_usd": "90", "motivo": "ok"}, headers=h)
    assert (corto.status_code, _codigo(corto)) == (422, "MOTIVO_REQUERIDO")
    ajustada = client.patch(url, json={"precio_venta_unit_usd": "90", "motivo": "Cliente frecuente"}, headers=h)
    assert ajustada.status_code == 200, ajustada.text
    linea = next(l for l in ajustada.json()["lineas"] if l["id"] == flete["id"])
    # 2,5 W/M × 90 = 225, sin mínimo de venta (360 = 300 × 1,2): queda bajo el mínimo; el comercial no ve bajo_costo.
    assert (linea["ajuste_manual"], linea["subtotal_venta_usd"], linea["bajo_minimo_venta"]) == (True, "225.0000", True)
    assert "bajo_costo" not in linea
    de_pricing = client.get(f"/v1/cotizaciones/{cotizacion['id']}", headers=headers_de(crear_usuario("pricing"))).json()
    assert next(l for l in de_pricing["lineas"] if l["id"] == flete["id"])["bajo_costo"] is True  # costo 300
    registro = db_session.scalars(
        select(Auditoria)
        .where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(cotizacion["id"]))
        .order_by(Auditoria.id.desc())
    ).first()
    assert (registro.accion, registro.nota) == ("EDITAR", "AJUSTE LINEA 1: Cliente frecuente")
    assert (registro.valores_antes["precio_venta_unit_usd"], registro.valores_despues["precio_venta_unit_usd"]) == (
        "120.0000", "90.0000"
    )
    quitado = client.patch(url, json={"quitar_ajuste": True}, headers=h).json()
    linea = next(l for l in quitado["lineas"] if l["id"] == flete["id"])
    assert (linea["ajuste_manual"], linea["subtotal_venta_usd"]) == (False, "360.0000")


def test_cambio_de_ruta_con_ajustes_exige_confirmar(client, crear_usuario, headers_de, db_session):  # T240 (D-F3-10)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    cotizacion = _crear(client, h, esc.payload("FOB")).json()
    flete = next(l for l in _proponer(client, h, cotizacion["id"]).json()["lineas"] if l["tarifa_id"])
    base = f"/v1/cotizaciones/{cotizacion['id']}"
    client.patch(f"{base}/lineas/{flete['id']}", json={"precio_venta_unit_usd": "99", "motivo": "Promoción"}, headers=h)
    # Cambiar el valor de la mercancía o las notas no borra líneas (H15).
    sin_borrar = client.patch(base, json={"valor_mercancia_usd": "1000", "notas_cliente": "Hola"}, headers=h)
    assert len(sin_borrar.json()["lineas"]) == 1
    respuesta = client.patch(base, json={"cbm": "3"}, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "AJUSTES_SE_PIERDEN")
    respuesta = _proponer(client, h, cotizacion["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "AJUSTES_SE_PIERDEN")
    confirmado = client.patch(base, json={"cbm": "3", "confirmar": True}, headers=h)
    assert confirmado.status_code == 200
    assert (confirmado.json()["lineas"], confirmado.json()["requiere_proponer"]) == ([], True)


def test_listado_paginado_y_validez_calculada(client, crear_usuario, headers_de, db_session):  # T241
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial, valido_hasta=date(2026, 9, 30))
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", valido_hasta="2026-08-31")
    ids = [_crear(client, h, esc.payload()).json()["id"] for _ in range(3)]
    detalle = _proponer(client, h, ids[0]).json()
    assert detalle["valida_hasta_calculada"] == "2026-08-31"  # la vigencia más cercana de las líneas incluidas
    pagina = client.get("/v1/cotizaciones?limit=2&offset=0", headers=h).json()
    assert (pagina["total"], len(pagina["items"]), pagina["items"][0]["id"]) == (3, 2, ids[2])
    assert client.get("/v1/cotizaciones?estado=EMITIDA", headers=h).json()["total"] == 0


# ---------- Seguro apagado sin valor (D-F3-15) ----------


def test_seguro_sin_valor_apagado_no_se_cobra(client, crear_usuario, headers_de, db_session):  # T260
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = Escenario(db_session, comercial)
    seguro = crear_recargo(
        db_session, esc.destino, "SEGURO", "DESTINO", concepto="Seguro de carga T260", rate_unit="PCT_VALOR",
        costo="0.35", minimo="25",
    )
    cotizacion = _crear(client, h, esc.payload("FOB")).json()  # sin valor de la mercancía
    datos = _proponer(client, h, cotizacion["id"]).json()
    linea = next(l for l in datos["lineas"] if l["recargo_id"] == seguro.id)
    assert (linea["incluida"], linea["cantidad"]) == (False, "0.0000")
    # El mínimo se calcula (25 × 1,10 = 27,50), pero una línea opcional apagada nunca se cobra.
    incluidas = sum(Decimal(l["subtotal_venta_usd"]) for l in datos["lineas"] if l["incluida"])
    assert Decimal(datos["totales"]["subtotal_recibo_caja"]) + Decimal(datos["totales"]["subtotal_factura"]) == incluidas
    pdf = client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h)
    texto = "".join(pagina.extract_text() for pagina in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "BORRADOR" in texto
    assert "Seguro de carga T260" not in texto

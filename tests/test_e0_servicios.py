"""E0 Servicios editables (TE0-01 a TE0-24): catálogos, permisos, reglas por forma de cobro y casos de punta a punta.

Los servicios nuevos se crean por la API, sin tocar código: COURIER (por peso con tramos de 0,5 kg), FTL (por unidad
de equipo, terrestre, con un tipo de equipo nuevo) y DOCS (tarifa plana).
"""
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select, text

from app.models import Auditoria, Incoterm, Servicio, ServicioTramo, TipoEquipo, TipoUbicacion
from app.services import pdf
from cotizacion_escenarios import Escenario, cargar_condiciones, fijar_hoy
from fabricas import crear_pais, crear_proveedor, crear_puerto, crear_tarifa, payload_recargo, tipo_equipo, usd
from matriz_rbac import PERMISOS_EXTENSIONES
from test_f4_pdf import _datos_minimos

D = Decimal


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _servicio(db_session, codigo: str) -> Servicio:
    return db_session.scalars(select(Servicio).where(Servicio.codigo == codigo)).one()


def _crear_servicio(client, h, **datos) -> dict:
    cuerpo = {"codigo": "COURIER", "nombre": "Courier", "forma_cobro": "PESO_TRAMOS",
              "tipo_ubicacion_origen": "AEREO", "tipo_ubicacion_destino": "AEREO", "orden": 40,
              "descripcion_pdf": "servicio courier puerta a puerta", "etiqueta_transportista": "Courier"} | datos
    respuesta = client.post("/v1/servicios", json=cuerpo, headers=h)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _tarifa(client, h, esc: Escenario, modo: str, **cambios) -> dict:
    cuerpo = {
        "proveedor_id": esc.proveedor.id, "modo": modo, "origen_puerto_id": esc.origen.id,
        "destino_puerto_id": esc.destino.id, "tipo_equipo_id": None, "rate_unit": "KG", "costo": "10",
        "moneda_id": usd(esc.db).id, "minimo": "0", "metodo_venta": "MARKUP", "parametro_venta": "20",
        "valido_desde": "2026-01-01", "valido_hasta": "2026-12-31", "transportista": "DHL Express",
    } | cambios
    respuesta = client.post("/v1/tarifas", json=cuerpo, headers=h)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# ---------- Siembra de la 0007 ----------


def test_siembra_servicios_ubicaciones_tramos(db_session):  # TE0-01
    servicios = {
        s.codigo: (s.nombre, s.forma_cobro, s.tipo_ubicacion_origen, s.tipo_ubicacion_destino, s.usa_tipo_equipo,
                   s.permite_libras, s.descripcion_pdf, s.etiqueta_transportista, s.activo)
        for s in db_session.scalars(select(Servicio).where(Servicio.codigo.in_(("AEREO", "LCL", "FCL"))))
    }
    assert servicios == {
        "AEREO": ("Aéreo", "PESO_TRAMOS", "AEREO", "AEREO", False, True, "vía aérea", "Aerolínea", True),
        "LCL": ("Marítimo LCL", "VOLUMEN_WM", "MARITIMO", "MARITIMO", False, False,
                "vía marítima · carga consolidada (LCL)", "Naviera / Motonave", True),
        "FCL": ("Marítimo FCL", "UNIDAD_EQUIPO", "MARITIMO", "MARITIMO", True, False,
                "vía marítima · contenedor completo (FCL)", "Naviera / Motonave", True),
    }
    tipos = dict(db_session.execute(text("SELECT codigo, activo FROM tipo_ubicacion")).all())
    assert {c: tipos[c] for c in ("MARITIMO", "AEREO", "TERRESTRE")} == {"MARITIMO": True, "AEREO": True, "TERRESTRE": False}
    aereo = _servicio(db_session, "AEREO")
    tramos = {(t.unidad_peso, t.desde) for t in db_session.scalars(select(ServicioTramo).where(ServicioTramo.servicio_id == aereo.id))}
    assert tramos == {("KG", D(d)) for d in (0, 45, 100, 300, 500, 1000)} | {("LB", D(d)) for d in (0, 100, 220, 660, 1100, 2200)}
    fcl = _servicio(db_session, "FCL")
    for codigo in ("20GP", "40GP", "40HC", "20RF", "40RF"):
        assert tipo_equipo(db_session, codigo).servicio_id == fcl.id


def test_siembra_incoterms_por_servicio(db_session):  # TE0-02 (mismo comportamiento que solo_maritimo)
    permitidos = {i.codigo: {s.codigo for s in i.servicios} for i in db_session.scalars(select(Incoterm))}
    for codigo, servicios in permitidos.items():
        esperado = {"LCL", "FCL"} if codigo in ("FAS", "FOB", "CFR", "CIF") else {"AEREO", "LCL", "FCL"}
        assert servicios >= esperado and {"AEREO", "LCL", "FCL"} & servicios == esperado, codigo


def test_permisos_de_extensiones_exactos(db_session):  # TE0-03 (D-E0-1)
    filas = db_session.execute(
        text("SELECT p.codigo, r.codigo FROM permiso p LEFT JOIN rol_permiso rp ON rp.permiso_id = p.id "
             "LEFT JOIN rol r ON r.id = rp.rol_id WHERE p.codigo = ANY(:codigos)"),
        {"codigos": list(PERMISOS_EXTENSIONES)},
    ).all()
    matriz: dict[str, set[str]] = {}
    for permiso, rol in filas:
        matriz.setdefault(permiso, set()).add(rol)
    assert matriz == PERMISOS_EXTENSIONES


def test_formas_de_cobro(client, crear_usuario, headers_de):  # TE0-04
    formas = {f["codigo"]: f for f in client.get("/v1/formas-cobro", headers=headers_de(crear_usuario("comercial"))).json()}
    assert set(formas) == {"PESO_TRAMOS", "VOLUMEN_WM", "UNIDAD_EQUIPO", "TARIFA_PLANA"}
    assert formas["PESO_TRAMOS"]["unidades_tarifa"] == ["KG", "ENVIO"] and formas["PESO_TRAMOS"]["usa_tramos"]
    assert formas["VOLUMEN_WM"]["unidades_tarifa"] == ["WM", "CBM", "ENVIO"]
    assert formas["UNIDAD_EQUIPO"]["unidades_recargo"] == ["CONTENEDOR", "ENVIO"] and formas["UNIDAD_EQUIPO"]["usa_tipo_equipo"]
    assert formas["TARIFA_PLANA"]["unidades_tarifa"] == ["ENVIO"]


# ---------- Permisos y CRUD ----------


@pytest.mark.parametrize("rol", ["pricing", "comercial", "gerencia"])
def test_solo_admin_gestiona_servicios(client, crear_usuario, headers_de, db_session, rol):  # TE0-05
    h = headers_de(crear_usuario(rol))
    assert client.get("/v1/servicios?activo=true", headers=h).status_code == 200
    cuerpo = {"codigo": "XX", "nombre": "X", "forma_cobro": "TARIFA_PLANA", "tipo_ubicacion_origen": "AEREO",
              "tipo_ubicacion_destino": "AEREO"}
    assert client.post("/v1/servicios", json=cuerpo, headers=h).status_code == 403
    aereo = _servicio(db_session, "AEREO")
    assert client.patch(f"/v1/servicios/{aereo.id}", json={"nombre": "X"}, headers=h).status_code == 403
    assert client.post(f"/v1/servicios/{aereo.id}/tramos", json={"desde": "2"}, headers=h).status_code == 403
    assert client.post("/v1/tipos-ubicacion", json={"codigo": "RIO", "nombre": "Puerto fluvial"}, headers=h).status_code == 403


def test_crear_servicio_audita_e_hereda_incoterms(client, crear_usuario, headers_de, db_session):  # TE0-06
    admin = crear_usuario("admin")
    creado = _crear_servicio(client, headers_de(admin))
    assert (creado["usa_tipo_equipo"], creado["permite_libras"], creado["activo"], creado["tramos"]) == (False, False, True, [])
    registro = db_session.scalars(select(Auditoria).where(Auditoria.entidad == "servicio", Auditoria.entidad_id == "COURIER")).one()
    assert (registro.accion, registro.usuario_id) == ("CREAR", admin.id)
    # Hereda los Incoterms del servicio con los mismos tipos de ubicación (AEREO): sin FAS, FOB, CFR ni CIF.
    assert sorted(registro.valores_despues["incoterms"]) == ["CIP", "CPT", "DAP", "DDP", "DPU", "EXW", "FCA"]
    activos = [s["codigo"] for s in client.get("/v1/servicios?activo=true", headers=headers_de(admin)).json()]
    assert activos.index("FCL") < activos.index("COURIER")  # ordenados por orden


@pytest.mark.parametrize(
    ("datos", "codigo"),
    [
        ({"forma_cobro": "VOLUMEN_WM", "permite_libras": True}, "SERVICIO_INCOHERENTE"),
        ({"forma_cobro": "UNIDAD_EQUIPO", "usa_tipo_equipo": False}, "SERVICIO_INCOHERENTE"),
        ({"forma_cobro": "POR_HORA"}, "FORMA_COBRO_INVALIDA"),
        ({"codigo": "1AB"}, "CODIGO_INVALIDO"),
        ({"tipo_ubicacion_origen": "TERRESTRE"}, "PADRE_INACTIVO"),
        ({"codigo": "AEREO"}, "SERVICIO_DUPLICADO"),
    ],
    ids=["libras_sin_peso", "equipo_incoherente", "forma_desconocida", "codigo_invalido", "ubicacion_inactiva", "duplicado"],
)
def test_validaciones_del_servicio(client, crear_usuario, headers_de, datos, codigo):  # TE0-07
    cuerpo = {"codigo": "NUEVO", "nombre": "Nuevo", "forma_cobro": "PESO_TRAMOS", "tipo_ubicacion_origen": "AEREO",
              "tipo_ubicacion_destino": "AEREO"} | datos
    respuesta = client.post("/v1/servicios", json=cuerpo, headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code in (409, 422) and _codigo(respuesta) == codigo


def test_codigo_inmutable_una_vez_usado_y_borrado(client, crear_usuario, headers_de, db_session):  # TE0-08
    h = headers_de(crear_usuario("admin"))
    libre = _crear_servicio(client, h, codigo="LIBRE", forma_cobro="TARIFA_PLANA")
    renombrado = client.patch(f"/v1/servicios/{libre['id']}", json={"codigo": "LIBRE2"}, headers=h)
    assert renombrado.status_code == 200 and renombrado.json()["codigo"] == "LIBRE2"
    assert client.delete(f"/v1/servicios/{libre['id']}", headers=h).status_code == 204
    assert db_session.scalars(select(Servicio).where(Servicio.codigo == "LIBRE2")).one_or_none() is None
    nota = db_session.scalars(select(Auditoria.nota).where(Auditoria.entidad == "servicio", Auditoria.entidad_id == "LIBRE2")).all()
    assert "BORRADO: nunca se usó" in nota

    usado = _crear_servicio(client, h, codigo="USADO", forma_cobro="TARIFA_PLANA")
    esc = Escenario(db_session, crear_usuario("comercial"), modo="AEREO", con_tarifa=False)
    _tarifa(client, headers_de(crear_usuario("pricing")), esc, "USADO", rate_unit="ENVIO")
    for cambio in ({"codigo": "OTRO"}, {"forma_cobro": "PESO_TRAMOS"}, {"tipo_ubicacion_destino": "MARITIMO"}):
        respuesta = client.patch(f"/v1/servicios/{usado['id']}", json=cambio, headers=h)
        assert (respuesta.status_code, _codigo(respuesta)) == (409, "SERVICIO_EN_USO"), cambio
    assert _codigo(client.delete(f"/v1/servicios/{usado['id']}", headers=h)) == "SERVICIO_EN_USO"
    # El nombre y los textos sí cambian aunque esté usado.
    assert client.patch(f"/v1/servicios/{usado['id']}", json={"nombre": "Usado bis"}, headers=h).status_code == 200


def test_servicio_inactivo_no_se_ofrece_y_lo_historico_sigue(client, crear_usuario, headers_de, db_session):  # TE0-09
    admin, pricing, comercial = crear_usuario("admin"), crear_usuario("pricing"), crear_usuario("comercial")
    servicio = _crear_servicio(client, headers_de(admin), codigo="TEMPORAL", forma_cobro="TARIFA_PLANA")
    esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
    vieja = _tarifa(client, headers_de(pricing), esc, "TEMPORAL", rate_unit="ENVIO")
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FCA", modo="TEMPORAL", peso_kg="5"), headers=headers_de(comercial))
    assert cotizacion.status_code == 201, cotizacion.text
    assert client.patch(f"/v1/servicios/{servicio['id']}", json={"activo": False}, headers=headers_de(admin)).status_code == 200

    activos = [s["codigo"] for s in client.get("/v1/servicios?activo=true", headers=headers_de(comercial)).json()]
    assert "TEMPORAL" not in activos
    otra = client.post("/v1/tarifas", json={**{k: v for k, v in vieja.items() if k in ("modo", "rate_unit")},
                                           "proveedor_id": crear_proveedor(db_session).id, "origen_puerto_id": esc.origen.id,
                                           "destino_puerto_id": esc.destino.id, "costo": "5", "moneda_id": usd(db_session).id,
                                           "minimo": "0", "metodo_venta": "MARKUP", "parametro_venta": "10",
                                           "valido_desde": "2026-01-01", "valido_hasta": "2026-12-31"}, headers=headers_de(pricing))
    assert (otra.status_code, _codigo(otra)) == (422, "PADRE_INACTIVO")
    nueva = client.post("/v1/cotizaciones", json=esc.payload("FCA", modo="TEMPORAL", peso_kg="5"), headers=headers_de(comercial))
    assert (nueva.status_code, _codigo(nueva)) == (422, "PADRE_INACTIVO")
    # Lo histórico: la tarifa se sigue listando y el borrador existente se sigue leyendo y proponiendo.
    assert [t["id"] for t in client.get("/v1/tarifas?modo=TEMPORAL", headers=headers_de(pricing)).json()] == [vieja["id"]]
    detalle = client.get(f"/v1/cotizaciones/{cotizacion.json()['id']}", headers=headers_de(comercial))
    assert detalle.status_code == 200 and detalle.json()["servicio"]["activo"] is False
    propuesta = client.post(f"/v1/cotizaciones/{cotizacion.json()['id']}/proponer-lineas", json={}, headers=headers_de(comercial))
    assert propuesta.status_code == 200, propuesta.text


# ---------- Tramos del servicio ----------


def test_tramo_usado_no_se_borra_solo_se_desactiva(client, crear_usuario, headers_de, db_session):  # TE0-10
    h_admin, h_pricing = headers_de(crear_usuario("admin")), headers_de(crear_usuario("pricing"))
    aereo = _servicio(db_session, "AEREO")
    tramo_45 = db_session.scalars(select(ServicioTramo).where(
        ServicioTramo.servicio_id == aereo.id, ServicioTramo.unidad_peso == "KG", ServicioTramo.desde == 45)).one()
    tarifa = crear_tarifa(db_session, "AEREO")
    tramos = {"tramos": [{"desde_kg": 0, "costo_kg": "5"}, {"desde_kg": 45, "costo_kg": "4"}]}
    assert client.put(f"/v1/tarifas/{tarifa.id}/tramos", json=tramos, headers=h_pricing).status_code == 200
    assert _codigo(client.delete(f"/v1/servicio-tramos/{tramo_45.id}", headers=h_admin)) == "TRAMO_EN_USO"
    assert _codigo(client.patch(f"/v1/servicio-tramos/{tramo_45.id}", json={"desde": "46"}, headers=h_admin)) == "TRAMO_EN_USO"
    assert client.patch(f"/v1/servicio-tramos/{tramo_45.id}", json={"activo": False}, headers=h_admin).status_code == 200
    # Desactivado: la tarifa conserva su tramo, pero ya no se puede volver a cargar.
    assert [t["desde_kg"] for t in client.get(f"/v1/tarifas/{tarifa.id}/tramos", headers=h_pricing).json()] == [0, 45]
    respuesta = client.put(f"/v1/tarifas/{tarifa.id}/tramos", json=tramos, headers=h_pricing)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "TRAMOS_INVALIDOS")
    libre = client.post(f"/v1/servicios/{aereo.id}/tramos", json={"unidad_peso": "KG", "desde": "2000"}, headers=h_admin)
    assert libre.status_code == 201 and libre.json()["desde"] == 2000
    assert client.delete(f"/v1/servicio-tramos/{libre.json()['id']}", headers=h_admin).status_code == 204


@pytest.mark.parametrize(
    ("servicio", "datos", "codigo"),
    [
        ("LCL", {"desde": "1"}, "TRAMOS_NO_PERMITIDOS"),
        ("AEREO", {"desde": "45"}, "TRAMO_DUPLICADO"),
        ("AEREO", {"desde": "1.0005"}, "TRAMOS_INVALIDOS"),
        ("AEREO", {"desde": "-1"}, "TRAMOS_INVALIDOS"),
    ],
    ids=["servicio_sin_tramos", "repetido", "cuatro_decimales", "negativo"],
)
def test_validaciones_del_tramo(client, crear_usuario, headers_de, db_session, servicio, datos, codigo):  # TE0-11
    respuesta = client.post(f"/v1/servicios/{_servicio(db_session, servicio).id}/tramos", json=datos,
                            headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code in (409, 422) and _codigo(respuesta) == codigo


# ---------- Courier por peso con tramos de 0,5 kg: de punta a punta, con PDF ----------


def test_courier_tramos_decimales_cotiza_0_8_kg_con_pdf(client, crear_usuario, headers_de, db_session):  # TE0-12
    admin, pricing, comercial = crear_usuario("admin"), crear_usuario("pricing"), crear_usuario("comercial")
    h_admin = headers_de(admin)
    courier = _crear_servicio(client, h_admin)
    for desde in ("0", "0.5", "1", "5", "10"):
        respuesta = client.post(f"/v1/servicios/{courier['id']}/tramos", json={"unidad_peso": "KG", "desde": desde}, headers=h_admin)
        assert respuesta.status_code == 201, respuesta.text
    esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
    esc.modo = "COURIER"
    tarifa = _tarifa(client, headers_de(pricing), esc, "COURIER")
    costos = {"0": "12", "0.5": "10", "1": "9", "5": "8", "10": "7"}
    tramos = {"tramos": [{"desde_kg": d, "costo_kg": c} for d, c in costos.items()]}
    respuesta = client.put(f"/v1/tarifas/{tarifa['id']}/tramos", json=tramos, headers=headers_de(pricing))
    assert respuesta.status_code == 200, respuesta.text
    assert [t["desde_kg"] for t in respuesta.json()] == [0, 0.5, 1, 5, 10]
    malos = {"tramos": [{"desde_kg": "0", "costo_kg": "12"}, {"desde_kg": "0.7", "costo_kg": "1"}]}
    rechazo = client.put(f"/v1/tarifas/{tarifa['id']}/tramos", json=malos, headers=headers_de(pricing))
    assert _codigo(rechazo) == "TRAMOS_INVALIDOS" and "0, 0.5, 1, 5, 10" in rechazo.json()["detail"]["mensaje"]

    h = headers_de(comercial)
    cargar_condiciones(db_session)
    creada = client.post("/v1/cotizaciones", json=esc.payload("FCA", peso_kg="0.8", cbm=None), headers=h)
    assert creada.status_code == 201, creada.text
    assert creada.json()["carga"]["peso_cobrable_kg"] == "0.800"
    propuesta = client.post(f"/v1/cotizaciones/{creada.json()['id']}/proponer-lineas", json={}, headers=h).json()
    flete = next(l for l in propuesta["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")
    # Tramo aplicable: +0,5 kg (10 USD/kg); venta MARKUP 20 % = 12 USD/kg × 0,8 kg = 9,60.
    assert (flete["concepto"].split()[1], flete["cantidad"], flete["precio_venta_unit_usd"], flete["subtotal_venta_usd"]) == (
        "COURIER", "0.8000", "12.0000", "9.6000")
    emitida = client.post(f"/v1/cotizaciones/{creada.json()['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    assert emitida.json()["totales"]["total_general"] == "9.60"
    fila = client.get(f"/v1/cotizaciones/{creada.json()['id']}/pdf", headers=h)
    assert fila.status_code == 200 and fila.content[:4] == b"%PDF"
    texto = " ".join(" ".join((pagina.extract_text() or "").split()) for pagina in PdfReader(BytesIO(fila.content)).pages)
    assert "servicio courier puerta a puerta" in texto and "Courier" in texto and "DHL Express" in texto
    assert esc.proveedor.nombre not in texto  # nunca el proveedor (agente)


# ---------- Unidad de equipo con un tipo de equipo nuevo (terrestre) ----------


def test_unidad_equipo_con_tipo_nuevo(client, crear_usuario, headers_de, db_session):  # TE0-13
    admin, pricing, comercial = crear_usuario("admin"), crear_usuario("pricing"), crear_usuario("comercial")
    h_admin, h_pricing, h = headers_de(admin), headers_de(pricing), headers_de(comercial)
    terrestre = db_session.scalars(select(TipoUbicacion.id).where(TipoUbicacion.codigo == "TERRESTRE")).one()
    assert client.patch(f"/v1/tipos-ubicacion/{terrestre}", json={"activo": True}, headers=h_admin).status_code == 200
    ftl = _crear_servicio(client, h_admin, codigo="FTL", nombre="Terrestre FTL", forma_cobro="UNIDAD_EQUIPO",
                          tipo_ubicacion_origen="TERRESTRE", tipo_ubicacion_destino="TERRESTRE",
                          descripcion_pdf="vía terrestre · camión completo (FTL)", etiqueta_transportista="Transportista")
    assert ftl["usa_tipo_equipo"] is True
    camion = client.post("/v1/tipos-equipo", json={"codigo": "53TR", "nombre": "Camión 53'", "servicio_id": ftl["id"]}, headers=h_pricing)
    assert camion.status_code == 201 and camion.json()["servicio_id"] == ftl["id"]

    pais = crear_pais(db_session)
    puertos = []
    for codigo in ("GYEBOD", "QTOBOD"):
        respuesta = client.post("/v1/puertos", json={"codigo": codigo, "nombre": codigo, "pais_id": pais.id, "tipo": "TERRESTRE"},
                                headers=h_admin)
        assert respuesta.status_code == 201, respuesta.text
        puertos.append(respuesta.json()["id"])
    esc = Escenario(db_session, comercial, modo="FCL", con_tarifa=False)
    cuerpo = {"proveedor_id": esc.proveedor.id, "modo": "FTL", "origen_puerto_id": puertos[0], "destino_puerto_id": puertos[1],
              "tipo_equipo_id": camion.json()["id"], "rate_unit": "CONTENEDOR", "costo": "800", "moneda_id": usd(db_session).id,
              "minimo": "0", "metodo_venta": "MARKUP", "parametro_venta": "25", "valido_desde": "2026-01-01",
              "valido_hasta": "2026-12-31"}
    ajeno = client.post("/v1/tarifas", json=cuerpo | {"tipo_equipo_id": tipo_equipo(db_session).id}, headers=h_pricing)
    assert (ajeno.status_code, _codigo(ajeno)) == (422, "TIPO_EQUIPO_NO_PERMITIDO")  # 40HC es de FCL
    assert client.post("/v1/tarifas", json=cuerpo, headers=h_pricing).status_code == 201
    datos = {"cliente_id": esc.cliente.id, "sentido": "IMPORTACION", "incoterm_id": db_session.scalars(
        select(Incoterm.id).where(Incoterm.codigo == "FCA")).one(), "modo": "FTL", "origen_puerto_id": puertos[0],
        "destino_puerto_id": puertos[1], "peso_kg": "15000", "contenedores": [{"tipo_equipo_id": camion.json()["id"], "cantidad": 2}]}
    creada = client.post("/v1/cotizaciones", json=datos, headers=h)
    assert creada.status_code == 201, creada.text
    sin_equipo = client.post("/v1/cotizaciones", json=datos | {"contenedores": []}, headers=h)
    assert _codigo(sin_equipo) == "CARGA_INCOMPLETA"
    propuesta = client.post(f"/v1/cotizaciones/{creada.json()['id']}/proponer-lineas", json={}, headers=h).json()
    flete = next(l for l in propuesta["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")
    assert (flete["tipo_equipo"], flete["cantidad"], flete["subtotal_venta_usd"]) == ("53TR", "2.0000", "2000.0000")


# ---------- Tarifa plana ----------


def test_tarifa_plana(client, crear_usuario, headers_de, db_session):  # TE0-14
    admin, pricing, comercial = crear_usuario("admin"), crear_usuario("pricing"), crear_usuario("comercial")
    _crear_servicio(client, headers_de(admin), codigo="DOCS", nombre="Documentos", forma_cobro="TARIFA_PLANA")
    esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
    esc.modo = "DOCS"
    rechazo = client.post("/v1/tarifas", json={"modo": "DOCS", "rate_unit": "KG", "proveedor_id": esc.proveedor.id,
                                               "origen_puerto_id": esc.origen.id, "destino_puerto_id": esc.destino.id,
                                               "costo": "40", "moneda_id": usd(db_session).id, "minimo": "0",
                                               "metodo_venta": "MARKUP", "parametro_venta": "25",
                                               "valido_desde": "2026-01-01", "valido_hasta": "2026-12-31"},
                          headers=headers_de(pricing))
    assert (rechazo.status_code, _codigo(rechazo)) == (422, "RATE_UNIT_INCOMPATIBLE")
    _tarifa(client, headers_de(pricing), esc, "DOCS", rate_unit="ENVIO", costo="40", parametro_venta="25")
    creada = client.post("/v1/cotizaciones", json=esc.payload("FCA", peso_kg="0", cbm=None), headers=headers_de(comercial))
    assert creada.status_code == 201, creada.text  # sin peso: la tarifa plana no lo exige
    propuesta = client.post(f"/v1/cotizaciones/{creada.json()['id']}/proponer-lineas", json={}, headers=headers_de(comercial)).json()
    flete = next(l for l in propuesta["lineas"] if l["bloque_incoterm"] == "FLETE_PRINCIPAL")
    assert (flete["cantidad"], flete["subtotal_venta_usd"]) == ("1.0000", "50.0000")


# ---------- Recargos con un servicio nuevo ----------


def test_recargo_de_servicio_nuevo(client, crear_usuario, headers_de, db_session):  # TE0-15
    _crear_servicio(client, headers_de(crear_usuario("admin")))
    h = headers_de(crear_usuario("pricing"))
    aeropuerto = crear_puerto(db_session, tipo="AEREO")
    ok = client.post("/v1/recargos", json=payload_recargo(db_session, aeropuerto, modo="COURIER", rate_unit="KG"), headers=h)
    assert ok.status_code == 201, ok.text
    maritimo = client.post("/v1/recargos", json=payload_recargo(db_session, crear_puerto(db_session), modo="COURIER"), headers=h)
    assert (maritimo.status_code, _codigo(maritimo)) == (422, "PUERTO_MODO_INCONSISTENTE")
    desconocido = client.post("/v1/recargos", json=payload_recargo(db_session, aeropuerto, modo="NOEXISTE"), headers=h)
    assert (desconocido.status_code, _codigo(desconocido)) == (422, "REFERENCIA_INEXISTENTE")


# ---------- Incoterms por servicio ----------


def test_incoterm_respeta_servicios_permitidos(client, crear_usuario, headers_de, db_session):  # TE0-16
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    esc = Escenario(db_session, comercial, modo="AEREO")
    bloqueada = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=headers_de(comercial))
    assert _codigo(bloqueada) == "INCOTERM_MODO_INVALIDO"
    assert "FOB es solo marítimo. Para aéreo use FCA, CPT o CIP" == bloqueada.json()["detail"]["mensaje"]
    respuesta = client.patch("/v1/incoterms/FOB", json={"servicios": ["LCL", "FCL", "AEREO"]}, headers=headers_de(admin))
    assert respuesta.status_code == 200
    assert (respuesta.json()["servicios"], respuesta.json()["solo_maritimo"]) == (["AEREO", "LCL", "FCL"], False)
    registro = db_session.scalars(select(Auditoria).where(Auditoria.entidad == "incoterm", Auditoria.entidad_id == "FOB")).one()
    assert (registro.valores_antes["servicios"], registro.valores_despues["servicios"]) == (["LCL", "FCL"], ["AEREO", "LCL", "FCL"])
    assert client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=headers_de(comercial)).status_code == 201
    malo = client.patch("/v1/incoterms/FOB", json={"servicios": ["NOEXISTE"]}, headers=headers_de(admin))
    assert (malo.status_code, _codigo(malo)) == (422, "REFERENCIA_INEXISTENTE")
    assert client.patch("/v1/incoterms/FOB", json={"servicios": ["LCL"]}, headers=headers_de(crear_usuario("pricing"))).status_code == 403


# ---------- Tipos de ubicación ----------


def test_tipo_ubicacion_regex(client, crear_usuario, headers_de, db_session):  # TE0-17
    h = headers_de(crear_usuario("admin"))
    invalida = client.post("/v1/tipos-ubicacion", json={"codigo": "FLUVIAL", "nombre": "Puerto fluvial", "regex_codigo": "[A-"}, headers=h)
    assert (invalida.status_code, _codigo(invalida)) == (422, "REGEX_INVALIDA")
    creado = client.post("/v1/tipos-ubicacion", json={"codigo": "FLUVIAL", "nombre": "Puerto fluvial",
                                                     "regex_codigo": "^[A-Z]{2}R[A-Z0-9]{2}$", "prefijo_pais": True,
                                                     "ayuda_codigo": "Código fluvial: país + R + 2, como ECRBA"}, headers=h)
    assert creado.status_code == 201, creado.text
    pais = crear_pais(db_session)
    malo = client.post("/v1/puertos", json={"codigo": f"{pais.iso2}X12", "nombre": "F", "pais_id": pais.id, "tipo": "FLUVIAL"}, headers=h)
    assert (_codigo(malo), malo.json()["detail"]["mensaje"]) == ("CODIGO_INVALIDO", "Código fluvial: país + R + 2, como ECRBA")
    bueno = client.post("/v1/puertos", json={"codigo": f"{pais.iso2}R12", "nombre": "F", "pais_id": pais.id, "tipo": "FLUVIAL"}, headers=h)
    assert bueno.status_code == 201, bueno.text
    # Una regla nueva que deja inválido un puerto existente se rechaza; desactivar con puertos activos, también.
    cambio = client.patch(f"/v1/tipos-ubicacion/{creado.json()['id']}", json={"regex_codigo": "^[A-Z]{3}$"}, headers=h)
    assert (cambio.status_code, _codigo(cambio)) == (409, "TIENE_DEPENDIENTES")
    apagar = client.patch(f"/v1/tipos-ubicacion/{creado.json()['id']}", json={"activo": False}, headers=h)
    assert (apagar.status_code, _codigo(apagar)) == (409, "TIENE_DEPENDIENTES")
    tipos = [t["codigo"] for t in client.get("/v1/tipos-ubicacion", headers=h).json()]
    assert {"MARITIMO", "AEREO", "TERRESTRE", "FLUVIAL"} <= set(tipos)


def test_puerto_de_tipo_inactivo_o_inexistente(client, crear_usuario, headers_de, db_session):  # TE0-18
    h = headers_de(crear_usuario("admin"))
    pais = crear_pais(db_session)
    inactivo = client.post("/v1/puertos", json={"codigo": "GYEBUS", "nombre": "T", "pais_id": pais.id, "tipo": "TERRESTRE"}, headers=h)
    assert (inactivo.status_code, _codigo(inactivo)) == (422, "PADRE_INACTIVO")
    nada = client.post("/v1/puertos", json={"codigo": "GYEBUS", "nombre": "T", "pais_id": pais.id, "tipo": "LUNAR"}, headers=h)
    assert (nada.status_code, _codigo(nada)) == (422, "REFERENCIA_INEXISTENTE")


# ---------- PDF de una cotización emitida antes de E0 (snapshot sin "servicio") ----------


@pytest.mark.parametrize(
    ("modo", "descripcion", "etiqueta"),
    [("AEREO", "vía aérea", "Aerolínea"), ("LCL", "vía marítima · carga consolidada (LCL)", "Naviera / Motonave"),
     ("FCL", "vía marítima · contenedor completo (FCL)", "Naviera / Motonave")],
)
def test_pdf_de_emitida_antes_de_e0(modo, descripcion, etiqueta):  # TE0-19
    datos = _datos_minimos() | {"modo": modo, "transportista": "Transportista X"}
    assert "servicio" not in datos
    html = pdf.renderizar_html(datos, False)
    assert f"({descripcion})" in html and etiqueta in html


def test_snapshot_nuevo_congela_el_servicio(client, crear_usuario, headers_de, db_session):  # TE0-20
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    esc = Escenario(db_session, comercial, modo="LCL")
    creada = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=h).json()
    client.post(f"/v1/cotizaciones/{creada['id']}/proponer-lineas", json={}, headers=h)
    assert client.post(f"/v1/cotizaciones/{creada['id']}/emitir", json={}, headers=h).status_code == 200
    snapshot = db_session.execute(text("SELECT snapshot_emision FROM cotizacion WHERE id = :i"), {"i": creada["id"]}).scalar_one()
    assert snapshot["servicio"] == {"codigo": "LCL", "nombre": "Marítimo LCL", "forma_cobro": "VOLUMEN_WM",
                                    "descripcion_pdf": "vía marítima · carga consolidada (LCL)",
                                    "etiqueta_transportista": "Naviera / Motonave"}


# ---------- Tipos de equipo y servicio ----------


def test_tipo_equipo_servicio(client, crear_usuario, headers_de, db_session):  # TE0-21
    h_pricing = headers_de(crear_usuario("pricing"))
    sin_servicio = client.post("/v1/tipos-equipo", json={"codigo": "45HC", "nombre": "Contenedor 45' HC"}, headers=h_pricing)
    assert sin_servicio.status_code == 201 and sin_servicio.json()["servicio_id"] == _servicio(db_session, "FCL").id
    lcl = client.post("/v1/tipos-equipo", json={"codigo": "45HD", "nombre": "X", "servicio_id": _servicio(db_session, "LCL").id},
                      headers=h_pricing)
    assert (lcl.status_code, _codigo(lcl)) == (422, "SERVICIO_INCOHERENTE")
    usado = tipo_equipo(db_session, "40HC")
    crear_tarifa(db_session, "FCL", tipo_equipo_id=usado.id)
    _crear_servicio(client, headers_de(crear_usuario("admin")), codigo="FCL2", forma_cobro="UNIDAD_EQUIPO",
                    tipo_ubicacion_origen="MARITIMO", tipo_ubicacion_destino="MARITIMO")
    mover = client.patch(f"/v1/tipos-equipo/{usado.id}", json={"servicio_id": _servicio(db_session, "FCL2").id}, headers=h_pricing)
    assert (mover.status_code, _codigo(mover)) == (409, "TIENE_DEPENDIENTES")
    filtrados = client.get(f"/v1/tipos-equipo?servicio_id={_servicio(db_session, 'FCL').id}", headers=h_pricing).json()
    assert {"20GP", "40GP", "40HC", "20RF", "40RF", "45HC"} <= {t["codigo"] for t in filtrados}


def test_tipo_equipo_por_orm_queda_en_el_primer_servicio_con_equipo(db_session):  # TE0-22 (compatibilidad F2)
    tipo = TipoEquipo(codigo="48HC", nombre="Prueba ORM")
    db_session.add(tipo)
    db_session.flush()
    assert tipo.servicio_id == _servicio(db_session, "FCL").id


def test_motor_puro_resuelve_la_forma_por_el_catalogo():  # TE0-23
    from app.services import cotizador

    carga = cotizador.Carga("LCL", peso_kg=D("1500"), cbm=D("1.2"))
    assert cotizador.cantidad_cobrable(carga) == D("1.5000")
    explicita = cotizador.Carga("CUALQUIERA", peso_kg=D("1500"), cbm=D("1.2"), forma_cobro="TARIFA_PLANA")
    assert cotizador.cantidad_cobrable(explicita) == D("1")


def test_tipo_equipo_no_va_en_servicio_sin_equipo(client, crear_usuario, headers_de, db_session):  # TE0-24
    h = headers_de(crear_usuario("pricing"))
    datos = payload_recargo(db_session, crear_puerto(db_session, tipo="AEREO"), modo="AEREO", rate_unit="KG",
                            tipo_equipo_id=tipo_equipo(db_session).id)
    respuesta = client.post("/v1/recargos", json=datos, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "TIPO_EQUIPO_NO_PERMITIDO")


# ---------- Pantallas nuevas ----------


@pytest.mark.parametrize("pagina", ["servicios", "tipos-ubicacion", "tipos-equipo"])
def test_paginas_e0(client, pagina):  # TE0-25 (mismas reglas que T204 y T257)
    import re

    from test_frontend import PATRONES_PROHIBIDOS_JS

    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    hojas_locales = re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text)
    assert hojas_locales == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []


def test_menu_servicios_solo_admin(client):  # TE0-26
    from test_frontend import _permisos_menu

    assert _permisos_menu(client, "Servicios") == ["configuracion.servicios.gestionar"]
    assert _permisos_menu(client, "Tipos de ubicación") == ["configuracion.servicios.gestionar"]
    assert _permisos_menu(client, "Tipos de equipo") == ["catalogo.editar", "tarifa.ver"]


def test_fuente_unica_de_servicios_activos(db_session):  # TE0-27
    from app.services import servicios

    activos = [s.codigo for s in servicios.servicios_activos(db_session)]
    assert activos[:3] == ["AEREO", "LCL", "FCL"]

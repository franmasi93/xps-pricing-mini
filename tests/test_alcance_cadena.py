"""Alcance en cadena de los recargos (TAC-01 a TAC-16) y tipo de carga (D-T1..D-T8).

La prueba central (TAC-01) compara, sobre un banco aleatorio de recargos "de antes" (puerto, servicio, tipo de equipo
y proveedor), lo que propone el motor nuevo con lo que proponía la regla de antes: deben ser idénticos.
Los precios de F3 al centavo los vigila test_regresion_f3.py.
"""
import random
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models import Recargo, RecargoAlcance, RecargoTarifa, TipoCarga
from app.services import alcance, cotizador
from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_pais, crear_proveedor, crear_puerto, payload_recargo, tipo_equipo

INCOTERM = {"LCL": "FOB", "FCL": "FOB", "AEREO": "FCA"}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _escenario(db, usuario, modo="LCL", **tarifa):
    extra = {"tipo_equipo_id": tipo_equipo(db, "40HC").id} if modo == "FCL" else {}
    return Escenario(db, usuario, modo=modo, **(extra | tarifa))


def _crear_cot(client, h, esc, incoterm=None, **cambios):
    r = client.post("/v1/cotizaciones", json=esc.payload(incoterm or INCOTERM[esc.modo], **cambios), headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _proponer(client, h, cotizacion_id, **cuerpo):
    r = client.post(f"/v1/cotizaciones/{cotizacion_id}/proponer-lineas", json=cuerpo, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _cot(client, h, esc, incoterm=None, **cambios):
    return _proponer(client, h, _crear_cot(client, h, esc, incoterm, **cambios)["id"])


def _ids(cotizacion, incluida=True):
    return {l["recargo_id"] for l in cotizacion["lineas"] if l["recargo_id"] and l["incluida"] == incluida}


def _alcance(db, recargo, **niveles):
    """Reemplaza el alcance de un recargo creado por ORM (nivel → lista de valores)."""
    db.query(RecargoAlcance).filter(RecargoAlcance.recargo_id == recargo.id).delete()
    for nivel, valores in niveles.items():
        for valor in valores:
            es_texto = nivel in alcance.NIVELES_TEXTO
            db.add(RecargoAlcance(recargo_id=recargo.id, nivel=nivel, valor_texto=valor if es_texto else None,
                                  valor_id=None if es_texto else valor))
    recargo = db.get(Recargo, recargo.id)
    recargo.alcance_firma = alcance.firma({k: set(v) for k, v in niveles.items() if v}, recargo.puerto_id, recargo.modo,
                                          recargo.tipo_equipo_id, recargo.proveedor_id)
    db.commit()
    db.expire_all()


# ---------- TAC-01/02: la migración no cambia lo que se propone ----------


def _propuesta_de_antes(db, cotizacion_id) -> set:
    """La regla de antes (FIX + D-R2, sin alcance): por puerto del bloque y lado, filtro de proveedor, servicio y tipo de
    equipo, y D-F3-7 con elegir_mas_especifico SIN rango_de (el camino de antes, intacto)."""
    from app.models import Cotizacion
    from app.services import cotizaciones as servicio
    from app.services.incoterms import bloques_incluidos

    cot = db.get(Cotizacion, cotizacion_id)
    bloques, _ = bloques_incluidos(cot.incoterm, cot.sentido)
    flete = next(l for l in cot.lineas if l.tarifa_id)
    prov, tipos = flete.proveedor_id, [c.tipo_equipo_id for c in cot.contenedores]
    hoy = servicio.fechas.hoy_ecuador()
    salida = set()
    for campo in servicio.CAMPOS_RECARGO:
        bloque = servicio.BLOQUE_RECARGO[campo]
        puerto, lado = servicio._puerto_de_bloque(cot, bloque)
        consulta = select(Recargo).where(Recargo.activo.is_(True), Recargo.puerto_id == puerto.id, Recargo.bloque_incoterm == bloque,
                                         Recargo.valido_desde <= hoy, Recargo.valido_hasta >= hoy)
        if lado is not None:
            consulta = consulta.where(Recargo.lado == lado)
        vigentes = list(db.scalars(consulta.order_by(Recargo.id)))
        elegidos = cotizador.elegir_mas_especifico(vigentes, prov, cot.modo, tipos, por_tipo_equipo=cot.servicio.usa_tipo_equipo)
        ganadores = {r.id for r, _ in elegidos}
        sel = "INCOTERM" if campo in bloques else "FUERA_INCOTERM"
        salida |= {(r.id, sel) for r, _ in elegidos}
        salida |= {(r.id, "ALTERNATIVA") for r in cotizador.recargos_aplicables(vigentes, prov, cot.modo, tipos) if r.id not in ganadores}
    return salida


@pytest.mark.parametrize("modo", ["LCL", "FCL", "AEREO"])
@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_migracion_no_cambia_lo_que_se_propone(client, crear_usuario, headers_de, db_session, modo, semilla):  # TAC-01
    rnd = random.Random(semilla)
    comercial = crear_usuario("pricing")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, modo)
    otro_puerto = crear_puerto(db_session, pais=esc.destino.pais, tipo=esc.destino.tipo)
    otro_prov = crear_proveedor(db_session)
    gp = tipo_equipo(db_session, "20GP")
    hc = tipo_equipo(db_session, "40HC")
    lados = {"ORIGEN": ["RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN"], "DESTINO": ["GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL"]}
    usadas = set()
    for n in range(28):
        lado = rnd.choice(["ORIGEN", "DESTINO"])
        puerto = rnd.choice([esc.origen, esc.destino, otro_puerto])
        cambios = {"concepto": rnd.choice(["THC", "thc", "BL", "Handling", "Aduana"]),
                   "proveedor_id": rnd.choice([None, esc.proveedor.id, otro_prov.id])}
        servicio = rnd.choice([None, modo, "LCL" if modo != "LCL" else "AEREO"])
        cambios["modo"] = servicio
        if servicio == "FCL" and rnd.random() < 0.5:
            cambios |= {"tipo_equipo_id": rnd.choice([gp.id, hc.id]), "rate_unit": "CONTENEDOR"}
        if servicio == "AEREO" or (servicio is None and esc.destino.tipo == "AEREO"):
            cambios.setdefault("rate_unit", "ENVIO")
        bloque = rnd.choice(lados[lado])
        clave = (cambios["proveedor_id"], puerto.id, lado, bloque, cambios["concepto"].lower(), servicio, cambios.get("tipo_equipo_id"))
        if clave in usadas:
            continue  # la base no admite dos recargos superpuestos con la misma clave
        usadas.add(clave)
        crear_recargo(db_session, puerto, bloque, lado, costo=str(10 + n), **cambios)
    cot = _cot(client, h, esc, "EXW")
    nueva = {(l["recargo_id"], l["seleccion"]) for l in cot["lineas"] if l["recargo_id"]}
    assert nueva == _propuesta_de_antes(db_session, cot["id"])


def test_sql_de_la_migracion_igual_al_alcance_por_defecto(db_session, crear_usuario):  # TAC-02
    esc = _escenario(db_session, crear_usuario("comercial"), "FCL")
    r = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", modo="FCL", tipo_equipo_id=tipo_equipo(db_session).id,
                      rate_unit="CONTENEDOR", proveedor_id=esc.proveedor.id)
    por_defecto = alcance.de(db_session.get(Recargo, r.id))
    db_session.execute(text("DELETE FROM recargo_alcance WHERE recargo_id = :i"), {"i": r.id})
    for sql in (  # las mismas sentencias de 0016_alcance_recargos_tipo_carga.py, solo para este recargo
        "INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'PUERTO', puerto_id FROM recargo WHERE puerto_id IS NOT NULL AND id = :i",
        "INSERT INTO recargo_alcance (recargo_id, nivel, valor_texto) SELECT id, 'SERVICIO', modo FROM recargo WHERE modo IS NOT NULL AND id = :i",
        "INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'TIPO_EQUIPO', tipo_equipo_id FROM recargo WHERE tipo_equipo_id IS NOT NULL AND id = :i",
        "INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'PROVEEDOR', proveedor_id FROM recargo WHERE proveedor_id IS NOT NULL AND id = :i",
    ):
        db_session.execute(text(sql), {"i": r.id})
    db_session.commit()
    db_session.expire_all()
    assert alcance.de(db_session.get(Recargo, r.id)) == por_defecto
    assert set(por_defecto) == {"PUERTO", "SERVICIO", "TIPO_EQUIPO", "PROVEEDOR"}


# ---------- TAC-03/04: cada nivel filtra, solo y combinado; multiselección; "Todos" ----------


def test_cada_nivel_filtra(client, crear_usuario, headers_de, db_session):  # TAC-03
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "LCL")
    dest, orig = esc.destino, esc.origen
    otra_region = crear_pais(db_session)
    casos = {  # nivel → (valores que aplican, valores que no)
        "SERVICIO": (["LCL", "FCL"], ["AEREO"]), "MODO": (["MARITIMO"], ["AEREO"]),
        "REGION": ([dest.pais.region_id], [otra_region.region_id]), "PAIS": ([dest.pais_id], [otra_region.id]),
        "PUERTO": ([dest.id, crear_puerto(db_session).id], [orig.id]), "PROVEEDOR": ([esc.proveedor.id], [crear_proveedor(db_session).id]),
        "TIPO_CARGA": (["GENERAL"], ["IMO"]),
    }
    aplica, no_aplica = {}, {}
    for nivel, (si, no) in casos.items():
        aplica[nivel] = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto=f"si {nivel}")
        _alcance(db_session, aplica[nivel], **{nivel: si})
        no_aplica[nivel] = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto=f"no {nivel}")
        _alcance(db_session, no_aplica[nivel], **{nivel: no})
    ruta_si = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto="ruta si")
    _alcance(db_session, ruta_si, PUERTO_ORIGEN=[orig.id], PUERTO_DESTINO=[dest.id])
    ruta_no = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto="ruta no")
    _alcance(db_session, ruta_no, PUERTO_ORIGEN=[dest.id], PUERTO_DESTINO=[orig.id])
    todos = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto="todos")
    _alcance(db_session, todos)
    combinado = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto="combinado")
    _alcance(db_session, combinado, SERVICIO=["LCL"], PAIS=[dest.pais_id], TIPO_CARGA=["GENERAL"])
    combinado_no = crear_recargo(db_session, dest, "GASTOS_DESTINO", "DESTINO", concepto="combinado no")
    _alcance(db_session, combinado_no, SERVICIO=["LCL"], PAIS=[otra_region.id])
    cot = _cot(client, h, esc)
    en_cot = _ids(cot)
    assert {r.id for r in aplica.values()} | {ruta_si.id, todos.id, combinado.id} <= en_cot
    assert en_cot.isdisjoint({r.id for r in no_aplica.values()} | {ruta_no.id, combinado_no.id})
    motivos = {r["recargo_id"]: " · ".join(r["motivos"]) for r in
               client.get(f"/v1/cotizaciones/{cot['id']}/recargos-descartados", headers=h).json()["recargos"]}
    assert "no aplica: el alcance de región es solo" in motivos[no_aplica["REGION"].id]
    assert "no aplica: el alcance de ruta es solo" in motivos[ruta_no.id]
    assert "tipo de carga es solo IMO" in motivos[no_aplica["TIPO_CARGA"].id]


def test_precedencia_completa(client, crear_usuario, headers_de, db_session):  # TAC-04
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "LCL")
    dest, orig = esc.destino, esc.origen
    niveles = [("todos", {}), ("servicio", {"SERVICIO": ["LCL"]}), ("región", {"REGION": [dest.pais.region_id]}),
               ("país", {"PAIS": [dest.pais_id]}), ("puerto", {"PUERTO": [dest.id]}),
               ("ruta exacta", {"PUERTO_ORIGEN": [orig.id], "PUERTO_DESTINO": [dest.id]})]
    creados = []
    for nombre, nivel in niveles:
        # se crea en un puerto propio y luego se le da el alcance (la clave de superposición incluye el alcance)
        recargo = crear_recargo(db_session, crear_puerto(db_session), "GASTOS_DESTINO", "DESTINO", concepto="THC")
        _alcance(db_session, recargo, **nivel)
        creados.append(recargo)
        cot = _cot(client, h, esc)
        assert _ids(cot) & {r.id for r in creados} == {recargo.id}, nombre  # el más específico gana
        if len(creados) > 1:
            perdedor = next(l for l in cot["lineas"] if l["recargo_id"] == creados[-2].id)
            if nombre != "servicio":
                assert f"más específico ({nombre})" in perdedor["motivo_alternativa"], perdedor["motivo_alternativa"]
    vinculado = crear_recargo(db_session, crear_puerto(db_session), "GASTOS_DESTINO", "DESTINO", concepto="THC")
    db_session.add(RecargoTarifa(recargo_id=vinculado.id, tarifa_id=esc.tarifa.id))
    db_session.commit()
    cot = _cot(client, h, esc)
    assert _ids(cot) & ({r.id for r in creados} | {vinculado.id}) == {vinculado.id}  # tarifa vinculada > ruta


def test_empate_proveedor_del_flete_le_gana_al_propio(client, crear_usuario, headers_de, db_session):  # TAC-05
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "LCL")
    propio = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC")
    del_prov = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="THC", proveedor_id=esc.proveedor.id)
    cot = _cot(client, h, esc)
    assert _ids(cot) & {propio.id, del_prov.id} == {del_prov.id}
    perdedor = next(l for l in cot["lineas"] if l["recargo_id"] == propio.id)
    assert "del proveedor del flete" in perdedor["motivo_alternativa"]
    # tipo de carga específico le gana a "Todos" en el mismo nivel de ubicación (D-T5)
    general = crear_recargo(db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO", concepto="Aduana")
    especifico = crear_recargo(db_session, crear_puerto(db_session), "DESPACHO_IMPORT", "DESTINO", concepto="Aduana")
    _alcance(db_session, especifico, PUERTO=[esc.destino.id], TIPO_CARGA=["GENERAL"])
    assert _ids(_cot(client, h, esc)) & {general.id, especifico.id} == {especifico.id}


# ---------- TAC-06/07: API, resumen, filtro, ruta y advertencias ----------


def test_api_alcance_resumen_y_filtro(client, crear_usuario, headers_de, db_session):  # TAC-06
    h = headers_de(crear_usuario("admin"))
    esc = _escenario(db_session, crear_usuario("comercial"), "LCL")
    cuerpo = payload_recargo(db_session, esc.destino) | {"puerto_id": None, "bloque_fiscal": "FACTURA",
                                                         "alcance": {"servicios": ["LCL", "FCL"], "puertos": [esc.destino.id]}}
    creado = client.post("/v1/recargos", json=cuerpo, headers=h)
    assert creado.status_code == 201, creado.text
    datos = creado.json()
    assert datos["alcance"] == {"servicios": ["FCL", "LCL"], "puertos": [esc.destino.id]}
    assert datos["aplica_a"].startswith("Aplica a: FCL y LCL") and f"destino {esc.destino.codigo}" in datos["aplica_a"]
    assert datos["puerto"]["id"] == esc.destino.id  # un solo puerto: copia en la columna de antes
    region = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino) | {
        "puerto_id": None, "bloque_fiscal": "FACTURA", "alcance": {"regiones": [esc.destino.pais.region_id]}}, headers=h).json()
    lejos = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino) | {
        "puerto_id": None, "bloque_fiscal": "FACTURA", "alcance": {"paises": [esc.origen.pais_id]}}, headers=h).json()
    en_puerto = {r["id"] for r in client.get(f"/v1/recargos?aplica_en={esc.destino.id}", headers=h).json()}
    assert {datos["id"], region["id"]} <= en_puerto and lejos["id"] not in en_puerto
    incompleta = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino) | {
        "alcance": {"puertos_origen": [esc.origen.id]}}, headers=h)
    assert incompleta.json()["detail"]["codigo"] == "RUTA_INCOMPLETA"
    imo_sin_tipo = client.post("/v1/recargos", json=payload_recargo(db_session, esc.destino) | {
        "alcance": {"clases_imo": ["3"]}}, headers=h)
    assert imo_sin_tipo.json()["detail"]["codigo"] == "CLASE_IMO_SIN_TIPO"
    editado = client.patch(f"/v1/recargos/{datos['id']}", json={"alcance": {"paises": [esc.destino.pais_id]}}, headers=h).json()
    assert editado["alcance"] == {"paises": [esc.destino.pais_id]} and editado["puerto"] is None


def test_advertencia_por_nivel_de_ubicacion(client, crear_usuario, headers_de, db_session):  # TAC-07
    h = headers_de(crear_usuario("pricing"))
    esc = _escenario(db_session, crear_usuario("comercial"), "LCL")

    def avisos(lado, **alc):
        return client.post("/v1/recargos/validar", json={"lado": lado, "alcance": alc}, headers=h).json()["advertencias"]

    assert "gasto de destino" in avisos("DESTINO", paises=[esc.origen.pais_id])[0]
    assert "gasto de destino" in avisos("DESTINO", regiones=[esc.origen.pais.region_id])[0]
    assert "gasto de origen" in avisos("ORIGEN", puertos=[esc.destino.id])[0]
    assert avisos("DESTINO", paises=[esc.destino.pais_id]) == []


# ---------- Tipo de carga (TAC-08 a TAC-14) ----------


def _imo(clase="3", un="1263", grupo="II", msds=False):
    return {"tipo_carga": "IMO", "imo_clase": clase, "imo_un": un, "imo_grupo": grupo, "msds_recibida": msds}


def test_tarifa_que_no_acepta_imo_no_se_ofrece(client, crear_usuario, headers_de, db_session):  # TAC-08
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "LCL")
    cot = _crear_cot(client, h, esc, **_imo())
    opciones = client.get(f"/v1/cotizaciones/{cot['id']}/opciones-flete", headers=h).json()
    assert opciones["grupos"][0]["opciones"] == []
    sin_tarifa = client.post(f"/v1/cotizaciones/{cot['id']}/proponer-lineas", json={}, headers=h)
    assert sin_tarifa.json()["detail"]["codigo"] == "SIN_TARIFA"
    esc.tarifa.tipos_carga = ["GENERAL", "IMO"]
    esc.tarifa.clases_imo_excluidas = ["1"]
    db_session.commit()
    assert client.get(f"/v1/cotizaciones/{cot['id']}/opciones-flete", headers=h).json()["grupos"][0]["opciones"]
    clase1 = _crear_cot(client, h, esc, **_imo(clase="1.4"))
    assert client.get(f"/v1/cotizaciones/{clase1['id']}/opciones-flete", headers=h).json()["grupos"][0]["opciones"] == []
    descartes = client.get(f"/v1/cotizaciones/{clase1['id']}/recargos-descartados", headers=h).json()
    assert descartes["tarifas"][0]["motivos"] == ["no acepta IMO clase 1"]


def test_recargo_imo_y_clases(client, crear_usuario, headers_de, db_session):  # TAC-09
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc = _escenario(db_session, pricing, "LCL", tipos_carga=["GENERAL", "IMO"])
    imo = crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", concepto="Recargo IMO")
    _alcance(db_session, imo, PUERTO=[esc.destino.id], TIPO_CARGA=["IMO"])
    clase3 = crear_recargo(db_session, esc.destino, "DESPACHO_IMPORT", "DESTINO", concepto="Manejo clase 3")
    _alcance(db_session, clase3, PUERTO=[esc.destino.id], TIPO_CARGA=["IMO"], CLASE_IMO=["3"])
    general = _cot(client, h, esc)
    assert _ids(general).isdisjoint({imo.id, clase3.id})
    con_imo3 = _cot(client, h, esc, **_imo(clase="3"))
    assert {imo.id, clase3.id} <= _ids(con_imo3)
    con_imo8 = _cot(client, h, esc, **_imo(clase="8", grupo=None))
    assert imo.id in _ids(con_imo8) and clase3.id not in _ids(con_imo8)
    assert "Falta la MSDS" in con_imo8["avisos"]
    assert con_imo8["carga_especial"] == "Carga peligrosa · IMO clase 8 · UN1263"


@pytest.mark.parametrize(("cambios", "codigo"), [
    ({"imo_clase": "10"}, "IMO_CLASE_INVALIDA"), ({"imo_clase": ""}, "IMO_CLASE_INVALIDA"),
    ({"imo_un": "12"}, "IMO_UN_INVALIDO"), ({"imo_grupo": "IV"}, "IMO_GRUPO_INVALIDO"), ({"tipo_carga": "NO_EXISTE"}, "TIPO_CARGA_INVALIDO"),
])
def test_validacion_datos_imo(client, crear_usuario, headers_de, db_session, cambios, codigo):  # TAC-10
    comercial = crear_usuario("comercial")
    esc = _escenario(db_session, comercial, "LCL")
    r = client.post("/v1/cotizaciones", json=esc.payload("FOB", **(_imo() | cambios)), headers=headers_de(comercial))
    assert (r.status_code, r.json()["detail"]["codigo"]) == (422, codigo)


def test_general_limpia_datos_imo_y_es_el_defecto(client, crear_usuario, headers_de, db_session):  # TAC-11
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    cot = _crear_cot(client, h, esc)
    assert (cot["tipo_carga"], cot["imo"]["clase"], cot["carga_especial"]) == ("GENERAL", None, None)
    refrigerada = _crear_cot(client, h, esc, tipo_carga="REFRIGERADA", imo_clase="3", imo_un="1263")
    assert (refrigerada["imo"]["clase"], refrigerada["carga_especial"]) == (None, "Carga refrigerada")


def test_pdf_con_linea_imo_y_texto_adicional(client, crear_usuario, headers_de, db_session):  # TAC-12
    from app.models import Cotizacion
    from app.services import pdf

    cargar_condiciones(db_session)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL", tipos_carga=["GENERAL", "IMO"])
    cot = _cot(client, h, esc, **_imo(msds=True))
    assert "Falta la MSDS" not in cot["avisos"]
    assert client.post(f"/v1/cotizaciones/{cot['id']}/emitir", json={}, headers=h).status_code == 200
    db_session.expire_all()
    foto = db_session.get(Cotizacion, cot["id"]).snapshot_emision
    html = pdf.renderizar_html(foto, False)
    assert "Carga peligrosa · IMO clase 3 · UN1263 · GE II" in html
    assert "código IMDG / IATA DGR" in foto["condiciones"]
    general = _cot(client, h, esc)
    assert client.post(f"/v1/cotizaciones/{general['id']}/emitir", json={}, headers=h).status_code == 200
    db_session.expire_all()
    foto_general = db_session.get(Cotizacion, general["id"]).snapshot_emision
    assert "carga_especial" not in foto_general and "IMDG" not in foto_general["condiciones"]  # GENERAL sin cambios


def test_catalogo_tipos_de_carga(client, crear_usuario, headers_de, db_session):  # TAC-13
    admin = headers_de(crear_usuario("admin"))
    codigos = [t["codigo"] for t in client.get("/v1/tipos-carga", headers=admin).json()]
    assert codigos[:6] == ["GENERAL", "IMO", "REFRIGERADA", "SOBREDIMENSIONADA", "PERECIBLE", "ALTO_VALOR"]
    assert db_session.scalars(select(TipoCarga).where(TipoCarga.codigo == "IMO")).one().pide_imo is True
    nuevo = client.post("/v1/tipos-carga", json={"codigo": "animales vivos", "nombre": "Animales vivos"}, headers=admin)
    assert nuevo.status_code == 201 and nuevo.json()["codigo"] == "ANIMALES_VIVOS"
    general = next(t for t in client.get("/v1/tipos-carga", headers=admin).json() if t["codigo"] == "GENERAL")
    assert client.patch(f"/v1/tipos-carga/{general['id']}", json={"activo": False}, headers=admin).status_code == 409
    comercial = headers_de(crear_usuario("comercial"))
    assert client.get("/v1/tipos-carga", headers=comercial).status_code == 200
    assert client.post("/v1/tipos-carga", json={"codigo": "X", "nombre": "X"}, headers=comercial).status_code == 403


def test_tarifa_api_tipos_de_carga(client, crear_usuario, headers_de, db_session):  # TAC-14
    h = headers_de(crear_usuario("admin"))
    esc = _escenario(db_session, crear_usuario("comercial"), "LCL")
    r = client.patch(f"/v1/tarifas/{esc.tarifa.id}", json={"tipos_carga": ["imo", "GENERAL"], "clases_imo_excluidas": ["1", "7"]}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["tipos_carga"], r.json()["clases_imo_excluidas"]) == (["GENERAL", "IMO"], ["1", "7"])
    malo = client.patch(f"/v1/tarifas/{esc.tarifa.id}", json={"tipos_carga": ["GENERAL"], "clases_imo_excluidas": ["1"]}, headers=h)
    assert malo.json()["detail"]["codigo"] == "CLASE_IMO_SIN_TIPO"


def test_comercial_sin_costo_margen_ni_proveedor(client, crear_usuario, headers_de, db_session):  # TAC-15
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    esc = _escenario(db_session, comercial, "LCL")
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", proveedor_id=esc.proveedor.id)
    cot = _cot(client, h, esc)
    prohibidas = {"costo_usd", "margen_usd", "proveedor", "proveedor_id", "proveedor_propio"}
    assert all(prohibidas.isdisjoint(l) for l in cot["lineas"])
    assert {"costo_total", "margen_total"}.isdisjoint(cot["totales"])


def test_pantallas(client):  # TAC-16
    from test_frontend import PATRONES_PROHIBIDOS_JS

    for pagina, script in (("recargos", "recargos.js"), ("tipos-carga", "tipos-carga.js"), ("cotizador", "cotizador.js"),
                           ("tarifas", "tarifas.js")):
        html = client.get(f"/app/{pagina}.html").text
        assert "<style" not in html and "style=" not in html
        assert [p for p in PATRONES_PROHIBIDOS_JS if p in client.get(f"/app/js/{script}").text] == []
    assert [p for p in PATRONES_PROHIBIDOS_JS if p in client.get("/app/js/alcance.js").text] == []
    assert 'id="niveles-alcance"' in client.get("/app/recargos.html").text
    assert 'id="tipo-carga"' in client.get("/app/cotizador.html").text
    assert '"tipos-carga.html", permisos: ["catalogo.editar"]' in client.get("/app/js/layout.js").text

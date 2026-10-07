"""M5 Tarifas y tramos aéreos (T139, T144–T176, T184, T186, T205, T206)."""
import random
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import ErrorNegocio
from app.models import Auditoria, Proveedor, Puerto, Tarifa, TipoEquipo
from app.schemas.tarifas import CLAVES_DE_COSTO
from fabricas import crear_moneda, crear_proveedor, crear_tarifa, payload_recargo, payload_tarifa, puertos_para, tipo_equipo


def _post(client, headers, datos):
    return client.post("/v1/tarifas", json=datos, headers=headers)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _hoy(monkeypatch, dia: date) -> None:
    monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: dia)


def _auditoria(db_session, entidad: str, entidad_id) -> list[Auditoria]:
    return db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == entidad, Auditoria.entidad_id == str(entidad_id)).order_by(Auditoria.id)
    ).all()


# ---------- Tipos de equipo ----------


@pytest.mark.parametrize("rol", ["comercial", "gerencia"])
def test_tipos_equipo_lectura_y_escritura(client, crear_usuario, headers_de, db_session, rol):  # T139
    h = headers_de(crear_usuario(rol))
    codigos = {t["codigo"] for t in client.get("/v1/tipos-equipo", headers=h).json()}
    assert {"20GP", "40GP", "40HC", "20RF", "40RF"} <= codigos
    assert client.post("/v1/tipos-equipo", json={"codigo": "45HC", "nombre": "X"}, headers=h).status_code == 403
    tipo = tipo_equipo(db_session)
    assert client.patch(f"/v1/tipos-equipo/{tipo.id}", json={"nombre": "X"}, headers=h).status_code == 403


# ---------- Alta y validaciones ----------


@pytest.mark.parametrize("modo", ["AEREO", "LCL", "FCL"])
def test_alta_valida_por_modo(client, crear_usuario, headers_de, db_session, modo):  # T144
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_tarifa(db_session, modo))
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["modo"], cuerpo["precio_venta"], cuerpo["precio_venta_minimo"]) == (modo, "120.0000", "0.0000")
    assert (cuerpo["tipo_equipo"] is not None) == (modo == "FCL")


@pytest.mark.parametrize(
    ("campo", "valor"), [("costo", "100.12345"), ("minimo", "1.00001"), ("parametro_venta", "20.00001")]
)
def test_mas_de_4_decimales_422(client, crear_usuario, headers_de, db_session, campo, valor):  # T145
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_tarifa(db_session, **{campo: valor}))
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == "MONTO_INVALIDO"


@pytest.mark.parametrize(
    ("modo", "con_equipo", "esperado"),
    [("FCL", False, "TIPO_EQUIPO_REQUERIDO"), ("AEREO", True, "TIPO_EQUIPO_NO_PERMITIDO"), ("LCL", True, "TIPO_EQUIPO_NO_PERMITIDO")],
)
def test_tipo_equipo_segun_modo(client, crear_usuario, headers_de, db_session, modo, con_equipo, esperado):  # T146
    datos = payload_tarifa(db_session, modo, tipo_equipo_id=tipo_equipo(db_session).id if con_equipo else None)
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == esperado


@pytest.mark.parametrize(("modo", "unidad"), [("AEREO", "WM"), ("LCL", "KG"), ("FCL", "ENVIO")])
def test_rate_unit_no_permitido(client, crear_usuario, headers_de, db_session, modo, unidad):  # T147
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_tarifa(db_session, modo, rate_unit=unidad))
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == "RATE_UNIT_INCOMPATIBLE"


@pytest.mark.parametrize(("modo", "puertos_de"), [("AEREO", "LCL"), ("LCL", "AEREO")])
def test_puerto_incompatible_con_modo(client, crear_usuario, headers_de, db_session, modo, puertos_de):  # T148
    origen, destino = puertos_para(db_session, puertos_de)
    datos = payload_tarifa(db_session, modo, origen_puerto_id=origen.id, destino_puerto_id=destino.id)
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == "PUERTO_MODO_INCONSISTENTE"


def test_origen_igual_destino_422(client, crear_usuario, headers_de, db_session):  # T149
    datos = payload_tarifa(db_session)
    datos["destino_puerto_id"] = datos["origen_puerto_id"]
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "ORIGEN_IGUAL_DESTINO")


def test_vigencia_invertida_422(client, crear_usuario, headers_de, db_session):  # T150
    datos = payload_tarifa(db_session, valido_desde="2026-06-01", valido_hasta="2026-05-31")
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "VIGENCIA_INVALIDA")


@pytest.mark.parametrize("padre", ["proveedor", "moneda", "puerto", "tipo_equipo"])
def test_padre_inactivo(client, crear_usuario, headers_de, db_session, padre):  # T151
    datos = payload_tarifa(db_session, "FCL")
    if padre == "proveedor":
        db_session.get(Proveedor, datos["proveedor_id"]).activo = False
    elif padre == "moneda":
        datos["moneda_id"] = crear_moneda(db_session, activo=False).id
    elif padre == "puerto":
        db_session.get(Puerto, datos["origen_puerto_id"]).activo = False
    else:
        inactivo = TipoEquipo(codigo=f"{random.randint(50, 99)}ZZ", nombre="Inactivo de prueba", activo=False)
        db_session.add(inactivo)
        db_session.flush()
        datos["tipo_equipo_id"] = inactivo.id
    db_session.commit()
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == ("MONEDA_INACTIVA" if padre == "moneda" else "PADRE_INACTIVO")


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"metodo_venta": "MANUAL", "parametro_venta": None}, "ESQUEMA_VENTA_INVALIDO"),
        ({"metodo_venta": "MANUAL", "precio_venta_manual": "130"}, "ESQUEMA_VENTA_INVALIDO"),
        ({"precio_venta_manual": "130"}, "ESQUEMA_VENTA_INVALIDO"),
        (
            {"metodo_venta": "MANUAL", "parametro_venta": None, "precio_venta_manual": "130", "minimo": "10"},
            "ESQUEMA_VENTA_INVALIDO",
        ),
        ({"parametro_venta": "-1"}, "MONTO_INVALIDO"),
    ],
    ids=["manual_sin_precio", "manual_con_parametro", "markup_con_precio_manual", "manual_minimo_sin_minimo_venta", "parametro_negativo"],
)
def test_esquema_de_venta_invalido(client, crear_usuario, headers_de, db_session, cambios, esperado):  # T152
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_tarifa(db_session, **cambios))
    assert respuesta.status_code == 422
    assert _codigo(respuesta) == esperado


# ---------- Vigencias (D-F2-1) ----------


def _primera_y_clave(client, headers, db_session) -> tuple[dict, dict]:
    datos = payload_tarifa(db_session, valido_desde="2026-01-01", valido_hasta="2026-06-30")
    primera = _post(client, headers, datos).json()
    return primera, datos


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [("2026-06-01", "2026-12-31"), ("2026-02-01", "2026-03-01"), ("2026-06-30", "2026-07-31")],
    ids=["parcial", "contenida", "mismo_dia"],
)
def test_superposicion_409(client, crear_usuario, headers_de, db_session, desde, hasta):  # T153
    h = headers_de(crear_usuario("pricing"))
    primera, datos = _primera_y_clave(client, h, db_session)
    respuesta = _post(client, h, datos | {"valido_desde": desde, "valido_hasta": hasta})
    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert (detalle["codigo"], detalle["id_en_conflicto"]) == ("VIGENCIA_SUPERPUESTA", primera["id"])


def test_adyacencia_permitida(client, crear_usuario, headers_de, db_session):  # T154
    h = headers_de(crear_usuario("pricing"))
    _, datos = _primera_y_clave(client, h, db_session)
    assert _post(client, h, datos | {"valido_desde": "2026-07-01", "valido_hasta": "2026-12-31"}).status_code == 201


@pytest.mark.parametrize("caso", ["inactiva_no_choca", "reactivar_superpuesta"])
def test_inactivas_y_reactivacion(client, crear_usuario, headers_de, db_session, caso):  # T155
    h = headers_de(crear_usuario("pricing"))
    primera, datos = _primera_y_clave(client, h, db_session)
    client.patch(f"/v1/tarifas/{primera['id']}", json={"activo": False}, headers=h)
    segunda = _post(client, h, datos | {"valido_desde": "2026-03-01", "valido_hasta": "2026-09-30"})
    assert segunda.status_code == 201
    if caso == "reactivar_superpuesta":
        respuesta = client.patch(f"/v1/tarifas/{primera['id']}", json={"activo": True}, headers=h)
        assert respuesta.status_code == 409
        assert respuesta.json()["detail"]["id_en_conflicto"] == segunda.json()["id"]


def test_claves_distintas_no_chocan(client, crear_usuario, headers_de, db_session):  # T156
    h = headers_de(crear_usuario("pricing"))
    datos = payload_tarifa(db_session, "FCL")
    assert _post(client, h, datos).status_code == 201
    assert _post(client, h, datos | {"tipo_equipo_id": tipo_equipo(db_session, "20GP").id}).status_code == 201
    assert _post(client, h, datos | {"proveedor_id": crear_proveedor(db_session).id}).status_code == 201


@pytest.mark.parametrize(
    ("hoy", "estado"),
    [
        (date(2026, 3, 1), "VIGENTE"),
        (date(2026, 3, 31), "POR_VENCER"),
        (date(2026, 3, 24), "POR_VENCER"),
        (date(2026, 3, 23), "VIGENTE"),
        (date(2026, 2, 28), "FUTURA"),
        (date(2026, 4, 1), "VENCIDA"),
    ],
    ids=["hoy_es_desde", "hoy_es_hasta", "hoy_mas_n_exacto", "hoy_mas_n_mas_1", "futura", "vencida"],
)
def test_estado_vigencia_en_bordes(client, crear_usuario, headers_de, db_session, monkeypatch, hoy, estado):  # T157
    tarifa = crear_tarifa(db_session, valido_desde=date(2026, 3, 1), valido_hasta=date(2026, 3, 31))
    _hoy(monkeypatch, hoy)  # N = 7 días (seed de configuración)
    cuerpo = client.get(f"/v1/tarifas/{tarifa.id}", headers=headers_de(crear_usuario("pricing"))).json()
    assert cuerpo["estado_vigencia"] == estado


def test_n_se_lee_de_configuracion(client, crear_usuario, headers_de, db_session, monkeypatch):  # T158
    tarifa = crear_tarifa(db_session, valido_desde=date(2026, 1, 1), valido_hasta=date(2026, 3, 31))
    _hoy(monkeypatch, date(2026, 3, 11))  # vence en 20 días
    h = headers_de(crear_usuario("admin"))
    assert client.get(f"/v1/tarifas/{tarifa.id}", headers=h).json()["estado_vigencia"] == "VIGENTE"
    assert client.patch("/v1/configuracion/dias_alerta_vencimiento", json={"valor": 30}, headers=h).status_code == 200
    assert client.get(f"/v1/tarifas/{tarifa.id}", headers=h).json()["estado_vigencia"] == "POR_VENCER"


@pytest.mark.parametrize(
    "filtro", ["modo", "origen", "destino", "proveedor", "tipo_equipo", "vigente_en", "por_vencer", "activo"]
)
def test_filtros_tarifas(client, crear_usuario, headers_de, db_session, monkeypatch, filtro):  # T159
    if filtro == "modo":
        buscada, otra = crear_tarifa(db_session, "AEREO"), crear_tarifa(db_session, "LCL")
        parametros = {"modo": "AEREO"}
    elif filtro == "tipo_equipo":
        buscada = crear_tarifa(db_session, "FCL", tipo_equipo_id=tipo_equipo(db_session, "20GP").id)
        otra = crear_tarifa(db_session, "FCL", tipo_equipo_id=tipo_equipo(db_session, "40HC").id)
        parametros = {"tipo_equipo": buscada.tipo_equipo_id}
    elif filtro in ("vigente_en", "por_vencer"):
        buscada = crear_tarifa(db_session, valido_desde=date(2026, 1, 1), valido_hasta=date(2026, 6, 30))
        otra = crear_tarifa(db_session, valido_desde=date(2026, 7, 1), valido_hasta=date(2026, 12, 31))
        _hoy(monkeypatch, date(2026, 6, 28))
        parametros = {"vigente_en": "2026-03-15"} if filtro == "vigente_en" else {"por_vencer": "true"}
    elif filtro == "activo":
        buscada, otra = crear_tarifa(db_session, activo=False), crear_tarifa(db_session)
        parametros = {"activo": "false"}
    else:
        buscada, otra = crear_tarifa(db_session), crear_tarifa(db_session)
        columna = {"origen": "origen_puerto_id", "destino": "destino_puerto_id", "proveedor": "proveedor_id"}[filtro]
        parametros = {filtro: getattr(buscada, columna)}
    ids = {t["id"] for t in client.get("/v1/tarifas", params=parametros, headers=headers_de(crear_usuario("pricing"))).json()}
    assert buscada.id in ids and otra.id not in ids


# ---------- Gating de costos (D-F2-5) ----------


def _tarifa_con_tramos(client, headers, db_session) -> dict:
    tarifa = _post(client, headers, payload_tarifa(db_session, "AEREO", notas="Acuerdo confidencial")).json()
    tramos = {"tramos": [{"desde_kg": 0, "costo_kg": "5.5"}, {"desde_kg": 45, "costo_kg": "4.8"}]}
    assert client.put(f"/v1/tarifas/{tarifa['id']}/tramos", json=tramos, headers=headers).status_code == 200
    return tarifa


def _sin_claves_de_costo(item: dict) -> None:
    presentes = [clave for clave in CLAVES_DE_COSTO if clave in item]
    assert presentes == [], presentes


@pytest.mark.parametrize("vista", ["listado", "detalle"])
def test_gating_comercial_tarifas(client, crear_usuario, headers_de, db_session, vista):  # T160
    tarifa = _tarifa_con_tramos(client, headers_de(crear_usuario("pricing")), db_session)
    h = headers_de(crear_usuario("comercial"))
    if vista == "listado":
        items = client.get("/v1/tarifas", headers=h).json()
        item = next(i for i in items if i["id"] == tarifa["id"])
    else:
        item = client.get(f"/v1/tarifas/{tarifa['id']}", headers=h).json()
    _sin_claves_de_costo(item)
    assert item["precio_venta"] == "6.6000"


def test_gating_comercial_tramos(client, crear_usuario, headers_de, db_session):  # T161
    tarifa = _tarifa_con_tramos(client, headers_de(crear_usuario("pricing")), db_session)
    tramos = client.get(f"/v1/tarifas/{tarifa['id']}/tramos", headers=headers_de(crear_usuario("comercial"))).json()
    assert [t["precio_venta_kg"] for t in tramos] == ["6.6000", "5.7600"]
    for tramo in tramos:
        _sin_claves_de_costo(tramo)


@pytest.mark.parametrize("vista", ["listado", "detalle"])
def test_gating_comercial_recargos(client, crear_usuario, headers_de, db_session, vista):  # T162
    recargo = client.post("/v1/recargos", json=payload_recargo(db_session), headers=headers_de(crear_usuario("pricing"))).json()
    h = headers_de(crear_usuario("comercial"))
    if vista == "listado":
        item = next(i for i in client.get("/v1/recargos", headers=h).json() if i["id"] == recargo["id"])
    else:
        item = client.get(f"/v1/recargos/{recargo['id']}", headers=h).json()
    _sin_claves_de_costo(item)
    assert item["precio_venta"] == "55.0000"


@pytest.mark.parametrize("rol", ["gerencia", "pricing"])
def test_gerencia_y_pricing_reciben_costos(client, crear_usuario, headers_de, db_session, rol):  # T163
    tarifa = _post(client, headers_de(crear_usuario("pricing")), payload_tarifa(db_session, notas="Nota interna")).json()
    item = client.get(f"/v1/tarifas/{tarifa['id']}", headers=headers_de(crear_usuario(rol))).json()
    assert all(clave in item for clave in CLAVES_DE_COSTO if clave != "costo_kg")
    assert (item["costo"], item["margen_unitario"], item["margen_pct"], item["notas"]) == (
        "100.0000",
        "20.0000",
        "16.67",
        "Nota interna",
    )


@pytest.mark.parametrize("operacion", ["crear_tarifa", "patch_tarifa", "crear_recargo", "put_tramos"])
def test_comercial_no_escribe(client, crear_usuario, headers_de, db_session, operacion):  # T164
    tarifa = crear_tarifa(db_session, "AEREO")
    h = headers_de(crear_usuario("comercial"))
    if operacion == "crear_tarifa":
        respuesta = _post(client, h, payload_tarifa(db_session))
    elif operacion == "patch_tarifa":
        respuesta = client.patch(f"/v1/tarifas/{tarifa.id}", json={"notas": "x"}, headers=h)
    elif operacion == "crear_recargo":
        respuesta = client.post("/v1/recargos", json=payload_recargo(db_session), headers=h)
    else:
        respuesta = client.put(f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": []}, headers=h)
    assert respuesta.status_code == 403


@pytest.mark.parametrize("caso", ["404", "403"])
def test_errores_al_comercial_sin_costos(client, crear_usuario, headers_de, db_session, caso):  # T165
    tarifa = crear_tarifa(db_session, costo="987.6543")
    h = headers_de(crear_usuario("comercial"))
    if caso == "404":
        respuesta = client.get(f"/v1/tarifas/{tarifa.id + 100000}", headers=h)
    else:
        respuesta = client.patch(f"/v1/tarifas/{tarifa.id}", json={"costo": "1"}, headers=h)
    assert respuesta.status_code == int(caso)
    assert "987.6543" not in respuesta.text
    assert all(f'"{clave}"' not in respuesta.text for clave in CLAVES_DE_COSTO)


# ---------- Duplicar, PATCH y estado ----------


def test_duplicar_copia_tramos_y_audita(client, crear_usuario, headers_de, db_session):  # T166
    h = headers_de(crear_usuario("pricing"))
    original = _tarifa_con_tramos(client, h, db_session)
    respuesta = client.post(
        f"/v1/tarifas/{original['id']}/duplicar", json={"valido_desde": "2027-01-01", "valido_hasta": "2027-12-31"}, headers=h
    )
    assert respuesta.status_code == 201
    copia = respuesta.json()
    assert copia["id"] != original["id"] and copia["tiene_tramos"] is True
    assert (copia["costo"], copia["valido_desde"]) == ("5.5000", "2027-01-01")
    tramos = client.get(f"/v1/tarifas/{copia['id']}/tramos", headers=h).json()
    assert [t["desde_kg"] for t in tramos] == [0, 45]
    registro = _auditoria(db_session, "tarifa", copia["id"])[0]
    assert (registro.accion, registro.nota) == ("CREAR", f"duplicada de #{original['id']}")


def test_duplicar_superpuesta_409(client, crear_usuario, headers_de, db_session):  # T167
    h = headers_de(crear_usuario("pricing"))
    original = _post(client, h, payload_tarifa(db_session)).json()
    respuesta = client.post(
        f"/v1/tarifas/{original['id']}/duplicar", json={"valido_desde": "2026-06-01", "valido_hasta": "2027-05-31"}, headers=h
    )
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "VIGENCIA_SUPERPUESTA")


def test_patch_parcial_recalcula_venta(client, crear_usuario, headers_de, db_session):  # T168
    h = headers_de(crear_usuario("pricing"))
    tarifa = _post(client, h, payload_tarifa(db_session, notas="Sin cambios", transit_time_dias=5)).json()
    cuerpo = client.patch(f"/v1/tarifas/{tarifa['id']}", json={"costo": "200"}, headers=h).json()
    assert (cuerpo["costo"], cuerpo["precio_venta"]) == ("200.0000", "240.0000")
    assert (cuerpo["notas"], cuerpo["transit_time_dias"], cuerpo["valido_hasta"]) == ("Sin cambios", 5, "2026-12-31")


@pytest.mark.parametrize(
    ("cambios", "estado", "esperado"),
    [({"costo": "9"}, 422, "COSTO_DESDE_TRAMOS"), ({"rate_unit": "ENVIO"}, 409, "TIENE_DEPENDIENTES")],
)
def test_cambios_bloqueados_con_tramos(client, crear_usuario, headers_de, db_session, cambios, estado, esperado):  # T169
    h = headers_de(crear_usuario("pricing"))
    tarifa = _tarifa_con_tramos(client, h, db_session)
    respuesta = client.patch(f"/v1/tarifas/{tarifa['id']}", json=cambios, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (estado, esperado)


def test_desactivar_y_reactivar(client, crear_usuario, headers_de, db_session):  # T170
    h = headers_de(crear_usuario("pricing"))
    tarifa = _post(client, h, payload_tarifa(db_session)).json()
    assert client.patch(f"/v1/tarifas/{tarifa['id']}", json={"activo": False}, headers=h).json()["activo"] is False
    db_session.get(Proveedor, tarifa["proveedor"]["id"]).activo = False
    db_session.commit()
    respuesta = client.patch(f"/v1/tarifas/{tarifa['id']}", json={"activo": True}, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "PADRE_INACTIVO")


# ---------- Tramos aéreos (D-F2-2) ----------


@pytest.mark.parametrize("metodo", ["MARKUP", "MANUAL"])
def test_put_tramos_valido(client, crear_usuario, headers_de, db_session, metodo):  # T171
    h = headers_de(crear_usuario("pricing"))
    extra = {"metodo_venta": "MANUAL", "parametro_venta": None, "precio_venta_manual": "9"} if metodo == "MANUAL" else {}
    tarifa = _post(client, h, payload_tarifa(db_session, "AEREO", **extra)).json()
    tramos = [{"desde_kg": 0, "costo_kg": "5.5"}, {"desde_kg": 100, "costo_kg": "4"}]
    if metodo == "MANUAL":
        tramos[0]["precio_venta_kg"], tramos[1]["precio_venta_kg"] = "7.25", "6"
    respuesta = client.put(f"/v1/tarifas/{tarifa['id']}/tramos", json={"tramos": tramos}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    ventas = [t["precio_venta_kg"] for t in respuesta.json()]
    assert ventas == (["6.6000", "4.8000"] if metodo == "MARKUP" else ["7.2500", "6.0000"])
    actualizada = client.get(f"/v1/tarifas/{tarifa['id']}", headers=h).json()
    assert actualizada["costo"] == "5.5000"
    if metodo == "MANUAL":
        assert actualizada["precio_venta_manual"] == "7.2500"


@pytest.mark.parametrize(
    ("tramos", "esperado"),
    [
        ([{"desde_kg": 0, "costo_kg": "5"}, {"desde_kg": 50, "costo_kg": "4"}], "TRAMOS_INVALIDOS"),
        ([{"desde_kg": 0, "costo_kg": "5"}, {"desde_kg": 45, "costo_kg": "4"}, {"desde_kg": 45, "costo_kg": "3"}], "TRAMOS_INVALIDOS"),
        ([{"desde_kg": 0, "costo_kg": "0"}], "MONTO_INVALIDO"),
    ],
    ids=["desde_no_permitido", "desde_repetido", "costo_cero"],
)
def test_conjunto_de_tramos_invalido(client, crear_usuario, headers_de, db_session, tramos, esperado):  # T172
    tarifa = crear_tarifa(db_session, "AEREO")
    respuesta = client.put(f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": tramos}, headers=headers_de(crear_usuario("pricing")))
    assert (respuesta.status_code, _codigo(respuesta)) == (422, esperado)


def test_sin_tramo_cero_422(client, crear_usuario, headers_de, db_session):  # T173
    tarifa = crear_tarifa(db_session, "AEREO")
    respuesta = client.put(
        f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": [{"desde_kg": 45, "costo_kg": "4"}]}, headers=headers_de(crear_usuario("pricing"))
    )
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "TRAMO_CERO_REQUERIDO")


@pytest.mark.parametrize(("modo", "unidad"), [("LCL", "WM"), ("AEREO", "ENVIO")])
def test_tramos_solo_aereo_kg(client, crear_usuario, headers_de, db_session, modo, unidad):  # T174
    tarifa = crear_tarifa(db_session, modo, rate_unit=unidad)
    respuesta = client.put(
        f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": [{"desde_kg": 0, "costo_kg": "4"}]}, headers=headers_de(crear_usuario("pricing"))
    )
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "TRAMOS_NO_PERMITIDOS")


@pytest.mark.parametrize("metodo", ["MANUAL", "MARKUP"])
def test_precio_por_kg_segun_metodo(client, crear_usuario, headers_de, db_session, metodo):  # T175
    if metodo == "MANUAL":
        tarifa = crear_tarifa(db_session, "AEREO", metodo_venta="MANUAL", parametro_venta=None, precio_venta_manual="9")
        tramos = [{"desde_kg": 0, "costo_kg": "5"}]
    else:
        tarifa = crear_tarifa(db_session, "AEREO")
        tramos = [{"desde_kg": 0, "costo_kg": "5", "precio_venta_kg": "7"}]
    respuesta = client.put(f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": tramos}, headers=headers_de(crear_usuario("pricing")))
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "TRAMOS_INVALIDOS")


def test_put_reemplaza_y_audita(client, crear_usuario, headers_de, db_session):  # T176
    h = headers_de(crear_usuario("pricing"))
    tarifa = crear_tarifa(db_session, "AEREO")
    tres = [{"desde_kg": 0, "costo_kg": "6"}, {"desde_kg": 45, "costo_kg": "5"}, {"desde_kg": 100, "costo_kg": "4"}]
    dos = [{"desde_kg": 0, "costo_kg": "5.9"}, {"desde_kg": 300, "costo_kg": "3"}]
    client.put(f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": tres}, headers=h)
    client.put(f"/v1/tarifas/{tarifa.id}/tramos", json={"tramos": dos}, headers=h)
    assert [t["desde_kg"] for t in client.get(f"/v1/tarifas/{tarifa.id}/tramos", headers=h).json()] == [0, 300]
    ultimo = _auditoria(db_session, "tarifa", tarifa.id)[-1]
    assert (ultimo.accion, ultimo.nota) == ("EDITAR", "tramos reemplazados")
    assert [t["desde_kg"] for t in ultimo.valores_antes["tramos"]] == [0, 45, 100]
    assert [t["desde_kg"] for t in ultimo.valores_despues["tramos"]] == [0, 300]
    assert (ultimo.valores_antes["costo"], ultimo.valores_despues["costo"]) == ("6.0000", "5.9000")


# ---------- Auditoría ----------


def test_auditoria_costo_y_precio(client, crear_usuario, headers_de, db_session):  # T184
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    tarifa = _post(client, h, payload_tarifa(db_session)).json()
    client.patch(f"/v1/tarifas/{tarifa['id']}", json={"costo": "150", "parametro_venta": "25"}, headers=h)
    registros = _auditoria(db_session, "tarifa", tarifa["id"])
    assert [r.accion for r in registros] == ["CREAR", "EDITAR"]
    edicion = registros[-1]
    assert edicion.usuario_id == pricing.id
    assert (edicion.valores_antes["costo"], edicion.valores_despues["costo"]) == ("100.0000", "150.0000")
    assert (edicion.valores_antes["parametro_venta"], edicion.valores_despues["parametro_venta"]) == ("20.0000", "25.0000")


def test_cambio_fallido_no_deja_auditoria(client, crear_usuario, headers_de, db_session, monkeypatch):  # T186
    tarifa = crear_tarifa(db_session)

    def confirmar_que_falla(db):
        db.rollback()
        raise ErrorNegocio(409, "FALLA_SIMULADA", "Fallo simulado al confirmar")

    monkeypatch.setattr("app.services.tarifas.confirmar", confirmar_que_falla)
    respuesta = client.patch(f"/v1/tarifas/{tarifa.id}", json={"costo": "321"}, headers=headers_de(crear_usuario("pricing")))
    assert respuesta.status_code == 409
    assert _auditoria(db_session, "tarifa", tarifa.id) == []
    db_session.refresh(tarifa)
    assert tarifa.costo == Decimal("100.0000")


# ---------- Exclusión en la base y auditoría cerrada (A2, A3) ----------


@pytest.mark.parametrize("recurso", ["tarifa", "recargo"])
def test_exclusion_de_la_base_responde_409(client, crear_usuario, headers_de, db_session, monkeypatch, recurso):  # T205
    """Sin la verificación previa del service, la exclusión ex_ de la base rechaza y errors.py da 409."""
    h = headers_de(crear_usuario("pricing"))
    monkeypatch.setattr(f"app.services.{recurso}s.superpuesta", lambda *args, **kwargs: None)
    if recurso == "tarifa":
        datos = payload_tarifa(db_session)
        ruta = "/v1/tarifas"
    else:
        datos = payload_recargo(db_session)
        ruta = "/v1/recargos"
    assert client.post(ruta, json=datos, headers=h).status_code == 201
    respuesta = client.post(ruta, json=datos | {"valido_desde": "2026-06-01"}, headers=h)
    assert respuesta.status_code == 409
    assert _codigo(respuesta) == "VIGENCIA_SUPERPUESTA"


def test_auditoria_guarda_costo_y_sigue_cerrada_al_comercial(client, crear_usuario, headers_de, db_session):  # T206
    h = headers_de(crear_usuario("pricing"))
    tarifa = _post(client, h, payload_tarifa(db_session, notas="Tarifa negociada")).json()
    client.patch(f"/v1/tarifas/{tarifa['id']}", json={"costo": "111", "notas": "Renegociada"}, headers=h)
    edicion = _auditoria(db_session, "tarifa", tarifa["id"])[-1]
    assert (edicion.valores_despues["costo"], edicion.valores_despues["notas"]) == ("111.0000", "Renegociada")
    assert client.get("/v1/auditoria", headers=headers_de(crear_usuario("comercial"))).status_code == 403
    assert db_session.get(Tarifa, tarifa["id"]).notas == "Renegociada"

"""M5 Recargos (T177–T183, T185)."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import Auditoria
from fabricas import crear_proveedor, crear_puerto, payload_recargo, tipo_equipo


def _post(client, headers, datos):
    return client.post("/v1/recargos", json=datos, headers=headers)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


@pytest.mark.parametrize(
    ("lado", "bloque"), [("ORIGEN", "GASTOS_ORIGEN"), ("DESTINO", "GASTOS_DESTINO"), ("ORIGEN", "SEGURO")]
)
def test_alta_valida(client, crear_usuario, headers_de, db_session, lado, bloque):  # T177
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_recargo(db_session, lado=lado, bloque_incoterm=bloque))
    assert respuesta.status_code == 201, respuesta.text
    assert (respuesta.json()["lado"], respuesta.json()["bloque_incoterm"]) == (lado, bloque)


@pytest.mark.parametrize(("lado", "bloque"), [("ORIGEN", "GASTOS_DESTINO"), ("DESTINO", "RECOGIDA_ORIGEN")])
def test_lado_y_bloque_incoherentes(client, crear_usuario, headers_de, db_session, lado, bloque):  # T178
    respuesta = _post(client, headers_de(crear_usuario("pricing")), payload_recargo(db_session, lado=lado, bloque_incoterm=bloque))
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "LADO_BLOQUE_INCOHERENTE")


@pytest.mark.parametrize(
    ("tipo_puerto", "cambios", "estado", "esperado"),
    [
        ("MARITIMO", {"modo": "AEREO", "rate_unit": "KG"}, 422, "PUERTO_MODO_INCONSISTENTE"),
        ("MARITIMO", {"modo": "LCL", "tipo_equipo": True}, 422, "TIPO_EQUIPO_NO_PERMITIDO"),
        ("MARITIMO", {"modo": "LCL", "rate_unit": "CONTENEDOR"}, 422, "RATE_UNIT_INCOMPATIBLE"),
        ("AEREO", {"rate_unit": "WM"}, 422, "RATE_UNIT_INCOMPATIBLE"),
        ("MARITIMO", {"rate_unit": "KG"}, 422, "RATE_UNIT_INCOMPATIBLE"),
        ("MARITIMO", {"rate_unit": "CONTENEDOR"}, 422, "RATE_UNIT_INCOMPATIBLE"),
        ("MARITIMO", {"modo": "FCL", "rate_unit": "ENVIO"}, 201, None),
    ],
    ids=[
        "modo_incompatible_con_puerto",
        "equipo_sin_fcl",
        "contenedor_con_lcl",
        "a1_aeropuerto_sin_modo_wm",
        "a1_maritimo_sin_modo_kg",
        "a1_maritimo_sin_modo_contenedor",
        "d_f2_10_fcl_con_envio",
    ],
)
def test_coherencia_modo_y_unidad(client, crear_usuario, headers_de, db_session, tipo_puerto, cambios, estado, esperado):  # T179
    cambios = dict(cambios)
    if cambios.pop("tipo_equipo", False):
        cambios["tipo_equipo_id"] = tipo_equipo(db_session).id
    datos = payload_recargo(db_session, crear_puerto(db_session, tipo=tipo_puerto), **cambios)
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert respuesta.status_code == estado, respuesta.text
    if esperado:
        assert _codigo(respuesta) == esperado


def test_seguro_solo_por_envio(client, crear_usuario, headers_de, db_session):  # T180
    datos = payload_recargo(db_session, lado="ORIGEN", bloque_incoterm="SEGURO", rate_unit="WM")
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "SEGURO_SOLO_POR_ENVIO")


@pytest.mark.parametrize("campo", ["aplica_iva", "rol_ingreso"])
def test_iva_y_rol_obligatorios(client, crear_usuario, headers_de, db_session, campo):  # T181
    datos = payload_recargo(db_session)
    del datos[campo]
    respuesta = _post(client, headers_de(crear_usuario("pricing")), datos)
    assert respuesta.status_code == 422
    assert any(error["loc"][-1] == campo for error in respuesta.json()["detail"])


@pytest.mark.parametrize("caso", ["se_guarda_normalizado", "choca_sin_distinguir_mayusculas"])
def test_concepto_normalizado(client, crear_usuario, headers_de, db_session, caso):  # T182
    h = headers_de(crear_usuario("pricing"))
    datos = payload_recargo(db_session, concepto="  THC   Destino  Naviera ")
    creado = _post(client, h, datos)
    assert creado.status_code == 201
    if caso == "se_guarda_normalizado":
        assert creado.json()["concepto"] == "THC Destino Naviera"
    else:
        respuesta = _post(client, h, datos | {"concepto": "thc destino   NAVIERA", "valido_desde": "2026-05-01"})
        assert respuesta.status_code == 409
        detalle = respuesta.json()["detail"]
        assert (detalle["codigo"], detalle["id_en_conflicto"]) == ("VIGENCIA_SUPERPUESTA", creado.json()["id"])


@pytest.mark.parametrize(
    "filtro", ["puerto", "lado", "bloque", "proveedor", "modo", "vigente_en", "por_vencer", "activo"]
)
def test_filtros_recargos(client, crear_usuario, headers_de, db_session, monkeypatch, filtro):  # T183
    h = headers_de(crear_usuario("pricing"))
    base = {}
    otra = {}
    if filtro == "lado":
        base, otra = {"lado": "ORIGEN", "bloque_incoterm": "GASTOS_ORIGEN"}, {}
        parametros = {"lado": "ORIGEN"}
    elif filtro == "bloque":
        base, otra = {"bloque_incoterm": "DESPACHO_IMPORT"}, {}
        parametros = {"bloque": "DESPACHO_IMPORT"}
    elif filtro == "proveedor":
        base = {"proveedor_id": crear_proveedor(db_session).id}
        parametros = {"proveedor": base["proveedor_id"]}
    elif filtro == "modo":
        base, otra = {"modo": "LCL"}, {}
        parametros = {"modo": "LCL"}
    elif filtro in ("vigente_en", "por_vencer"):
        base = {"valido_desde": "2026-01-01", "valido_hasta": "2026-06-30"}
        otra = {"valido_desde": "2026-07-01", "valido_hasta": "2026-12-31"}
        monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: date(2026, 6, 28))
        parametros = {"vigente_en": "2026-03-15"} if filtro == "vigente_en" else {"por_vencer": "true"}
    elif filtro == "activo":
        parametros = {"activo": "false"}
    else:
        parametros = {}
    buscado = _post(client, h, payload_recargo(db_session, **base)).json()
    no_buscado = _post(client, h, payload_recargo(db_session, **otra)).json()
    if filtro == "puerto":
        parametros = {"puerto": buscado["puerto"]["id"]}
    if filtro == "activo":
        client.patch(f"/v1/recargos/{buscado['id']}", json={"activo": False}, headers=h)
    ids = {r["id"] for r in client.get("/v1/recargos", params=parametros, headers=h).json()}
    assert buscado["id"] in ids and no_buscado["id"] not in ids


def test_auditoria_de_recargo(client, crear_usuario, headers_de, db_session):  # T185
    h = headers_de(crear_usuario("pricing"))
    recargo = _post(client, h, payload_recargo(db_session)).json()
    client.patch(f"/v1/recargos/{recargo['id']}", json={"costo": "65.5"}, headers=h)
    registros = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "recargo", Auditoria.entidad_id == str(recargo["id"])).order_by(Auditoria.id)
    ).all()
    assert [r.accion for r in registros] == ["CREAR", "EDITAR"]
    assert (registros[-1].valores_antes["costo"], registros[-1].valores_despues["costo"]) == ("50.0000", "65.5000")

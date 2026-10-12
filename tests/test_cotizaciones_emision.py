"""M7 Emisión, numeración, inmutabilidad, duplicar y estados (T242–T251)."""
import re
from datetime import date

import pytest
from sqlalchemy import select

from app.models import Auditoria, Tarifa
from cotizacion_escenarios import HOY, Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_moneda, crear_tasa

PATRON_NUMERO = re.compile(r"^COT-2026-\d{5}$")


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _notas(db_session, cotizacion_id) -> list[tuple[str, str]]:
    return [
        (r.accion, r.nota)
        for r in db_session.scalars(
            select(Auditoria)
            .where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(cotizacion_id))
            .order_by(Auditoria.id)
        )
    ]


def _borrador_propuesto(client, h, db_session, comercial, **tarifa) -> tuple[Escenario, dict]:
    esc = Escenario(db_session, comercial, **tarifa)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", valido_hasta="2026-08-31")
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=h).json()
    respuesta = client.post(f"/v1/cotizaciones/{cotizacion['id']}/proponer-lineas", json={}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    return esc, respuesta.json()


def _emitir(client, h, cotizacion_id, **cuerpo):
    return client.post(f"/v1/cotizaciones/{cotizacion_id}/emitir", json=cuerpo, headers=h)


def test_emitir_numera_congela_y_audita(client, crear_usuario, headers_de, db_session):  # T242
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, primera = _borrador_propuesto(client, h, db_session, comercial)
    _, segunda = _borrador_propuesto(client, h, db_session, comercial)
    emitida = _emitir(client, h, primera["id"])
    assert emitida.status_code == 200, emitida.text
    datos = emitida.json()
    assert PATRON_NUMERO.match(datos["numero"])
    assert (datos["estado"], datos["etiqueta"], datos["fecha_emision"]) == ("EMITIDA", datos["numero"], HOY.isoformat())
    assert datos["valida_hasta"] == "2026-08-31"  # la vigencia más cercana (el recargo)
    # 2,5 W/M × 120 = 300 (recibo de caja) + recargo 55 en Ecuador (factura, IVA 15 % = 8,25).
    assert datos["totales"] == {
        "subtotal_recibo_caja": "300.00",
        "subtotal_factura": "55.00",
        "iva": "8.25",
        "total_general": "363.25",
        "iva_tasa_aplicada": "15.00",
    }
    siguiente = _emitir(client, h, segunda["id"]).json()["numero"]
    assert int(siguiente[-5:]) == int(datos["numero"][-5:]) + 1  # consecutivos
    assert ("EDITAR", f"EMITIR {datos['numero']}") in _notas(db_session, primera["id"])


@pytest.mark.parametrize(
    ("caso", "estado", "codigo"),
    [
        ("condiciones_vacias", 422, "CONDICIONES_PDF_VACIAS"),
        ("sin_lineas", 422, "SIN_LINEAS"),
        ("extender_validez", 422, "NO_SE_PUEDE_EXTENDER"),
        ("tarifa_desactivada", 409, "RE_PROPONER"),
        ("gerencia_no_emite", 403, None),
    ],
)
def test_emitir_validaciones(client, crear_usuario, headers_de, db_session, caso, estado, codigo):  # T243
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    if caso != "condiciones_vacias":
        cargar_condiciones(db_session)
    esc, borrador = _borrador_propuesto(client, h, db_session, comercial)
    cuerpo = {}
    if caso == "sin_lineas":
        client.patch(f"/v1/cotizaciones/{borrador['id']}", json={"cbm": "4"}, headers=h)
    elif caso == "extender_validez":
        cuerpo = {"valida_hasta": "2026-09-01"}
    elif caso == "tarifa_desactivada":
        db_session.get(Tarifa, esc.tarifa.id).activo = False
        db_session.commit()
    elif caso == "gerencia_no_emite":
        h = headers_de(crear_usuario("gerencia"))
    respuesta = _emitir(client, h, borrador["id"], **cuerpo)
    assert respuesta.status_code == estado, respuesta.text
    if codigo:
        assert _codigo(respuesta) == codigo
    if caso == "condiciones_vacias":
        assert respuesta.json()["detail"]["mensaje"] == "Cargue las condiciones generales en Configuración antes de emitir"
    if caso == "tarifa_desactivada":
        assert respuesta.json()["detail"]["lineas"][0]["orden"] == 1


def test_acortar_validez(client, crear_usuario, headers_de, db_session):  # T243 (acortar sí)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    assert _emitir(client, h, borrador["id"], valida_hasta="2026-07-15").json()["valida_hasta"] == "2026-07-15"


@pytest.mark.parametrize("operacion", ["patch", "linea", "proponer", "emitir", "descartar"])
def test_emitida_inmutable(client, crear_usuario, headers_de, db_session, operacion):  # T244
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    linea_id = borrador["lineas"][0]["id"]
    _emitir(client, h, borrador["id"])
    base = f"/v1/cotizaciones/{borrador['id']}"
    respuesta = {
        "patch": lambda: client.patch(base, json={"notas_cliente": "cambio"}, headers=h),
        "linea": lambda: client.patch(f"{base}/lineas/{linea_id}", json={"precio_venta_unit_usd": "1", "motivo": "Prueba"}, headers=h),
        "proponer": lambda: client.post(f"{base}/proponer-lineas", json={}, headers=h),
        "emitir": lambda: _emitir(client, h, borrador["id"]),
        "descartar": lambda: client.post(f"{base}/descartar", headers=h),
    }[operacion]()
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "COTIZACION_NO_EDITABLE")


def test_tasa_congelada_al_emitir(client, crear_usuario, headers_de, db_session):  # T245
    comercial, admin = crear_usuario("comercial"), crear_usuario("admin")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    eur = crear_moneda(db_session, codigo="EUR")
    crear_tasa(db_session, eur, "1.100000", date(2026, 6, 1), admin)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial, moneda_id=eur.id)
    emitida = _emitir(client, h, borrador["id"]).json()
    flete = next(l for l in emitida["lineas"] if l["tarifa_id"])
    # 2,5 W/M × 100 EUR × 1,10 = 275 de costo; venta 120 EUR × 1,10 = 132 USD/W/M → 330.
    assert (flete["tasa_aplicada"], flete["subtotal_venta_usd"]) == ("1.100000", "330.0000")
    crear_tasa(db_session, eur, "1.500000", HOY, admin)  # una tasa nueva después de emitir
    otra_vez = client.get(f"/v1/cotizaciones/{borrador['id']}", headers=h).json()
    assert next(l for l in otra_vez["lineas"] if l["tarifa_id"])["tasa_aplicada"] == "1.100000"
    assert otra_vez["totales"] == emitida["totales"]


def test_duplicar_desde_emitida(client, crear_usuario, headers_de, db_session):  # T246
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    esc, borrador = _borrador_propuesto(client, h, db_session, comercial)
    flete = next(l for l in borrador["lineas"] if l["tarifa_id"])
    base = f"/v1/cotizaciones/{borrador['id']}"
    client.patch(f"{base}/lineas/{flete['id']}", json={"precio_venta_unit_usd": "99", "motivo": "Promoción"}, headers=h)
    _emitir(client, h, borrador["id"])
    copia = client.post(f"{base}/duplicar", headers=h)
    assert copia.status_code == 201, copia.text
    datos = copia.json()
    assert (datos["estado"], datos["numero"], datos["cotizacion_origen_id"]) == ("BORRADOR", None, borrador["id"])
    flete_copia = next(l for l in datos["lineas"] if l["tarifa_id"])
    assert (flete_copia["tarifa_id"], flete_copia["ajuste_manual"]) == (esc.tarifa.id, False)  # sin los ajustes
    assert ("EDITAR", f"DUPLICAR desde #{borrador['id']}") in _notas(db_session, datos["id"])
    # Si la tarifa ya no es elegible, la copia queda sin líneas y lo dice.
    db_session.get(Tarifa, esc.tarifa.id).activo = False
    db_session.commit()
    sin_lineas = client.post(f"{base}/duplicar", headers=h).json()
    assert (sin_lineas["lineas"], sin_lineas["requiere_proponer"]) == ([], True)
    assert sin_lineas["avisos"][0].startswith("No se pudieron proponer las líneas")


@pytest.mark.parametrize(
    ("cuerpo", "estado", "codigo"),
    [
        ({"estado": "ACEPTADA"}, 200, None),
        ({"estado": "RECHAZADA"}, 422, "MOTIVO_RECHAZO_REQUERIDO"),
        ({"estado": "RECHAZADA", "motivo_rechazo": "OTRO"}, 422, "DETALLE_RECHAZO_REQUERIDO"),
        ({"estado": "RECHAZADA", "motivo_rechazo": "PRECIO"}, 200, None),
        ({"estado": "ENVIADA"}, 422, "ESTADO_NO_PERMITIDO"),
    ],
    ids=["aceptada", "rechazo_sin_motivo", "otro_sin_detalle", "rechazo_por_precio", "enviada_por_patch"],
)
def test_estados_desde_emitida(client, crear_usuario, headers_de, db_session, cuerpo, estado, codigo):  # T247
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    _emitir(client, h, borrador["id"])
    respuesta = client.patch(f"/v1/cotizaciones/{borrador['id']}/estado", json=cuerpo, headers=h)
    assert respuesta.status_code == estado, respuesta.text
    if codigo:
        assert _codigo(respuesta) == codigo
    if cuerpo.get("motivo_rechazo") == "PRECIO":
        assert ("EDITAR", "ESTADO EMITIDA→RECHAZADA (PRECIO)") in _notas(db_session, borrador["id"])
        final = client.patch(f"/v1/cotizaciones/{borrador['id']}/estado", json={"estado": "ACEPTADA"}, headers=h)
        assert (final.status_code, _codigo(final)) == (409, "TRANSICION_INVALIDA")  # estado final


def test_estado_desde_borrador_409(client, crear_usuario, headers_de, db_session):  # T247 (BORRADOR)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    respuesta = client.patch(f"/v1/cotizaciones/{borrador['id']}/estado", json={"estado": "ACEPTADA"}, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "TRANSICION_INVALIDA")


def test_descartar_borrador(client, crear_usuario, headers_de, db_session):  # T248 (D-F3-11)
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    respuesta = client.post(f"/v1/cotizaciones/{borrador['id']}/descartar", headers=h)
    assert (respuesta.status_code, respuesta.json()["activo"]) == (200, False)
    assert ("DESACTIVAR", "DESCARTAR BORRADOR") in _notas(db_session, borrador["id"])
    assert client.get("/v1/cotizaciones", headers=h).json()["total"] == 0
    otra_vez = client.post(f"/v1/cotizaciones/{borrador['id']}/descartar", headers=h)
    assert (otra_vez.status_code, _codigo(otra_vez)) == (409, "COTIZACION_NO_EDITABLE")


def test_vencida_se_calcula_al_leer(client, crear_usuario, headers_de, db_session, monkeypatch):  # T249
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    _emitir(client, h, borrador["id"], valida_hasta="2026-06-30")
    assert client.get(f"/v1/cotizaciones/{borrador['id']}", headers=h).json()["vencida"] is False
    fijar_hoy(monkeypatch, date(2026, 7, 1))
    assert client.get(f"/v1/cotizaciones/{borrador['id']}", headers=h).json()["vencida"] is True
    assert client.get("/v1/cotizaciones?vencidas=true", headers=h).json()["total"] == 1
    assert client.get("/v1/cotizaciones?vencidas=false", headers=h).json()["total"] == 0


def test_borrador_recalcula_en_vivo_con_la_tasa_de_hoy(client, crear_usuario, headers_de, db_session, monkeypatch):  # T250
    comercial, admin = crear_usuario("comercial"), crear_usuario("admin")
    h = headers_de(comercial)
    eur = crear_moneda(db_session, codigo="EUR")
    crear_tasa(db_session, eur, "1.100000", date(2026, 6, 1), admin)
    crear_tasa(db_session, eur, "1.200000", date(2026, 6, 20), admin)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial, moneda_id=eur.id)
    flete = next(l for l in borrador["lineas"] if l["tarifa_id"])
    assert flete["subtotal_venta_usd"] == "330.0000"  # 2,5 × 120 × 1,10
    fijar_hoy(monkeypatch, date(2026, 6, 20))
    vivo = client.get(f"/v1/cotizaciones/{borrador['id']}", headers=h).json()
    assert next(l for l in vivo["lineas"] if l["tarifa_id"])["subtotal_venta_usd"] == "360.0000"  # 2,5 × 120 × 1,20


def test_notas_de_auditoria_por_accion(client, crear_usuario, headers_de, db_session):  # T251
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _, borrador = _borrador_propuesto(client, h, db_session, comercial)
    flete = next(l for l in borrador["lineas"] if l["tarifa_id"])
    base = f"/v1/cotizaciones/{borrador['id']}"
    client.patch(f"{base}/lineas/{flete['id']}", json={"precio_venta_unit_usd": "110", "motivo": "Negociado"}, headers=h)
    numero = _emitir(client, h, borrador["id"]).json()["numero"]
    client.patch(f"{base}/estado", json={"estado": "RECHAZADA", "motivo_rechazo": "TIEMPO"}, headers=h)
    notas = [nota for accion, nota in _notas(db_session, borrador["id"]) if accion != "CREAR"]
    assert notas[-3:] == ["AJUSTE LINEA 1: Negociado", f"EMITIR {numero}", "ESTADO EMITIDA→RECHAZADA (TIEMPO)"]
    assert all(nota and nota.split()[0].isupper() for nota in notas)  # la nota empieza con la acción real

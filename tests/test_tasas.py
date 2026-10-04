"""M3 Tasas de cambio y protección de tasas invertidas (T95 a T107)."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import ErrorNegocio
from app.models import Auditoria, TasaCambio
from app.services.tasas import obtener_tasa_vigente
from fabricas import crear_moneda, crear_tasa


def _post_tasa(client, headers, moneda, tasa, fecha, confirmar=None):
    cuerpo = {"moneda": moneda, "tasa_a_usd": tasa, "fecha_vigencia": fecha}
    if confirmar is not None:
        cuerpo["confirmar_desvio"] = confirmar
    return client.post("/v1/tasas", json=cuerpo, headers=headers)


def _auditoria_de(db_session, tasa_id) -> list[Auditoria]:
    return db_session.scalars(
        select(Auditoria)
        .where(Auditoria.entidad == "tasa_cambio", Auditoria.entidad_id == str(tasa_id))
        .order_by(Auditoria.id)
    ).all()


@pytest.mark.parametrize("tasa", ["0", "-1", "0.1234567"], ids=["cero", "negativa", "7_decimales"])
def test_tasa_invalida_422(client, crear_usuario, headers_de, db_session, tasa):  # T95
    moneda = crear_moneda(db_session)
    respuesta = _post_tasa(client, headers_de(crear_usuario("pricing")), moneda.codigo, tasa, "2026-01-01")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "TASA_INVALIDA"
    assert db_session.scalars(select(TasaCambio).where(TasaCambio.moneda_id == moneda.id)).first() is None


def test_misma_fecha_409(client, crear_usuario, headers_de, db_session):  # T96
    moneda = crear_moneda(db_session)
    h = headers_de(crear_usuario("pricing"))
    assert _post_tasa(client, h, moneda.codigo, "1.08", "2026-01-01").status_code == 201
    respuesta = _post_tasa(client, h, moneda.codigo, "1.09", "2026-01-01")
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["codigo"] == "TASA_DUPLICADA"


def test_vigente_mas_reciente_menor_o_igual(crear_usuario, db_session):  # T97
    usuario = crear_usuario("pricing")
    moneda = crear_moneda(db_session)
    crear_tasa(db_session, moneda, "1.050000", date(2026, 1, 1), usuario)
    crear_tasa(db_session, moneda, "1.080000", date(2026, 2, 1), usuario)
    crear_tasa(db_session, moneda, "1.100000", date(2026, 3, 1), usuario)
    consultas = {
        date(2026, 1, 1): Decimal("1.050000"),
        date(2026, 1, 31): Decimal("1.050000"),
        date(2026, 2, 15): Decimal("1.080000"),
        date(2026, 12, 31): Decimal("1.100000"),
    }
    for fecha, esperada in consultas.items():
        assert obtener_tasa_vigente(db_session, moneda.codigo, fecha) == esperada, fecha


@pytest.mark.parametrize("caso", ["antes_de_la_primera", "moneda_sin_tasas"])
def test_tasa_no_disponible_422(crear_usuario, db_session, caso):  # T98
    moneda = crear_moneda(db_session)
    if caso == "antes_de_la_primera":
        crear_tasa(db_session, moneda, "1.08", date(2026, 3, 1), crear_usuario("pricing"))
    with pytest.raises(ErrorNegocio) as error:
        obtener_tasa_vigente(db_session, moneda.codigo, date(2026, 2, 1))
    assert (error.value.status_code, error.value.codigo) == (422, "TASA_NO_DISPONIBLE")


def test_usd_vigente_es_1(client, crear_usuario, headers_de, db_session):  # T99
    assert obtener_tasa_vigente(db_session, "USD", date(2026, 1, 1)) == Decimal("1")
    respuesta = client.get(
        "/v1/tasas/vigente", params={"moneda": "usd", "fecha": "2026-01-01"}, headers=headers_de(crear_usuario("gerencia"))
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["tasa_a_usd"] == "1"


def test_cny_invertida_409_con_anterior(client, crear_usuario, headers_de, db_session):  # T100
    moneda = crear_moneda(db_session)
    h = headers_de(crear_usuario("pricing"))
    assert _post_tasa(client, h, moneda.codigo, "0.14", "2026-01-01").status_code == 201
    respuesta = _post_tasa(client, h, moneda.codigo, "7.1", "2026-02-01")
    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["codigo"] == "TASA_DESVIO_REQUIERE_CONFIRMACION"
    assert (detalle["tasa_anterior"], detalle["fecha_anterior"]) == ("0.140000", "2026-01-01")
    assert len(db_session.scalars(select(TasaCambio).where(TasaCambio.moneda_id == moneda.id)).all()) == 1


def test_cny_confirmada_201_y_nota(client, crear_usuario, headers_de, db_session):  # T101
    moneda = crear_moneda(db_session)
    h = headers_de(crear_usuario("pricing"))
    _post_tasa(client, h, moneda.codigo, "0.14", "2026-01-01")
    respuesta = _post_tasa(client, h, moneda.codigo, "7.1", "2026-02-01", confirmar=True)
    assert respuesta.status_code == 201
    assert respuesta.json()["tasa_a_usd"] == "7.100000"
    registros = _auditoria_de(db_session, respuesta.json()["id"])
    assert [(r.accion, r.nota) for r in registros] == [("CREAR", "desvío >20% confirmado")]
    assert registros[0].valores_despues["tasa_a_usd"] == "7.100000"


@pytest.mark.parametrize(("nueva", "pide"), [("0.168", False), ("0.168001", True)], ids=["20_exacto", "20_mas_epsilon"])
def test_umbral_20(client, crear_usuario, headers_de, db_session, nueva, pide):  # T102
    moneda = crear_moneda(db_session)
    h = headers_de(crear_usuario("pricing"))
    _post_tasa(client, h, moneda.codigo, "0.14", "2026-01-01")
    respuesta = _post_tasa(client, h, moneda.codigo, nueva, "2026-02-01")
    assert respuesta.status_code == (409 if pide else 201)


@pytest.mark.parametrize("caso", ["primera_tasa", "sin_anterior_usa_posterior"])
def test_primera_tasa_y_posterior(client, crear_usuario, headers_de, db_session, caso):  # T103
    moneda = crear_moneda(db_session)
    h = headers_de(crear_usuario("pricing"))
    if caso == "primera_tasa":
        respuesta = _post_tasa(client, h, moneda.codigo, "7.1", "2026-01-01")
        assert respuesta.status_code == 201
        assert _auditoria_de(db_session, respuesta.json()["id"])[0].nota is None
    else:
        _post_tasa(client, h, moneda.codigo, "0.14", "2026-06-01")
        respuesta = _post_tasa(client, h, moneda.codigo, "7.1", "2026-01-01")
        assert respuesta.status_code == 409
        assert respuesta.json()["detail"]["fecha_anterior"] == "2026-06-01"


@pytest.mark.parametrize("caso", ["auditada", "con_desvio_exige_confirmacion"])
def test_correccion(client, crear_usuario, headers_de, db_session, caso):  # T104
    moneda = crear_moneda(db_session)
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _post_tasa(client, h, moneda.codigo, "0.14", "2026-01-01")
    if caso == "auditada":
        invertida = _post_tasa(client, h, moneda.codigo, "7.1", "2026-02-01", confirmar=True).json()
        # Corregir la invertida hacia la vecina no pide confirmación: se excluye la propia fila.
        respuesta = client.patch(f"/v1/tasas/{invertida['id']}", json={"tasa_a_usd": "0.141"}, headers=h)
        assert respuesta.status_code == 200
        edicion = _auditoria_de(db_session, invertida["id"])[-1]
        assert edicion.accion == "EDITAR" and edicion.usuario_id == pricing.id
        assert (edicion.valores_antes["tasa_a_usd"], edicion.valores_despues["tasa_a_usd"]) == ("7.100000", "0.141000")
    else:
        normal = _post_tasa(client, h, moneda.codigo, "0.15", "2026-03-01").json()
        respuesta = client.patch(f"/v1/tasas/{normal['id']}", json={"tasa_a_usd": "15"}, headers=h)
        assert respuesta.status_code == 409
        assert respuesta.json()["detail"]["codigo"] == "TASA_DESVIO_REQUIERE_CONFIRMACION"


@pytest.mark.parametrize(
    ("rol", "metodo", "ruta", "esperado"),
    [
        ("comercial", "get", "/v1/tasas", 403),
        ("comercial", "get", "/v1/tasas/vigente?moneda=USD&fecha=2026-01-01", 403),
        ("gerencia", "get", "/v1/tasas", 200),
        ("gerencia", "post", "/v1/tasas", 403),
    ],
    ids=["comercial_get", "comercial_vigente", "gerencia_get", "gerencia_post"],
)
def test_permisos_tasas(client, crear_usuario, headers_de, db_session, rol, metodo, ruta, esperado):  # T105
    moneda = crear_moneda(db_session)
    kwargs = {"headers": headers_de(crear_usuario(rol))}
    if metodo == "post":
        kwargs["json"] = {"moneda": moneda.codigo, "tasa_a_usd": "1.08", "fecha_vigencia": "2026-01-01"}
    assert client.request(metodo.upper(), ruta, **kwargs).status_code == esperado


def test_tasa_en_moneda_inactiva_422(client, crear_usuario, headers_de, db_session):  # T106
    moneda = crear_moneda(db_session, activo=False)
    respuesta = _post_tasa(client, headers_de(crear_usuario("admin")), moneda.codigo, "1.08", "2026-01-01")
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "MONEDA_INACTIVA"


def test_vigente_devuelve_decimal_exacto(crear_usuario, db_session):  # T107
    moneda = crear_moneda(db_session)
    crear_tasa(db_session, moneda, "0.137512", date(2026, 1, 1), crear_usuario("pricing"))
    valor = obtener_tasa_vigente(db_session, moneda.codigo, date(2026, 1, 1))
    assert isinstance(valor, Decimal)
    assert valor == Decimal("0.137512")
    # Una moneda desactivada conserva su historial (decisión 5 del diseño).
    moneda.activo = False
    db_session.commit()
    assert obtener_tasa_vigente(db_session, moneda.codigo, date(2026, 1, 1)) == Decimal("0.137512")

"""M3 Monedas (T90 a T94)."""
import pytest
from sqlalchemy import select

from app.models import Auditoria, Moneda
from fabricas import codigo_moneda_libre, crear_moneda


def _usd(db_session) -> Moneda:
    return db_session.scalars(select(Moneda).where(Moneda.codigo == "USD")).one()


def test_seed_solo_usd(db_session):  # T90
    # El harness aísla cada test: lo único persistente en la base de tests es el seed.
    monedas = db_session.scalars(select(Moneda)).all()
    assert [(m.codigo, m.nombre, m.simbolo, m.activo) for m in monedas] == [
        ("USD", "Dólar estadounidense", "$", True)
    ]


@pytest.mark.parametrize("caso", ["desactivar", "cambiar_codigo", "registrar_tasa"])
def test_usd_protegida(client, crear_usuario, headers_de, db_session, caso):  # T91
    h = headers_de(crear_usuario("admin"))
    usd = _usd(db_session)
    if caso == "desactivar":
        respuesta = client.patch(f"/v1/monedas/{usd.id}", json={"activo": False}, headers=h)
        esperado = 409
    elif caso == "cambiar_codigo":
        respuesta = client.patch(f"/v1/monedas/{usd.id}", json={"codigo": "USN"}, headers=h)
        esperado = 409
    else:
        respuesta = client.post(
            "/v1/tasas", json={"moneda": "USD", "tasa_a_usd": "1", "fecha_vigencia": "2026-01-01"}, headers=h
        )
        esperado = 422
    assert respuesta.status_code == esperado
    assert respuesta.json()["detail"]["codigo"] == "MONEDA_BASE_PROTEGIDA"
    db_session.refresh(usd)
    assert (usd.codigo, usd.activo) == ("USD", True)


@pytest.mark.parametrize("codigo", ["US", "USD1", "U$D"])
def test_codigo_iso_invalido_422(client, crear_usuario, headers_de, codigo):  # T92
    respuesta = client.post(
        "/v1/monedas",
        json={"codigo": codigo, "nombre": "Moneda", "simbolo": "x"},
        headers=headers_de(crear_usuario("pricing")),
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "CODIGO_INVALIDO"


def test_duplicada_409(client, crear_usuario, headers_de, db_session):  # T93
    existente = crear_moneda(db_session)
    respuesta = client.post(
        "/v1/monedas",
        json={"codigo": existente.codigo.lower(), "nombre": "Otra", "simbolo": "x"},
        headers=headers_de(crear_usuario("admin")),
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["codigo"] == "MONEDA_DUPLICADA"


def test_cambios_auditados(client, crear_usuario, headers_de, db_session):  # T94
    admin = crear_usuario("admin")
    h = headers_de(admin)
    creada = client.post(
        "/v1/monedas", json={"codigo": codigo_moneda_libre(db_session), "nombre": "Euro", "simbolo": "€"}, headers=h
    ).json()
    client.patch(f"/v1/monedas/{creada['id']}", json={"nombre": "Euro (UE)"}, headers=h)
    client.patch(f"/v1/monedas/{creada['id']}", json={"activo": False}, headers=h)

    registros = db_session.scalars(
        select(Auditoria)
        .where(Auditoria.entidad == "moneda", Auditoria.entidad_id == str(creada["id"]))
        .order_by(Auditoria.id)
    ).all()
    assert [r.accion for r in registros] == ["CREAR", "EDITAR", "DESACTIVAR"]
    assert all(r.usuario_id == admin.id for r in registros)
    assert registros[1].valores_antes["nombre"] == "Euro"
    assert registros[1].valores_despues["nombre"] == "Euro (UE)"
    assert registros[2].valores_antes["activo"] is True
    assert registros[2].valores_despues["activo"] is False

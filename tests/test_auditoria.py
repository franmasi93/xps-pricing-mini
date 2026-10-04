"""Auditoría (T132 a T135)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import ErrorNegocio
from app.models import Auditoria
from app.services.monedas import actualizar_moneda
from fabricas import crear_moneda


def _editar_monedas(client, headers, monedas, veces=1):
    for moneda in monedas:
        for numero in range(veces):
            client.patch(f"/v1/monedas/{moneda.id}", json={"nombre": f"Nombre {numero}"}, headers=headers)


@pytest.mark.parametrize(("rol", "esperado"), [("admin", 200), ("gerencia", 200), ("pricing", 403), ("comercial", 403)])
def test_permisos(client, crear_usuario, headers_de, rol, esperado):  # T132
    assert client.get("/v1/auditoria", headers=headers_de(crear_usuario(rol))).status_code == esperado


@pytest.mark.parametrize("filtro", ["entidad", "entidad_id", "fechas"])
def test_filtros(client, crear_usuario, headers_de, db_session, filtro):  # T133
    pricing = headers_de(crear_usuario("pricing"))
    gerencia = headers_de(crear_usuario("gerencia"))
    moneda_a, moneda_b = crear_moneda(db_session), crear_moneda(db_session)
    _editar_monedas(client, pricing, [moneda_a, moneda_b])
    client.patch("/v1/configuracion/dias_alerta_vencimiento", json={"valor": 9}, headers=pricing)

    if filtro == "entidad":
        items = client.get("/v1/auditoria", params={"entidad": "configuracion"}, headers=gerencia).json()["items"]
        assert items and all(i["entidad"] == "configuracion" for i in items)
    elif filtro == "entidad_id":
        params = {"entidad": "moneda", "entidad_id": str(moneda_a.id)}
        items = client.get("/v1/auditoria", params=params, headers=gerencia).json()["items"]
        assert [i["entidad_id"] for i in items] == [str(moneda_a.id)]
    else:
        registro = db_session.scalars(select(Auditoria).order_by(Auditoria.id.desc())).first()
        dia = registro.fecha.date()
        incluye = client.get("/v1/auditoria", params={"desde": dia.isoformat(), "hasta": dia.isoformat()}, headers=gerencia)
        excluye = client.get("/v1/auditoria", params={"hasta": (dia - timedelta(days=1)).isoformat()}, headers=gerencia)
        assert registro.id in {i["id"] for i in incluye.json()["items"]}
        assert registro.id not in {i["id"] for i in excluye.json()["items"]}


@pytest.mark.parametrize("caso", ["limit_201_422", "orden_descendente"])
def test_paginacion_y_orden(client, crear_usuario, headers_de, db_session, caso):  # T134
    gerencia = headers_de(crear_usuario("gerencia"))
    if caso == "limit_201_422":
        assert client.get("/v1/auditoria", params={"limit": 201}, headers=gerencia).status_code == 422
        return
    moneda = crear_moneda(db_session)
    _editar_monedas(client, headers_de(crear_usuario("pricing")), [moneda], veces=3)
    pagina = client.get(
        "/v1/auditoria", params={"entidad": "moneda", "entidad_id": str(moneda.id), "limit": 2}, headers=gerencia
    ).json()
    ids = [i["id"] for i in pagina["items"]]
    assert (pagina["total"], pagina["limit"], len(ids)) == (3, 2, 2)
    assert ids == sorted(ids, reverse=True)


def test_misma_transaccion(crear_usuario, db_session):  # T135
    """Si el cambio falla al confirmar, el registro de auditoría tampoco queda."""
    admin = crear_usuario("admin")
    existente, otra = crear_moneda(db_session), crear_moneda(db_session)
    with pytest.raises(ErrorNegocio) as error:
        actualizar_moneda(db_session, admin, otra.id, {"codigo": existente.codigo})
    assert error.value.codigo == "MONEDA_DUPLICADA"
    assert db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "moneda", Auditoria.entidad_id == str(otra.id))
    ).first() is None

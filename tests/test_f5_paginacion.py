"""F5-A2 (T302): paginación de tarifas y recargos con los mismos filtros; sin limit, la lista completa como en F2."""
from fabricas import crear_proveedor, crear_puerto, crear_tarifa
from cotizacion_escenarios import crear_recargo


def test_paginacion_de_tarifas(client, crear_usuario, headers_de, db_session):  # T302
    h = headers_de(crear_usuario("comercial"))
    proveedor = crear_proveedor(db_session)
    ids = [crear_tarifa(db_session, "LCL", proveedor_id=proveedor.id).id for _ in range(3)]
    completa = client.get(f"/v1/tarifas?proveedor={proveedor.id}", headers=h)
    assert completa.headers["x-total-count"] == "3"
    assert sorted(t["id"] for t in completa.json()) == sorted(ids)
    primera = client.get(f"/v1/tarifas?proveedor={proveedor.id}&limit=2&offset=0", headers=h)
    segunda = client.get(f"/v1/tarifas?proveedor={proveedor.id}&limit=2&offset=2", headers=h)
    assert (len(primera.json()), len(segunda.json())) == (2, 1)
    assert primera.headers["x-total-count"] == segunda.headers["x-total-count"] == "3"
    assert sorted(t["id"] for t in primera.json() + segunda.json()) == sorted(ids)
    assert client.get("/v1/tarifas?limit=0", headers=h).status_code == 422
    assert client.get("/v1/tarifas?limit=201", headers=h).status_code == 422


def test_paginacion_de_recargos(client, crear_usuario, headers_de, db_session):  # T302
    h = headers_de(crear_usuario("comercial"))
    puerto = crear_puerto(db_session)
    ids = [crear_recargo(db_session, puerto, "GASTOS_DESTINO", "DESTINO").id for _ in range(3)]
    pagina = client.get(f"/v1/recargos?puerto={puerto.id}&limit=2&offset=1", headers=h)
    assert pagina.headers["x-total-count"] == "3"
    assert [r["id"] for r in pagina.json()] == sorted(ids)[1:]
    completa = client.get(f"/v1/recargos?puerto={puerto.id}", headers=h)
    assert len(completa.json()) == 3 and completa.headers["x-total-count"] == "3"

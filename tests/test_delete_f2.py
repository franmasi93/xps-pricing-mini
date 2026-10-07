"""Sin DELETE en los recursos de F2 (T187): la baja es activo=false."""
import pytest

from fabricas import crear_cliente, crear_contacto, crear_tarifa, payload_recargo, tipo_equipo

RECURSOS = ["tarifas", "tramos", "recargos", "tipos-equipo", "clientes", "contactos"]


@pytest.mark.parametrize("recurso", RECURSOS)
def test_delete_405(client, crear_usuario, headers_de, db_session, recurso):  # T187
    h = headers_de(crear_usuario("admin"))
    if recurso == "tarifas":
        ruta = f"/v1/tarifas/{crear_tarifa(db_session).id}"
    elif recurso == "tramos":
        ruta = f"/v1/tarifas/{crear_tarifa(db_session, 'AEREO').id}/tramos"
    elif recurso == "recargos":
        recargo = client.post("/v1/recargos", json=payload_recargo(db_session), headers=h).json()
        ruta = f"/v1/recargos/{recargo['id']}"
    elif recurso == "tipos-equipo":
        ruta = f"/v1/tipos-equipo/{tipo_equipo(db_session).id}"
    else:
        cliente = crear_cliente(db_session, crear_usuario("comercial"))
        ruta = f"/v1/clientes/{cliente.id}"
        if recurso == "contactos":
            ruta += f"/contactos/{crear_contacto(db_session, cliente, principal=True).id}"
    respuesta = client.delete(ruta, headers=h)
    assert respuesta.status_code == 405
    assert respuesta.json()["detail"]["codigo"] == "METODO_NO_PERMITIDO"

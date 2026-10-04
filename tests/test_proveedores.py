"""M4 Proveedores (T108 a T114)."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Pais
from fabricas import crear_pais, crear_proveedor


def _nombre() -> str:
    return f"Agente {uuid4().hex[:10]}"


@pytest.mark.parametrize("rol", ["admin", "pricing"])
def test_crud(client, crear_usuario, headers_de, db_session, rol):  # T108
    h = headers_de(crear_usuario(rol))
    pais = crear_pais(db_session)
    creado = client.post(
        "/v1/proveedores",
        json={"nombre": _nombre(), "pais_id": pais.id, "contacto": "Ana", "email": "Ventas@Agente.COM", "telefono": "+86 1"},
        headers=h,
    )
    assert creado.status_code == 201
    proveedor_id = creado.json()["id"]
    assert client.get(f"/v1/proveedores/{proveedor_id}", headers=h).json()["contacto"] == "Ana"
    editado = client.patch(f"/v1/proveedores/{proveedor_id}", json={"contacto": None, "notas": "Tarifas LCL"}, headers=h)
    assert editado.status_code == 200
    assert (editado.json()["contacto"], editado.json()["notas"], editado.json()["telefono"]) == (None, "Tarifas LCL", "+86 1")
    baja = client.patch(f"/v1/proveedores/{proveedor_id}", json={"activo": False}, headers=h)
    assert baja.json()["activo"] is False


def test_duplicado_sin_mayusculas_409(client, crear_usuario, headers_de, db_session):  # T109
    existente = crear_proveedor(db_session, nombre=f"MSL {uuid4().hex[:8]}")
    respuesta = client.post(
        "/v1/proveedores",
        json={"nombre": existente.nombre.lower(), "pais_id": existente.pais_id},
        headers=headers_de(crear_usuario("pricing")),
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["codigo"] == "PROVEEDOR_DUPLICADO"


@pytest.mark.parametrize("caso", ["invalido", "minusculas"])
def test_email(client, crear_usuario, headers_de, db_session, caso):  # T110
    pais = crear_pais(db_session)
    email = "no-es-email" if caso == "invalido" else "  Ventas@MSL.Com "
    respuesta = client.post(
        "/v1/proveedores",
        json={"nombre": _nombre(), "pais_id": pais.id, "email": email},
        headers=headers_de(crear_usuario("pricing")),
    )
    if caso == "invalido":
        assert respuesta.status_code == 422
        assert respuesta.json()["detail"]["codigo"] == "EMAIL_INVALIDO"
    else:
        assert respuesta.status_code == 201
        assert respuesta.json()["email"] == "ventas@msl.com"


@pytest.mark.parametrize("caso", ["inexistente", "inactivo"])
def test_pais(client, crear_usuario, headers_de, db_session, caso):  # T111
    if caso == "inexistente":
        pais_id = (db_session.scalar(select(func.max(Pais.id))) or 0) + 1000
        esperado = "REFERENCIA_INEXISTENTE"
    else:
        pais_id = crear_pais(db_session, activo=False).id
        esperado = "PADRE_INACTIVO"
    respuesta = client.post(
        "/v1/proveedores", json={"nombre": _nombre(), "pais_id": pais_id}, headers=headers_de(crear_usuario("admin"))
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == esperado


@pytest.mark.parametrize(
    ("rol", "metodo", "con_id", "esperado"),
    [("comercial", "get", False, 403), ("gerencia", "get", False, 200), ("gerencia", "post", False, 403), ("gerencia", "patch", True, 403)],
    ids=["comercial_get", "gerencia_get", "gerencia_post", "gerencia_patch"],
)
def test_permisos(client, crear_usuario, headers_de, db_session, rol, metodo, con_id, esperado):  # T112
    proveedor = crear_proveedor(db_session)
    url = f"/v1/proveedores/{proveedor.id}" if con_id else "/v1/proveedores"
    kwargs = {"headers": headers_de(crear_usuario(rol))}
    if metodo != "get":
        kwargs["json"] = {"nombre": _nombre(), "pais_id": proveedor.pais_id}
    assert client.request(metodo.upper(), url, **kwargs).status_code == esperado


@pytest.mark.parametrize("filtro", ["pais_id", "activo", "q"])
def test_filtros(client, crear_usuario, headers_de, db_session, filtro):  # T113
    pais = crear_pais(db_session)
    marca = uuid4().hex[:8]
    buscado = crear_proveedor(db_session, pais=pais, nombre=f"Charter Link {marca}")
    otro = crear_proveedor(db_session)
    otro.activo = False
    db_session.commit()
    parametros = {"pais_id": {"pais_id": pais.id}, "activo": {"activo": "false"}, "q": {"q": f"link {marca}"}}[filtro]
    ids = {p["id"] for p in client.get("/v1/proveedores", params=parametros, headers=headers_de(crear_usuario("pricing"))).json()}
    if filtro == "activo":
        assert otro.id in ids and buscado.id not in ids
    else:
        assert buscado.id in ids and otro.id not in ids


def test_delete_405(client, crear_usuario, headers_de, db_session):  # T114
    proveedor = crear_proveedor(db_session)
    respuesta = client.delete(f"/v1/proveedores/{proveedor.id}", headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code == 405
    assert respuesta.json()["detail"]["codigo"] == "METODO_NO_PERMITIDO"

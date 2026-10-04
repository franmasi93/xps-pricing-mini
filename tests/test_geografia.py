"""M2 Geografía: regiones, países y puertos (T73 a T89)."""
import pytest
from sqlalchemy import func, select

from app.models import Pais, Puerto, Region
from fabricas import codigo_region, crear_pais, crear_puerto, crear_region, iso2_libre


def _codigo_error(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


@pytest.mark.parametrize("rol", ["admin", "pricing"])
def test_admin_y_pricing_crean_editan_desactivan(client, crear_usuario, headers_de, db_session, rol):  # T73
    h = headers_de(crear_usuario(rol))
    region = client.post("/v1/regiones", json={"codigo": codigo_region(), "nombre": "Región"}, headers=h)
    assert region.status_code == 201
    iso2 = iso2_libre(db_session)
    pais = client.post(
        "/v1/paises", json={"iso2": iso2, "nombre": "País", "region_id": region.json()["id"]}, headers=h
    )
    assert pais.status_code == 201
    puerto = client.post(
        "/v1/puertos",
        json={"codigo": f"{iso2}ABC", "nombre": "Puerto", "pais_id": pais.json()["id"], "tipo": "MARITIMO"},
        headers=h,
    )
    assert puerto.status_code == 201

    editado = client.patch(f"/v1/puertos/{puerto.json()['id']}", json={"nombre": "Puerto Nuevo"}, headers=h)
    assert editado.status_code == 200 and editado.json()["nombre"] == "Puerto Nuevo"
    for ruta, recurso in (("puertos", puerto), ("paises", pais), ("regiones", region)):
        baja = client.patch(f"/v1/{ruta}/{recurso.json()['id']}", json={"activo": False}, headers=h)
        assert baja.status_code == 200 and baja.json()["activo"] is False, ruta


OPERACIONES_ESCRITURA = [
    ("post", "regiones", None),
    ("patch", "regiones", "region"),
    ("post", "paises", None),
    ("patch", "paises", "pais"),
    ("post", "puertos", None),
    ("patch", "puertos", "puerto"),
]


@pytest.mark.parametrize("rol", ["comercial", "gerencia"])
@pytest.mark.parametrize(
    ("metodo", "ruta", "recurso"), OPERACIONES_ESCRITURA, ids=[f"{m}_{r}" for m, r, _ in OPERACIONES_ESCRITURA]
)
def test_comercial_y_gerencia_no_escriben_403(
    client, crear_usuario, headers_de, db_session, rol, metodo, ruta, recurso
):  # T74
    puerto = crear_puerto(db_session)
    ids = {"region": puerto.pais.region_id, "pais": puerto.pais_id, "puerto": puerto.id}
    url = f"/v1/{ruta}" if recurso is None else f"/v1/{ruta}/{ids[recurso]}"
    respuesta = client.request(metodo.upper(), url, json={"nombre": "X"}, headers=headers_de(crear_usuario(rol)))
    assert respuesta.status_code == 403
    assert _codigo_error(respuesta) == "PERMISO_DENEGADO"


@pytest.mark.parametrize("rol", ["comercial", "gerencia"])
@pytest.mark.parametrize("ruta", ["regiones", "paises", "puertos"])
def test_todos_leen_200(client, crear_usuario, headers_de, db_session, rol, ruta):  # T75
    puerto = crear_puerto(db_session)
    ids = {"regiones": puerto.pais.region_id, "paises": puerto.pais_id, "puertos": puerto.id}
    h = headers_de(crear_usuario(rol))
    assert client.get(f"/v1/{ruta}", headers=h).status_code == 200
    assert client.get(f"/v1/{ruta}/{ids[ruta]}", headers=h).status_code == 200


def test_codigos_normalizados_mayusculas(client, crear_usuario, headers_de, db_session):  # T76
    h = headers_de(crear_usuario("admin"))
    codigo = codigo_region()
    region = client.post("/v1/regiones", json={"codigo": f"  {codigo.lower()} ", "nombre": "R"}, headers=h)
    assert region.json()["codigo"] == codigo
    iso2 = iso2_libre(db_session)
    pais = client.post(
        "/v1/paises", json={"iso2": f" {iso2.lower()}", "nombre": "P", "region_id": region.json()["id"]}, headers=h
    )
    assert pais.json()["iso2"] == iso2
    puerto = client.post(
        "/v1/puertos",
        json={"codigo": f" {iso2.lower()} gy e", "nombre": "Pu", "pais_id": pais.json()["id"], "tipo": "MARITIMO"},
        headers=h,
    )
    assert puerto.status_code == 201
    assert puerto.json()["codigo"] == f"{iso2}GYE"


@pytest.mark.parametrize("recurso", ["region", "pais", "puerto"])
def test_duplicado_en_minusculas_409(client, crear_usuario, headers_de, db_session, recurso):  # T77
    h = headers_de(crear_usuario("admin"))
    existente = crear_puerto(db_session)
    if recurso == "region":
        respuesta = client.post(
            "/v1/regiones", json={"codigo": existente.pais.region.codigo.lower(), "nombre": "R"}, headers=h
        )
        esperado = "REGION_DUPLICADA"
    elif recurso == "pais":
        respuesta = client.post(
            "/v1/paises",
            json={"iso2": existente.pais.iso2.lower(), "nombre": "P", "region_id": existente.pais.region_id},
            headers=h,
        )
        esperado = "PAIS_DUPLICADO"
    else:
        respuesta = client.post(
            "/v1/puertos",
            json={"codigo": existente.codigo.lower(), "nombre": "Pu", "pais_id": existente.pais_id, "tipo": "MARITIMO"},
            headers=h,
        )
        esperado = "PUERTO_DUPLICADO"
    assert respuesta.status_code == 409
    assert _codigo_error(respuesta) == esperado


@pytest.mark.parametrize("iso2", ["E", "ECU", "E1"])
def test_iso2_invalido_422(client, crear_usuario, headers_de, db_session, iso2):  # T78
    region = crear_region(db_session)
    respuesta = client.post(
        "/v1/paises",
        json={"iso2": iso2, "nombre": "P", "region_id": region.id},
        headers=headers_de(crear_usuario("admin")),
    )
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == "CODIGO_INVALIDO"


@pytest.mark.parametrize("codigo", ["A", "SUD-AMERICA", "R" * 21], ids=["1_caracter", "guion", "21_caracteres"])
def test_region_codigo_invalido_422(client, crear_usuario, headers_de, codigo):  # T79
    respuesta = client.post(
        "/v1/regiones", json={"codigo": codigo, "nombre": "R"}, headers=headers_de(crear_usuario("admin"))
    )
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == "CODIGO_INVALIDO"


def test_locode_prefijo_otro_pais_422(client, crear_usuario, headers_de, db_session):  # T80
    pais = crear_pais(db_session)
    otro_prefijo = "ZZ" if pais.iso2 != "ZZ" else "ZY"
    respuesta = client.post(
        "/v1/puertos",
        json={"codigo": f"{otro_prefijo}XXX", "nombre": "Pu", "pais_id": pais.id, "tipo": "MARITIMO"},
        headers=headers_de(crear_usuario("admin")),
    )
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == "PUERTO_PAIS_INCONSISTENTE"


@pytest.mark.parametrize(
    ("tipo", "sufijo"),
    [("AEREO", "GYE12"), ("MARITIMO", "GYE"), ("AEREO", "GY1")],
    ids=["aereo_5", "maritimo_3", "aereo_con_digito"],
)
def test_codigo_no_corresponde_al_tipo_422(client, crear_usuario, headers_de, db_session, tipo, sufijo):  # T81
    pais = crear_pais(db_session)
    codigo = f"{pais.iso2}{sufijo[2:]}" if tipo == "AEREO" and len(sufijo) == 5 else sufijo
    respuesta = client.post(
        "/v1/puertos",
        json={"codigo": codigo, "nombre": "Pu", "pais_id": pais.id, "tipo": tipo},
        headers=headers_de(crear_usuario("admin")),
    )
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == "CODIGO_INVALIDO"


def test_aeropuerto_y_puerto_maritimo_conviven(client, crear_usuario, headers_de, db_session):  # T82
    pais = crear_pais(db_session)
    h = headers_de(crear_usuario("admin"))
    usados = set(db_session.scalars(select(Puerto.codigo)))
    sufijo = next(s for s in ("GYE", "GYF", "GYG", "GYH") if s not in usados and f"{pais.iso2}{s}" not in usados)
    aereo = client.post("/v1/puertos", json={"codigo": sufijo, "nombre": "A", "pais_id": pais.id, "tipo": "AEREO"}, headers=h)
    maritimo = client.post(
        "/v1/puertos",
        json={"codigo": f"{pais.iso2}{sufijo}", "nombre": "M", "pais_id": pais.id, "tipo": "MARITIMO"},
        headers=h,
    )
    assert (aereo.status_code, maritimo.status_code) == (201, 201)


@pytest.mark.parametrize("filtro", ["tipo", "pais_id", "q"])
def test_filtros_puertos(client, crear_usuario, headers_de, db_session, filtro):  # T83
    pais = crear_pais(db_session)
    maritimo = crear_puerto(db_session, pais=pais, tipo="MARITIMO")
    aereo = crear_puerto(db_session, pais=pais, tipo="AEREO")
    otro = crear_puerto(db_session)
    parametros = {"tipo": {"tipo": "AEREO"}, "pais_id": {"pais_id": pais.id}, "q": {"q": maritimo.codigo.lower()}}[filtro]
    lista = client.get("/v1/puertos", params=parametros, headers=headers_de(crear_usuario("comercial"))).json()
    ids = {p["id"] for p in lista}
    if filtro == "tipo":
        assert aereo.id in ids and maritimo.id not in ids
        assert all(p["tipo"] == "AEREO" for p in lista)
    elif filtro == "pais_id":
        assert {maritimo.id, aereo.id} <= ids and otro.id not in ids
    else:
        assert maritimo.id in ids and otro.id not in ids


def test_filtros_paises(client, crear_usuario, headers_de, db_session):  # T84
    region = crear_region(db_session)
    activo = crear_pais(db_session, region=region)
    inactivo = crear_pais(db_session, region=region, activo=False)
    otro = crear_pais(db_session)
    h = headers_de(crear_usuario("gerencia"))
    de_region = {p["id"] for p in client.get("/v1/paises", params={"region_id": region.id}, headers=h).json()}
    assert de_region == {activo.id, inactivo.id}
    activos = {
        p["id"] for p in client.get("/v1/paises", params={"region_id": region.id, "activo": "true"}, headers=h).json()
    }
    assert activos == {activo.id}
    assert otro.id not in de_region


@pytest.mark.parametrize("caso", ["region_con_pais", "pais_con_puerto"])
def test_tiene_dependientes_409(client, crear_usuario, headers_de, db_session, caso):  # T85
    puerto = crear_puerto(db_session)
    url = f"/v1/regiones/{puerto.pais.region_id}" if caso == "region_con_pais" else f"/v1/paises/{puerto.pais_id}"
    respuesta = client.patch(url, json={"activo": False}, headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code == 409
    assert _codigo_error(respuesta) == "TIENE_DEPENDIENTES"


@pytest.mark.parametrize("caso", ["crear_pais", "crear_puerto", "reactivar_hijo", "patch_a_padre_inactivo"])
def test_padre_inactivo_422(client, crear_usuario, headers_de, db_session, caso):  # T86
    h = headers_de(crear_usuario("admin"))
    if caso == "crear_pais":
        region = crear_region(db_session, activo=False)
        respuesta = client.post(
            "/v1/paises", json={"iso2": iso2_libre(db_session), "nombre": "P", "region_id": region.id}, headers=h
        )
    elif caso == "crear_puerto":
        pais = crear_pais(db_session, activo=False)
        respuesta = client.post(
            "/v1/puertos", json={"codigo": f"{pais.iso2}AAA", "nombre": "Pu", "pais_id": pais.id, "tipo": "MARITIMO"}, headers=h
        )
    elif caso == "reactivar_hijo":
        region = crear_region(db_session, activo=False)
        pais = crear_pais(db_session, region=region, activo=False)
        respuesta = client.patch(f"/v1/paises/{pais.id}", json={"activo": True}, headers=h)
    else:
        pais = crear_pais(db_session)
        region_inactiva = crear_region(db_session, activo=False)
        respuesta = client.patch(f"/v1/paises/{pais.id}", json={"region_id": region_inactiva.id}, headers=h)
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == "PADRE_INACTIVO"


@pytest.mark.parametrize("caso", ["cambiar_pais", "cambiar_tipo"])
def test_patch_puerto_revalida(client, crear_usuario, headers_de, db_session, caso):  # T87
    puerto = crear_puerto(db_session, tipo="MARITIMO")
    h = headers_de(crear_usuario("admin"))
    if caso == "cambiar_pais":
        otro_pais = crear_pais(db_session)
        respuesta = client.patch(f"/v1/puertos/{puerto.id}", json={"pais_id": otro_pais.id}, headers=h)
        esperado = "PUERTO_PAIS_INCONSISTENTE"
    else:
        respuesta = client.patch(f"/v1/puertos/{puerto.id}", json={"tipo": "AEREO"}, headers=h)
        esperado = "CODIGO_INVALIDO"
    assert respuesta.status_code == 422
    assert _codigo_error(respuesta) == esperado
    db_session.refresh(puerto)
    assert puerto.tipo == "MARITIMO"


@pytest.mark.parametrize(
    ("ruta", "modelo", "codigo"),
    [("regiones", Region, "REGION_NO_ENCONTRADA"), ("paises", Pais, "PAIS_NO_ENCONTRADO"), ("puertos", Puerto, "PUERTO_NO_ENCONTRADO")],
)
def test_404(client, crear_usuario, headers_de, db_session, ruta, modelo, codigo):  # T88
    inexistente = (db_session.scalar(select(func.max(modelo.id))) or 0) + 1000
    respuesta = client.get(f"/v1/{ruta}/{inexistente}", headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code == 404
    assert _codigo_error(respuesta) == codigo


@pytest.mark.parametrize("ruta", ["regiones", "paises", "puertos"])
def test_delete_405(client, crear_usuario, headers_de, db_session, ruta):  # T89
    puerto = crear_puerto(db_session)
    ids = {"regiones": puerto.pais.region_id, "paises": puerto.pais_id, "puertos": puerto.id}
    respuesta = client.delete(f"/v1/{ruta}/{ids[ruta]}", headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code == 405
    assert _codigo_error(respuesta) == "METODO_NO_PERMITIDO"

"""M6 Clientes y contactos (T188–T203 y T207)."""
import pytest
from sqlalchemy import func, select

from app.models import Auditoria, Pais
from fabricas import cedula_libre, crear_cliente, crear_contacto, crear_pais

MENSAJE_DUPLICADO = "Ya existe un cliente con esa identificación; solicite su asignación al administrador"


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _payload(db_session, **cambios) -> dict:
    datos = {
        "razon_social": "Importadora Andina S.A.",
        "tipo_id": "CEDULA",
        "ruc_o_id": cedula_libre(db_session),
        "pais_id": crear_pais(db_session).id,
    }
    return datos | cambios


def _post(client, headers, datos):
    return client.post("/v1/clientes", json=datos, headers=headers)


def _auditoria(db_session, entidad: str, entidad_id) -> list[Auditoria]:
    return db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == entidad, Auditoria.entidad_id == str(entidad_id)).order_by(Auditoria.id)
    ).all()


# ---------- Asignación y alcance ----------


@pytest.mark.parametrize("caso", ["queda_asignado", "envia_comercial_422"])
def test_comercial_crea_y_queda_asignado(client, crear_usuario, headers_de, db_session, caso):  # T188
    comercial, otro = crear_usuario("comercial"), crear_usuario("comercial")
    datos = _payload(db_session)
    if caso == "envia_comercial_422":
        datos["comercial_asignado_id"] = otro.id
    respuesta = _post(client, headers_de(comercial), datos)
    if caso == "queda_asignado":
        assert respuesta.status_code == 201
        assert respuesta.json()["comercial_asignado"]["id"] == comercial.id
    else:
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "ASIGNACION_NO_PERMITIDA")


@pytest.mark.parametrize("operacion", ["get", "patch", "get_contactos", "post_contactos", "patch_contacto"])
def test_cliente_ajeno_404(client, crear_usuario, headers_de, db_session, operacion):  # T189
    dueno, intruso = crear_usuario("comercial"), crear_usuario("comercial")
    cliente = crear_cliente(db_session, dueno)
    contacto = crear_contacto(db_session, cliente, principal=True)
    h = headers_de(intruso)
    base = f"/v1/clientes/{cliente.id}"
    respuesta = {
        "get": lambda: client.get(base, headers=h),
        "patch": lambda: client.patch(base, json={"razon_social": "Otra"}, headers=h),
        "get_contactos": lambda: client.get(f"{base}/contactos", headers=h),
        "post_contactos": lambda: client.post(f"{base}/contactos", json={"nombre": "X"}, headers=h),
        "patch_contacto": lambda: client.patch(f"{base}/contactos/{contacto.id}", json={"nombre": "X"}, headers=h),
    }[operacion]()
    assert (respuesta.status_code, _codigo(respuesta)) == (404, "CLIENTE_NO_ENCONTRADO")


@pytest.mark.parametrize("caso", ["respeta_alcance", "q_corta_422", "maximo_20"])
def test_busqueda(client, crear_usuario, headers_de, db_session, caso):  # T190
    comercial, otro = crear_usuario("comercial"), crear_usuario("comercial")
    h = headers_de(comercial)
    if caso == "respeta_alcance":
        propio = crear_cliente(db_session, comercial, razon_social="Zafiro Logística Propia")
        ajeno = crear_cliente(db_session, otro, razon_social="Zafiro Logística Ajena")
        ids = {c["id"] for c in client.get("/v1/clientes/buscar", params={"q": "zafiro"}, headers=h).json()}
        assert propio.id in ids and ajeno.id not in ids
        por_identificacion = client.get("/v1/clientes/buscar", params={"q": ajeno.ruc_o_id}, headers=h).json()
        assert por_identificacion == []
    elif caso == "q_corta_422":
        respuesta = client.get("/v1/clientes/buscar", params={"q": "a"}, headers=h)
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "BUSQUEDA_CORTA")
    else:
        for numero in range(22):
            crear_cliente(db_session, comercial, razon_social=f"Cuarzo Comercial {numero:02d}")
        assert len(client.get("/v1/clientes/buscar", params={"q": "cuarzo"}, headers=h).json()) == 20


@pytest.mark.parametrize("rol", ["comercial", "pricing", "gerencia"])
def test_listado_con_alcance(client, crear_usuario, headers_de, db_session, rol):  # T191
    usuario = crear_usuario(rol)
    dueno = usuario if rol == "comercial" else crear_usuario("comercial")
    propio, ajeno = crear_cliente(db_session, dueno), crear_cliente(db_session, crear_usuario("comercial"))
    ids = {c["id"] for c in client.get("/v1/clientes", headers=headers_de(usuario)).json()}
    assert propio.id in ids
    assert (ajeno.id in ids) == (rol != "comercial")


@pytest.mark.parametrize("caso", ["reasigna_con_auditoria", "destino_inactivo", "destino_sin_cotizar", "admin_omite_comercial"])
def test_reasignacion_por_admin(client, crear_usuario, headers_de, db_session, caso):  # T192
    admin = crear_usuario("admin")
    h = headers_de(admin)
    if caso == "admin_omite_comercial":
        respuesta = _post(client, h, _payload(db_session))
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "COMERCIAL_ASIGNADO_REQUERIDO")
        return
    original = crear_usuario("comercial")
    cliente = crear_cliente(db_session, original)
    destino = {
        "reasigna_con_auditoria": lambda: crear_usuario("comercial"),
        "destino_inactivo": lambda: crear_usuario("comercial", activo=False),
        "destino_sin_cotizar": lambda: crear_usuario("gerencia"),
    }[caso]()
    respuesta = client.patch(f"/v1/clientes/{cliente.id}", json={"comercial_asignado_id": destino.id}, headers=h)
    if caso == "reasigna_con_auditoria":
        assert respuesta.status_code == 200
        assert respuesta.json()["comercial_asignado"]["id"] == destino.id
        registro = _auditoria(db_session, "cliente", cliente.id)[-1]
        assert registro.accion == "EDITAR" and registro.usuario_id == admin.id
        assert (registro.valores_antes["comercial_asignado_id"], registro.valores_despues["comercial_asignado_id"]) == (
            original.id,
            destino.id,
        )
        assert "reasignado" in registro.nota
    else:
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "COMERCIAL_INVALIDO")


def test_comercial_no_reasigna(client, crear_usuario, headers_de, db_session):  # T193
    comercial = crear_usuario("comercial")
    cliente = crear_cliente(db_session, comercial)
    respuesta = client.patch(
        f"/v1/clientes/{cliente.id}", json={"comercial_asignado_id": crear_usuario("comercial").id}, headers=headers_de(comercial)
    )
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "ASIGNACION_NO_PERMITIDA")


def test_duplicado_409_sin_filtrar_datos(client, crear_usuario, headers_de, db_session):  # T194
    dueno = crear_usuario("comercial", nombre="Comercial Dueño Secreto")
    existente = crear_cliente(db_session, dueno, razon_social="Razón Social Reservada")
    respuesta = _post(
        client, headers_de(crear_usuario("comercial")), _payload(db_session, ruc_o_id=existente.ruc_o_id)
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == {"codigo": "CLIENTE_DUPLICADO", "mensaje": MENSAJE_DUPLICADO}
    assert "Reservada" not in respuesta.text and "Secreto" not in respuesta.text


@pytest.mark.parametrize(
    ("tipo", "valor", "valido"),
    [
        ("RUC", "1790012345001", True),
        ("RUC", "1790012345002", False),
        ("RUC", "179001234500", False),
        ("CEDULA", None, True),
        ("CEDULA", "123456789", False),
        ("PASAPORTE", "AB12", False),
        ("PASAPORTE", "AB1234567", True),
        ("EXTRANJERO", "AB-123", False),
    ],
    ids=["ruc_valido", "ruc_sin_001", "ruc_12_digitos", "cedula_valida", "cedula_9", "pasaporte_4", "pasaporte_valido", "extranjero_con_guion"],
)
def test_formatos_de_identificacion(client, crear_usuario, headers_de, db_session, tipo, valor, valido):  # T195
    datos = _payload(db_session, tipo_id=tipo)
    if valor is not None:
        datos["ruc_o_id"] = valor
    respuesta = _post(client, headers_de(crear_usuario("comercial")), datos)
    if valido:
        assert respuesta.status_code == 201, respuesta.text
    else:
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "IDENTIFICACION_INVALIDA")


def test_identificacion_normalizada(client, crear_usuario, headers_de, db_session):  # T196
    respuesta = _post(client, headers_de(crear_usuario("comercial")), _payload(db_session, tipo_id="PASAPORTE", ruc_o_id=" ab 12 34567 "))
    assert respuesta.status_code == 201
    assert respuesta.json()["ruc_o_id"] == "AB1234567"


@pytest.mark.parametrize("caso", ["pais_inactivo", "pais_inexistente"])
def test_pais_invalido(client, crear_usuario, headers_de, db_session, caso):  # T197
    if caso == "pais_inactivo":
        pais_id, esperado = crear_pais(db_session, activo=False).id, "PADRE_INACTIVO"
    else:
        pais_id, esperado = (db_session.scalar(select(func.max(Pais.id))) or 0) + 1000, "REFERENCIA_INEXISTENTE"
    respuesta = _post(client, headers_de(crear_usuario("comercial")), _payload(db_session, pais_id=pais_id))
    assert (respuesta.status_code, _codigo(respuesta)) == (422, esperado)


@pytest.mark.parametrize("rol", ["pricing", "gerencia"])
def test_pricing_y_gerencia_no_escriben(client, crear_usuario, headers_de, db_session, rol):  # T198
    cliente = crear_cliente(db_session, crear_usuario("comercial"))
    h = headers_de(crear_usuario(rol))
    assert _post(client, h, _payload(db_session)).status_code == 403
    assert client.patch(f"/v1/clientes/{cliente.id}", json={"notas": "x"}, headers=h).status_code == 403


# ---------- Contactos ----------


def _contacto(client, headers, cliente_id, **datos):
    return client.post(f"/v1/clientes/{cliente_id}/contactos", json={"nombre": "Contacto"} | datos, headers=headers)


def test_primer_contacto_es_principal(client, crear_usuario, headers_de, db_session):  # T199
    comercial = crear_usuario("comercial")
    cliente = crear_cliente(db_session, comercial)
    h = headers_de(comercial)
    primero = _contacto(client, h, cliente.id).json()
    segundo = _contacto(client, h, cliente.id).json()
    assert (primero["principal"], segundo["principal"]) == (True, False)
    assert client.get(f"/v1/clientes/{cliente.id}", headers=h).json()["contacto_principal"]["id"] == primero["id"]


def test_marcar_otro_desmarca_el_anterior(client, crear_usuario, headers_de, db_session):  # T200
    comercial = crear_usuario("comercial")
    cliente = crear_cliente(db_session, comercial)
    h = headers_de(comercial)
    primero = _contacto(client, h, cliente.id).json()
    segundo = _contacto(client, h, cliente.id).json()
    respuesta = client.patch(f"/v1/clientes/{cliente.id}/contactos/{segundo['id']}", json={"principal": True}, headers=h)
    assert respuesta.status_code == 200 and respuesta.json()["principal"] is True
    contactos = {c["id"]: c["principal"] for c in client.get(f"/v1/clientes/{cliente.id}/contactos", headers=h).json()}
    assert contactos == {primero["id"]: False, segundo["id"]: True}


def test_desactivar_principal_deja_sin_principal(client, crear_usuario, headers_de, db_session):  # T201
    comercial = crear_usuario("comercial")
    cliente = crear_cliente(db_session, comercial)
    h = headers_de(comercial)
    principal = _contacto(client, h, cliente.id).json()
    respuesta = client.patch(f"/v1/clientes/{cliente.id}/contactos/{principal['id']}", json={"activo": False}, headers=h)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["activo"], cuerpo["principal"], cuerpo["cliente_tiene_principal"]) == (False, False, False)
    assert client.get(f"/v1/clientes/{cliente.id}", headers=h).json()["contacto_principal"] is None


@pytest.mark.parametrize("caso", ["invalido", "minusculas"])
def test_email_de_contacto(client, crear_usuario, headers_de, db_session, caso):  # T202
    comercial = crear_usuario("comercial")
    cliente = crear_cliente(db_session, comercial)
    email = "no-es-email" if caso == "invalido" else "  Compras@Andina.EC "
    respuesta = _contacto(client, headers_de(comercial), cliente.id, email=email)
    if caso == "invalido":
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "EMAIL_INVALIDO")
    else:
        assert respuesta.json()["email"] == "compras@andina.ec"


def test_auditoria_de_cliente_y_contacto(client, crear_usuario, headers_de, db_session):  # T203
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cliente = _post(client, h, _payload(db_session)).json()
    client.patch(f"/v1/clientes/{cliente['id']}", json={"ciudad": "Guayaquil"}, headers=h)
    contacto = _contacto(client, h, cliente["id"], cargo="Compras").json()
    client.patch(f"/v1/clientes/{cliente['id']}/contactos/{contacto['id']}", json={"cargo": "Gerente"}, headers=h)

    registros_cliente = _auditoria(db_session, "cliente", cliente["id"])
    assert [r.accion for r in registros_cliente] == ["CREAR", "EDITAR"]
    assert (registros_cliente[1].valores_antes["ciudad"], registros_cliente[1].valores_despues["ciudad"]) == (None, "Guayaquil")
    registros_contacto = _auditoria(db_session, "contacto_cliente", contacto["id"])
    assert [r.accion for r in registros_contacto] == ["CREAR", "EDITAR"]
    assert registros_contacto[1].valores_despues["cargo"] == "Gerente"
    assert all(r.usuario_id == comercial.id for r in registros_cliente + registros_contacto)


# ---------- Candidatos a comercial de la pantalla P8 ----------


def test_candidatos_a_comercial_para_el_admin(client, crear_usuario, headers_de):  # T207
    admin, comercial, gerencia = crear_usuario("admin"), crear_usuario("comercial"), crear_usuario("gerencia")
    h = headers_de(admin)
    roles = client.get("/v1/roles", headers=h)
    usuarios = client.get("/v1/usuarios?activo=true", headers=h)
    assert (roles.status_code, usuarios.status_code) == (200, 200)
    assert all(isinstance(r["codigo"], str) and isinstance(r["permisos"], list) for r in roles.json())
    assert all(isinstance(u["rol"]["codigo"], str) for u in usuarios.json())

    # El mismo filtro que frontend/js/clientes.js: roles con cotizacion.crear.
    roles_que_cotizan = {r["codigo"] for r in roles.json() if "cotizacion.crear" in r["permisos"]}
    candidatos = {u["id"] for u in usuarios.json() if u["rol"]["codigo"] in roles_que_cotizan}
    assert comercial.id in candidatos
    assert gerencia.id not in candidatos

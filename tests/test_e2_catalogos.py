"""E2 Catálogos de administración: roles y matriz editables, motivos de rechazo, tipos de identificación y textos del
PDF (TE2-01 a TE2-16)."""
import pytest
from sqlalchemy import select

from app.models import Auditoria, Cotizacion, MotivoRechazo, Permiso, Rol, TipoIdentificacion, Usuario
from app.services import pdf
from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_pais
from matriz_rbac import MATRIZ_6_2, PERMISOS_EXTENSIONES, sin_extensiones

TEXTO_DDP = "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación"
TEXTO_EXW = "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación"
TEXTO_ACEPTACION = (
    "Yo, en representación de la empresa, acepto los términos y condiciones aquí establecidos y confirmo la presente "
    "cotización."
)


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _rol(db_session, codigo: str) -> Rol:
    return db_session.scalars(select(Rol).where(Rol.codigo == codigo)).one()


def _emitida(client, h, db_session, comercial) -> dict:
    cargar_condiciones(db_session)
    esc = Escenario(db_session, comercial)
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", valido_hasta="2026-08-31")
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=h).json()
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/proponer-lineas", json={}, headers=h).status_code == 200
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    return emitida.json()


# ---------- Siembra (0009) ----------


def test_siembra_identica_a_lo_fijo(db_session):  # TE2-01
    roles = {rol.codigo: rol for rol in db_session.scalars(select(Rol))}
    assert set(roles) == {"admin", "pricing", "comercial", "gerencia"}
    assert [codigo for codigo, rol in roles.items() if rol.protegido] == ["admin"]
    assert all(rol.descripcion and rol.activo for rol in roles.values())
    motivos = {m.codigo: (m.nombre, m.exige_detalle) for m in db_session.scalars(select(MotivoRechazo))}
    assert motivos == {"PRECIO": ("Precio", False), "TIEMPO": ("Tiempo", False),
                       "COMPETENCIA": ("Competencia", False), "OTRO": ("Otro", True)}
    tipos = {t.codigo: (t.regex, t.formato) for t in db_session.scalars(select(TipoIdentificacion))}
    assert tipos == {
        "RUC": ("^[0-9]{10}001$", "13 dígitos terminados en 001"),
        "CEDULA": ("^[0-9]{10}$", "10 dígitos"),
        "PASAPORTE": ("^[A-Z0-9]{5,20}$", "de 5 a 20 letras o números"),
        "EXTRANJERO": ("^[A-Z0-9]{3,30}$", "de 3 a 30 letras o números"),
    }


def test_textos_pdf_sembrados_identicos(client, crear_usuario, headers_de):  # TE2-02
    textos = client.get("/v1/textos-pdf", headers=headers_de(crear_usuario("admin"))).json()
    assert textos == pdf.TEXTOS_PDF_ANTES_DE_E2 | {"advertencia_ddp": TEXTO_DDP, "advertencia_exw": TEXTO_EXW}
    assert textos["aceptacion_texto"] == TEXTO_ACEPTACION


def test_e2_no_agrega_permisos(db_session):  # TE2-03: roles y catálogos usan usuario.admin y config.editar
    codigos = set(db_session.scalars(select(Permiso.codigo)))
    assert codigos == set().union(*MATRIZ_6_2.values()) | set(PERMISOS_EXTENSIONES)


# ---------- Permisos de las pantallas ----------


@pytest.mark.parametrize("rol", ["pricing", "comercial", "gerencia"])
def test_solo_el_admin_edita(client, crear_usuario, headers_de, rol):  # TE2-04
    h = headers_de(crear_usuario(rol))
    assert client.get("/v1/roles", headers=h).status_code == 403
    assert client.get("/v1/roles/permisos", headers=h).status_code == 403
    assert client.post("/v1/roles", json={"codigo": "x_rol", "nombre": "X"}, headers=h).status_code == 403
    assert client.post("/v1/motivos-rechazo", json={"codigo": "PLAZO", "nombre": "Plazo"}, headers=h).status_code == 403
    assert client.post("/v1/tipos-identificacion", json={"codigo": "NIT", "nombre": "NIT", "regex": "^[0-9]+$",
                                                         "formato": "solo dígitos"}, headers=h).status_code == 403
    assert client.put("/v1/textos-pdf", json={"firma_sello": "Sello"}, headers=h).status_code == 403
    # Las listas las lee cualquiera (las usan las pantallas de cotización y clientes).
    assert client.get("/v1/motivos-rechazo", headers=h).status_code == 200
    assert client.get("/v1/tipos-identificacion", headers=h).status_code == 200


# ---------- Roles ----------


def test_crear_rol_y_asignarlo(client, crear_usuario, headers_de, db_session):  # TE2-05
    admin = crear_usuario("admin")
    h = headers_de(admin)
    creado = client.post("/v1/roles", json={"codigo": "Operaciones", "nombre": "Operaciones", "descripcion": "Solo ve tarifas",
                                            "permisos": ["tarifa.ver", "cliente.ver"]}, headers=h)
    assert creado.status_code == 201, creado.text
    rol = creado.json()
    assert (rol["codigo"], rol["permisos"], rol["usuarios_activos"], rol["protegido"]) == (
        "operaciones", ["cliente.ver", "tarifa.ver"], 0, False)
    usuario = client.post("/v1/usuarios", json={"email": "operaciones.e2@xpress.test", "nombre": "Ops", "rol_codigo": "operaciones",
                                                "password_temporal": "TemporalSegura2026"}, headers=h)
    assert usuario.status_code == 201, usuario.text
    auditoria = db_session.scalars(select(Auditoria).where(Auditoria.entidad == "rol", Auditoria.entidad_id == "operaciones")).all()
    assert [a.accion for a in auditoria] == ["CREAR"]
    assert _codigo(client.post("/v1/roles", json={"codigo": "operaciones", "nombre": "Otra"}, headers=h)) == "ROL_DUPLICADO"
    assert _codigo(client.post("/v1/roles", json={"codigo": "1mal", "nombre": "Mal"}, headers=h)) == "CODIGO_INVALIDO"
    assert _codigo(client.post("/v1/roles", json={"codigo": "otro_rol", "nombre": "X", "permisos": ["no.existe"]},
                               headers=h)) == "PERMISO_INEXISTENTE"


def test_cambiar_permisos_invalida_sesiones(client, crear_usuario, headers_de, db_session):  # TE2-06
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    h_admin, h_comercial = headers_de(admin), headers_de(comercial)
    assert client.get("/v1/auth/yo", headers=h_comercial).status_code == 200
    rol = _rol(db_session, "comercial")
    nuevos = sorted({p.codigo for p in rol.permisos} | {"auditoria.ver"})
    respuesta = client.patch(f"/v1/roles/{rol.id}", json={"permisos": nuevos}, headers=h_admin)
    assert respuesta.status_code == 200, respuesta.text
    assert "auditoria.ver" in respuesta.json()["permisos"]
    assert client.get("/v1/auth/yo", headers=h_comercial).status_code == 401  # token_version subió
    assert client.get("/v1/auth/yo", headers=h_admin).status_code == 200  # el admin no es de ese rol
    nuevo_token = headers_de(db_session.get(Usuario, comercial.id))
    assert "auditoria.ver" in client.get("/v1/auth/yo", headers=nuevo_token).json()["permisos"]
    # Solo cambiar el nombre no cierra sesiones.
    assert client.patch(f"/v1/roles/{rol.id}", json={"nombre": "Comercial senior"}, headers=h_admin).status_code == 200
    assert client.get("/v1/auth/yo", headers=nuevo_token).status_code == 200


def test_editar_el_propio_rol_no_cierra_la_sesion_del_actor(client, crear_usuario, headers_de, db_session):  # TE2-07
    admin, otro_admin = crear_usuario("admin"), crear_usuario("admin")
    h, h_otro = headers_de(admin), headers_de(otro_admin)
    rol = _rol(db_session, "admin")
    permisos = sorted(p.codigo for p in rol.permisos if p.codigo != "auditoria.ver")
    assert client.patch(f"/v1/roles/{rol.id}", json={"permisos": permisos}, headers=h).status_code == 200
    assert client.get("/v1/auth/yo", headers=h).status_code == 200
    assert client.get("/v1/auth/yo", headers=h_otro).status_code == 401


def test_rol_admin_protegido(client, crear_usuario, headers_de, db_session):  # TE2-08
    h = headers_de(crear_usuario("admin"))
    rol = _rol(db_session, "admin")
    sin_admin = [p.codigo for p in rol.permisos if p.codigo != "usuario.admin"]
    assert _codigo(client.patch(f"/v1/roles/{rol.id}", json={"permisos": sin_admin}, headers=h)) == "ROL_PROTEGIDO"
    assert _codigo(client.patch(f"/v1/roles/{rol.id}", json={"activo": False}, headers=h)) == "ROL_PROTEGIDO"
    assert _codigo(client.patch(f"/v1/roles/{rol.id}", json={"codigo": "jefe"}, headers=h)) == "CODIGO_NO_EDITABLE"


def test_desactivar_rol(client, crear_usuario, headers_de, db_session):  # TE2-09
    h = headers_de(crear_usuario("admin"))
    crear_usuario("gerencia")
    gerencia = _rol(db_session, "gerencia")
    assert _codigo(client.patch(f"/v1/roles/{gerencia.id}", json={"activo": False}, headers=h)) == "ROL_CON_USUARIOS"
    vacio = client.post("/v1/roles", json={"codigo": "temporal", "nombre": "Temporal"}, headers=h).json()
    assert client.patch(f"/v1/roles/{vacio['id']}", json={"activo": False}, headers=h).json()["activo"] is False
    usuario = client.post("/v1/usuarios", json={"email": "temporal.e2@xpress.test", "nombre": "T", "rol_codigo": "temporal",
                                                "password_temporal": "TemporalSegura2026"}, headers=h)
    assert (usuario.status_code, _codigo(usuario)) == (422, "ROL_INACTIVO")


def test_matriz_6_2_intacta_en_la_api(client, crear_usuario, headers_de):  # TE2-10
    roles = client.get("/v1/roles", headers=headers_de(crear_usuario("admin"))).json()
    assert sin_extensiones({r["codigo"]: set(r["permisos"]) for r in roles}) == MATRIZ_6_2
    assert all({"descripcion", "protegido", "activo", "usuarios_activos"} <= set(r) for r in roles)


# ---------- Motivos de rechazo ----------


def test_motivo_nuevo_en_el_rechazo(client, crear_usuario, headers_de, db_session):  # TE2-11
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    h_admin, h = headers_de(admin), headers_de(comercial)
    nuevo = client.post("/v1/motivos-rechazo", json={"codigo": "9-PLAZO", "nombre": "Plazo de pago",
                                                     "exige_detalle": True}, headers=h_admin)
    assert _codigo(nuevo) == "CODIGO_INVALIDO"
    nuevo = client.post("/v1/motivos-rechazo", json={"codigo": "PLAZO_PAGO", "nombre": "Plazo de pago", "exige_detalle": True},
                        headers=h_admin)
    assert nuevo.status_code == 201, nuevo.text
    emitida = _emitida(client, h, db_session, comercial)
    base = f"/v1/cotizaciones/{emitida['id']}/estado"
    sin_detalle = client.patch(base, json={"estado": "RECHAZADA", "motivo_rechazo": "PLAZO_PAGO"}, headers=h)
    assert (_codigo(sin_detalle), sin_detalle.json()["detail"]["mensaje"]) == (
        "DETALLE_RECHAZO_REQUERIDO", "Con motivo PLAZO_PAGO, el detalle es obligatorio")
    inexistente = client.patch(base, json={"estado": "RECHAZADA", "motivo_rechazo": "CARO"}, headers=h)
    assert (inexistente.status_code, _codigo(inexistente)) == (422, "MOTIVO_RECHAZO_INVALIDO")
    ok = client.patch(base, json={"estado": "RECHAZADA", "motivo_rechazo": "PLAZO_PAGO", "detalle_rechazo": "Pide 60 días"},
                      headers=h)
    assert (ok.status_code, ok.json()["motivo_rechazo"]) == (200, "PLAZO_PAGO")
    # Desactivado: sale de la lista nueva, pero la cotización lo conserva.
    assert client.patch(f"/v1/motivos-rechazo/{nuevo.json()['id']}", json={"activo": False}, headers=h_admin).status_code == 200
    assert db_session.get(Cotizacion, emitida["id"]).motivo_rechazo == "PLAZO_PAGO"
    activos = client.get("/v1/motivos-rechazo?activo=true", headers=h).json()
    assert "PLAZO_PAGO" not in {m["codigo"] for m in activos}


def test_motivo_otro_protegido(client, crear_usuario, headers_de, db_session):  # TE2-12
    h = headers_de(crear_usuario("admin"))
    otro = db_session.scalars(select(MotivoRechazo).where(MotivoRechazo.codigo == "OTRO")).one()
    assert _codigo(client.patch(f"/v1/motivos-rechazo/{otro.id}", json={"exige_detalle": False}, headers=h)) == "MOTIVO_PROTEGIDO"
    assert _codigo(client.patch(f"/v1/motivos-rechazo/{otro.id}", json={"activo": False}, headers=h)) == "MOTIVO_PROTEGIDO"
    assert _codigo(client.patch(f"/v1/motivos-rechazo/{otro.id}", json={"codigo": "OTROS"}, headers=h)) == "CODIGO_NO_EDITABLE"
    renombrado = client.patch(f"/v1/motivos-rechazo/{otro.id}", json={"nombre": "Otro motivo", "orden": 99}, headers=h)
    assert (renombrado.status_code, renombrado.json()["nombre"]) == (200, "Otro motivo")


# ---------- Tipos de identificación ----------


def test_tipo_de_identificacion_nuevo(client, crear_usuario, headers_de, db_session):  # TE2-13
    h, hc = headers_de(crear_usuario("admin")), headers_de(crear_usuario("comercial"))
    malo = client.post("/v1/tipos-identificacion", json={"codigo": "NIT", "nombre": "NIT", "regex": "^[0-9+$",
                                                          "formato": "9 dígitos"}, headers=h)
    assert _codigo(malo) == "REGEX_INVALIDA"
    nit = client.post("/v1/tipos-identificacion", json={"codigo": "nit", "nombre": "NIT (Colombia)", "regex": "^[0-9]{9}$",
                                                         "formato": "9 dígitos"}, headers=h)
    assert (nit.status_code, nit.json()["codigo"]) == (201, "NIT")
    pais = crear_pais(db_session).id
    datos = {"razon_social": "Andina Colombia SAS", "tipo_id": "NIT", "pais_id": pais}
    mal = client.post("/v1/clientes", json=datos | {"ruc_o_id": "12345"}, headers=hc)
    assert (_codigo(mal), mal.json()["detail"]["mensaje"]) == ("IDENTIFICACION_INVALIDA", "La identificación NIT debe tener 9 dígitos")
    cliente = client.post("/v1/clientes", json=datos | {"ruc_o_id": " 900 123 456 "}, headers=hc)
    assert cliente.status_code == 201, cliente.text
    assert cliente.json()["ruc_o_id"] == "900123456"
    # Cambiar la regla o desactivar el tipo no traba a un cliente ya guardado; uno nuevo ya no puede usarlo.
    client.patch(f"/v1/tipos-identificacion/{nit.json()['id']}", json={"regex": "^[0-9]{10}$", "activo": False}, headers=h)
    editado = client.patch(f"/v1/clientes/{cliente.json()['id']}", json={"notas": "Revisado"}, headers=hc)
    assert editado.status_code == 200, editado.text
    otro = client.post("/v1/clientes", json=datos | {"ruc_o_id": "9001234567"}, headers=hc)
    assert _codigo(otro) == "TIPO_IDENTIFICACION_INVALIDO"
    assert _codigo(client.post("/v1/clientes", json=datos | {"tipo_id": "ZZ", "ruc_o_id": "1"}, headers=hc)) == "TIPO_IDENTIFICACION_INVALIDO"


def test_codigo_del_tipo_no_cambia(client, crear_usuario, headers_de, db_session):  # TE2-14
    h = headers_de(crear_usuario("admin"))
    ruc = db_session.scalars(select(TipoIdentificacion).where(TipoIdentificacion.codigo == "RUC")).one()
    assert _codigo(client.patch(f"/v1/tipos-identificacion/{ruc.id}", json={"codigo": "RUC2"}, headers=h)) == "CODIGO_NO_EDITABLE"
    cambio = client.patch(f"/v1/tipos-identificacion/{ruc.id}", json={"nombre": "RUC (SRI)"}, headers=h)
    assert (cambio.status_code, cambio.json()["regex"]) == (200, "^[0-9]{10}001$")


# ---------- Textos del PDF ----------


def test_advertencia_editable(client, crear_usuario, headers_de, db_session):  # TE2-15
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    nuevo = "DDP: el comprador no paga a XPRESS. Cotice al vendedor (exportación)."
    respuesta = client.put("/v1/textos-pdf", json={"advertencia_ddp": nuevo}, headers=headers_de(admin))
    assert (respuesta.status_code, respuesta.json()["advertencia_ddp"]) == (200, nuevo)
    assert _codigo(client.put("/v1/textos-pdf", json={"firma_sello": "   "}, headers=headers_de(admin))) == "CONFIG_VALOR_INVALIDO"
    esc = Escenario(db_session, comercial, con_tarifa=False)
    creada = client.post("/v1/cotizaciones", json=esc.payload("DDP", "IMPORTACION"), headers=headers_de(comercial))
    assert (_codigo(creada), creada.json()["detail"]["mensaje"]) == ("NADA_QUE_COTIZAR", nuevo)
    assert [a.accion for a in db_session.scalars(select(Auditoria).where(Auditoria.entidad == "config_textos_pdf"))] == ["EDITAR"]


def test_textos_del_pdf_se_congelan_al_emitir(client, crear_usuario, headers_de, db_session):  # TE2-16
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    h = headers_de(comercial)
    emitida = _emitida(client, h, db_session, comercial)
    foto = db_session.get(Cotizacion, emitida["id"]).snapshot_emision
    assert foto["textos_pdf"]["aceptacion_texto"] == TEXTO_ACEPTACION
    html_antes = pdf.renderizar_html(foto, False)
    assert TEXTO_ACEPTACION in html_antes and "Firma: _____________________" in html_antes
    client.put("/v1/textos-pdf", json={"aceptacion_texto": "Acepto la cotización.", "firma_sello": "Sello de la empresa"},
               headers=headers_de(admin))
    db_session.expire_all()
    assert pdf.renderizar_html(db_session.get(Cotizacion, emitida["id"]).snapshot_emision, False) == html_antes
    # Una emitida antes de E2 (sin textos en la foto) sale con los textos de siempre, idéntica.
    sin_textos = {clave: valor for clave, valor in foto.items() if clave != "textos_pdf"}
    assert pdf.renderizar_html(sin_textos, False) == html_antes
    # Una nueva emisión usa los textos nuevos.
    segunda = _emitida(client, h, db_session, comercial)
    html_nuevo = pdf.renderizar_html(db_session.get(Cotizacion, segunda["id"]).snapshot_emision, False)
    assert "Acepto la cotización." in html_nuevo and "Sello de la empresa" in html_nuevo


@pytest.mark.parametrize("pagina", ["roles", "motivos-rechazo", "tipos-identificacion"])
def test_paginas_e2(client, pagina):  # TE2-17 (mismas reglas que T204 y T257)
    import re

    from test_frontend import PATRONES_PROHIBIDOS_JS

    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    assert re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text) == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []

"""F4 bloque B (T282–T299): cifrado, configuración del correo, salud, plantillas, prueba, envío y bitácora.

Todo con el proveedor FALSO (tests/correo_falso.py) y una llave Fernet propia de los tests: nunca el .env,
nunca Tencent, nunca la red (un guardia bloquea toda conexión que no sea local).
"""
import json
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import get_settings
from app.core import cifrado
from app.models import Auditoria, ConfigCorreo, ContactoCliente, Cotizacion, EnvioCorreo, EnvioCorreoPrueba
from app.services import correo
from app.services.proveedor_correo import TABLA_B9, traducir
from correo_falso import CorreoFalso
from cotizacion_escenarios import Escenario, cargar_condiciones, fijar_hoy
from fabricas import crear_contacto

RAIZ = Path(__file__).resolve().parent.parent
LLAVE_PRUEBA = Fernet.generate_key().decode()  # propia de los tests; nunca la del .env
# Armadas en tiempo de ejecución: el control de secretos no debe encontrar nada parecido a una llave real.
SECRET_ID = "IK" + "ID" + "pruebaFalsaSoloTests" + "ZQ3"
SECRET_KEY = "clave" + "FalsaSoloParaTests" + "XYZ"
LOCALES = ("127.0.0.1", "localhost", "::1")


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Ninguna prueba de correo abre conexiones de red (solo la base local por el proxy)."""
    original = socket.socket.connect

    def conectar(self, direccion):
        host = direccion[0] if isinstance(direccion, tuple) else direccion
        if host not in LOCALES:
            raise RuntimeError(f"Conexión de red bloqueada en las pruebas: {host}")
        return original(self, direccion)

    monkeypatch.setattr(socket.socket, "connect", conectar)


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


@pytest.fixture
def llave(monkeypatch):
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", SecretStr(LLAVE_PRUEBA))


@pytest.fixture
def falso(monkeypatch, llave):
    proveedor = CorreoFalso()
    monkeypatch.setattr(correo, "fabrica_proveedor", proveedor.fabrica)
    correo.invalidar_cache()
    yield proveedor
    correo.invalidar_cache()


def _config(db_session, **cambios) -> ConfigCorreo:
    fila = db_session.get(ConfigCorreo, 1)
    for campo, valor in cambios.items():
        setattr(fila, campo, valor)
    db_session.commit()
    correo.invalidar_cache()
    return fila


def _con_llaves(db_session, habilitado: bool = True, **cambios) -> ConfigCorreo:
    return _config(db_session, habilitado=habilitado, secret_id_cifrado=cifrado.cifrar(SECRET_ID),
                   secret_key_cifrado=cifrado.cifrar(SECRET_KEY), **cambios)


def _emitida(client, h, db_session, comercial, email="compras@cliente-prueba.ec") -> tuple[dict, Escenario]:
    cargar_condiciones(db_session)
    esc = Escenario(db_session, comercial)
    esc.contacto.email = email
    db_session.commit()
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=h).json()
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/proponer-lineas", json={}, headers=h).status_code == 200
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    return emitida.json(), esc


def _enviar(client, h, cotizacion_id, cc=None):
    return client.post(f"/v1/cotizaciones/{cotizacion_id}/enviar", json={"cc_contacto_ids": cc or []}, headers=h)


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


# ---------- Cifrado (T282) ----------


def test_cifrado_y_enmascarado(llave, monkeypatch):  # T282
    token = cifrado.cifrar(SECRET_ID)
    assert token != SECRET_ID and SECRET_ID not in token
    assert cifrado.descifrar(token) == SECRET_ID
    assert cifrado.enmascarar(SECRET_ID) == "IKID****ZQ3"
    assert cifrado.enmascarar("corta") == "****"
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", SecretStr(Fernet.generate_key().decode()))
    assert cifrado.descifrar(token) is None  # otra llave: no descifra, no revienta
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", SecretStr("no-es-una-llave-fernet"))
    assert (cifrado.disponible(), cifrado.descifrar(token)) == (False, None)
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", None)
    assert (cifrado.disponible(), cifrado.cifrar("x"), cifrado.descifrar(token)) == (False, None, None)


# ---------- Configuración (T283–T287) ----------


def test_llaves_nunca_salen_en_claro(client, crear_usuario, headers_de, db_session, falso):  # T283
    h = headers_de(crear_usuario("admin"))
    respuesta = client.put("/v1/correo/config", json={"secret_id": SECRET_ID, "secret_key": SECRET_KEY}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    for cuerpo in (respuesta.text, client.get("/v1/correo/config", headers=h).text):
        assert SECRET_ID not in cuerpo and SECRET_KEY not in cuerpo
    datos = respuesta.json()
    assert (datos["secret_id"], datos["estado"], datos["habilitado"]) == ("IKID****ZQ3", "DESHABILITADO", False)
    fila = db_session.get(ConfigCorreo, 1)
    db_session.refresh(fila)
    assert SECRET_ID not in fila.secret_id_cifrado and cifrado.descifrar(fila.secret_id_cifrado) == SECRET_ID
    registro = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "config_correo").order_by(Auditoria.id.desc())
    ).first()
    crudo = json.dumps([registro.valores_antes, registro.valores_despues])
    assert SECRET_ID not in crudo and SECRET_KEY not in crudo
    assert registro.valores_despues["secret_id"] == "IKID****ZQ3"
    assert falso.consultas == 0  # guardar con habilitado=false no exige prueba


@pytest.mark.parametrize(
    ("ajuste", "codigo"),
    [
        ({"dominio_ok": False}, "DOMINIO_NO_VERIFICADO"),
        ({"remitente_ok": False}, "REMITENTE_NO_VALIDO"),
        ({"plantilla_estado": 1}, "PLANTILLA_NO_DISPONIBLE"),
        ({"error_consulta": "AuthFailure.SecretIdNotFound"}, "CREDENCIALES_INVALIDAS"),
    ],
)
def test_habilitar_valida_antes_de_guardar(client, crear_usuario, headers_de, db_session, falso, ajuste, codigo):  # T284
    h = headers_de(crear_usuario("admin"))
    _con_llaves(db_session, habilitado=False)
    for campo, valor in ajuste.items():
        setattr(falso, campo, valor)
    respuesta = client.put("/v1/correo/config", json={"habilitado": True, "remitente": "Otro <otro@notificaciones.xpress.ec>"},
                           headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, codigo)
    fila = db_session.get(ConfigCorreo, 1)
    db_session.refresh(fila)
    assert (fila.habilitado, fila.remitente) == (False, "Xpress - Tarifas <pricing@notificaciones.xpress.ec>")


def test_habilitar_con_todo_en_orden(client, crear_usuario, headers_de, db_session, falso):  # T284
    h = headers_de(crear_usuario("admin"))
    _con_llaves(db_session, habilitado=False)
    respuesta = client.put("/v1/correo/config", json={"habilitado": True}, headers=h)
    assert (respuesta.status_code, respuesta.json()["estado"]) == (200, "HABILITADO")
    assert falso.consultas == 3  # dominio, remitente y plantilla
    assert falso.configs[-1].secret_id == SECRET_ID  # el proveedor recibe las llaves descifradas
    sin_llaves = client.put("/v1/correo/config", json={"habilitado": True, "secret_id": SECRET_ID}, headers=h)
    assert (sin_llaves.status_code, _codigo(sin_llaves)) == (422, "LLAVES_INCOMPLETAS")


def test_cache_se_invalida_al_guardar(client, crear_usuario, headers_de, db_session, falso):  # T285
    h = headers_de(crear_usuario("admin"))
    antes = correo.config_vigente(db_session)
    _fila = db_session.get(ConfigCorreo, 1)
    _fila.reply_to = "cambio-directo@xpress.ec"  # sin pasar por el service: la caché de 60 s sigue
    db_session.commit()
    assert correo.config_vigente(db_session).reply_to == antes.reply_to
    respuesta = client.put("/v1/correo/config", json={"reply_to": "nuevo@xpress.ec"}, headers=h)
    assert respuesta.status_code == 200
    assert correo.config_vigente(db_session).reply_to == "nuevo@xpress.ec"  # sin reiniciar


@pytest.mark.parametrize("rol", ["pricing", "comercial", "gerencia"])
def test_solo_admin(client, crear_usuario, headers_de, db_session, falso, rol):  # T286
    h = headers_de(crear_usuario(rol))
    llamadas = [
        client.get("/v1/correo/config", headers=h),
        client.put("/v1/correo/config", json={"habilitado": False}, headers=h),
        client.post("/v1/correo/probar", headers=h),
        client.get("/v1/correo/plantillas", headers=h),
        client.post("/v1/correo/enviar-prueba", json={"email": "x@xpress.ec"}, headers=h),
    ]
    assert [r.status_code for r in llamadas] == [403] * 5


def test_sin_llave_de_cifrado_no_configurado(client, crear_usuario, headers_de, db_session, falso, monkeypatch):  # T287
    h = headers_de(crear_usuario("admin"))
    _con_llaves(db_session, habilitado=False)
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", None)
    correo.invalidar_cache()
    datos = client.get("/v1/correo/config", headers=h).json()
    assert (datos["estado"], datos["secret_id"], datos["cifrado_disponible"]) == ("NO_CONFIGURADO", None, False)
    respuesta = client.put("/v1/correo/config", json={"secret_id": SECRET_ID, "secret_key": SECRET_KEY}, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "CIFRADO_NO_CONFIGURADO")
    salud = client.post("/v1/correo/probar", headers=h).json()
    assert (salud["estado"], salud["consultado"]) == ("NO_CONFIGURADO", False)
    assert falso.consultas == 0  # no llama a Tencent
    prueba = client.post("/v1/correo/enviar-prueba", json={"email": "x@xpress.ec"}, headers=h)
    assert (prueba.status_code, _codigo(prueba)) == (503, "CORREO_NO_CONFIGURADO")


# ---------- Salud, plantillas y correo de prueba (T288–T290) ----------


def test_salud_con_cache_y_con_interruptor_apagado(client, crear_usuario, headers_de, db_session, falso):  # T288
    h = headers_de(crear_usuario("admin"))
    _con_llaves(db_session, habilitado=False)  # H-F4-10: apagado, pero con llaves, sí consulta
    primera = client.post("/v1/correo/probar", headers=h).json()
    assert (primera["todo_ok"], primera["dominio"], primera["plantilla_estado_texto"]) == (
        True, "notificaciones.xpress.ec", "Aprobada")
    assert SECRET_ID not in json.dumps(primera)
    assert falso.consultas == 3
    client.post("/v1/correo/probar", headers=h)
    assert falso.consultas == 3  # caché de 10 minutos
    falso.plantilla_estado = 2
    refrescada = client.post("/v1/correo/probar?refrescar=true", headers=h).json()
    assert (falso.consultas, refrescada["todo_ok"], refrescada["plantilla_estado_texto"]) == (6, False, "Rechazada")
    falso.error_consulta = "InternalError"
    caida = client.post("/v1/correo/probar?refrescar=true", headers=h).json()
    assert caida["error"]["codigo"] == "PROVEEDOR_NO_DISPONIBLE"


def test_plantillas_solo_aprobadas(client, crear_usuario, headers_de, db_session, falso):  # T289
    h = headers_de(crear_usuario("admin"))
    _con_llaves(db_session, habilitado=False)
    plantillas = client.get("/v1/correo/plantillas", headers=h).json()
    assert plantillas == [{"id": 72669, "nombre": "Cotización", "estado": 0, "estado_texto": "Aprobada"}]


def test_correo_de_prueba(client, crear_usuario, headers_de, db_session, falso):  # T290
    admin = crear_usuario("admin")
    h = headers_de(admin)
    _con_llaves(db_session, habilitado=False)
    respuesta = client.post("/v1/correo/enviar-prueba", json={"email": "francois@prueba.ec"}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    mensaje = falso.enviados[-1]
    assert (mensaje.destinatario, mensaje.adjunto[:4], mensaje.adjunto_nombre) == (
        "francois@prueba.ec", b"%PDF", "COT-PRUEBA_Xpress.pdf")
    fila = db_session.scalars(select(EnvioCorreoPrueba).order_by(EnvioCorreoPrueba.id.desc())).first()
    assert (fila.estado, fila.message_id, fila.enviado_por) == ("ENVIADO", "msg-falso-0001-abcdef", admin.id)
    assert db_session.scalar(select(EnvioCorreo.id).where(EnvioCorreo.destinatario == "francois@prueba.ec")) is None
    falso.error_envio = "FailedOperation.NoAttachPermission"
    fallida = client.post("/v1/correo/enviar-prueba", json={"email": "francois@prueba.ec"}, headers=h)
    assert (fallida.status_code, _codigo(fallida)) == (502, "SIN_PERMISO_ADJUNTOS")
    fila = db_session.scalars(select(EnvioCorreoPrueba).order_by(EnvioCorreoPrueba.id.desc())).first()
    assert (fila.estado, fila.codigo_error, fila.request_id) == ("FALLIDO", "SIN_PERMISO_ADJUNTOS", "req-falso-2")


# ---------- Envío de una cotización (T291–T297) ----------


def test_envio_exitoso_emitida_a_enviada(client, crear_usuario, headers_de, db_session, falso):  # T291
    comercial = crear_usuario("comercial", nombre="Ana Comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    emitida, esc = _emitida(client, h, db_session, comercial)
    respuesta = _enviar(client, h, emitida["id"])
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["cotizacion"]["estado"] == "ENVIADA"
    mensaje = falso.enviados[-1]
    assert mensaje.destinatario == "compras@cliente-prueba.ec"
    assert mensaje.asunto == f"Cotización {emitida['numero']} – XPRESS LOGISTICS XPS S.A."
    assert (mensaje.remitente, mensaje.reply_to, mensaje.bcc, mensaje.cc) == (
        "Xpress - Tarifas <pricing@notificaciones.xpress.ec>", "pricing@xpress.ec", ("pricing@xpress.ec",), ())
    assert mensaje.plantilla_id == 72669
    assert mensaje.datos_plantilla == {"contacto": esc.contacto.nombre, "numero": emitida["numero"],
                                       "valida_hasta": "31/12/2026", "comercial": "Ana Comercial"}
    assert all("<" not in valor for valor in mensaje.datos_plantilla.values())  # texto plano
    assert mensaje.adjunto[:4] == b"%PDF" and mensaje.adjunto_nombre.startswith(f"{emitida['numero']}_")
    assert esc.proveedor.nombre not in json.dumps(mensaje.datos_plantilla) + mensaje.asunto
    envios = client.get(f"/v1/cotizaciones/{emitida['id']}/envios", headers=h).json()
    assert [(e["estado"], e["message_id"], e["request_id"], e["enviado_por"]) for e in envios] == [
        ("ENVIADO", "msg-falso-0001-abcdef", "req-falso-1", "Ana Comercial")]
    nota = db_session.scalars(
        select(Auditoria.nota).where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(emitida["id"]))
        .order_by(Auditoria.id.desc())
    ).first()
    assert nota.startswith(f"ENVIAR {emitida['numero']}")


def test_reenvio_desde_enviada(client, crear_usuario, headers_de, db_session, falso):  # T292
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    emitida, _ = _emitida(client, h, db_session, comercial)
    assert _enviar(client, h, emitida["id"]).status_code == 200
    segundo = _enviar(client, h, emitida["id"])
    assert (segundo.status_code, segundo.json()["cotizacion"]["estado"]) == (200, "ENVIADA")
    assert len(client.get(f"/v1/cotizaciones/{emitida['id']}/envios", headers=h).json()) == 2
    transiciones = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(emitida["id"]),
                                Auditoria.nota.like("ENVIAR%"))
    ).all()
    assert len(transiciones) == 1  # el reenvío no cambia el estado


def test_estados_que_no_permiten_envio_y_vencida(client, crear_usuario, headers_de, db_session, falso, monkeypatch):  # T293
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    borrador = client.post("/v1/cotizaciones", json=Escenario(db_session, comercial).payload("FOB"), headers=h).json()
    respuesta = _enviar(client, h, borrador["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "ESTADO_NO_PERMITE_ENVIO")
    for estado, extra in (("ACEPTADA", {}), ("RECHAZADA", {"motivo_rechazo": "PRECIO"})):
        emitida, _ = _emitida(client, h, db_session, comercial)
        client.patch(f"/v1/cotizaciones/{emitida['id']}/estado", json={"estado": estado} | extra, headers=h)
        respuesta = _enviar(client, h, emitida["id"])
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "ESTADO_NO_PERMITE_ENVIO"), estado
    emitida, _ = _emitida(client, h, db_session, comercial)
    fijar_hoy(monkeypatch, date(2027, 1, 1))  # válida hasta el 31/12/2026
    respuesta = _enviar(client, h, emitida["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "COTIZACION_VENCIDA")
    assert "Duplíquela" in respuesta.json()["detail"]["mensaje"]
    assert falso.enviados == []


def test_permiso_alcance_y_gerencia(client, crear_usuario, headers_de, db_session, falso):  # T294
    comercial, otro, gerencia = crear_usuario("comercial"), crear_usuario("comercial"), crear_usuario("gerencia")
    _con_llaves(db_session)
    emitida, _ = _emitida(client, headers_de(comercial), db_session, comercial)
    ajena = _enviar(client, headers_de(otro), emitida["id"])
    assert (ajena.status_code, _codigo(ajena)) == (404, "COTIZACION_NO_ENCONTRADA")
    assert client.get(f"/v1/cotizaciones/{emitida['id']}/envios", headers=headers_de(otro)).status_code == 404
    assert _enviar(client, headers_de(gerencia), emitida["id"]).status_code == 403  # sin cotizacion.enviar
    assert client.get(f"/v1/cotizaciones/{emitida['id']}/envios", headers=headers_de(gerencia)).status_code == 200
    assert falso.enviados == []


def test_cc_solo_del_mismo_cliente_y_contacto_sin_email(client, crear_usuario, headers_de, db_session, falso):  # T295
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    emitida, esc = _emitida(client, h, db_session, comercial)
    copia = crear_contacto(db_session, esc.cliente)
    copia.email = "pricing@xpress.ec"  # coincide con la copia oculta: no se duplica
    sin_email = crear_contacto(db_session, esc.cliente)
    inactivo = crear_contacto(db_session, esc.cliente)
    inactivo.email, inactivo.activo = "inactivo@cliente.ec", False
    ajeno = crear_contacto(db_session, Escenario(db_session, comercial).cliente)
    ajeno.email = "ajeno@otro.ec"
    db_session.commit()
    for ident, codigo in ((ajeno.id, "CC_INVALIDO"), (inactivo.id, "CC_INVALIDO"), (sin_email.id, "CONTACTO_SIN_EMAIL"),
                          (esc.contacto.id, "CC_INVALIDO")):
        respuesta = _enviar(client, h, emitida["id"], [ident])
        assert (respuesta.status_code, _codigo(respuesta)) == (422, codigo), ident
    assert _enviar(client, h, emitida["id"], [1, 2, 3, 4, 5, 6]).status_code == 422  # máximo 5
    bien = _enviar(client, h, emitida["id"], [copia.id])
    assert bien.status_code == 200
    assert (falso.enviados[-1].cc, falso.enviados[-1].bcc) == (("pricing@xpress.ec",), ())
    esc.contacto.email = None
    db_session.commit()
    respuesta = _enviar(client, h, emitida["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "CONTACTO_SIN_EMAIL")


def test_deshabilitado_503_sin_bitacora(client, crear_usuario, headers_de, db_session, falso):  # T296
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session, habilitado=False)
    emitida, _ = _emitida(client, h, db_session, comercial)
    respuesta = _enviar(client, h, emitida["id"])
    assert (respuesta.status_code, _codigo(respuesta)) == (503, "CORREO_DESHABILITADO")
    _config(db_session, habilitado=True, secret_id_cifrado=None, secret_key_cifrado=None)  # habilitado sin llaves
    assert _codigo(_enviar(client, h, emitida["id"])) == "CORREO_DESHABILITADO"
    assert db_session.scalars(select(EnvioCorreo).where(EnvioCorreo.cotizacion_id == emitida["id"])).all() == []


# Una fila de la tabla B9 por código de Tencent representativo.
FILAS_B9 = [
    ("FailedOperation.NoAttachPermission", "SIN_PERMISO_ADJUNTOS", False),
    ("FailedOperation.AttachContentToolarge", "ADJUNTO_DEMASIADO_GRANDE", False),
    ("FailedOperation.InvalidAttachName", "NOMBRE_ADJUNTO_INVALIDO", False),
    ("FailedOperation.EmailAddrInBlacklist", "DESTINATARIO_BLOQUEADO", False),
    ("FailedOperation.ReceiverHasUnsubscribed", "DESTINATARIO_DADO_DE_BAJA", False),
    ("InvalidParameterValue.ReceiverEmailInvalid", "EMAIL_INVALIDO", False),
    ("FailedOperation.WrongContentJson", "PLANTILLA_NO_DISPONIBLE", False),
    ("InvalidParameterValue.NoSuchSender", "REMITENTE_NO_VALIDO", False),
    ("FailedOperation.InsufficientQuota", "SIN_CUOTA", False),
    ("RequestLimitExceeded.UinLimitExceeded", "ENVIO_LIMITADO", True),
    ("AuthFailure.SignatureExpire", "HORA_DESFASADA", True),
    ("AuthFailure.SecretIdNotFound", "CREDENCIALES_INVALIDAS", False),
    ("ClientNetworkError", "PROVEEDOR_NO_DISPONIBLE", True),
    ("FailedOperation.AlgoNuevo", "ERROR_CORREO", False),
]


def test_cada_fila_de_b9_sin_cambiar_el_estado(client, crear_usuario, headers_de, db_session, falso):  # T297
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    emitida, _ = _emitida(client, h, db_session, comercial)
    for numero, (tencent, interno, reintentable) in enumerate(FILAS_B9, start=1):
        falso.error_envio = tencent
        respuesta = _enviar(client, h, emitida["id"])
        detalle = respuesta.json()["detail"]
        assert (respuesta.status_code, detalle["codigo"], detalle["reintentable"]) == (502, interno, reintentable), tencent
        assert detalle["mensaje"] == traducir(tencent).mensaje
        assert "Mensaje crudo" not in detalle["mensaje"]
        fila = db_session.get(EnvioCorreo, detalle["envio_id"])
        assert (fila.estado, fila.codigo_error, fila.request_id, fila.reintentable) == (
            "FALLIDO", interno, f"req-falso-{numero}", reintentable)
    assert "Código: FailedOperation.AlgoNuevo" in traducir("FailedOperation.AlgoNuevo").mensaje
    assert client.get(f"/v1/cotizaciones/{emitida['id']}", headers=h).json()["estado"] == "EMITIDA"
    envios = client.get(f"/v1/cotizaciones/{emitida['id']}/envios", headers=h).json()
    assert len(envios) == len(FILAS_B9) and all("crudo" not in e["mensaje"] for e in envios)
    # Adjunto más grande que el límite: no se llama al proveedor.
    falso.error_envio = None
    enviados = len(falso.enviados)
    _config(db_session, adjunto_max_bytes=1000)
    grande = _enviar(client, h, emitida["id"])
    assert (grande.status_code, _codigo(grande)) == (502, "ADJUNTO_DEMASIADO_GRANDE")
    assert len(falso.enviados) == enviados


def test_traduccion_por_codigo_de_toda_la_tabla():  # T297
    for codigo, traduccion in TABLA_B9.items():
        assert traducir(codigo) == traduccion
    assert traducir("RequestLimitExceeded").codigo == "ENVIO_LIMITADO"
    assert traducir("UnauthorizedOperation.Algo").codigo == "CREDENCIALES_INVALIDAS"
    assert traducir("InternalError.Algo").codigo == "PROVEEDOR_NO_DISPONIBLE"


# ---------- Bitácoras de solo lectura (T298) ----------


def test_bitacoras_solo_lectura_y_checks(client, crear_usuario, headers_de, db_session, falso):  # T298
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    _con_llaves(db_session)
    emitida, _ = _emitida(client, h, db_session, comercial)
    assert _enviar(client, h, emitida["id"]).status_code == 200
    ruta = f"/v1/cotizaciones/{emitida['id']}/envios"
    assert [getattr(client, m)(ruta, headers=h).status_code for m in ("post", "put", "patch", "delete")] == [405] * 4
    fila = db_session.scalars(select(EnvioCorreo).where(EnvioCorreo.cotizacion_id == emitida["id"])).one()
    for sentencia in (f"UPDATE envio_correo SET estado = 'FALLIDO' WHERE id = {fila.id}",
                      f"DELETE FROM envio_correo WHERE id = {fila.id}"):
        with pytest.raises(DBAPIError, match="solo inserción"):
            db_session.execute(text(sentencia))
        db_session.rollback()
    base = {"cotizacion_id": emitida["id"], "destinatario": "a@b.ec", "asunto": "x", "adjunto_nombre": "x.pdf",
            "adjunto_bytes": 1, "enviado_por": comercial.id}
    for malo in ({"estado": "ENVIADO"}, {"estado": "FALLIDO"}, {"estado": "OTRO", "codigo_error": "X"}):
        db_session.add(EnvioCorreo(**base, **malo))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


# ---------- Sin SDK ni red (T299) ----------


def test_la_app_no_importa_el_sdk():  # T299
    codigo = ("import os, sys; os.environ['APP_ENV'] = 'test'; sys.path.insert(0, '.'); import app.main;"
              " import app.services.correo; print(any(m.startswith('tencentcloud') for m in sys.modules))")
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=120)
    assert salida.stdout.strip() == "False", salida.stderr
    assert not any(m.startswith("tencentcloud") for m in sys.modules)
    assert "app.services.tencent_ses" not in sys.modules

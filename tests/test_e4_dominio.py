"""E4 Dominio propio (TE4-01 a TE4-08): URL pública del sistema como fuente única de los enlaces, www → dominio
principal y el sistema funcionando igual con cualquier dominio (run.app o pricing.xpress.ec)."""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Auditoria, ConfigSistema, Notificacion
from app.services import eventos, notificaciones, sistema
from test_e1_boletines import (  # noqa: F401 - fixtures y ayudas de E1
    _campana,
    _contactos,
    _enviar,
    _escenario,
    _hoy,
    _lista,
    _lote,
    correo_listo,
)
from test_f4_correo import _sin_red, falso, llave  # noqa: F401 - fixtures de F4

RUN_APP = "https://xps-pricing-809824844407.us-central1.run.app"
PROPIO = "https://pricing.xpress.ec"
RAIZ = Path(__file__).resolve().parent.parent


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _fijar_url(db_session, url: str) -> None:
    db_session.get(ConfigSistema, 1).url_publica = url
    db_session.commit()


def test_siembra_y_ninguna_url_fija_en_el_codigo(db_session):  # TE4-01
    assert sistema.url_publica(db_session) == RUN_APP  # 0011 copia el valor de config_masivos (E1)
    fijas = [
        str(ruta.relative_to(RAIZ)) for carpeta in ("app", "frontend") for ruta in (RAIZ / carpeta).rglob("*")
        if ruta.suffix in (".py", ".js", ".html") and "run.app" in ruta.read_text(encoding="utf-8", errors="ignore")
    ]
    assert fijas == []  # la URL run.app solo vive en la base (config_sistema) y en la migración que la siembra


@pytest.mark.parametrize(("rol", "lee"), [("admin", 200), ("pricing", 403), ("comercial", 403), ("gerencia", 403)])
def test_permisos(client, crear_usuario, headers_de, rol, lee):  # TE4-02
    h = headers_de(crear_usuario(rol))
    assert client.get("/v1/configuracion/sistema", headers=h).status_code == lee
    esperado = 200 if lee == 200 else 403
    assert client.put("/v1/configuracion/sistema", json={"url_publica": RUN_APP}, headers=h).status_code == esperado


def test_validacion_y_auditoria(client, crear_usuario, headers_de, db_session):  # TE4-03
    h = headers_de(crear_usuario("admin"))
    for malo in ("http://pricing.xpress.ec", "https://pricing.xpress.ec/app", "pricing.xpress.ec", "https://", ""):
        respuesta = client.put("/v1/configuracion/sistema", json={"url_publica": malo}, headers=h)
        assert (respuesta.status_code, _codigo(respuesta)) == (422, "URL_PUBLICA_INVALIDA"), malo
    guardada = client.put("/v1/configuracion/sistema", json={"url_publica": f" {PROPIO}/ "}, headers=h)
    assert guardada.json()["url_publica"] == PROPIO  # sin espacios ni barra final
    cambios = db_session.scalars(select(Auditoria).where(Auditoria.entidad == "config_sistema")).all()
    assert [(c.valores_antes["url_publica"], c.valores_despues["url_publica"]) for c in cambios] == [(RUN_APP, PROPIO)]
    assert client.put("/v1/configuracion/sistema", json={"url_publica": PROPIO}, headers=h).status_code == 200
    assert len(db_session.scalars(select(Auditoria).where(Auditoria.entidad == "config_sistema")).all()) == 1  # sin cambio


def test_enlace_de_baja_de_boletines_con_la_url_configurada(client, crear_usuario, headers_de, db_session, correo_listo):  # TE4-04
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _fijar_url(db_session, PROPIO)
    _, tarifa = _escenario(db_session, pricing)
    lista = _lista(client, h, _contactos(db_session, pricing, 1, "dom"))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    assert _enviar(client, h, campana["id"]).status_code == 200
    _lote(db_session)
    mensaje = correo_listo.enviados[-1]
    assert mensaje.datos_plantilla["enlace_baja"].startswith(f"{PROPIO}/b/")


def test_enlace_interno_es_solo_la_ruta():  # TE4-05: el dominio lo pone la plantilla
    assert notificaciones.ruta_interna("/app/cotizacion.html?id=7") == "/app/cotizacion.html?id=7"
    assert notificaciones.ruta_interna("app/tarifas.html") == "/app/tarifas.html"
    assert notificaciones.ruta_interna(None) == "/app/inicio.html"


def test_avisos_generados_con_la_url_configurada(db_session, crear_usuario):  # TE4-06
    admin = crear_usuario("admin")
    _fijar_url(db_session, PROPIO)
    regla = notificaciones.reglas_activas(db_session, "USUARIO_BLOQUEADO")[0]
    ocurrencia = eventos.Ocurrencia(entidad_tipo="usuario", entidad_id=str(admin.id), clave="e4", titulo="Prueba E4",
                                    mensaje="Prueba", enlace="/app/usuarios.html")
    notificaciones.generar(db_session, "USUARIO_BLOQUEADO", [ocurrencia], regla, notificaciones.contexto(db_session))
    db_session.commit()
    correo = db_session.scalars(select(Notificacion).where(Notificacion.evento == "USUARIO_BLOQUEADO",
                                                           Notificacion.canal == "CORREO",
                                                           Notificacion.usuario_id == admin.id)).one()
    assert correo.variables["enlace"] == "/app/usuarios.html"  # solo la ruta (sin dominio)
    assert correo.variables["referencia"] == admin.email and correo.variables["evento"] == "Usuario bloqueado"


def test_www_redirige_al_dominio_principal(client):  # TE4-07
    respuesta = client.get("/app/login.html?x=1", headers={"host": "www.pricing.xpress.ec"}, follow_redirects=False)
    assert (respuesta.status_code, respuesta.headers["location"]) == (301, f"{PROPIO}/app/login.html?x=1")
    post = client.post("/v1/auth/login", headers={"host": "www.pricing.xpress.ec"}, json={}, follow_redirects=False)
    assert (post.status_code, post.headers["location"]) == (308, f"{PROPIO}/v1/auth/login")  # conserva el cuerpo


@pytest.mark.parametrize("host", ["pricing.xpress.ec", "xps-pricing-809824844407.us-central1.run.app"])
def test_el_sistema_responde_igual_con_ambos_dominios(client, crear_usuario, host):  # TE4-08
    from conftest import PASSWORD_PRUEBA

    assert client.get("/v1/salud", headers={"host": host}).status_code in (200, 503)
    assert client.get("/app/login.html", headers={"host": host}).status_code == 200
    assert client.get("/", headers={"host": host}, follow_redirects=False).headers["location"] == "/app/login.html"
    usuario = crear_usuario("comercial")
    ingreso = client.post("/v1/auth/login", headers={"host": host}, json={"email": usuario.email, "password": PASSWORD_PRUEBA})
    assert ingreso.status_code == 200, ingreso.text
    token = ingreso.json()["access_token"]
    yo = client.get("/v1/auth/yo", headers={"host": host, "Authorization": f"Bearer {token}"})
    assert yo.status_code == 200 and yo.json()["email"] == usuario.email

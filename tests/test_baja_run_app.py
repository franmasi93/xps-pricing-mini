"""Baja de run.app (TRA-01 a TRA-07): por la URL de Cloud Run solo siguen /internal/* y /v1/salud; GET y HEAD van con
301 a la URL pública del sistema y la escritura recibe 410. pricing.xpress.ec no cambia. Los eventos de Tencent de
"Enviarme una prueba" quedan vinculados. Ninguna URL .run.app fija en el código, los scripts ni las plantillas."""
import re
from pathlib import Path

import pytest

from app.models import ConfigSistema, EnvioCorreoPrueba
from app.services import historial_correos

RUN_APP = "xps-pricing-809824844407.us-central1.run.app"
PROPIO = "https://pricing.xpress.ec"
RAIZ = Path(__file__).resolve().parent.parent
URL_RUN_APP = re.compile(r"https?://[\w.-]+\.run\.app")


@pytest.fixture
def con_dominio(db_session):
    db_session.get(ConfigSistema, 1).url_publica = PROPIO
    db_session.commit()


@pytest.mark.parametrize("metodo", ["GET", "HEAD"])
def test_lectura_por_run_app_redirige_con_ruta_y_query(client, con_dominio, metodo):  # TRA-01
    respuesta = client.request(metodo, "/app/cotizacion.html?id=5&x=a%20b", headers={"host": RUN_APP}, follow_redirects=False)
    assert (respuesta.status_code, respuesta.headers["location"]) == (301, f"{PROPIO}/app/cotizacion.html?id=5&x=a%20b")
    raiz = client.get("/", headers={"host": RUN_APP}, follow_redirects=False)
    assert (raiz.status_code, raiz.headers["location"]) == (301, f"{PROPIO}/")
    baja = client.get("/b/token-viejo", headers={"host": f"{RUN_APP}:443"}, follow_redirects=False)
    assert (baja.status_code, baja.headers["location"]) == (301, f"{PROPIO}/b/token-viejo")  # enlaces de baja viejos


@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_escritura_por_run_app_responde_410(client, con_dominio, metodo):  # TRA-02
    respuesta = client.request(metodo, "/v1/auth/login", headers={"host": RUN_APP}, json={})
    assert respuesta.status_code == 410
    assert respuesta.json()["detail"]["codigo"] == "USE_DOMINIO_PROPIO"
    assert f"Use {PROPIO}" in respuesta.json()["detail"]["mensaje"]


def test_internal_y_salud_siguen_por_run_app(client, con_dominio):  # TRA-03
    lote = client.post("/internal/boletines/procesar-lote", headers={"host": RUN_APP, "X-Tarea-Secreto": "otro"})
    assert lote.status_code not in (301, 410)  # llega al endpoint (que rechaza el secreto o avisa que no está configurado)
    evaluar = client.post("/internal/notificaciones/evaluar", headers={"host": RUN_APP})
    assert evaluar.status_code not in (301, 410)
    tencent = client.post("/internal/tencent/eventos/token-falso", headers={"host": RUN_APP}, json={})
    assert tencent.status_code not in (301, 410)
    assert client.get("/v1/salud", headers={"host": RUN_APP}).status_code in (200, 503)


def test_el_dominio_propio_no_cambia(client, con_dominio, crear_usuario):  # TRA-04
    from conftest import PASSWORD_PRUEBA

    host = {"host": "pricing.xpress.ec"}
    assert client.get("/app/login.html", headers=host).status_code == 200
    usuario = crear_usuario("comercial")
    ingreso = client.post("/v1/auth/login", headers=host, json={"email": usuario.email, "password": PASSWORD_PRUEBA})
    assert ingreso.status_code == 200, ingreso.text
    assert client.get("/", headers=host, follow_redirects=False).headers["location"] == "/app/login.html"


def test_sin_dominio_propio_no_redirige(client, db_session):  # TRA-05
    db_session.get(ConfigSistema, 1).url_publica = f"https://{RUN_APP}"
    db_session.commit()
    assert client.get("/app/login.html", headers={"host": RUN_APP}, follow_redirects=False).status_code == 200


def test_evento_de_una_prueba_queda_vinculado(db_session, crear_usuario):  # TRA-06
    prueba = EnvioCorreoPrueba(destinatario="admin@prueba.ec", asunto="[PRUEBA] x", adjunto_nombre="", adjunto_bytes=0,
                               estado="ENVIADO", message_id="msg-prueba-tra06", enviado_por=crear_usuario("admin").id)
    db_session.add(prueba)
    db_session.commit()
    resultado = historial_correos.guardar_evento(db_session, {"event": "delivery", "bulkId": "msg-prueba-tra06"})
    db_session.commit()
    assert (resultado["origen"], resultado["origen_id"], resultado["nuevo"]) == ("PRUEBA", prueba.id, True)
    repetido = historial_correos.guardar_evento(db_session, {"event": "delivery", "bulkId": "msg-prueba-tra06"})
    assert repetido["nuevo"] is False  # idempotente por (MessageId, evento)


def test_ninguna_url_run_app_fija():  # TRA-07
    carpetas = ("app", "frontend", "scripts", "docs/extensiones/plantillas")
    fijas = [
        str(ruta.relative_to(RAIZ)) for carpeta in carpetas if (RAIZ / carpeta).exists() for ruta in (RAIZ / carpeta).rglob("*")
        if ruta.is_file() and ruta.suffix in (".py", ".js", ".html", ".txt", ".json", ".md", ".ps1")
        and URL_RUN_APP.search(ruta.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert fijas == []

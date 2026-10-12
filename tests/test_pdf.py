"""PDF de cotización (T253–T256): nunca muestra proveedor, costo, tasa ni margen (§12, D-F3-13)."""
import io
from datetime import date

import pytest
from pypdf import PdfReader

from cotizacion_escenarios import Escenario, cargar_condiciones, crear_recargo, fijar_hoy
from fabricas import crear_moneda, crear_tasa

PROVEEDOR_SECRETO = "PROVEEDOR-SECRETO-XYZ"


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _texto(contenido: bytes) -> str:
    return "".join(pagina.extract_text() for pagina in PdfReader(io.BytesIO(contenido)).pages)


def _cotizacion_eur(client, h, db_session, comercial, admin) -> dict:
    eur = crear_moneda(db_session, codigo="EUR")
    crear_tasa(db_session, eur, "1.234567", date(2026, 6, 1), admin)
    esc = Escenario(db_session, comercial, moneda_id=eur.id, costo="77.7777")
    esc.proveedor.nombre = PROVEEDOR_SECRETO
    db_session.commit()
    crear_recargo(db_session, esc.destino, "GASTOS_DESTINO", "DESTINO", proveedor_id=esc.proveedor.id)
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=h).json()
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/proponer-lineas", json={}, headers=h).status_code == 200
    return cotizacion


def test_pdf_emitida_sin_datos_internos(client, crear_usuario, headers_de, db_session):  # T253
    comercial, admin = crear_usuario("comercial"), crear_usuario("admin")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    cotizacion = _cotizacion_eur(client, h, db_session, comercial, admin)
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h).json()
    respuesta = client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h)
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert f'filename="{emitida["numero"]}_' in respuesta.headers["content-disposition"]
    texto = _texto(respuesta.content)
    for prohibido in (PROVEEDOR_SECRETO, "77.7777", "1.234567", "POSTAL"):
        assert prohibido not in texto, prohibido
    assert "margen" not in texto.lower()
    for requerido in (emitida["numero"], emitida["totales"]["total_general"], "XPRESS LOGISTICS XPS S.A.",
                      "Recibo de Caja (IVA 0%)", "Factura (IVA 15%)", "TEXTO DE PRUEBA"):
        assert requerido in texto, requerido


def test_pdf_desde_el_snapshot_mismo_contenido(client, crear_usuario, headers_de, db_session):  # T254
    comercial, admin = crear_usuario("comercial"), crear_usuario("admin")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    cotizacion = _cotizacion_eur(client, h, db_session, comercial, admin)
    client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    primero = _texto(client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h).content)
    cargar_condiciones(db_session, "TEXTO DE PRUEBA: otras condiciones cargadas después de emitir.")
    crear_tasa(db_session, crear_moneda(db_session), "2.000000", date(2026, 6, 15), admin)
    segundo = _texto(client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h).content)
    assert primero == segundo  # sale del snapshot congelado, no de la configuración actual


def test_pdf_vista_previa_del_borrador(client, crear_usuario, headers_de, db_session):  # T255
    comercial, admin = crear_usuario("comercial"), crear_usuario("admin")
    h = headers_de(comercial)
    cotizacion = _cotizacion_eur(client, h, db_session, comercial, admin)
    respuesta = client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=h)
    assert respuesta.status_code == 200
    assert f'filename="BORRADOR-{cotizacion["id"]}_' in respuesta.headers["content-disposition"]
    texto = _texto(respuesta.content)
    assert "BORRADOR" in texto
    assert "COT-" not in texto
    assert PROVEEDOR_SECRETO not in texto


def test_pdf_ajeno_404(client, crear_usuario, headers_de, db_session):  # T256
    comercial, otro, admin = crear_usuario("comercial"), crear_usuario("comercial"), crear_usuario("admin")
    cotizacion = _cotizacion_eur(client, headers_de(comercial), db_session, comercial, admin)
    respuesta = client.get(f"/v1/cotizaciones/{cotizacion['id']}/pdf", headers=headers_de(otro))
    assert (respuesta.status_code, respuesta.json()["detail"]["codigo"]) == (404, "COTIZACION_NO_ENCONTRADA")

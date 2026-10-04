"""Pantallas servidas en /app; / y /app llevan al login."""
import re

import pytest


@pytest.mark.parametrize("ruta", ["/", "/app", "/app/"])
def test_raiz_redirige_a_login(client, ruta):  # T64
    respuesta = client.get(ruta, follow_redirects=False)
    assert respuesta.status_code in (302, 307)
    assert respuesta.headers["location"] == "/app/login.html"


PAGINAS_F1 = ["geografia.html", "proveedores.html", "monedas.html", "incoterms.html", "configuracion.html"]


@pytest.mark.parametrize("pagina", PAGINAS_F1)
def test_paginas_f1(client, pagina):  # T137
    respuesta = client.get(f"/app/{pagina}")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/html")
    hojas_locales = re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text)
    assert hojas_locales == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text


def test_app_sirve_login_y_css(client):  # T65
    pagina = client.get("/app/login.html")
    assert pagina.status_code == 200
    assert pagina.headers["content-type"].startswith("text/html")
    assert 'href="css/xps-pricing.css"' in pagina.text
    assert 'src="img/xpress-logo-blanco.png"' in pagina.text

    hoja = client.get("/app/css/xps-pricing.css")
    assert hoja.status_code == 200
    assert hoja.headers["content-type"].startswith("text/css")
    assert "--navy: #000771" in hoja.text
    assert "--naranja: #ED4C01" in hoja.text

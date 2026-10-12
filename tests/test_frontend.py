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


PAGINAS_F2 = ["tarifas", "recargos", "clientes"]
PATRONES_PROHIBIDOS_JS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "localStorage")


@pytest.mark.parametrize("pagina", PAGINAS_F2)
def test_paginas_f2(client, pagina):  # T204
    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    hojas_locales = re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text)
    assert hojas_locales == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []


PAGINAS_F3 = ["cotizaciones", "cotizador", "cotizacion"]


@pytest.mark.parametrize("pagina", PAGINAS_F3)
def test_paginas_f3(client, pagina):  # T257
    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    hojas_locales = re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text)
    assert hojas_locales == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []


def _permisos_menu(client, texto: str) -> list[str] | None:
    """Permisos de una opción del menú de layout.js (None = visible para todos)."""
    layout = client.get("/app/js/layout.js").text
    opcion = re.search(rf'\{{ texto: "{texto}", archivo: "[^"]+", permisos: (null|\[[^\]]*\]) \}}', layout)
    assert opcion is not None, texto
    return None if opcion.group(1) == "null" else re.findall(r'"([^"]+)"', opcion.group(1))


def _visible(permisos_opcion: list[str] | None, permisos_rol: set[str]) -> bool:
    # La misma regla de iniciarLayout: null = todos; si no, basta uno de la lista.
    return permisos_opcion is None or any(permiso in permisos_rol for permiso in permisos_opcion)


def test_menu_cotizaciones_por_permiso(client, db_session):  # T258
    from sqlalchemy import select

    from app.models import Rol

    permisos_opcion = _permisos_menu(client, "Cotizaciones")
    assert set(permisos_opcion) == {"cotizacion.crear", "cotizacion.ver_todas"}
    roles = {rol.codigo: {p.codigo for p in rol.permisos} for rol in db_session.scalars(select(Rol))}
    # Seed real: admin, pricing y comercial crean; gerencia lee todas. Los cuatro ven la opción.
    assert {codigo: _visible(permisos_opcion, permisos) for codigo, permisos in roles.items()} == {
        "admin": True, "pricing": True, "comercial": True, "gerencia": True
    }
    # Un rol sin cotizacion.crear ni cotizacion.ver_todas no la ve.
    assert _visible(permisos_opcion, roles["comercial"] - {"cotizacion.crear", "cotizacion.ver_todas"}) is False


def test_incoterms_devuelven_id(client, crear_usuario, headers_de):  # T259
    respuesta = client.get("/v1/incoterms", headers=headers_de(crear_usuario("comercial")))
    assert respuesta.status_code == 200
    assert all(isinstance(incoterm["id"], int) for incoterm in respuesta.json())


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

"""F5-A1 (T303): pantalla de auditoría: permiso, filtros (usuario), paginación y nunca secretos."""
import json
import re

from sqlalchemy import select

from app.models import Rol
from app.services import auditoria
from test_frontend import PATRONES_PROHIBIDOS_JS, _permisos_menu, _visible


def test_pantalla_y_menu_de_auditoria(client, db_session):  # T303
    pagina = client.get("/app/auditoria.html")
    assert pagina.status_code == 200
    assert re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', pagina.text) == ["css/xps-pricing.css"]
    assert "<style" not in pagina.text and "style=" not in pagina.text
    script = client.get("/app/js/auditoria.js").text
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script] == []
    permisos = _permisos_menu(client, "Auditoría")
    assert permisos == ["auditoria.ver"]
    roles = {rol.codigo: {p.codigo for p in rol.permisos} for rol in db_session.scalars(select(Rol))}
    assert {codigo: _visible(permisos, p) for codigo, p in roles.items()} == {
        "admin": True, "pricing": False, "comercial": False, "gerencia": True}


def test_filtro_por_usuario_paginacion_y_permiso(client, crear_usuario, headers_de, db_session):  # T303
    gerencia, autor, otro = crear_usuario("gerencia"), crear_usuario("admin", nombre="Autor F5"), crear_usuario("admin")
    for numero in range(3):
        auditoria.registrar(db_session, autor, "prueba_f5", numero, "EDITAR", antes={"valor": numero},
                            despues={"valor": numero + 1, "secret_id": "IKID****ZQ3"})
    auditoria.registrar(db_session, otro, "prueba_f5", 9, "CREAR", despues={"valor": 9})
    db_session.commit()
    h = headers_de(gerencia)
    pagina = client.get(f"/v1/auditoria?entidad=prueba_f5&usuario_id={autor.id}&limit=2&offset=0", headers=h).json()
    assert (pagina["total"], len(pagina["items"])) == (3, 2)
    assert {item["usuario_nombre"] for item in pagina["items"]} == {"Autor F5"}
    segunda = client.get(f"/v1/auditoria?entidad=prueba_f5&usuario_id={autor.id}&limit=2&offset=2", headers=h).json()
    assert len(segunda["items"]) == 1
    usuarios = client.get("/v1/auditoria/usuarios", headers=h).json()
    assert {"id": autor.id, "nombre": "Autor F5"} in usuarios
    assert "IKID****ZQ3" in json.dumps(pagina) and not re.search(r"IKID[A-Za-z0-9]{20,}", json.dumps(pagina))
    comercial = headers_de(crear_usuario("comercial"))
    assert client.get("/v1/auditoria", headers=comercial).status_code == 403
    assert client.get("/v1/auditoria/usuarios", headers=comercial).status_code == 403

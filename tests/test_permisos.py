"""RBAC contra el seed real: solo admin entra a /usuarios y /roles."""
import pytest
from sqlalchemy import text

from app.core.rbac import tiene_permiso
from matriz_rbac import MATRIZ_6_2, sin_extensiones

ENDPOINTS_ADMIN = [
    ("get", "/v1/usuarios", None),
    ("get", "/v1/usuarios/{id}", None),
    ("post", "/v1/usuarios", {"email": "nuevo@prueba.xps", "nombre": "Nuevo", "rol_codigo": "comercial",
                              "password_temporal": "Temporal2026x"}),
    ("patch", "/v1/usuarios/{id}", {"nombre": "Otro nombre"}),
    ("post", "/v1/usuarios/{id}/restablecer-password", {"password_temporal": "Temporal2026x"}),
    ("get", "/v1/roles", None),
]


@pytest.mark.parametrize("rol", ["comercial", "pricing", "gerencia"])
@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"), ENDPOINTS_ADMIN, ids=[f"{m}_{r}" for m, r, _ in ENDPOINTS_ADMIN]
)
def test_no_admin_403_en_endpoints_admin(client, crear_usuario, headers_de, rol, metodo, ruta, cuerpo):  # T37 (h)
    usuario = crear_usuario(rol)
    kwargs = {"headers": headers_de(usuario)}
    if cuerpo is not None:
        kwargs["json"] = cuerpo
    respuesta = client.request(metodo.upper(), ruta.format(id=usuario.id), **kwargs)
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"]["codigo"] == "PERMISO_DENEGADO"


def test_admin_200_en_usuarios_y_roles(client, crear_usuario, headers_de):  # T38 (h)
    admin = crear_usuario("admin")
    assert client.get("/v1/usuarios", headers=headers_de(admin)).status_code == 200
    assert client.get("/v1/roles", headers=headers_de(admin)).status_code == 200


def test_tiene_permiso_lee_de_bd(crear_usuario, db_session):  # T39
    usuario = crear_usuario("gerencia")
    assert tiene_permiso(usuario, "costo.ver") is True
    db_session.execute(
        text(
            "DELETE FROM rol_permiso WHERE rol_id = :rol_id "
            "AND permiso_id = (SELECT id FROM permiso WHERE codigo = 'costo.ver')"
        ),
        {"rol_id": usuario.rol_id},
    )
    db_session.expire_all()
    assert tiene_permiso(usuario, "costo.ver") is False
    assert tiene_permiso(usuario, "auditoria.ver") is True


def test_roles_lista_4_con_permisos_6_2(client, crear_usuario, headers_de):  # T40
    admin = crear_usuario("admin")
    respuesta = client.get("/v1/roles", headers=headers_de(admin))
    assert respuesta.status_code == 200
    roles = {rol["codigo"]: set(rol["permisos"]) for rol in respuesta.json()}
    assert sin_extensiones(roles) == MATRIZ_6_2  # D-E0-1: los permisos de las extensiones, en test_e0_servicios

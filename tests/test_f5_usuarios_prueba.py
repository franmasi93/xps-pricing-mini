"""F5-C2 (T308): usuarios de prueba, uno por rol, con cambio obligatorio; la baja es activo=false, sin borrar."""
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.security import verificar_password
from app.models import Auditoria, Usuario

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import usuarios_prueba  # noqa: E402


def test_crear_reactivar_y_desactivar(client, db_session):  # T308
    creados = usuarios_prueba.crear_o_reactivar(db_session)
    assert [u["rol"] for u in creados] == ["admin", "pricing", "comercial", "gerencia"]
    for dato in creados:
        usuario = db_session.scalars(select(Usuario).where(Usuario.email == dato["email"])).one()
        assert (usuario.activo, usuario.forzar_cambio_password, usuario.rol.codigo) == (True, True, dato["rol"])
        assert verificar_password(usuario.hash_password, dato["password"]) and len(dato["password"]) == 16
    login = client.post("/v1/auth/login", json={"email": creados[2]["email"], "password": creados[2]["password"]})
    assert login.status_code == 200  # entra, y el sistema le exige cambiar la contraseña
    assert login.json()["forzar_cambio_password"] is True
    otra_vez = usuarios_prueba.crear_o_reactivar(db_session)  # reactivar cambia la contraseña
    assert otra_vez[0]["password"] != creados[0]["password"]
    assert usuarios_prueba.desactivar(db_session) == [u["email"] for u in creados]
    assert usuarios_prueba.desactivar(db_session) == []  # ya no hay activos
    for dato in creados:
        assert db_session.scalars(select(Usuario).where(Usuario.email == dato["email"])).one().activo is False
    bajas = db_session.scalars(select(Auditoria).where(Auditoria.entidad == "usuario", Auditoria.accion == "DESACTIVAR",
                                                       Auditoria.nota == "USUARIO DE PRUEBA F5-C2 DESACTIVADO")).all()
    assert len(bajas) == 4

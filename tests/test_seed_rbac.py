"""El seed de la migración 0001 debe coincidir EXACTAMENTE con la matriz §6.2."""
from sqlalchemy import text

from matriz_rbac import MATRIZ_6_2, PERMISOS_6_2


def test_seed_4_roles(db_session):  # T03
    roles = set(db_session.execute(text("SELECT codigo FROM rol")).scalars())
    assert roles == {"admin", "pricing", "comercial", "gerencia"}


def test_seed_15_permisos(db_session):  # T04
    permisos = list(db_session.execute(text("SELECT codigo FROM permiso")).scalars())
    assert len(permisos) == 15
    assert set(permisos) == PERMISOS_6_2


def test_seed_matriz_6_2_exacta(db_session):  # T05
    filas = db_session.execute(
        text(
            "SELECT r.codigo, p.codigo FROM rol_permiso rp "
            "JOIN rol r ON r.id = rp.rol_id JOIN permiso p ON p.id = rp.permiso_id"
        )
    ).all()
    assert len(filas) == 38
    matriz_bd: dict[str, set[str]] = {}
    for rol, permiso in filas:
        matriz_bd.setdefault(rol, set()).add(permiso)
    assert matriz_bd == MATRIZ_6_2

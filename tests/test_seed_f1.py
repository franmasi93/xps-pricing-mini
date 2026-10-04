"""Seed de la migración 0002 (T136): solo USD, 11 Incoterms, 4 claves; RBAC sin cambios."""
from sqlalchemy import text


def test_conteos_despues_de_upgrade(db_session):  # T136
    def contar(tabla: str) -> int:
        return db_session.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar_one()

    assert db_session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0002"
    assert list(db_session.execute(text("SELECT codigo FROM moneda")).scalars()) == ["USD"]
    assert (contar("incoterm"), contar("configuracion")) == (11, 4)
    assert (contar("rol"), contar("permiso"), contar("rol_permiso")) == (4, 15, 38)

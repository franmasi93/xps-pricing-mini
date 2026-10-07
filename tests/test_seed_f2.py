"""Seed de la migración 0003 (T138): 5 tipos de equipo, exclusiones de vigencia y RBAC sin cambios."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

RAIZ = Path(__file__).resolve().parent.parent
TIPOS_EQUIPO = {
    "20GP": "Contenedor 20' estándar",
    "40GP": "Contenedor 40' estándar",
    "40HC": "Contenedor 40' High Cube",
    "20RF": "Contenedor 20' refrigerado",
    "40RF": "Contenedor 40' refrigerado",
}


def _head_de_alembic() -> str:
    """Head real del script de Alembic: el test no se rompe al agregar migraciones."""
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def test_seed_tipos_equipo_y_rbac(db_session):  # T138
    def contar(tabla: str) -> int:
        return db_session.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar_one()

    assert db_session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _head_de_alembic()
    tipos = dict(db_session.execute(text("SELECT codigo, nombre FROM tipo_equipo WHERE activo")).all())
    assert tipos == TIPOS_EQUIPO
    assert (contar("rol"), contar("permiso"), contar("rol_permiso")) == (4, 15, 38)
    exclusiones = set(db_session.execute(text("SELECT conname FROM pg_constraint WHERE contype = 'x'")).scalars())
    assert exclusiones.issuperset({"ex_tarifa_vigencia_sin_superposicion", "ex_recargo_vigencia_sin_superposicion"})
    assert db_session.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'btree_gist'")).scalar_one() == 1

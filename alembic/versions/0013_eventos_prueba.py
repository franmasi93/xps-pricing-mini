"""Baja de run.app: los eventos de Tencent de "Enviarme una prueba" quedan vinculados a su envío (origen PRUEBA).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19

Migración escrita a mano. Solo amplía el CHECK de tencent_evento.origen. El downgrade deja esos eventos como
SIN_VINCULAR (sin origen_id) y vuelve al CHECK de 0012.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

ANTES = "'COTIZACION', 'BOLETIN', 'AVISO', 'SIN_VINCULAR'"
DESPUES = "'COTIZACION', 'BOLETIN', 'AVISO', 'PRUEBA', 'SIN_VINCULAR'"


def upgrade() -> None:
    op.drop_constraint("ck_tencent_evento_origen", "tencent_evento", type_="check")
    op.create_check_constraint("ck_tencent_evento_origen", "tencent_evento", f"origen IN ({DESPUES})")


def downgrade() -> None:
    op.execute("UPDATE tencent_evento SET origen = 'SIN_VINCULAR', origen_id = NULL WHERE origen = 'PRUEBA'")
    op.drop_constraint("ck_tencent_evento_origen", "tencent_evento", type_="check")
    op.create_check_constraint("ck_tencent_evento_origen", "tencent_evento", f"origen IN ({ANTES})")

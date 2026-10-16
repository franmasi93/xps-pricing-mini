"""F5-A3: índices de trigramas (pg_trgm) para la búsqueda de clientes por razón social o identificación.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15

Migración escrita a mano. pricing_app crea la extensión sin superusuario (probado en xps_pricing_test el
2026-10-15). La búsqueda sigue siendo ILIKE '%texto%' (services/clientes); los índices GIN la aceleran sin cambiar
resultados.
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_cliente_razon_social_trgm ON cliente USING gin (razon_social gin_trgm_ops)")
    op.execute("CREATE INDEX ix_cliente_ruc_o_id_trgm ON cliente USING gin (ruc_o_id gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cliente_ruc_o_id_trgm")
    op.execute("DROP INDEX IF EXISTS ix_cliente_razon_social_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

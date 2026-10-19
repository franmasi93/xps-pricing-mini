"""E4: "URL pública del sistema" en una configuración propia (config_sistema), fuente única de todos los enlaces.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19

Migración escrita a mano. config_sistema (una fila) toma el valor que hoy tiene config_masivos.url_publica (E1) y esa
columna se retira: los enlaces de baja, de avisos y cualquier otro salen solo de config_sistema.url_publica. El valor no
cambia (la URL run.app); el cambio a https://pricing.xpress.ec se hace por pantalla, con auditoría, cuando el dominio
propio esté activo. El downgrade devuelve el valor a config_masivos.
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

URL_POR_DEFECTO = "https://xps-pricing-809824844407.us-central1.run.app"


def upgrade() -> None:
    op.create_table(
        "config_sistema",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("url_publica", sa.String(300), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_config_sistema"),
        sa.CheckConstraint("id = 1", name="ck_config_sistema_una_fila"),
        sa.CheckConstraint("url_publica ~ '^https://[^/\\s]+$'", name="ck_config_sistema_url_publica"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_sistema_actualizado_por_usuario"),
    )
    op.execute(
        "INSERT INTO config_sistema (id, url_publica) SELECT 1, COALESCE(NULLIF(rtrim(btrim(url_publica), '/'), ''), "
        f"'{URL_POR_DEFECTO}') FROM config_masivos WHERE id = 1"
    )
    op.execute(f"INSERT INTO config_sistema (id, url_publica) SELECT 1, '{URL_POR_DEFECTO}' "
               "WHERE NOT EXISTS (SELECT 1 FROM config_sistema)")
    op.drop_column("config_masivos", "url_publica")


def downgrade() -> None:
    op.add_column("config_masivos", sa.Column("url_publica", sa.String(300), nullable=False, server_default=""))
    op.execute("UPDATE config_masivos SET url_publica = (SELECT url_publica FROM config_sistema WHERE id = 1)")
    op.drop_table("config_sistema")

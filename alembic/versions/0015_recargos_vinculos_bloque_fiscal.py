"""Recargos vinculados a tarifas y servicios (D-R2) y bloque fiscal en el recargo (D-R3).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-21

Migración escrita a mano.
- recargo_tarifa (recargo, tarifa) y recargo_servicio (recargo, servicio): únicos por par, se borran con el recargo
  o con la tarifa. Un recargo sin vínculos sigue siendo "general" y funciona como antes.
- recargo.puerto_id pasa a ser opcional: un recargo vinculado a tarifas toma el puerto de la tarifa según su lado
  (el servicio exige que un recargo sin puerto tenga al menos una tarifa vinculada).
- recargo.bloque_fiscal (RECIBO_CAJA | FACTURA), obligatorio. SIN CAMBIOS DE PRECIO: cada recargo existente se
  llena con el bloque que hoy le asigna el motor (D-F3-4): el seguro → Recibo de Caja; en un puerto de Ecuador →
  Factura; en el exterior → Recibo de Caja. aplica_iva no se toca.
- linea_cotizacion.vinculado: la línea salió de un recargo vinculado a la tarifa o al servicio (etiqueta interna).
El downgrade exige que todos los recargos tengan puerto (devuelve el NOT NULL).
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recargo_tarifa",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("recargo_id", sa.Integer(), nullable=False),
        sa.Column("tarifa_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recargo_tarifa"),
        sa.UniqueConstraint("recargo_id", "tarifa_id", name="uq_recargo_tarifa_par"),
        sa.ForeignKeyConstraint(["recargo_id"], ["recargo.id"], name="fk_recargo_tarifa_recargo", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tarifa_id"], ["tarifa.id"], name="fk_recargo_tarifa_tarifa", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_recargo_tarifa_creado_por"),
    )
    op.create_index("ix_recargo_tarifa_tarifa", "recargo_tarifa", ["tarifa_id"])
    op.create_table(
        "recargo_servicio",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("recargo_id", sa.Integer(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recargo_servicio"),
        sa.UniqueConstraint("recargo_id", "servicio_id", name="uq_recargo_servicio_par"),
        sa.ForeignKeyConstraint(["recargo_id"], ["recargo.id"], name="fk_recargo_servicio_recargo", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"], name="fk_recargo_servicio_servicio", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_recargo_servicio_creado_por"),
    )
    op.alter_column("recargo", "puerto_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("recargo", sa.Column("bloque_fiscal", sa.String(11), nullable=True))
    op.execute(
        "UPDATE recargo r SET bloque_fiscal = CASE "
        "WHEN r.bloque_incoterm = 'SEGURO' THEN 'RECIBO_CAJA' "
        "WHEN pa.iso2 = 'EC' THEN 'FACTURA' ELSE 'RECIBO_CAJA' END "
        "FROM puerto p JOIN pais pa ON pa.id = p.pais_id WHERE p.id = r.puerto_id"
    )
    op.alter_column("recargo", "bloque_fiscal", existing_type=sa.String(11), nullable=False)
    op.create_check_constraint("ck_recargo_bloque_fiscal", "recargo", "bloque_fiscal IN ('RECIBO_CAJA', 'FACTURA')")
    op.add_column("linea_cotizacion", sa.Column("vinculado", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("linea_cotizacion", "vinculado")
    op.drop_constraint("ck_recargo_bloque_fiscal", "recargo", type_="check")
    op.drop_column("recargo", "bloque_fiscal")
    op.alter_column("recargo", "puerto_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("recargo_servicio")
    op.drop_index("ix_recargo_tarifa_tarifa", table_name="recargo_tarifa")
    op.drop_table("recargo_tarifa")

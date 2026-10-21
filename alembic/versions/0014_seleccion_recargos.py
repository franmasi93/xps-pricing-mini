"""FIX cotizador: cada línea de recargo dice por qué se propuso (seleccion).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-21

Migración escrita a mano. linea_cotizacion.seleccion (nula en el flete y en las líneas anteriores al FIX):
- INCOTERM: el Incoterm se lo asigna a XPRESS; se propone marcado (como antes).
- FUERA_INCOTERM: el Incoterm no se lo asigna a XPRESS; se propone desmarcado y el usuario puede marcarlo.
- ALTERNATIVA: perdió contra otro del mismo concepto (D-F3-7); desmarcado, elegible en su lugar.
No cambia ningún precio ni total: las líneas desmarcadas no se cobran.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("linea_cotizacion", sa.Column("seleccion", sa.String(14), nullable=True))
    op.create_check_constraint(
        "ck_linea_cotizacion_seleccion", "linea_cotizacion",
        "seleccion IS NULL OR seleccion IN ('INCOTERM', 'FUERA_INCOTERM', 'ALTERNATIVA')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_linea_cotizacion_seleccion", "linea_cotizacion", type_="check")
    op.drop_column("linea_cotizacion", "seleccion")

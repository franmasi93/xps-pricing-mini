"""Alcance en cadena de los recargos (D-A1..D-A4) y tipo de carga (D-T1..D-T8).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-21

Migración escrita a mano.
- recargo_alcance (recargo, nivel, valor): un recargo aplica si cumple TODOS los niveles que tiene; un nivel sin filas
  es "Todos". Niveles: SERVICIO, MODO (tipo de ubicación), TIPO_EQUIPO, REGION, PAIS, PUERTO (el del lado),
  PUERTO_ORIGEN y PUERTO_DESTINO (ruta exacta), PROVEEDOR (de la tarifa), TIPO_CARGA y CLASE_IMO.
  Los recargos existentes se traducen a su alcance equivalente de hoy, para que propongan EXACTAMENTE lo mismo:
  su puerto → PUERTO; su servicio (modo) y los servicios vinculados en 0015 → SERVICIO; su tipo de equipo →
  TIPO_EQUIPO; su proveedor → PROVEEDOR. recargo_servicio (0015) pasa a recargo_alcance y se retira.
- tipo_carga: catálogo (GENERAL, IMO, REFRIGERADA, SOBREDIMENSIONADA, PERECIBLE, ALTO_VALOR); "pide datos IMO".
- cotizacion: tipo_carga (GENERAL por defecto) y datos IMO (clase, UN, grupo de embalaje, MSDS). Las existentes
  quedan GENERAL; las emitidas no cambian (foto congelada).
- tarifa: tipos de carga que acepta (por defecto solo GENERAL) y clases IMO excluidas.
- linea_cotizacion.motivo_alternativa: por qué perdió una alternativa (D-A2).
- configuracion.condiciones_imo_pdf: texto adicional de condiciones para carga IMO (config.editar).
- recargo.alcance_firma: huella (md5) del alcance cuando NO es el equivalente a sus columnas (vacía en todos los
  recargos de antes). La exclusión ex_recargo_vigencia_sin_superposicion se rehace con la huella: dos recargos del
  mismo concepto con alcances distintos (por ejemplo, uno general y otro solo IMO) ya no chocan; los de antes, igual.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

NIVELES = ("'SERVICIO', 'MODO', 'TIPO_EQUIPO', 'REGION', 'PAIS', 'PUERTO', 'PUERTO_ORIGEN', 'PUERTO_DESTINO', "
           "'PROVEEDOR', 'TIPO_CARGA', 'CLASE_IMO'")
TIPOS_CARGA = [
    ("GENERAL", "General", False, 1),
    ("IMO", "IMO (Peligrosa)", True, 2),
    ("REFRIGERADA", "Refrigerada", False, 3),
    ("SOBREDIMENSIONADA", "Sobredimensionada (OOG)", False, 4),
    ("PERECIBLE", "Perecible", False, 5),
    ("ALTO_VALOR", "Alto valor", False, 6),
]
EXCLUSION_ANTES = (
    "ALTER TABLE recargo ADD CONSTRAINT ex_recargo_vigencia_sin_superposicion EXCLUDE USING gist ("
    " (COALESCE(proveedor_id, 0)) WITH =, puerto_id WITH =, lado WITH =, bloque_incoterm WITH =, (lower(concepto)) WITH =,"
    " (COALESCE(modo, '')) WITH =, (COALESCE(tipo_equipo_id, 0)) WITH =, daterange(valido_desde, valido_hasta, '[]') WITH &&"
    ") WHERE (activo)"
)
EXCLUSION_CON_ALCANCE = EXCLUSION_ANTES.replace(" daterange(", " alcance_firma WITH =, daterange(")
TEXTO_IMO = ("Sujeto a aceptación de la naviera o aerolínea y a la presentación de la MSDS. "
             "El embarque debe cumplir el código IMDG / IATA DGR.")


def upgrade() -> None:
    # --- Tipo de carga ---
    op.create_table(
        "tipo_carga",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("pide_imo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tipo_carga"),
        sa.UniqueConstraint("codigo", name="uq_tipo_carga_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{0,19}$'", name="ck_tipo_carga_codigo"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_tipo_carga_creado_por_usuario"),
    )
    tabla = sa.table("tipo_carga", sa.column("codigo"), sa.column("nombre"), sa.column("pide_imo"), sa.column("orden"))
    op.bulk_insert(tabla, [{"codigo": c, "nombre": n, "pide_imo": p, "orden": o} for c, n, p, o in TIPOS_CARGA])

    op.add_column("cotizacion", sa.Column("tipo_carga", sa.String(20), nullable=False, server_default="GENERAL"))
    op.add_column("cotizacion", sa.Column("imo_clase", sa.String(4), nullable=True))
    op.add_column("cotizacion", sa.Column("imo_un", sa.String(4), nullable=True))
    op.add_column("cotizacion", sa.Column("imo_grupo", sa.String(3), nullable=True))
    op.add_column("cotizacion", sa.Column("msds_recibida", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("fk_cotizacion_tipo_carga", "cotizacion", "tipo_carga", ["tipo_carga"], ["codigo"], ondelete="RESTRICT")
    op.create_check_constraint("ck_cotizacion_imo_clase", "cotizacion", "imo_clase IS NULL OR imo_clase ~ '^[1-9](\\.[1-9])?$'")
    op.create_check_constraint("ck_cotizacion_imo_un", "cotizacion", "imo_un IS NULL OR imo_un ~ '^[0-9]{4}$'")
    op.create_check_constraint("ck_cotizacion_imo_grupo", "cotizacion", "imo_grupo IS NULL OR imo_grupo IN ('I', 'II', 'III')")

    op.add_column("tarifa", sa.Column("tipos_carga", JSONB(), nullable=False, server_default=sa.text("'[\"GENERAL\"]'::jsonb")))
    op.add_column("tarifa", sa.Column("clases_imo_excluidas", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

    # --- Alcance en cadena de los recargos ---
    op.create_table(
        "recargo_alcance",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("recargo_id", sa.Integer(), nullable=False),
        sa.Column("nivel", sa.String(16), nullable=False),
        sa.Column("valor_id", sa.Integer(), nullable=True),
        sa.Column("valor_texto", sa.String(20), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recargo_alcance"),
        sa.ForeignKeyConstraint(["recargo_id"], ["recargo.id"], name="fk_recargo_alcance_recargo", ondelete="CASCADE"),
        sa.CheckConstraint(f"nivel IN ({NIVELES})", name="ck_recargo_alcance_nivel"),
        sa.CheckConstraint("(valor_id IS NULL) <> (valor_texto IS NULL)", name="ck_recargo_alcance_un_valor"),
    )
    op.execute("CREATE UNIQUE INDEX uq_recargo_alcance_valor ON recargo_alcance "
               "(recargo_id, nivel, coalesce(valor_id, 0), coalesce(valor_texto, ''))")
    op.create_index("ix_recargo_alcance_recargo", "recargo_alcance", ["recargo_id"])
    # Traducción del alcance de hoy (sin cambios en lo que se propone).
    op.execute("INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'PUERTO', puerto_id FROM recargo "
               "WHERE puerto_id IS NOT NULL")
    op.execute("INSERT INTO recargo_alcance (recargo_id, nivel, valor_texto) SELECT id, 'SERVICIO', modo FROM recargo "
               "WHERE modo IS NOT NULL")
    op.execute("INSERT INTO recargo_alcance (recargo_id, nivel, valor_texto) SELECT DISTINCT rs.recargo_id, 'SERVICIO', s.codigo "
               "FROM recargo_servicio rs JOIN servicio s ON s.id = rs.servicio_id JOIN recargo r ON r.id = rs.recargo_id "
               "WHERE r.modo IS NULL")
    op.execute("INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'TIPO_EQUIPO', tipo_equipo_id FROM recargo "
               "WHERE tipo_equipo_id IS NOT NULL")
    op.execute("INSERT INTO recargo_alcance (recargo_id, nivel, valor_id) SELECT id, 'PROVEEDOR', proveedor_id FROM recargo "
               "WHERE proveedor_id IS NOT NULL")
    op.drop_table("recargo_servicio")
    op.add_column("recargo", sa.Column("alcance_firma", sa.String(32), nullable=False, server_default=""))
    op.execute("ALTER TABLE recargo DROP CONSTRAINT ex_recargo_vigencia_sin_superposicion")
    op.execute(EXCLUSION_CON_ALCANCE)

    op.add_column("linea_cotizacion", sa.Column("motivo_alternativa", sa.String(200), nullable=True))
    op.execute(sa.text("INSERT INTO configuracion (clave, valor, tipo, permiso_edicion) VALUES "
                       "('condiciones_imo_pdf', :texto, 'TEXTO', 'config.editar')").bindparams(texto=TEXTO_IMO))


def downgrade() -> None:
    op.execute("DELETE FROM configuracion WHERE clave = 'condiciones_imo_pdf'")
    op.drop_column("linea_cotizacion", "motivo_alternativa")
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
    op.execute("INSERT INTO recargo_servicio (recargo_id, servicio_id) SELECT a.recargo_id, s.id FROM recargo_alcance a "
               "JOIN servicio s ON s.codigo = a.valor_texto JOIN recargo r ON r.id = a.recargo_id "
               "WHERE a.nivel = 'SERVICIO' AND r.modo IS NULL")
    op.execute("ALTER TABLE recargo DROP CONSTRAINT ex_recargo_vigencia_sin_superposicion")
    op.drop_column("recargo", "alcance_firma")
    op.execute(EXCLUSION_ANTES)
    op.drop_index("ix_recargo_alcance_recargo", table_name="recargo_alcance")
    op.execute("DROP INDEX uq_recargo_alcance_valor")
    op.drop_table("recargo_alcance")
    op.drop_column("tarifa", "clases_imo_excluidas")
    op.drop_column("tarifa", "tipos_carga")
    op.drop_constraint("ck_cotizacion_imo_grupo", "cotizacion", type_="check")
    op.drop_constraint("ck_cotizacion_imo_un", "cotizacion", type_="check")
    op.drop_constraint("ck_cotizacion_imo_clase", "cotizacion", type_="check")
    op.drop_constraint("fk_cotizacion_tipo_carga", "cotizacion", type_="foreignkey")
    for columna in ("msds_recibida", "imo_grupo", "imo_un", "imo_clase", "tipo_carga"):
        op.drop_column("cotizacion", columna)
    op.drop_table("tipo_carga")

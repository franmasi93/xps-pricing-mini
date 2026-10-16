"""F4: transportista, kg/lb, recargo sobre el Recibo de Caja, datos de la empresa para el PDF, correo y bitácoras.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14

Migración escrita a mano, con constraints de nombre explícito.
- D1-D4: tarifa.transportista y unidad_peso; cotizacion.transportista, unidad_peso, peso_lb (lo capturado en
  libras, H-F4-1) y descripcion_carga; linea_cotizacion.unidad_peso; unidad PCT_RECIBO en recargos y líneas;
  tramos en libras (H-F4-2: 0, 100, 220, 660, 1100, 2200). Las filas existentes quedan en KG sin cambios.
- A4: config_empresa, una sola fila con los 14 datos vacíos (los edita config.editar; H-F4-8, H-F4-17).
- B2: config_correo (una sola fila) con los valores iniciales; las llaves vacías.
- B7: envio_correo y envio_correo_prueba, solo inserción (trigger que rechaza UPDATE y DELETE).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UNIDADES_F3 = "'KG', 'CBM', 'WM', 'CONTENEDOR', 'ENVIO', 'PCT_VALOR'"
UNIDADES = "'KG', 'CBM', 'WM', 'CONTENEDOR', 'ENVIO', 'PCT_VALOR', 'PCT_RECIBO'"
DESDE_F2 = "0, 45, 100, 300, 500, 1000"
DESDE = "0, 45, 100, 220, 300, 500, 660, 1000, 1100, 2200"

CLAVES_EMPRESA = (
    "empresa_departamento",
    "empresa_ciudad",
    "empresa_telefono",
    "empresa_celular",
    "empresa_whatsapp",
    "empresa_horario",
    "empresa_direccion_matriz",
    "pago_banco",
    "pago_titular",
    "pago_tipo_cuenta",
    "pago_numero_cuenta",
    "pago_ruc",
    "clausula_fundamental",
    "texto_legal_pie",
)


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _columnas_envio() -> list:
    """Columnas comunes de las dos bitácoras de correo."""
    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("destinatario", sa.String(254), nullable=False),
        sa.Column("asunto", sa.String(300), nullable=False),
        sa.Column("adjunto_nombre", sa.String(120), nullable=False),
        sa.Column("adjunto_bytes", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(8), nullable=False),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("codigo_error", sa.String(60), nullable=True),
        sa.Column("reintentable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("respuesta_proveedor", sa.Text(), nullable=True),
        sa.Column("enviado_por", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
    ]


def _checks_envio(tabla: str) -> list:
    return [
        sa.CheckConstraint("estado IN ('ENVIADO', 'FALLIDO')", name=f"ck_{tabla}_estado"),
        sa.CheckConstraint("estado <> 'ENVIADO' OR message_id IS NOT NULL", name=f"ck_{tabla}_enviado_con_message_id"),
        sa.CheckConstraint("estado <> 'FALLIDO' OR codigo_error IS NOT NULL", name=f"ck_{tabla}_fallido_con_codigo"),
        sa.CheckConstraint("adjunto_bytes >= 0", name=f"ck_{tabla}_adjunto_bytes_no_negativo"),
        sa.ForeignKeyConstraint(["enviado_por"], ["usuario.id"], name=f"fk_{tabla}_enviado_por_usuario"),
    ]


def upgrade() -> None:
    # --- D1 / D2: tarifa ---
    op.add_column("tarifa", sa.Column("transportista", sa.Text(), nullable=True))
    op.add_column("tarifa", sa.Column("unidad_peso", sa.String(2), nullable=False, server_default="KG"))
    op.create_check_constraint("ck_tarifa_unidad_peso", "tarifa", "unidad_peso IN ('KG', 'LB')")
    op.create_check_constraint(
        "ck_tarifa_lb_solo_aereo_por_peso", "tarifa", "unidad_peso = 'KG' OR (modo = 'AEREO' AND rate_unit = 'KG')"
    )
    op.drop_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", type_="check")
    op.create_check_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", f"desde_kg IN ({DESDE})")

    # --- D1 / D2 / D4: cotización ---
    op.add_column("cotizacion", sa.Column("transportista", sa.Text(), nullable=True))
    op.add_column("cotizacion", sa.Column("descripcion_carga", sa.Text(), nullable=True))
    op.add_column("cotizacion", sa.Column("unidad_peso", sa.String(2), nullable=False, server_default="KG"))
    op.add_column("cotizacion", sa.Column("peso_lb", sa.Numeric(10, 3), nullable=True))
    op.create_check_constraint("ck_cotizacion_unidad_peso", "cotizacion", "unidad_peso IN ('KG', 'LB')")
    op.create_check_constraint(
        "ck_cotizacion_peso_lb_segun_unidad", "cotizacion", "(unidad_peso = 'LB') = (peso_lb IS NOT NULL)"
    )
    op.create_check_constraint("ck_cotizacion_peso_lb_no_negativo", "cotizacion", "peso_lb IS NULL OR peso_lb >= 0")

    # --- D2 / D3: línea ---
    op.add_column("linea_cotizacion", sa.Column("unidad_peso", sa.String(2), nullable=True))
    op.create_check_constraint(
        "ck_linea_cotizacion_unidad_peso", "linea_cotizacion", "unidad_peso IS NULL OR unidad_peso IN ('KG', 'LB')"
    )
    op.drop_constraint("ck_linea_cotizacion_rate_unit", "linea_cotizacion", type_="check")
    op.create_check_constraint("ck_linea_cotizacion_rate_unit", "linea_cotizacion", f"rate_unit IN ({UNIDADES})")

    # --- D3: recargo porcentual sobre el Recibo de Caja ---
    op.drop_constraint("ck_recargo_rate_unit", "recargo", type_="check")
    op.create_check_constraint("ck_recargo_rate_unit", "recargo", f"rate_unit IN ({UNIDADES})")
    op.create_check_constraint(
        "ck_recargo_pct_recibo_no_seguro", "recargo", "rate_unit <> 'PCT_RECIBO' OR bloque_incoterm <> 'SEGURO'"
    )

    # --- A4: datos de la empresa para el PDF (una sola fila, vacíos; los edita config.editar; H-F4-17) ---
    op.create_table(
        "config_empresa",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        *[sa.Column(clave, sa.Text(), nullable=False, server_default="") for clave in CLAVES_EMPRESA],
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_config_empresa"),
        sa.CheckConstraint("id = 1", name="ck_config_empresa_una_sola_fila"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_empresa_actualizado_por_usuario"),
    )
    op.execute("INSERT INTO config_empresa (id) VALUES (1)")

    # --- B2: configuración del correo (una sola fila) ---
    op.create_table(
        "config_correo",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("habilitado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("region", sa.String(40), nullable=False),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("remitente", sa.String(300), nullable=False),
        sa.Column("reply_to", sa.String(254), nullable=False),
        sa.Column("bcc", sa.String(254), nullable=True),
        sa.Column("plantilla_cotizacion_id", sa.BigInteger(), nullable=False),
        sa.Column("timeout_s", sa.SmallInteger(), nullable=False),
        sa.Column("adjunto_max_bytes", sa.Integer(), nullable=False),
        sa.Column("secret_id_cifrado", sa.Text(), nullable=True),
        sa.Column("secret_key_cifrado", sa.Text(), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_config_correo"),
        sa.CheckConstraint("id = 1", name="ck_config_correo_una_sola_fila"),
        sa.CheckConstraint("timeout_s BETWEEN 5 AND 120", name="ck_config_correo_timeout"),
        sa.CheckConstraint("adjunto_max_bytes BETWEEN 1 AND 10000000", name="ck_config_correo_adjunto_max"),
        sa.CheckConstraint("plantilla_cotizacion_id > 0", name="ck_config_correo_plantilla_positiva"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_correo_actualizado_por_usuario"),
    )
    op.execute(
        sa.text(
            "INSERT INTO config_correo (id, habilitado, region, endpoint, remitente, reply_to, bcc,"
            " plantilla_cotizacion_id, timeout_s, adjunto_max_bytes)"
            " VALUES (1, false, 'ap-singapore', 'ses.intl.tencentcloudapi.com', :remitente,"
            " 'pricing@xpress.ec', 'pricing@xpress.ec', 72669, 30, 2500000)"
        ).bindparams(remitente="Xpress - Tarifas <pricing@notificaciones.xpress.ec>")
    )

    # --- B7: bitácoras de envío (solo inserción) ---
    op.create_table(
        "envio_correo",
        *_columnas_envio(),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("cc", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bcc", sa.String(254), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_envio_correo"),
        *_checks_envio("envio_correo"),
        sa.ForeignKeyConstraint(
            ["cotizacion_id"], ["cotizacion.id"], name="fk_envio_correo_cotizacion_id_cotizacion", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_envio_correo_cotizacion_id", "envio_correo", ["cotizacion_id"])
    op.create_table(
        "envio_correo_prueba",
        *_columnas_envio(),
        sa.PrimaryKeyConstraint("id", name="pk_envio_correo_prueba"),
        *_checks_envio("envio_correo_prueba"),
    )
    op.execute(
        "CREATE FUNCTION fn_bitacora_solo_insercion() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN RAISE EXCEPTION 'La bitácora % es de solo inserción', TG_TABLE_NAME; END; $$"
    )
    for tabla in ("envio_correo", "envio_correo_prueba"):
        op.execute(
            f"CREATE TRIGGER tg_{tabla}_solo_insercion BEFORE UPDATE OR DELETE ON {tabla}"
            " FOR EACH ROW EXECUTE FUNCTION fn_bitacora_solo_insercion()"
        )


def downgrade() -> None:
    for tabla in ("envio_correo", "envio_correo_prueba"):
        op.execute(f"DROP TRIGGER tg_{tabla}_solo_insercion ON {tabla}")
    op.execute("DROP FUNCTION fn_bitacora_solo_insercion()")
    op.drop_table("envio_correo_prueba")
    op.drop_index("ix_envio_correo_cotizacion_id", table_name="envio_correo")
    op.drop_table("envio_correo")
    op.drop_table("config_correo")
    op.drop_table("config_empresa")
    op.drop_constraint("ck_recargo_pct_recibo_no_seguro", "recargo", type_="check")
    op.drop_constraint("ck_recargo_rate_unit", "recargo", type_="check")
    op.create_check_constraint("ck_recargo_rate_unit", "recargo", f"rate_unit IN ({UNIDADES_F3})")
    op.drop_constraint("ck_linea_cotizacion_rate_unit", "linea_cotizacion", type_="check")
    op.create_check_constraint("ck_linea_cotizacion_rate_unit", "linea_cotizacion", f"rate_unit IN ({UNIDADES_F3})")
    op.drop_constraint("ck_linea_cotizacion_unidad_peso", "linea_cotizacion", type_="check")
    op.drop_column("linea_cotizacion", "unidad_peso")
    for nombre in ("ck_cotizacion_peso_lb_no_negativo", "ck_cotizacion_peso_lb_segun_unidad", "ck_cotizacion_unidad_peso"):
        op.drop_constraint(nombre, "cotizacion", type_="check")
    for columna in ("peso_lb", "unidad_peso", "descripcion_carga", "transportista"):
        op.drop_column("cotizacion", columna)
    op.drop_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", type_="check")
    op.create_check_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", f"desde_kg IN ({DESDE_F2})")
    op.drop_constraint("ck_tarifa_lb_solo_aereo_por_peso", "tarifa", type_="check")
    op.drop_constraint("ck_tarifa_unidad_peso", "tarifa", type_="check")
    op.drop_column("tarifa", "unidad_peso")
    op.drop_column("tarifa", "transportista")

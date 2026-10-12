"""F3: contador anual, cotizaciones, contenedores y líneas; seguro como % del valor (PCT_VALOR).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07

Migración escrita a mano. Sin seed de negocio. H2: si las condiciones del PDF siguen con el texto
provisional sembrado en 0002, quedan vacías (emitir exige cargarlas); el downgrade lo restaura.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

MODOS = "'AEREO', 'LCL', 'FCL'"
ESTADOS = "'BORRADOR', 'EMITIDA', 'ENVIADA', 'ACEPTADA', 'RECHAZADA'"
MOTIVOS_RECHAZO = "'PRECIO', 'TIEMPO', 'COMPETENCIA', 'OTRO'"
BLOQUES_LINEA = (
    "'RECOGIDA_ORIGEN', 'DESPACHO_EXPORT', 'GASTOS_ORIGEN', 'FLETE_PRINCIPAL', 'SEGURO', "
    "'GASTOS_DESTINO', 'DESPACHO_IMPORT', 'ENTREGA_FINAL'"
)
UNIDADES_RECARGO_F2 = "'KG', 'CBM', 'WM', 'CONTENEDOR', 'ENVIO'"
UNIDADES = "'KG', 'CBM', 'WM', 'CONTENEDOR', 'ENVIO', 'PCT_VALOR'"
CONDICIONES_PROVISIONALES = "Pendiente de definir (P5)."


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    # --- Contador anual de numeración (D-F3-1: SELECT … FOR UPDATE al emitir) ---
    op.create_table(
        "contador_cotizacion",
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("ultimo", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("anio", name="pk_contador_cotizacion"),
        sa.CheckConstraint("anio BETWEEN 2000 AND 9999", name="ck_contador_cotizacion_anio"),
        sa.CheckConstraint("ultimo >= 0", name="ck_contador_cotizacion_ultimo_no_negativo"),
    )

    # --- Cotización ---
    op.create_table(
        "cotizacion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("numero", sa.String(20), nullable=True),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("contacto_id", sa.Integer(), nullable=True),
        sa.Column("comercial_id", sa.Integer(), nullable=False),
        sa.Column("sentido", sa.String(11), nullable=False),
        sa.Column("incoterm_id", sa.Integer(), nullable=False),
        sa.Column("modo", sa.String(5), nullable=False),
        sa.Column("origen_puerto_id", sa.Integer(), nullable=False),
        sa.Column("destino_puerto_id", sa.Integer(), nullable=False),
        sa.Column("proveedor_recargos_id", sa.Integer(), nullable=True),
        # Carga
        sa.Column("peso_kg", sa.Numeric(10, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("cbm", sa.Numeric(10, 4), nullable=True),
        sa.Column("bultos", sa.Integer(), nullable=True),
        sa.Column("dimensiones", JSONB(), nullable=True),
        sa.Column("valor_mercancia_usd", sa.Numeric(14, 2), nullable=True),
        # Estado y fechas
        sa.Column("estado", sa.String(9), nullable=False, server_default=sa.text("'BORRADOR'")),
        sa.Column("fecha_emision", sa.Date(), nullable=True),
        sa.Column("valida_hasta", sa.Date(), nullable=True),
        sa.Column("moneda_cotizacion", sa.String(3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("notas_cliente", sa.Text(), nullable=True),
        sa.Column("notas_internas", sa.Text(), nullable=True),
        # Totales congelados al emitir
        sa.Column("subtotal_recibo_caja", sa.Numeric(14, 2), nullable=True),
        sa.Column("subtotal_factura", sa.Numeric(14, 2), nullable=True),
        sa.Column("iva", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_general", sa.Numeric(14, 2), nullable=True),
        sa.Column("costo_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("margen_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("margen_pct", sa.Numeric(7, 2), nullable=True),
        sa.Column("iva_tasa_aplicada", sa.Numeric(5, 2), nullable=True),
        sa.Column("snapshot_emision", JSONB(), nullable=True),
        # Rechazo
        sa.Column("motivo_rechazo", sa.String(11), nullable=True),
        sa.Column("detalle_rechazo", sa.Text(), nullable=True),
        sa.Column("cotizacion_origen_id", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_cotizacion"),
        sa.UniqueConstraint("numero", name="uq_cotizacion_numero"),
        sa.CheckConstraint(f"estado IN ({ESTADOS})", name="ck_cotizacion_estado"),
        sa.CheckConstraint("sentido IN ('IMPORTACION', 'EXPORTACION')", name="ck_cotizacion_sentido"),
        sa.CheckConstraint(f"modo IN ({MODOS})", name="ck_cotizacion_modo"),
        sa.CheckConstraint("origen_puerto_id <> destino_puerto_id", name="ck_cotizacion_origen_distinto_destino"),
        sa.CheckConstraint("moneda_cotizacion = 'USD'", name="ck_cotizacion_moneda_usd"),
        sa.CheckConstraint(
            "numero IS NULL OR numero ~ '^[A-Z]{2,10}-[0-9]{4}-[0-9]{5}$'", name="ck_cotizacion_numero_formato"
        ),
        sa.CheckConstraint("estado = 'BORRADOR' OR numero IS NOT NULL", name="ck_cotizacion_numero_si_emitida"),
        sa.CheckConstraint(
            "estado = 'BORRADOR' OR (contacto_id IS NOT NULL AND fecha_emision IS NOT NULL AND valida_hasta IS NOT NULL"
            " AND total_general IS NOT NULL AND iva_tasa_aplicada IS NOT NULL AND snapshot_emision IS NOT NULL)",
            name="ck_cotizacion_congelada_si_emitida",
        ),
        sa.CheckConstraint(
            "valida_hasta IS NULL OR fecha_emision IS NULL OR valida_hasta >= fecha_emision",
            name="ck_cotizacion_validez_ordenada",
        ),
        sa.CheckConstraint(
            f"motivo_rechazo IS NULL OR motivo_rechazo IN ({MOTIVOS_RECHAZO})", name="ck_cotizacion_motivo_rechazo"
        ),
        sa.CheckConstraint(
            "estado <> 'RECHAZADA' OR motivo_rechazo IS NOT NULL", name="ck_cotizacion_rechazo_con_motivo"
        ),
        sa.CheckConstraint(
            "motivo_rechazo IS DISTINCT FROM 'OTRO'"
            " OR (detalle_rechazo IS NOT NULL AND btrim(detalle_rechazo) <> '')",
            name="ck_cotizacion_detalle_si_otro",
        ),
        sa.CheckConstraint("peso_kg >= 0", name="ck_cotizacion_peso_no_negativo"),
        sa.CheckConstraint("cbm IS NULL OR cbm >= 0", name="ck_cotizacion_cbm_no_negativo"),
        sa.CheckConstraint("bultos IS NULL OR bultos >= 0", name="ck_cotizacion_bultos_no_negativo"),
        sa.CheckConstraint(
            "valor_mercancia_usd IS NULL OR valor_mercancia_usd >= 0", name="ck_cotizacion_valor_no_negativo"
        ),
        sa.CheckConstraint("activo OR estado = 'BORRADOR'", name="ck_cotizacion_descartar_solo_borrador"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["cliente.id"], name="fk_cotizacion_cliente_id_cliente", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["contacto_id"], ["contacto_cliente.id"], name="fk_cotizacion_contacto_id_contacto_cliente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["comercial_id"], ["usuario.id"], name="fk_cotizacion_comercial_id_usuario", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["incoterm_id"], ["incoterm.id"], name="fk_cotizacion_incoterm_id_incoterm", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["origen_puerto_id"], ["puerto.id"], name="fk_cotizacion_origen_puerto_id_puerto", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destino_puerto_id"], ["puerto.id"], name="fk_cotizacion_destino_puerto_id_puerto", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_recargos_id"], ["proveedor.id"], name="fk_cotizacion_proveedor_recargos_id_proveedor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cotizacion_origen_id"], ["cotizacion.id"], name="fk_cotizacion_cotizacion_origen_id_cotizacion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_cotizacion_creado_por_usuario"),
    )
    op.create_index("ix_cotizacion_comercial_estado", "cotizacion", ["comercial_id", "estado"])
    op.create_index("ix_cotizacion_cliente_id", "cotizacion", ["cliente_id"])
    op.create_index("ix_cotizacion_estado_valida_hasta", "cotizacion", ["estado", "valida_hasta"])

    # --- Contenedores (FCL) ---
    op.create_table(
        "cotizacion_contenedor",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("tipo_equipo_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cotizacion_contenedor"),
        sa.UniqueConstraint("cotizacion_id", "tipo_equipo_id", name="uq_cotizacion_contenedor_cotizacion_tipo"),
        sa.CheckConstraint("cantidad > 0", name="ck_cotizacion_contenedor_cantidad_positiva"),
        sa.ForeignKeyConstraint(
            ["cotizacion_id"], ["cotizacion.id"], name="fk_cotizacion_contenedor_cotizacion_id_cotizacion",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tipo_equipo_id"], ["tipo_equipo.id"], name="fk_cotizacion_contenedor_tipo_equipo_id_tipo_equipo",
            ondelete="RESTRICT",
        ),
    )

    # --- Líneas ---
    op.create_table(
        "linea_cotizacion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("concepto", sa.String(160), nullable=False),
        sa.Column("bloque_incoterm", sa.String(20), nullable=False),
        sa.Column("tarifa_id", sa.Integer(), nullable=True),
        sa.Column("recargo_id", sa.Integer(), nullable=True),
        sa.Column("proveedor_id", sa.Integer(), nullable=True),
        sa.Column("tipo_equipo_id", sa.Integer(), nullable=True),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False),
        sa.Column("rate_unit", sa.String(10), nullable=False),
        # Costo
        sa.Column("costo_unit_original", sa.Numeric(14, 4), nullable=False),
        sa.Column("minimo_original", sa.Numeric(14, 4), nullable=False),
        sa.Column("moneda_original_id", sa.Integer(), nullable=False),
        sa.Column("tasa_aplicada", sa.Numeric(14, 6), nullable=False),
        sa.Column("costo_usd", sa.Numeric(14, 4), nullable=False),
        # Venta
        sa.Column("precio_venta_unit_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("minimo_venta_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("subtotal_venta_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("precio_calculado_unit_usd", sa.Numeric(14, 4), nullable=False),
        # Fiscal
        sa.Column("bloque_fiscal", sa.String(11), nullable=False),
        sa.Column("aplica_iva", sa.Boolean(), nullable=False),
        sa.Column("rol_ingreso", sa.String(9), nullable=False),
        # Control
        sa.Column("opcional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("incluida", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ajuste_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("motivo_ajuste", sa.String(300), nullable=True),
        sa.Column("valido_hasta_origen", sa.Date(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_linea_cotizacion"),
        sa.UniqueConstraint("cotizacion_id", "orden", name="uq_linea_cotizacion_cotizacion_orden"),
        sa.CheckConstraint(
            "(tarifa_id IS NULL) <> (recargo_id IS NULL)", name="ck_linea_cotizacion_tarifa_xor_recargo"
        ),
        sa.CheckConstraint(f"bloque_incoterm IN ({BLOQUES_LINEA})", name="ck_linea_cotizacion_bloque"),
        sa.CheckConstraint(
            "(bloque_incoterm = 'FLETE_PRINCIPAL') = (tarifa_id IS NOT NULL)", name="ck_linea_cotizacion_flete_es_tarifa"
        ),
        sa.CheckConstraint(f"rate_unit IN ({UNIDADES})", name="ck_linea_cotizacion_rate_unit"),
        sa.CheckConstraint("bloque_fiscal IN ('RECIBO_CAJA', 'FACTURA')", name="ck_linea_cotizacion_bloque_fiscal"),
        sa.CheckConstraint("rol_ingreso IN ('PRINCIPAL', 'AGENTE')", name="ck_linea_cotizacion_rol_ingreso"),
        sa.CheckConstraint("cantidad >= 0", name="ck_linea_cotizacion_cantidad_no_negativa"),
        sa.CheckConstraint(
            "costo_unit_original >= 0 AND minimo_original >= 0 AND costo_usd >= 0",
            name="ck_linea_cotizacion_costos_no_negativos",
        ),
        sa.CheckConstraint(
            "precio_venta_unit_usd >= 0 AND minimo_venta_usd >= 0 AND subtotal_venta_usd >= 0"
            " AND precio_calculado_unit_usd >= 0",
            name="ck_linea_cotizacion_ventas_no_negativas",
        ),
        sa.CheckConstraint("tasa_aplicada > 0", name="ck_linea_cotizacion_tasa_positiva"),
        sa.CheckConstraint("opcional OR incluida", name="ck_linea_cotizacion_obligatoria_incluida"),
        sa.CheckConstraint(
            "ajuste_manual = (motivo_ajuste IS NOT NULL)", name="ck_linea_cotizacion_ajuste_con_motivo"
        ),
        sa.ForeignKeyConstraint(
            ["cotizacion_id"], ["cotizacion.id"], name="fk_linea_cotizacion_cotizacion_id_cotizacion",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tarifa_id"], ["tarifa.id"], name="fk_linea_cotizacion_tarifa_id_tarifa", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recargo_id"], ["recargo.id"], name="fk_linea_cotizacion_recargo_id_recargo", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["proveedor.id"], name="fk_linea_cotizacion_proveedor_id_proveedor", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tipo_equipo_id"], ["tipo_equipo.id"], name="fk_linea_cotizacion_tipo_equipo_id_tipo_equipo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["moneda_original_id"], ["moneda.id"], name="fk_linea_cotizacion_moneda_original_id_moneda",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_linea_cotizacion_cotizacion_id", "linea_cotizacion", ["cotizacion_id"])

    # --- Recargo: seguro como % del valor de la mercancía (D-F3-3, P11) ---
    op.drop_constraint("ck_recargo_rate_unit", "recargo", type_="check")
    op.drop_constraint("ck_recargo_seguro_por_envio", "recargo", type_="check")
    op.create_check_constraint("ck_recargo_rate_unit", "recargo", f"rate_unit IN ({UNIDADES})")
    op.create_check_constraint(
        "ck_recargo_seguro_unidad", "recargo", "bloque_incoterm <> 'SEGURO' OR rate_unit IN ('ENVIO', 'PCT_VALOR')"
    )
    op.create_check_constraint(
        "ck_recargo_pct_valor_solo_seguro", "recargo", "rate_unit <> 'PCT_VALOR' OR bloque_incoterm = 'SEGURO'"
    )

    # --- H2: condiciones provisionales → vacías (emitir exige cargarlas) ---
    op.execute(
        sa.text("UPDATE configuracion SET valor = '' WHERE clave = 'condiciones_generales_pdf' AND valor = :provisional")
        .bindparams(provisional=CONDICIONES_PROVISIONALES)
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE configuracion SET valor = :provisional WHERE clave = 'condiciones_generales_pdf' AND valor = ''")
        .bindparams(provisional=CONDICIONES_PROVISIONALES)
    )
    op.drop_constraint("ck_recargo_pct_valor_solo_seguro", "recargo", type_="check")
    op.drop_constraint("ck_recargo_seguro_unidad", "recargo", type_="check")
    op.drop_constraint("ck_recargo_rate_unit", "recargo", type_="check")
    op.create_check_constraint("ck_recargo_rate_unit", "recargo", f"rate_unit IN ({UNIDADES_RECARGO_F2})")
    op.create_check_constraint(
        "ck_recargo_seguro_por_envio", "recargo", "bloque_incoterm <> 'SEGURO' OR rate_unit = 'ENVIO'"
    )
    op.drop_index("ix_linea_cotizacion_cotizacion_id", table_name="linea_cotizacion")
    op.drop_table("linea_cotizacion")
    op.drop_table("cotizacion_contenedor")
    op.drop_index("ix_cotizacion_estado_valida_hasta", table_name="cotizacion")
    op.drop_index("ix_cotizacion_cliente_id", table_name="cotizacion")
    op.drop_index("ix_cotizacion_comercial_estado", table_name="cotizacion")
    op.drop_table("cotizacion")
    op.drop_table("contador_cotizacion")

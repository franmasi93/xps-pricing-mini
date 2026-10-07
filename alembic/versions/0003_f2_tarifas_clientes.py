"""F2: tipos de equipo, tarifas, tramos aéreos, recargos, clientes y contactos.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03

Migración escrita a mano. Siembra solo los 5 tipos de equipo (§15.6).
No superposición de vigencias (D-F2-1): EXCLUDE con btree_gist sobre las filas activas,
rango cerrado '[]' y COALESCE en las columnas nulas (en un EXCLUDE dos NULL nunca son iguales).
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TIPOS_EQUIPO = [
    ("20GP", "Contenedor 20' estándar"),
    ("40GP", "Contenedor 40' estándar"),
    ("40HC", "Contenedor 40' High Cube"),
    ("20RF", "Contenedor 20' refrigerado"),
    ("40RF", "Contenedor 40' refrigerado"),
]

MODOS = "'AEREO', 'LCL', 'FCL'"
METODOS_VENTA = "'MANUAL', 'MARKUP', 'MARGEN', 'FIJO'"
BLOQUES_RECARGO = (
    "'RECOGIDA_ORIGEN', 'DESPACHO_EXPORT', 'GASTOS_ORIGEN', 'SEGURO', "
    "'GASTOS_DESTINO', 'DESPACHO_IMPORT', 'ENTREGA_FINAL'"
)


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _columnas_catalogo(tabla: str) -> list:
    """activo, creado_en, actualizado_en y creado_por, igual que en 0002."""
    return [
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name=f"fk_{tabla}_creado_por_usuario"),
    ]


def _columnas_venta() -> list:
    """Costo, mínimo y esquema de venta (§7 M5, D-F2-3), comunes a tarifa y recargo."""
    return [
        sa.Column("costo", sa.Numeric(14, 4), nullable=False),
        sa.Column("moneda_id", sa.Integer(), nullable=False),
        sa.Column("minimo", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("metodo_venta", sa.String(7), nullable=False),
        sa.Column("parametro_venta", sa.Numeric(10, 4), nullable=True),
        sa.Column("precio_venta_manual", sa.Numeric(14, 4), nullable=True),
        sa.Column("minimo_venta_manual", sa.Numeric(14, 4), nullable=True),
        sa.Column("valido_desde", sa.Date(), nullable=False),
        sa.Column("valido_hasta", sa.Date(), nullable=False),
    ]


def _checks_venta(tabla: str) -> list:
    # Cada comparación lleva IS NOT NULL: un CHECK con resultado NULL se da por cumplido.
    return [
        sa.CheckConstraint("costo > 0", name=f"ck_{tabla}_costo_positivo"),
        sa.CheckConstraint("minimo >= 0", name=f"ck_{tabla}_minimo_no_negativo"),
        sa.CheckConstraint(f"metodo_venta IN ({METODOS_VENTA})", name=f"ck_{tabla}_metodo_venta"),
        sa.CheckConstraint(
            "(metodo_venta = 'MANUAL'"
            " AND parametro_venta IS NULL"
            " AND precio_venta_manual IS NOT NULL AND precio_venta_manual > 0"
            " AND (minimo = 0 OR minimo_venta_manual IS NOT NULL)"
            " AND (minimo_venta_manual IS NULL OR minimo_venta_manual >= 0))"
            " OR (metodo_venta <> 'MANUAL'"
            " AND parametro_venta IS NOT NULL AND parametro_venta >= 0"
            " AND precio_venta_manual IS NULL AND minimo_venta_manual IS NULL)",
            name=f"ck_{tabla}_esquema_venta",
        ),
        sa.CheckConstraint(
            "metodo_venta <> 'MARGEN' OR parametro_venta < 100", name=f"ck_{tabla}_margen_menor_100"
        ),
        sa.CheckConstraint("valido_hasta >= valido_desde", name=f"ck_{tabla}_vigencia_ordenada"),
        sa.ForeignKeyConstraint(
            ["moneda_id"], ["moneda.id"], name=f"fk_{tabla}_moneda_id_moneda", ondelete="RESTRICT"
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # --- Tipos de equipo (FCL) ---
    op.create_table(
        "tipo_equipo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        *_columnas_catalogo("tipo_equipo"),
        sa.PrimaryKeyConstraint("id", name="pk_tipo_equipo"),
        sa.UniqueConstraint("codigo", name="uq_tipo_equipo_codigo"),
        sa.CheckConstraint("codigo ~ '^[0-9]{2}[A-Z]{2}$'", name="ck_tipo_equipo_codigo_formato"),
    )

    # --- Tarifas ---
    op.create_table(
        "tarifa",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("proveedor_id", sa.Integer(), nullable=False),
        sa.Column("modo", sa.String(5), nullable=False),
        sa.Column("origen_puerto_id", sa.Integer(), nullable=False),
        sa.Column("destino_puerto_id", sa.Integer(), nullable=False),
        sa.Column("tipo_equipo_id", sa.Integer(), nullable=True),
        sa.Column("rate_unit", sa.String(10), nullable=False),
        *_columnas_venta(),
        sa.Column("transit_time_dias", sa.SmallInteger(), nullable=True),
        sa.Column("dias_libres", sa.SmallInteger(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        *_columnas_catalogo("tarifa"),
        sa.PrimaryKeyConstraint("id", name="pk_tarifa"),
        sa.CheckConstraint(f"modo IN ({MODOS})", name="ck_tarifa_modo"),
        sa.CheckConstraint("origen_puerto_id <> destino_puerto_id", name="ck_tarifa_origen_distinto_destino"),
        sa.CheckConstraint("(modo = 'FCL') = (tipo_equipo_id IS NOT NULL)", name="ck_tarifa_tipo_equipo_segun_modo"),
        sa.CheckConstraint(
            "(modo = 'AEREO' AND rate_unit IN ('KG', 'ENVIO'))"
            " OR (modo = 'LCL' AND rate_unit IN ('WM', 'CBM', 'ENVIO'))"
            " OR (modo = 'FCL' AND rate_unit = 'CONTENEDOR')",
            name="ck_tarifa_rate_unit_segun_modo",
        ),
        sa.CheckConstraint(
            "transit_time_dias IS NULL OR transit_time_dias >= 0", name="ck_tarifa_transit_time_no_negativo"
        ),
        sa.CheckConstraint("dias_libres IS NULL OR dias_libres >= 0", name="ck_tarifa_dias_libres_no_negativo"),
        *_checks_venta("tarifa"),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["proveedor.id"], name="fk_tarifa_proveedor_id_proveedor", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["origen_puerto_id"], ["puerto.id"], name="fk_tarifa_origen_puerto_id_puerto", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destino_puerto_id"], ["puerto.id"], name="fk_tarifa_destino_puerto_id_puerto", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tipo_equipo_id"], ["tipo_equipo.id"], name="fk_tarifa_tipo_equipo_id_tipo_equipo", ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_tarifa_busqueda",
        "tarifa",
        ["proveedor_id", "modo", "origen_puerto_id", "destino_puerto_id", "tipo_equipo_id", "valido_desde"],
    )
    op.create_index(
        "ix_tarifa_ruta_vigencia", "tarifa", ["origen_puerto_id", "destino_puerto_id", "modo", "valido_hasta"]
    )
    op.execute(
        "ALTER TABLE tarifa ADD CONSTRAINT ex_tarifa_vigencia_sin_superposicion EXCLUDE USING gist ("
        " proveedor_id WITH =,"
        " modo WITH =,"
        " origen_puerto_id WITH =,"
        " destino_puerto_id WITH =,"
        " (COALESCE(tipo_equipo_id, 0)) WITH =,"
        " daterange(valido_desde, valido_hasta, '[]') WITH &&"
        ") WHERE (activo)"
    )

    # --- Tramos aéreos (se auditan dentro de la tarifa) ---
    op.create_table(
        "tramo_aereo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("tarifa_id", sa.Integer(), nullable=False),
        sa.Column("desde_kg", sa.SmallInteger(), nullable=False),
        sa.Column("costo_kg", sa.Numeric(14, 4), nullable=False),
        sa.Column("precio_venta_kg", sa.Numeric(14, 4), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_tramo_aereo"),
        sa.UniqueConstraint("tarifa_id", "desde_kg", name="uq_tramo_aereo_tarifa_desde"),
        sa.CheckConstraint("desde_kg IN (0, 45, 100, 300, 500, 1000)", name="ck_tramo_aereo_desde_kg_permitido"),
        sa.CheckConstraint("costo_kg > 0", name="ck_tramo_aereo_costo_positivo"),
        sa.CheckConstraint(
            "precio_venta_kg IS NULL OR precio_venta_kg > 0", name="ck_tramo_aereo_precio_venta_positivo"
        ),
        sa.ForeignKeyConstraint(
            ["tarifa_id"], ["tarifa.id"], name="fk_tramo_aereo_tarifa_id_tarifa", ondelete="RESTRICT"
        ),
    )

    # --- Recargos ---
    op.create_table(
        "recargo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("proveedor_id", sa.Integer(), nullable=True),
        sa.Column("puerto_id", sa.Integer(), nullable=False),
        sa.Column("lado", sa.String(7), nullable=False),
        sa.Column("bloque_incoterm", sa.String(20), nullable=False),
        sa.Column("concepto", sa.String(120), nullable=False),
        sa.Column("modo", sa.String(5), nullable=True),
        sa.Column("tipo_equipo_id", sa.Integer(), nullable=True),
        sa.Column("rate_unit", sa.String(10), nullable=False),
        *_columnas_venta(),
        sa.Column("aplica_iva", sa.Boolean(), nullable=False),
        sa.Column("rol_ingreso", sa.String(9), nullable=False),
        *_columnas_catalogo("recargo"),
        sa.PrimaryKeyConstraint("id", name="pk_recargo"),
        sa.CheckConstraint("lado IN ('ORIGEN', 'DESTINO')", name="ck_recargo_lado"),
        sa.CheckConstraint(f"bloque_incoterm IN ({BLOQUES_RECARGO})", name="ck_recargo_bloque"),
        sa.CheckConstraint(
            "bloque_incoterm = 'SEGURO'"
            " OR (lado = 'ORIGEN' AND bloque_incoterm IN ('RECOGIDA_ORIGEN', 'DESPACHO_EXPORT', 'GASTOS_ORIGEN'))"
            " OR (lado = 'DESTINO' AND bloque_incoterm IN ('GASTOS_DESTINO', 'DESPACHO_IMPORT', 'ENTREGA_FINAL'))",
            name="ck_recargo_lado_bloque",
        ),
        sa.CheckConstraint("concepto = btrim(concepto) AND concepto <> ''", name="ck_recargo_concepto_normalizado"),
        sa.CheckConstraint(f"modo IS NULL OR modo IN ({MODOS})", name="ck_recargo_modo"),
        sa.CheckConstraint(
            "tipo_equipo_id IS NULL OR modo IS NOT DISTINCT FROM 'FCL'", name="ck_recargo_tipo_equipo_solo_fcl"
        ),
        sa.CheckConstraint(
            "rate_unit IN ('KG', 'CBM', 'WM', 'CONTENEDOR', 'ENVIO')", name="ck_recargo_rate_unit"
        ),
        sa.CheckConstraint(
            "rate_unit <> 'CONTENEDOR' OR modo IS NOT DISTINCT FROM 'FCL'", name="ck_recargo_contenedor_solo_fcl"
        ),
        sa.CheckConstraint(
            "bloque_incoterm <> 'SEGURO' OR rate_unit = 'ENVIO'", name="ck_recargo_seguro_por_envio"
        ),
        sa.CheckConstraint("rol_ingreso IN ('PRINCIPAL', 'AGENTE')", name="ck_recargo_rol_ingreso"),
        *_checks_venta("recargo"),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["proveedor.id"], name="fk_recargo_proveedor_id_proveedor", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["puerto_id"], ["puerto.id"], name="fk_recargo_puerto_id_puerto", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tipo_equipo_id"], ["tipo_equipo.id"], name="fk_recargo_tipo_equipo_id_tipo_equipo", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_recargo_puerto_lado_bloque", "recargo", ["puerto_id", "lado", "bloque_incoterm"])
    op.execute(
        "ALTER TABLE recargo ADD CONSTRAINT ex_recargo_vigencia_sin_superposicion EXCLUDE USING gist ("
        " (COALESCE(proveedor_id, 0)) WITH =,"
        " puerto_id WITH =,"
        " lado WITH =,"
        " bloque_incoterm WITH =,"
        " (lower(concepto)) WITH =,"
        " (COALESCE(modo, '')) WITH =,"
        " (COALESCE(tipo_equipo_id, 0)) WITH =,"
        " daterange(valido_desde, valido_hasta, '[]') WITH &&"
        ") WHERE (activo)"
    )

    # --- Clientes (M6) ---
    op.create_table(
        "cliente",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("razon_social", sa.String(200), nullable=False),
        sa.Column("tipo_id", sa.String(10), nullable=False),
        sa.Column("ruc_o_id", sa.String(30), nullable=False),
        sa.Column("pais_id", sa.Integer(), nullable=False),
        sa.Column("direccion", sa.String(250), nullable=True),
        sa.Column("ciudad", sa.String(100), nullable=True),
        sa.Column("telefono", sa.String(40), nullable=True),
        sa.Column("comercial_asignado_id", sa.Integer(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        *_columnas_catalogo("cliente"),
        sa.PrimaryKeyConstraint("id", name="pk_cliente"),
        sa.UniqueConstraint("tipo_id", "ruc_o_id", name="uq_cliente_tipo_identificacion"),
        sa.CheckConstraint(
            "tipo_id IN ('RUC', 'CEDULA', 'PASAPORTE', 'EXTRANJERO')", name="ck_cliente_tipo_id"
        ),
        sa.CheckConstraint(
            "(tipo_id = 'RUC' AND ruc_o_id ~ '^[0-9]{10}001$')"
            " OR (tipo_id = 'CEDULA' AND ruc_o_id ~ '^[0-9]{10}$')"
            " OR (tipo_id = 'PASAPORTE' AND ruc_o_id ~ '^[A-Z0-9]{5,20}$')"
            " OR (tipo_id = 'EXTRANJERO' AND ruc_o_id ~ '^[A-Z0-9]{3,30}$')",
            name="ck_cliente_identificacion_formato",
        ),
        sa.CheckConstraint("btrim(razon_social) <> ''", name="ck_cliente_razon_social_no_vacia"),
        sa.ForeignKeyConstraint(["pais_id"], ["pais.id"], name="fk_cliente_pais_id_pais", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["comercial_asignado_id"],
            ["usuario.id"],
            name="fk_cliente_comercial_asignado_id_usuario",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_cliente_comercial_asignado_id", "cliente", ["comercial_asignado_id"])

    op.create_table(
        "contacto_cliente",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("cargo", sa.String(80), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("telefono", sa.String(40), nullable=True),
        sa.Column("principal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_columnas_catalogo("contacto_cliente"),
        sa.PrimaryKeyConstraint("id", name="pk_contacto_cliente"),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(email)", name="ck_contacto_cliente_email_minusculas"
        ),
        sa.CheckConstraint("NOT principal OR activo", name="ck_contacto_cliente_principal_activo"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["cliente.id"], name="fk_contacto_cliente_cliente_id_cliente", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_contacto_cliente_cliente_id", "contacto_cliente", ["cliente_id"])
    # Máximo un contacto principal por cliente (índice parcial único).
    op.create_index(
        "uq_contacto_cliente_principal",
        "contacto_cliente",
        ["cliente_id"],
        unique=True,
        postgresql_where=sa.text("principal"),
    )

    # --- Seed ---
    tabla_tipo_equipo = sa.table("tipo_equipo", sa.column("codigo", sa.String), sa.column("nombre", sa.String))
    op.bulk_insert(tabla_tipo_equipo, [{"codigo": codigo, "nombre": nombre} for codigo, nombre in TIPOS_EQUIPO])


def downgrade() -> None:
    op.drop_index("uq_contacto_cliente_principal", table_name="contacto_cliente")
    op.drop_index("ix_contacto_cliente_cliente_id", table_name="contacto_cliente")
    op.drop_table("contacto_cliente")
    op.drop_index("ix_cliente_comercial_asignado_id", table_name="cliente")
    op.drop_table("cliente")
    op.drop_index("ix_recargo_puerto_lado_bloque", table_name="recargo")
    op.drop_table("recargo")
    op.drop_table("tramo_aereo")
    op.drop_index("ix_tarifa_ruta_vigencia", table_name="tarifa")
    op.drop_index("ix_tarifa_busqueda", table_name="tarifa")
    op.drop_table("tarifa")
    op.drop_table("tipo_equipo")
    # Solo la usan las dos exclusiones de esta migración, ya eliminadas con sus tablas.
    op.execute("DROP EXTENSION IF EXISTS btree_gist")

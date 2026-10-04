"""F1 catálogos: geografía, monedas y tasas, proveedores, Incoterms, configuración y auditoría.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02

Migración escrita a mano. Siembra solo lo permitido por §15.6: la moneda USD,
los Incoterms 2020 (matriz §9.1 tal cual, D-F1-1) y la configuración inicial (§5.2).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

BLOQUES = [
    "recogida_origen",
    "despacho_export",
    "gastos_origen",
    "flete_principal",
    "seguro",
    "gastos_destino",
    "despacho_import",
    "entrega_final",
]

# Importación (§9.1): codigo, nombre, solo_maritimo, 8 bloques en el orden de BLOQUES.
INCOTERMS = [
    ("EXW", "Ex Works", False, (1, 1, 1, 1, 1, 1, 1, 1)),
    ("FCA", "Free Carrier", False, (0, 0, 1, 1, 1, 1, 1, 1)),
    ("FAS", "Free Alongside Ship", True, (0, 0, 1, 1, 1, 1, 1, 1)),
    ("FOB", "Free On Board", True, (0, 0, 0, 1, 1, 1, 1, 1)),
    ("CFR", "Cost and Freight", True, (0, 0, 0, 0, 1, 1, 1, 1)),
    ("CIF", "Cost, Insurance and Freight", True, (0, 0, 0, 0, 0, 1, 1, 1)),
    ("CPT", "Carriage Paid To", False, (0, 0, 0, 0, 1, 1, 1, 1)),
    ("CIP", "Carriage and Insurance Paid To", False, (0, 0, 0, 0, 0, 1, 1, 1)),
    ("DAP", "Delivered At Place", False, (0, 0, 0, 0, 0, 0, 1, 0)),
    ("DPU", "Delivered at Place Unloaded", False, (0, 0, 0, 0, 0, 0, 1, 0)),
    ("DDP", "Delivered Duty Paid", False, (0, 0, 0, 0, 0, 0, 0, 0)),
]

CONFIGURACION = [
    ("iva_tasa", "15.00", "DECIMAL", "config.editar"),
    ("dias_alerta_vencimiento", "7", "ENTERO", "tarifa.editar"),
    ("condiciones_generales_pdf", "Pendiente de definir (P5).", "TEXTO", "config.editar"),
    ("firma_correo", "Pendiente de definir.", "TEXTO", "config.editar"),
]


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _columnas_catalogo(tabla: str) -> list:
    """activo, creado_en, actualizado_en y creado_por (§2.1 del prompt de F1)."""
    return [
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name=f"fk_{tabla}_creado_por_usuario"),
    ]


def upgrade() -> None:
    # --- M2 Geografía ---
    op.create_table(
        "region",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        *_columnas_catalogo("region"),
        sa.PrimaryKeyConstraint("id", name="pk_region"),
        sa.UniqueConstraint("codigo", name="uq_region_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z0-9_]{2,20}$'", name="ck_region_codigo_formato"),
    )

    op.create_table(
        "pais",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("iso2", sa.String(2), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        *_columnas_catalogo("pais"),
        sa.PrimaryKeyConstraint("id", name="pk_pais"),
        sa.UniqueConstraint("iso2", name="uq_pais_iso2"),
        sa.CheckConstraint("iso2 ~ '^[A-Z]{2}$'", name="ck_pais_iso2_formato"),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], name="fk_pais_region_id_region", ondelete="RESTRICT"),
    )
    op.create_index("ix_pais_region_id", "pais", ["region_id"])

    op.create_table(
        "puerto",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(5), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("pais_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        *_columnas_catalogo("puerto"),
        sa.PrimaryKeyConstraint("id", name="pk_puerto"),
        sa.UniqueConstraint("codigo", name="uq_puerto_codigo"),
        sa.CheckConstraint("tipo IN ('MARITIMO', 'AEREO')", name="ck_puerto_tipo"),
        sa.CheckConstraint(
            "(tipo = 'MARITIMO' AND codigo ~ '^[A-Z]{2}[A-Z0-9]{3}$') OR (tipo = 'AEREO' AND codigo ~ '^[A-Z]{3}$')",
            name="ck_puerto_codigo_formato",
        ),
        sa.ForeignKeyConstraint(["pais_id"], ["pais.id"], name="fk_puerto_pais_id_pais", ondelete="RESTRICT"),
    )
    op.create_index("ix_puerto_pais_id", "puerto", ["pais_id"])
    op.create_index("ix_puerto_tipo", "puerto", ["tipo"])

    # --- M3 Monedas y tasas ---
    op.create_table(
        "moneda",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(3), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("simbolo", sa.String(8), nullable=False),
        *_columnas_catalogo("moneda"),
        sa.PrimaryKeyConstraint("id", name="pk_moneda"),
        sa.UniqueConstraint("codigo", name="uq_moneda_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z]{3}$'", name="ck_moneda_codigo_formato"),
    )

    op.create_table(
        "tasa_cambio",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("moneda_id", sa.Integer(), nullable=False),
        sa.Column("tasa_a_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("fecha_vigencia", sa.Date(), nullable=False),
        sa.Column("registrado_por", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_tasa_cambio"),
        sa.UniqueConstraint("moneda_id", "fecha_vigencia", name="uq_tasa_cambio_moneda_fecha"),
        sa.CheckConstraint("tasa_a_usd > 0", name="ck_tasa_cambio_tasa_positiva"),
        sa.ForeignKeyConstraint(
            ["moneda_id"], ["moneda.id"], name="fk_tasa_cambio_moneda_id_moneda", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["registrado_por"], ["usuario.id"], name="fk_tasa_cambio_registrado_por_usuario"),
    )

    # --- M4 Proveedores ---
    op.create_table(
        "proveedor",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("pais_id", sa.Integer(), nullable=False),
        sa.Column("contacto", sa.String(120), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("telefono", sa.String(40), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        *_columnas_catalogo("proveedor"),
        sa.PrimaryKeyConstraint("id", name="pk_proveedor"),
        sa.CheckConstraint("email IS NULL OR email = lower(email)", name="ck_proveedor_email_minusculas"),
        sa.ForeignKeyConstraint(["pais_id"], ["pais.id"], name="fk_proveedor_pais_id_pais", ondelete="RESTRICT"),
    )
    op.create_index("uq_proveedor_nombre_lower", "proveedor", [sa.text("lower(nombre)")], unique=True)
    op.create_index("ix_proveedor_pais_id", "proveedor", ["pais_id"])

    # --- Incoterms 2020 ---
    op.create_table(
        "incoterm",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(3), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("solo_maritimo", sa.Boolean(), nullable=False),
        *[sa.Column(bloque, sa.Boolean(), nullable=False) for bloque in BLOQUES],
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_incoterm"),
        sa.UniqueConstraint("codigo", name="uq_incoterm_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z]{3}$'", name="ck_incoterm_codigo_formato"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_incoterm_actualizado_por_usuario"),
    )

    # --- Configuración (§5.2) ---
    op.create_table(
        "configuracion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("clave", sa.String(60), nullable=False),
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("permiso_edicion", sa.String(50), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_configuracion"),
        sa.UniqueConstraint("clave", name="uq_configuracion_clave"),
        sa.CheckConstraint("tipo IN ('DECIMAL', 'ENTERO', 'TEXTO')", name="ck_configuracion_tipo"),
        sa.ForeignKeyConstraint(
            ["permiso_edicion"], ["permiso.codigo"], name="fk_configuracion_permiso_edicion_permiso"
        ),
        sa.ForeignKeyConstraint(
            ["actualizado_por"], ["usuario.id"], name="fk_configuracion_actualizado_por_usuario"
        ),
    )

    # --- Auditoría (D-F1-4) ---
    op.create_table(
        "auditoria",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("entidad", sa.String(40), nullable=False),
        sa.Column("entidad_id", sa.String(40), nullable=False),
        sa.Column("accion", sa.String(12), nullable=False),
        sa.Column("valores_antes", JSONB(), nullable=True),
        sa.Column("valores_despues", JSONB(), nullable=True),
        sa.Column("nota", sa.String(300), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria"),
        sa.CheckConstraint("accion IN ('CREAR', 'EDITAR', 'DESACTIVAR')", name="ck_auditoria_accion"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_auditoria_usuario_id_usuario"),
    )
    op.create_index("ix_auditoria_entidad_entidad_id", "auditoria", ["entidad", "entidad_id"])
    op.create_index("ix_auditoria_fecha", "auditoria", ["fecha"])

    # --- Seed ---
    tabla_moneda = sa.table(
        "moneda", sa.column("codigo", sa.String), sa.column("nombre", sa.String), sa.column("simbolo", sa.String)
    )
    op.bulk_insert(tabla_moneda, [{"codigo": "USD", "nombre": "Dólar estadounidense", "simbolo": "$"}])

    tabla_incoterm = sa.table(
        "incoterm",
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("solo_maritimo", sa.Boolean),
        *[sa.column(bloque, sa.Boolean) for bloque in BLOQUES],
    )
    op.bulk_insert(
        tabla_incoterm,
        [
            {"codigo": codigo, "nombre": nombre, "solo_maritimo": solo_maritimo}
            | {bloque: bool(valor) for bloque, valor in zip(BLOQUES, valores, strict=True)}
            for codigo, nombre, solo_maritimo, valores in INCOTERMS
        ],
    )

    tabla_configuracion = sa.table(
        "configuracion",
        sa.column("clave", sa.String),
        sa.column("valor", sa.Text),
        sa.column("tipo", sa.String),
        sa.column("permiso_edicion", sa.String),
    )
    op.bulk_insert(
        tabla_configuracion,
        [
            {"clave": clave, "valor": valor, "tipo": tipo, "permiso_edicion": permiso}
            for clave, valor, tipo, permiso in CONFIGURACION
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_fecha", table_name="auditoria")
    op.drop_index("ix_auditoria_entidad_entidad_id", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_table("configuracion")
    op.drop_table("incoterm")
    op.drop_index("ix_proveedor_pais_id", table_name="proveedor")
    op.drop_index("uq_proveedor_nombre_lower", table_name="proveedor")
    op.drop_table("proveedor")
    op.drop_table("tasa_cambio")
    op.drop_table("moneda")
    op.drop_index("ix_puerto_tipo", table_name="puerto")
    op.drop_index("ix_puerto_pais_id", table_name="puerto")
    op.drop_table("puerto")
    op.drop_index("ix_pais_region_id", table_name="pais")
    op.drop_table("pais")
    op.drop_table("region")

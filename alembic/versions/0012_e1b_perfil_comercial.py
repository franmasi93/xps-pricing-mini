"""E1-B: perfil comercial del cliente, catálogos del perfil, consentimiento, eventos de Tencent y preferencias de pantalla.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19

Migración escrita a mano. No borra ni cambia datos existentes; solo agrega columnas con valores por defecto:
- cliente: nombre_comercial, tipo_cliente, estado_comercial (los existentes = ACTIVO), sector, servicios_interes, rutas_interes,
  tipos_carga, volumen_estimado, frecuencia, origen_cliente, etiquetas, acepta_promociones (existentes = SI),
  fecha_consentimiento y medio_consentimiento (existentes = RELACION_COMERCIAL_PREVIA).
- contacto_cliente: area y recibe_promociones (existentes = SI). "recibe_cotizaciones" de la plantilla oficial es la
  columna recibir_avisos de E3 (la misma preferencia, sin duplicarla).
- catalogo_perfil: los catálogos del perfil (tipos de cliente, estados comerciales fijos, sectores, tipos de carga,
  frecuencias, volúmenes, orígenes, áreas de contacto y medios de consentimiento), sembrados con la hoja Catalogos de la
  plantilla oficial de importación (docs/extensiones/importacion/).
- tencent_evento: la bitácora de eventos del callback de Tencent, vinculados por MessageId a la cotización, el boletín o el
  aviso que los originó (o SIN_VINCULAR).
- preferencia_pantalla: preferencias por usuario (columnas visibles de la lista de clientes).
- config_sistema.importacion_max_filas: máximo de filas por importación (2.000).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# (tipo, código, nombre) — de la hoja Catalogos de plantilla_importacion_clientes.xlsx (2026-10-19).
CATALOGOS = {
    "TIPO_CLIENTE": ["IMPORTADOR", "EXPORTADOR", "IMPORTADOR_EXPORTADOR", "AGENTE_DE_CARGA", "COURIER", "PERSONA_NATURAL"],
    "ESTADO_COMERCIAL": ["PROSPECTO", "ACTIVO", "INACTIVO", "PERDIDO"],
    "SECTOR": ["COMERCIO", "TEXTIL", "ALIMENTOS", "AGRO_EXPORTACION", "FARMACEUTICO", "TECNOLOGIA", "AUTOMOTRIZ_REPUESTOS",
               "CONSTRUCCION", "MANUFACTURA", "E_COMMERCE", "OTRO"],
    "FRECUENCIA": ["SEMANAL", "QUINCENAL", "MENSUAL", "TRIMESTRAL", "OCASIONAL"],
    "ORIGEN_CLIENTE": ["REFERIDO", "WEB", "FERIA", "REDES_SOCIALES", "VISITA", "LLAMADA", "OTRO"],
    "AREA_CONTACTO": ["COMPRAS", "LOGISTICA", "COMERCIO_EXTERIOR", "GERENCIA", "FINANZAS", "OTRO"],
    "MEDIO_CONSENTIMIENTO": ["RELACION_COMERCIAL_PREVIA", "FORMULARIO_WEB", "CORREO", "VERBAL", "CONTRATO"],
    "TIPO_CARGA": ["GENERAL", "PERECIBLE", "REFRIGERADA", "PELIGROSA", "VALORES", "SOBREDIMENSIONADA"],
}
VOLUMENES = [
    ("BAJO", "BAJO (menos de 1 TON o 1 contenedor al mes)"),
    ("MEDIO", "MEDIO (1 a 5 TON o 1 a 3 contenedores al mes)"),
    ("ALTO", "ALTO (más de 5 TON o más de 3 contenedores al mes)"),
]
ORIGENES_EVENTO = "'COTIZACION', 'BOLETIN', 'AVISO', 'SIN_VINCULAR'"


def _nombre(codigo: str) -> str:
    return codigo.replace("_", " ").capitalize()


def upgrade() -> None:
    op.create_table(
        "catalogo_perfil",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("fijo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_catalogo_perfil"),
        sa.UniqueConstraint("tipo", "codigo", name="uq_catalogo_perfil_tipo_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{0,39}$'", name="ck_catalogo_perfil_codigo_formato"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_catalogo_perfil_nombre_no_vacio"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_catalogo_perfil_creado_por_usuario"),
    )
    filas = []
    for tipo, codigos in CATALOGOS.items():
        for orden, codigo in enumerate(codigos, start=1):
            filas.append({"tipo": tipo, "codigo": codigo, "nombre": _nombre(codigo), "orden": orden * 10,
                          "fijo": tipo == "ESTADO_COMERCIAL"})
    for orden, (codigo, nombre) in enumerate(VOLUMENES, start=1):
        filas.append({"tipo": "VOLUMEN", "codigo": codigo, "nombre": nombre, "orden": orden * 10, "fijo": False})
    op.bulk_insert(sa.table("catalogo_perfil", sa.column("tipo"), sa.column("codigo"), sa.column("nombre"),
                            sa.column("orden"), sa.column("fijo")), filas)

    vacio = sa.text("'[]'::jsonb")
    for nombre, tipo, extra in (
        ("nombre_comercial", sa.String(200), {}), ("tipo_cliente", sa.String(40), {}),
        ("estado_comercial", sa.String(40), {"nullable": False, "server_default": "ACTIVO"}),
        ("sector", sa.String(40), {}), ("servicios_interes", JSONB, {"nullable": False, "server_default": vacio}),
        ("rutas_interes", JSONB, {"nullable": False, "server_default": vacio}),
        ("tipos_carga", JSONB, {"nullable": False, "server_default": vacio}), ("volumen_estimado", sa.String(40), {}),
        ("frecuencia", sa.String(40), {}), ("origen_cliente", sa.String(40), {}),
        ("etiquetas", JSONB, {"nullable": False, "server_default": vacio}),
        ("acepta_promociones", sa.Boolean(), {"nullable": False, "server_default": sa.true()}),
        ("fecha_consentimiento", sa.Date(), {}), ("medio_consentimiento", sa.String(40), {}),
    ):
        op.add_column("cliente", sa.Column(nombre, tipo, nullable=extra.get("nullable", True),
                                           server_default=extra.get("server_default")))
    op.execute("UPDATE cliente SET medio_consentimiento = 'RELACION_COMERCIAL_PREVIA'")
    op.create_index("ix_cliente_estado_comercial", "cliente", ["estado_comercial"])
    op.add_column("contacto_cliente", sa.Column("area", sa.String(40), nullable=True))
    op.add_column("contacto_cliente", sa.Column("recibe_promociones", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.create_table(
        "tencent_evento",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("evento", sa.String(30), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("origen_id", sa.BigInteger(), nullable=True),
        sa.Column("datos", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id", name="pk_tencent_evento"),
        sa.CheckConstraint(f"origen IN ({ORIGENES_EVENTO})", name="ck_tencent_evento_origen"),
    )
    op.create_index("ix_tencent_evento_message_id", "tencent_evento", ["message_id"])
    op.create_index("uq_tencent_evento_mensaje_evento", "tencent_evento", ["message_id", "evento"], unique=True,
                    postgresql_where=sa.text("message_id IS NOT NULL"))

    op.create_table(
        "preferencia_pantalla",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(60), nullable=False),
        sa.Column("valor", JSONB, nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("usuario_id", "clave", name="pk_preferencia_pantalla"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_preferencia_pantalla_usuario_id_usuario",
                                ondelete="CASCADE"),
    )
    op.add_column("config_sistema", sa.Column("importacion_max_filas", sa.Integer(), nullable=False, server_default="2000"))
    op.create_check_constraint("ck_config_sistema_importacion_max_filas", "config_sistema",
                               "importacion_max_filas BETWEEN 1 AND 20000")


def downgrade() -> None:
    op.drop_constraint("ck_config_sistema_importacion_max_filas", "config_sistema", type_="check")
    op.drop_column("config_sistema", "importacion_max_filas")
    op.drop_table("preferencia_pantalla")
    op.drop_index("uq_tencent_evento_mensaje_evento", table_name="tencent_evento")
    op.drop_index("ix_tencent_evento_message_id", table_name="tencent_evento")
    op.drop_table("tencent_evento")
    op.drop_column("contacto_cliente", "recibe_promociones")
    op.drop_column("contacto_cliente", "area")
    op.drop_index("ix_cliente_estado_comercial", table_name="cliente")
    for nombre in ("medio_consentimiento", "fecha_consentimiento", "acepta_promociones", "etiquetas", "origen_cliente",
                   "frecuencia", "volumen_estimado", "tipos_carga", "rutas_interes", "servicios_interes", "sector",
                   "estado_comercial", "tipo_cliente", "nombre_comercial"):
        op.drop_column("cliente", nombre)
    op.drop_table("catalogo_perfil")

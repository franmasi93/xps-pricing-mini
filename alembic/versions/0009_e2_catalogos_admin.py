"""E2: catálogos de administración (roles editables, motivos de rechazo, tipos de identificación y textos del PDF).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19

Migración escrita a mano. No cambia ningún dato existente:
- rol: agrega descripcion, protegido (admin) y activo, y las columnas de trazabilidad. Los 4 roles y su matriz quedan
  igual.
- motivo_rechazo: catálogo con los 4 motivos de F3 (PRECIO, TIEMPO, COMPETENCIA, OTRO). cotizacion.motivo_rechazo pasa
  de CHECK a FK (y de 11 a 30 caracteres). OTRO sigue exigiendo detalle (ck_cotizacion_detalle_si_otro no cambia).
- tipo_identificacion: catálogo con los 4 tipos de F2, con su regla (regex) y su formato, idénticos a los de
  services/clientes.py. cliente.tipo_id pasa de CHECK a FK, y el CHECK del formato por tipo
  (ck_cliente_identificacion_formato) se retira: la regla la aplica el service con el regex del catálogo.
- config_textos_pdf: una fila con los textos que estaban fijos (aceptación y firma del PDF, y las advertencias DDP y
  EXW), con el texto idéntico.
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

DESCRIPCIONES_ROL = {
    "admin": "Acceso total: usuarios, roles, configuración, catálogos y auditoría",
    "pricing": "Carga tarifas, costos y tasas; cotiza y emite",
    "comercial": "Gestiona sus clientes; cotiza, emite y envía",
    "gerencia": "Consulta tarifas, costos, márgenes, cotizaciones y auditoría",
}
# (código, nombre, exige detalle, orden) — los de F3 (0004).
MOTIVOS = [
    ("PRECIO", "Precio", False, 10),
    ("TIEMPO", "Tiempo", False, 20),
    ("COMPETENCIA", "Competencia", False, 30),
    ("OTRO", "Otro", True, 90),
]
# (código, nombre, regex, formato, orden) — idénticos a PATRONES_IDENTIFICACION y FORMATOS_IDENTIFICACION de F2.
TIPOS_ID = [
    ("RUC", "RUC", "^[0-9]{10}001$", "13 dígitos terminados en 001", 10),
    ("CEDULA", "Cédula", "^[0-9]{10}$", "10 dígitos", 20),
    ("PASAPORTE", "Pasaporte", "^[A-Z0-9]{5,20}$", "de 5 a 20 letras o números", 30),
    ("EXTRANJERO", "Extranjero", "^[A-Z0-9]{3,30}$", "de 3 a 30 letras o números", 40),
]
TEXTOS_PDF = {
    "aceptacion_titulo": "Aceptación de la cotización",
    "aceptacion_texto": (
        "Yo, en representación de la empresa, acepto los términos y condiciones aquí establecidos y confirmo la "
        "presente cotización."
    ),
    "firma_fecha": "Fecha: _______________",
    "firma_firma": "Firma: _____________________",
    "firma_sello": "Sello (opcional)",
    "advertencia_ddp": "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación",
    "advertencia_exw": "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación",
}
MOTIVOS_F3 = "'PRECIO', 'TIEMPO', 'COMPETENCIA', 'OTRO'"
TIPOS_F2 = "'RUC', 'CEDULA', 'PASAPORTE', 'EXTRANJERO'"
FORMATO_F2 = (
    "(tipo_id = 'RUC' AND ruc_o_id ~ '^[0-9]{10}001$')"
    " OR (tipo_id = 'CEDULA' AND ruc_o_id ~ '^[0-9]{10}$')"
    " OR (tipo_id = 'PASAPORTE' AND ruc_o_id ~ '^[A-Z0-9]{5,20}$')"
    " OR (tipo_id = 'EXTRANJERO' AND ruc_o_id ~ '^[A-Z0-9]{3,30}$')"
)


def _ahora():
    return sa.text("now()")


def _columnas_catalogo(tabla: str) -> list:
    """activo, creado_en, actualizado_en y creado_por, igual que en 0002, 0003 y 0007."""
    return [
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name=f"fk_{tabla}_creado_por_usuario"),
    ]


def upgrade() -> None:
    # --- Roles editables ---
    op.add_column("rol", sa.Column("descripcion", sa.String(300), nullable=True))
    op.add_column("rol", sa.Column("protegido", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("rol", sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("rol", sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()))
    op.add_column("rol", sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()))
    op.add_column("rol", sa.Column("creado_por", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_rol_creado_por_usuario", "rol", "usuario", ["creado_por"], ["id"])
    op.create_check_constraint("ck_rol_codigo_formato", "rol", "codigo ~ '^[a-z][a-z0-9_]{1,29}$'")
    op.create_check_constraint("ck_rol_nombre_no_vacio", "rol", "btrim(nombre) <> ''")
    op.create_check_constraint("ck_rol_protegido_activo", "rol", "NOT protegido OR activo")
    conexion = op.get_bind()
    for codigo, descripcion in DESCRIPCIONES_ROL.items():
        conexion.execute(sa.text("UPDATE rol SET descripcion = :d, protegido = (codigo = 'admin') WHERE codigo = :c"),
                         {"d": descripcion, "c": codigo})

    # --- Motivos de rechazo ---
    op.create_table(
        "motivo_rechazo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("exige_detalle", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        *_columnas_catalogo("motivo_rechazo"),
        sa.PrimaryKeyConstraint("id", name="pk_motivo_rechazo"),
        sa.UniqueConstraint("codigo", name="uq_motivo_rechazo_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{1,29}$'", name="ck_motivo_rechazo_codigo_formato"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_motivo_rechazo_nombre_no_vacio"),
        sa.CheckConstraint("codigo <> 'OTRO' OR exige_detalle", name="ck_motivo_rechazo_otro_exige_detalle"),
    )
    op.bulk_insert(
        sa.table("motivo_rechazo", sa.column("codigo"), sa.column("nombre"), sa.column("exige_detalle"),
                 sa.column("orden")),
        [{"codigo": c, "nombre": n, "exige_detalle": e, "orden": o} for c, n, e, o in MOTIVOS],
    )
    op.drop_constraint("ck_cotizacion_motivo_rechazo", "cotizacion", type_="check")
    op.alter_column("cotizacion", "motivo_rechazo", type_=sa.String(30), existing_type=sa.String(11),
                    existing_nullable=True)
    op.create_foreign_key("fk_cotizacion_motivo_rechazo_motivo_rechazo", "cotizacion", "motivo_rechazo",
                          ["motivo_rechazo"], ["codigo"], ondelete="RESTRICT")

    # --- Tipos de identificación ---
    op.create_table(
        "tipo_identificacion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("regex", sa.String(300), nullable=False),
        sa.Column("formato", sa.String(120), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        *_columnas_catalogo("tipo_identificacion"),
        sa.PrimaryKeyConstraint("id", name="pk_tipo_identificacion"),
        sa.UniqueConstraint("codigo", name="uq_tipo_identificacion_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{1,9}$'", name="ck_tipo_identificacion_codigo_formato"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_tipo_identificacion_nombre_no_vacio"),
        sa.CheckConstraint("btrim(regex) <> '' AND btrim(formato) <> ''", name="ck_tipo_identificacion_regla"),
    )
    op.bulk_insert(
        sa.table("tipo_identificacion", sa.column("codigo"), sa.column("nombre"), sa.column("regex"),
                 sa.column("formato"), sa.column("orden")),
        [{"codigo": c, "nombre": n, "regex": r, "formato": f, "orden": o} for c, n, r, f, o in TIPOS_ID],
    )
    op.drop_constraint("ck_cliente_tipo_id", "cliente", type_="check")
    op.drop_constraint("ck_cliente_identificacion_formato", "cliente", type_="check")  # la regla vive en el catálogo
    op.create_foreign_key("fk_cliente_tipo_id_tipo_identificacion", "cliente", "tipo_identificacion",
                          ["tipo_id"], ["codigo"], ondelete="RESTRICT")

    # --- Textos del PDF ---
    op.create_table(
        "config_textos_pdf",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        *[sa.Column(clave, sa.Text(), nullable=False) for clave in TEXTOS_PDF],
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_config_textos_pdf"),
        sa.CheckConstraint("id = 1", name="ck_config_textos_pdf_una_fila"),
        sa.CheckConstraint(" AND ".join(f"btrim({clave}) <> ''" for clave in TEXTOS_PDF),
                           name="ck_config_textos_pdf_no_vacios"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_textos_pdf_actualizado_por_usuario"),
    )
    op.bulk_insert(sa.table("config_textos_pdf", sa.column("id"), *[sa.column(c) for c in TEXTOS_PDF]),
                   [{"id": 1, **TEXTOS_PDF}])


def downgrade() -> None:
    conexion = op.get_bind()
    fuera_motivos = conexion.execute(sa.text(
        f"SELECT count(*) FROM cotizacion WHERE motivo_rechazo IS NOT NULL AND motivo_rechazo NOT IN ({MOTIVOS_F3})"
    )).scalar_one()
    fuera_tipos = conexion.execute(sa.text(f"SELECT count(*) FROM cliente WHERE NOT ({FORMATO_F2})")).scalar_one()
    roles_nuevos = conexion.execute(sa.text(
        "SELECT count(*) FROM rol WHERE codigo NOT IN ('admin', 'pricing', 'comercial', 'gerencia')"
    )).scalar_one()
    if fuera_motivos or fuera_tipos or roles_nuevos:
        raise RuntimeError(
            "No se revierte 0009: hay datos que usan lo nuevo de E2 "
            f"(cotizaciones con motivos nuevos: {fuera_motivos}; clientes fuera de las reglas de F2: {fuera_tipos}; "
            f"roles nuevos: {roles_nuevos}). Corríjalos antes."
        )
    op.drop_table("config_textos_pdf")

    op.drop_constraint("fk_cliente_tipo_id_tipo_identificacion", "cliente", type_="foreignkey")
    op.create_check_constraint("ck_cliente_tipo_id", "cliente", f"tipo_id IN ({TIPOS_F2})")
    op.create_check_constraint("ck_cliente_identificacion_formato", "cliente", FORMATO_F2)
    op.drop_table("tipo_identificacion")

    op.drop_constraint("fk_cotizacion_motivo_rechazo_motivo_rechazo", "cotizacion", type_="foreignkey")
    op.alter_column("cotizacion", "motivo_rechazo", type_=sa.String(11), existing_type=sa.String(30),
                    existing_nullable=True)
    op.create_check_constraint("ck_cotizacion_motivo_rechazo", "cotizacion",
                               f"motivo_rechazo IS NULL OR motivo_rechazo IN ({MOTIVOS_F3})")
    op.drop_table("motivo_rechazo")

    for nombre in ("ck_rol_protegido_activo", "ck_rol_nombre_no_vacio", "ck_rol_codigo_formato"):
        op.drop_constraint(nombre, "rol", type_="check")
    op.drop_constraint("fk_rol_creado_por_usuario", "rol", type_="foreignkey")
    for columna in ("creado_por", "actualizado_en", "creado_en", "activo", "protegido", "descripcion"):
        op.drop_column("rol", columna)

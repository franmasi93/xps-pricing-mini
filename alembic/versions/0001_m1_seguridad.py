"""M1 Seguridad: rol, permiso, rol_permiso, usuario + seed RBAC (§6.2).

Revision ID: 0001
Revises:
Create Date: 2026-10-01

Migración escrita a mano. El seed de RBAC es la única siembra de seguridad
(§6.3.5); el admin inicial se crea con scripts/crear_admin.py.
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ROLES = [
    ("admin", "Administrador"),
    ("pricing", "Pricing"),
    ("comercial", "Comercial"),
    ("gerencia", "Gerencia"),
]

PERMISOS = [
    ("usuario.admin", "Administrar usuarios y ver roles"),
    ("config.editar", "Editar la configuración del sistema"),
    ("catalogo.editar", "Editar catálogos: geografía, proveedores e Incoterms"),
    ("tarifa.ver", "Ver tarifas"),
    ("tarifa.editar", "Crear y editar tarifas y recargos"),
    ("costo.ver", "Ver costos"),
    ("margen.ver", "Ver márgenes"),
    ("tasa.editar", "Registrar tasas de cambio"),
    ("cliente.ver", "Ver clientes (el comercial solo los suyos)"),
    ("cliente.editar", "Crear y editar clientes (el comercial solo los suyos)"),
    ("cotizacion.crear", "Crear cotizaciones en borrador"),
    ("cotizacion.emitir", "Emitir cotizaciones"),
    ("cotizacion.enviar", "Enviar cotizaciones por correo"),
    ("cotizacion.ver_todas", "Ver las cotizaciones de todos los comerciales"),
    ("auditoria.ver", "Ver la auditoría"),
]

# Matriz §6.2 del documento rector: 15 + 11 + 6 + 6 = 38 pares.
MATRIZ = {
    "admin": [codigo for codigo, _ in PERMISOS],
    "pricing": [
        "catalogo.editar",
        "tarifa.ver",
        "tarifa.editar",
        "costo.ver",
        "margen.ver",
        "tasa.editar",
        "cliente.ver",
        "cotizacion.crear",
        "cotizacion.emitir",
        "cotizacion.enviar",
        "cotizacion.ver_todas",
    ],
    "comercial": [
        "tarifa.ver",
        "cliente.ver",
        "cliente.editar",
        "cotizacion.crear",
        "cotizacion.emitir",
        "cotizacion.enviar",
    ],
    "gerencia": [
        "tarifa.ver",
        "costo.ver",
        "margen.ver",
        "cliente.ver",
        "cotizacion.ver_todas",
        "auditoria.ver",
    ],
}


def upgrade() -> None:
    op.create_table(
        "rol",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rol"),
        sa.UniqueConstraint("codigo", name="uq_rol_codigo"),
    )

    op.create_table(
        "permiso",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permiso"),
        sa.UniqueConstraint("codigo", name="uq_permiso_codigo"),
    )

    op.create_table(
        "rol_permiso",
        sa.Column("rol_id", sa.Integer(), nullable=False),
        sa.Column("permiso_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("rol_id", "permiso_id", name="pk_rol_permiso"),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["rol.id"], name="fk_rol_permiso_rol_id_rol", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["permiso_id"], ["permiso.id"], name="fk_rol_permiso_permiso_id_permiso", ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("hash_password", sa.String(255), nullable=False),
        sa.Column("rol_id", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("forzar_cambio_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_usuario"),
        sa.ForeignKeyConstraint(["rol_id"], ["rol.id"], name="fk_usuario_rol_id_rol"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_usuario_creado_por_usuario"),
        sa.CheckConstraint("email = lower(email)", name="ck_usuario_email_minusculas"),
        sa.CheckConstraint("token_version >= 0", name="ck_usuario_token_version_no_negativo"),
        sa.CheckConstraint("intentos_fallidos >= 0", name="ck_usuario_intentos_fallidos_no_negativo"),
    )
    op.create_index("uq_usuario_email_lower", "usuario", [sa.text("lower(email)")], unique=True)
    op.create_index("ix_usuario_rol_id", "usuario", ["rol_id"])

    # --- Seed RBAC ---
    tabla_rol = sa.table("rol", sa.column("codigo", sa.String), sa.column("nombre", sa.String))
    tabla_permiso = sa.table("permiso", sa.column("codigo", sa.String), sa.column("descripcion", sa.String))
    op.bulk_insert(tabla_rol, [{"codigo": codigo, "nombre": nombre} for codigo, nombre in ROLES])
    op.bulk_insert(tabla_permiso, [{"codigo": codigo, "descripcion": desc} for codigo, desc in PERMISOS])

    conexion = op.get_bind()
    for rol_codigo, permisos in MATRIZ.items():
        insertadas = conexion.execute(
            sa.text(
                "INSERT INTO rol_permiso (rol_id, permiso_id) "
                "SELECT r.id, p.id FROM rol r JOIN permiso p ON p.codigo = ANY(:permisos) "
                "WHERE r.codigo = :rol"
            ),
            {"rol": rol_codigo, "permisos": permisos},
        ).rowcount
        if insertadas != len(permisos):
            raise RuntimeError(
                f"Seed RBAC: el rol {rol_codigo} esperaba {len(permisos)} permisos y se insertaron {insertadas}"
            )


def downgrade() -> None:
    op.drop_index("ix_usuario_rol_id", table_name="usuario")
    op.drop_index("uq_usuario_email_lower", table_name="usuario")
    op.drop_table("usuario")
    op.drop_table("rol_permiso")
    op.drop_table("permiso")
    op.drop_table("rol")

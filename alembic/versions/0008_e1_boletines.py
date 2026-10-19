"""E1: boletines de tarifas (configuración de masivos, plantillas, listas, bajas, campañas y destinatarios).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18

Migración escrita a mano. No toca datos existentes: solo crea tablas, la fila de config_masivos (con el remitente y el
reply-to del correo de F4), el catálogo de plantillas (la de cotizaciones de F4 ya aprobada en Tencent, y las 12 del
sistema generadas con los datos de la empresa, SIN_REGISTRAR hasta que se carguen en Tencent) y 4 permisos:
- boletines.ver: los 4 roles;
- boletines.listas.gestionar, boletines.campanas.gestionar y boletines.campanas.enviar: admin y pricing.
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.services import plantillas_diseno

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

ESTADOS_CAMPANA = "'BORRADOR', 'PROGRAMADA', 'ENVIANDO', 'PAUSADA', 'ENVIADA', 'CANCELADA'"
ESTADOS_DESTINATARIO = (
    "'PENDIENTE', 'ENVIADO', 'REBOTADO', 'FALLIDO', 'OMITIDO_BAJA', 'OMITIDO_DUPLICADO', 'CANCELADO'"
)
DISENOS = "'GENERAL', 'PESO_TRAMOS', 'VOLUMEN_WM', 'UNIDAD_EQUIPO', 'TARIFA_PLANA', 'AVISO', 'LIBRE'"
ESTADOS_TENCENT = "'SIN_REGISTRAR', 'EN_REVISION', 'APROBADA', 'RECHAZADA', 'NO_ENCONTRADA'"
CLAVES_EMPRESA = (
    "empresa_departamento", "empresa_ciudad", "empresa_telefono", "empresa_celular", "empresa_whatsapp",
    "empresa_horario", "empresa_direccion_matriz",
)
ASUNTOS = {
    "GENERAL": "Tarifas vigentes – XPRESS LOGISTICS", "PESO_TRAMOS": "Tarifas por peso – XPRESS LOGISTICS",
    "VOLUMEN_WM": "Tarifas de carga consolidada – XPRESS LOGISTICS",
    "UNIDAD_EQUIPO": "Tarifas por contenedor – XPRESS LOGISTICS", "TARIFA_PLANA": "Tarifas por envío – XPRESS LOGISTICS",
}
TEXTO_LEGAL = (
    "Recibe este correo porque es cliente o contacto comercial de XPRESS LOGISTICS XPS S.A. Las tarifas están "
    "sujetas a la vigencia indicada, a disponibilidad de espacio y a los recargos locales que correspondan."
)
URL_PUBLICA = "https://xps-pricing-809824844407.us-central1.run.app"
PERMISOS = [
    ("boletines.ver", "Ver campañas, listas, plantillas y bajas de boletines", ("admin", "pricing", "comercial", "gerencia")),
    ("boletines.listas.gestionar", "Crear y editar listas de envío y registrar bajas", ("admin", "pricing")),
    ("boletines.campanas.gestionar", "Crear borradores de campañas, enviarse pruebas y editar plantillas", ("admin", "pricing")),
    ("boletines.campanas.enviar", "Enviar, programar, pausar, reanudar y cancelar campañas", ("admin", "pricing")),
]


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _columnas_catalogo(tabla: str) -> list:
    return [
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name=f"fk_{tabla}_creado_por_usuario"),
    ]


def upgrade() -> None:
    op.create_table(
        "config_masivos",
        sa.Column("id", sa.SmallInteger(), nullable=False, autoincrement=False),
        sa.Column("remitente", sa.String(300), nullable=False, server_default=""),
        sa.Column("reply_to", sa.String(254), nullable=False, server_default=""),
        sa.Column("tamano_lote", sa.SmallInteger(), nullable=False, server_default="50"),
        sa.Column("pausa_segundos", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("tope_diario", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("tope_hora", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("reserva_pct", sa.SmallInteger(), nullable=False, server_default="20"),
        sa.Column("adjuntar_pdf", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limite_filas", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("texto_legal", sa.Text(), nullable=False, server_default=""),
        sa.Column("correos_prueba", sa.Text(), nullable=False, server_default=""),
        sa.Column("dias_envio", sa.String(20), nullable=False, server_default="1,2,3,4,5"),
        sa.Column("hora_desde", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("hora_hasta", sa.SmallInteger(), nullable=False, server_default="19"),
        sa.Column("calentamiento", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calentamiento_inicio", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("calentamiento_incremento", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("calentamiento_desde", sa.Date(), nullable=True),
        sa.Column("url_publica", sa.String(300), nullable=False, server_default=""),
        sa.Column("ultimo_lote_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_sincronizacion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_config_masivos"),
        sa.CheckConstraint("id = 1", name="ck_config_masivos_una_sola_fila"),
        sa.CheckConstraint("tamano_lote BETWEEN 1 AND 200", name="ck_config_masivos_lote"),
        sa.CheckConstraint("pausa_segundos BETWEEN 0 AND 3600", name="ck_config_masivos_pausa"),
        sa.CheckConstraint("tope_diario BETWEEN 1 AND 1000000", name="ck_config_masivos_tope"),
        sa.CheckConstraint("limite_filas BETWEEN 1 AND 8", name="ck_config_masivos_limite_filas"),
        sa.CheckConstraint("tope_hora BETWEEN 1 AND 100000", name="ck_config_masivos_tope_hora"),
        sa.CheckConstraint("reserva_pct BETWEEN 0 AND 90", name="ck_config_masivos_reserva"),
        sa.CheckConstraint("hora_desde BETWEEN 0 AND 23 AND hora_hasta BETWEEN 0 AND 23 AND hora_desde <= hora_hasta",
                           name="ck_config_masivos_horario"),
        sa.CheckConstraint("dias_envio ~ '^[1-7](,[1-7])*$'", name="ck_config_masivos_dias"),
        sa.CheckConstraint("calentamiento_inicio >= 1 AND calentamiento_incremento >= 0",
                           name="ck_config_masivos_calentamiento"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_masivos_actualizado_por_usuario"),
    )
    op.execute(
        sa.text(
            "INSERT INTO config_masivos (id, remitente, reply_to, texto_legal, url_publica) "
            "SELECT 1, COALESCE((SELECT remitente FROM config_correo WHERE id = 1), ''), "
            "COALESCE((SELECT reply_to FROM config_correo WHERE id = 1), ''), :legal, :url"
        ).bindparams(legal=TEXTO_LEGAL, url=URL_PUBLICA)
    )

    op.create_table(
        "plantilla_correo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("uso", sa.String(10), nullable=False),
        sa.Column("diseno", sa.String(20), nullable=False),
        sa.Column("evento_o_servicio", sa.String(40), nullable=True),
        sa.Column("asunto_sugerido", sa.String(200), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("variables_esperadas", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tencent_id", sa.BigInteger(), nullable=True),
        sa.Column("estado_tencent", sa.String(14), nullable=False, server_default="SIN_REGISTRAR"),
        sa.Column("motivo_tencent", sa.Text(), nullable=True),
        sa.Column("sincronizada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        *_columnas_catalogo("plantilla_correo"),
        sa.PrimaryKeyConstraint("id", name="pk_plantilla_correo"),
        sa.UniqueConstraint("tencent_id", name="uq_plantilla_correo_tencent_id"),
        sa.CheckConstraint("tencent_id IS NULL OR tencent_id > 0", name="ck_plantilla_correo_tencent_id_positivo"),
        sa.CheckConstraint("uso IN ('COTIZACION', 'BOLETIN', 'AVISO')", name="ck_plantilla_correo_uso"),
        sa.CheckConstraint(f"estado_tencent IN ({ESTADOS_TENCENT})", name="ck_plantilla_correo_estado_tencent"),
        sa.CheckConstraint("(tencent_id IS NULL) = (estado_tencent = 'SIN_REGISTRAR')",
                           name="ck_plantilla_correo_id_segun_estado"),
        sa.CheckConstraint(f"diseno IN ({DISENOS})", name="ck_plantilla_correo_diseno"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_plantilla_correo_nombre_no_vacio"),
    )
    op.execute("CREATE UNIQUE INDEX uq_plantilla_correo_nombre_lower ON plantilla_correo (lower(nombre))")
    _sembrar_plantillas()

    op.create_table(
        "lista_envio",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("filtros", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_columnas_catalogo("lista_envio"),
        sa.PrimaryKeyConstraint("id", name="pk_lista_envio"),
        sa.CheckConstraint("tipo IN ('MANUAL', 'FILTRO')", name="ck_lista_envio_tipo"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_lista_envio_nombre_no_vacio"),
    )
    op.execute("CREATE UNIQUE INDEX uq_lista_envio_nombre_lower ON lista_envio (lower(nombre))")
    op.create_table(
        "lista_envio_miembro",
        sa.Column("lista_id", sa.Integer(), nullable=False),
        sa.Column("contacto_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("lista_id", "contacto_id", name="pk_lista_envio_miembro"),
        sa.ForeignKeyConstraint(["lista_id"], ["lista_envio.id"], name="fk_lista_envio_miembro_lista_id_lista_envio",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contacto_id"], ["contacto_cliente.id"],
                                name="fk_lista_envio_miembro_contacto_id_contacto_cliente", ondelete="RESTRICT"),
    )

    op.create_table(
        "campana",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("asunto", sa.String(200), nullable=False, server_default=""),
        sa.Column("texto_intro", sa.Text(), nullable=False, server_default=""),
        sa.Column("plantilla_id", sa.Integer(), nullable=True),
        sa.Column("servicios", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tipos_equipo", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tarifas_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("listas_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("adjuntar_pdf", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("snapshot_tarifas", JSONB(), nullable=True),
        sa.Column("adjunto_pdf", sa.LargeBinary(), nullable=True),
        sa.Column("estado", sa.String(10), nullable=False, server_default="BORRADOR"),
        sa.Column("programada_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_destinatarios", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enviados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rebotados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("omitidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_por", sa.Integer(), nullable=False),
        sa.Column("enviado_por", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminada_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_campana"),
        sa.CheckConstraint(f"estado IN ({ESTADOS_CAMPANA})", name="ck_campana_estado"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_campana_nombre_no_vacio"),
        sa.CheckConstraint("estado <> 'PROGRAMADA' OR programada_para IS NOT NULL", name="ck_campana_programada_con_fecha"),
        sa.CheckConstraint("estado = 'BORRADOR' OR snapshot_tarifas IS NOT NULL", name="ck_campana_snapshot_si_enviada"),
        sa.ForeignKeyConstraint(["plantilla_id"], ["plantilla_correo.id"], name="fk_campana_plantilla_id_plantilla_correo",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_campana_creado_por_usuario"),
        sa.ForeignKeyConstraint(["enviado_por"], ["usuario.id"], name="fk_campana_enviado_por_usuario"),
    )
    op.create_index("ix_campana_estado", "campana", ["estado"])

    op.create_table(
        "campana_destinatario",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("campana_id", sa.Integer(), nullable=False),
        sa.Column("contacto_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False, server_default=""),
        sa.Column("empresa", sa.String(200), nullable=False, server_default=""),
        sa.Column("estado", sa.String(18), nullable=False, server_default="PENDIENTE"),
        sa.Column("intentos", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.String(300), nullable=True),
        sa.Column("token_baja", sa.String(80), nullable=False),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_campana_destinatario"),
        sa.UniqueConstraint("campana_id", "email", name="uq_campana_destinatario_campana_email"),
        sa.UniqueConstraint("token_baja", name="uq_campana_destinatario_token_baja"),
        sa.CheckConstraint(f"estado IN ({ESTADOS_DESTINATARIO})", name="ck_campana_destinatario_estado"),
        sa.CheckConstraint("email = lower(email)", name="ck_campana_destinatario_email_minusculas"),
        sa.CheckConstraint("intentos BETWEEN 0 AND 10", name="ck_campana_destinatario_intentos"),
        sa.CheckConstraint("estado <> 'ENVIADO' OR message_id IS NOT NULL", name="ck_campana_destinatario_enviado_con_id"),
        sa.ForeignKeyConstraint(["campana_id"], ["campana.id"], name="fk_campana_destinatario_campana_id_campana",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contacto_id"], ["contacto_cliente.id"],
                                name="fk_campana_destinatario_contacto_id_contacto_cliente", ondelete="SET NULL"),
    )
    op.create_index("ix_campana_destinatario_campana_id", "campana_destinatario", ["campana_id"])
    op.execute(
        "CREATE INDEX ix_campana_destinatario_pendiente ON campana_destinatario (campana_id, id) "
        "WHERE estado = 'PENDIENTE'"
    )
    op.create_index("ix_campana_destinatario_message_id", "campana_destinatario", ["message_id"])

    op.create_table(
        "baja_correo",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("motivo", sa.String(10), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("revertida", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revertida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("campana_id", sa.Integer(), nullable=True),
        sa.Column("registrado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_baja_correo"),
        sa.UniqueConstraint("email", name="uq_baja_correo_email"),
        sa.CheckConstraint("email = lower(email)", name="ck_baja_correo_email_minusculas"),
        sa.CheckConstraint("motivo IN ('ENLACE', 'MANUAL', 'TENCENT')", name="ck_baja_correo_motivo"),
        sa.ForeignKeyConstraint(["campana_id"], ["campana.id"], name="fk_baja_correo_campana_id_campana", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registrado_por"], ["usuario.id"], name="fk_baja_correo_registrado_por_usuario"),
    )

    for codigo, descripcion, roles in PERMISOS:
        op.execute(
            sa.text("INSERT INTO permiso (codigo, descripcion) VALUES (:c, :d)").bindparams(c=codigo, d=descripcion)
        )
        op.execute(
            sa.text(
                "INSERT INTO rol_permiso (rol_id, permiso_id) SELECT r.id, p.id FROM rol r JOIN permiso p "
                "ON p.codigo = :c WHERE r.codigo = ANY(:roles)"
            ).bindparams(c=codigo, roles=list(roles))
        )


def _sembrar_plantillas() -> None:
    """La de cotizaciones de F4 (la que usa config_correo, aprobada) y las 12 del sistema, con los datos de la empresa."""
    conexion = op.get_bind()
    insertar = sa.text(
        "INSERT INTO plantilla_correo (nombre, uso, diseno, evento_o_servicio, asunto_sugerido, html, texto, "
        "variables_esperadas, tencent_id, estado_tencent) VALUES (:nombre, :uso, :diseno, :evento, :asunto, :html, "
        ":texto, CAST(:variables AS jsonb), :tencent_id, :estado)"
    )
    cotizacion = conexion.execute(sa.text("SELECT plantilla_cotizacion_id FROM config_correo WHERE id = 1")).scalar()
    if cotizacion:
        conexion.execute(insertar, {
            "nombre": "Cotización (F4)", "uso": "COTIZACION", "diseno": "LIBRE", "evento": None,
            "asunto": "Cotización {numero} – XPRESS LOGISTICS XPS S.A.", "html": None, "texto": None,
            "variables": json.dumps(["contacto", "numero", "valida_hasta", "comercial"]), "tencent_id": cotizacion,
            "estado": "APROBADA",
        })
    fila = conexion.execute(sa.text(f"SELECT {', '.join(CLAVES_EMPRESA)} FROM config_empresa WHERE id = 1")).mappings().first()
    empresa = {clave: (fila[clave] if fila else "") or "" for clave in CLAVES_EMPRESA}
    for plantilla in plantillas_diseno.catalogo(empresa, TEXTO_LEGAL):
        conexion.execute(insertar, {
            "nombre": plantilla["nombre"], "uso": plantilla["uso"], "diseno": plantilla["diseno"],
            "evento": plantilla["evento_o_servicio"], "asunto": ASUNTOS.get(plantilla["diseno"]),
            "html": plantilla["html"], "texto": plantillas_diseno.texto_plano(plantilla["html"]),
            "variables": json.dumps(plantilla["variables"]), "tencent_id": None, "estado": "SIN_REGISTRAR",
        })


def downgrade() -> None:
    conexion = op.get_bind()
    for consulta, motivo in (
        ("SELECT count(*) FROM baja_correo", "baja(s) de correo registradas"),
        ("SELECT count(*) FROM campana WHERE estado <> 'BORRADOR'", "campaña(s) enviadas o programadas"),
    ):
        cantidad = conexion.execute(sa.text(consulta)).scalar_one()
        if cantidad:
            raise RuntimeError(
                f"Downgrade de 0008 rechazado sin cambios: hay {cantidad} {motivo}, que se perderían. Restaure el "
                "respaldo previo a la migración si necesita volver."
            )
    codigos = [codigo for codigo, _, _ in PERMISOS]
    op.execute(
        sa.text("DELETE FROM rol_permiso WHERE permiso_id IN (SELECT id FROM permiso WHERE codigo = ANY(:c))").bindparams(
            c=codigos
        )
    )
    op.execute(sa.text("DELETE FROM permiso WHERE codigo = ANY(:c)").bindparams(c=codigos))
    op.drop_table("baja_correo")
    op.drop_index("ix_campana_destinatario_message_id", table_name="campana_destinatario")
    op.execute("DROP INDEX ix_campana_destinatario_pendiente")
    op.drop_index("ix_campana_destinatario_campana_id", table_name="campana_destinatario")
    op.drop_table("campana_destinatario")
    op.drop_index("ix_campana_estado", table_name="campana")
    op.drop_table("campana")
    op.drop_table("lista_envio_miembro")
    op.execute("DROP INDEX uq_lista_envio_nombre_lower")
    op.drop_table("lista_envio")
    op.execute("DROP INDEX uq_plantilla_correo_nombre_lower")
    op.drop_table("plantilla_correo")
    op.drop_table("config_masivos")

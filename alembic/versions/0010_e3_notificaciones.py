"""E3: notificaciones y avisos (configuración, reglas, notificaciones con outbox, preferencias e interruptores).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-19

Migración escrita a mano. No cambia ningún dato existente:
- config_avisos (una fila): avisos externos en SIMULACIÓN, "aplicar desde" = fecha de la migración (nunca reprocesar el
  histórico), tope semanal por cliente y horario hábil.
- regla_notificacion: una regla sembrada por evento (los eventos viven en el código: services/eventos.py). Las externas
  activas salvo TARIFA_RUTA_INTERES; plantillas por evento (las 72747–72753 que subió el gerente).
- notificacion: el outbox y la bitácora, con clave_idempotencia única.
- preferencia_notificacion: qué eventos internos recibe cada usuario por correo.
- cotizacion.avisos_activos, cliente.avisos_activos y contacto_cliente.recibir_avisos (por defecto, sí).
- 3 permisos: notificaciones.ver (los 4 roles), notificaciones.reglas.gestionar (admin) y notificaciones.bitacora.ver
  (admin y pricing).
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

APLICAR_DESDE = "2026-10-19"
ESTADOS = "'PENDIENTE', 'ENVIADO', 'SIMULADO', 'FALLIDO', 'CANCELADO', 'OMITIDO'"
PERMISOS = [
    ("notificaciones.ver", "Ver sus notificaciones y elegir sus preferencias", ("admin", "pricing", "comercial", "gerencia")),
    ("notificaciones.reglas.gestionar", "Configurar eventos, reglas y el interruptor de avisos a clientes", ("admin",)),
    ("notificaciones.bitacora.ver", "Ver la bitácora de notificaciones y reenviar las fallidas", ("admin", "pricing")),
]
_COMERCIAL = {"tipos": ["COMERCIAL"], "roles": ["pricing"]}
# (evento, nombre, canal correo, canal interno, destinatarios, parámetros, plantilla (evento_o_servicio), agrupación,
#  obligatoria, activa)
REGLAS = [
    ("COT_SEGUIMIENTO", "Seguimiento de cotización enviada", True, False, {"tipos": ["CONTACTO_COTIZACION"]},
     {"dias": 3, "repeticiones": 2, "intervalo": 4, "adjuntar_pdf": False}, "COT_SEGUIMIENTO", "INDIVIDUAL", False, True),
    ("COT_POR_VENCER", "Cotización por vencer", True, False, {"tipos": ["CONTACTO_COTIZACION"]},
     {"dias": 3, "adjuntar_pdf": False}, "COT_POR_VENCER", "INDIVIDUAL", False, True),
    ("COT_VENCIDA", "Cotización vencida", True, False, {"tipos": ["CONTACTO_COTIZACION"]},
     {"ventana": 7}, "COT_VENCIDA", "INDIVIDUAL", False, True),
    ("COT_ACEPTADA_CLIENTE", "Confirmación al cliente que aceptó", True, False, {"tipos": ["CONTACTO_COTIZACION"]},
     {"pasos": ["Le enviaremos la reserva de espacio y las instrucciones de entrega.",
                "Prepare la factura comercial y la lista de empaque.",
                "Su comercial coordinará con usted la fecha de embarque."]},
     "COT_ACEPTADA_CLIENTE", "INDIVIDUAL", False, True),
    ("TARIFA_RUTA_INTERES", "Nueva tarifa en una ruta que el cliente cotizó", True, False,
     {"tipos": ["CONTACTO_COTIZACION"]}, {"meses": 6, "dias_nueva": 1}, "TARIFA_RUTA_INTERES", "INDIVIDUAL", False, False),
    ("COT_ACEPTADA", "Cotización aceptada", True, True, _COMERCIAL, {}, "INTERNO", "INDIVIDUAL", False, True),
    ("COT_RECHAZADA", "Cotización rechazada", True, True, _COMERCIAL, {}, "INTERNO", "INDIVIDUAL", False, True),
    ("COT_SIN_RESPUESTA", "Cotización sin respuesta del cliente", True, True, {"tipos": ["COMERCIAL"]}, {}, "INTERNO",
     "INDIVIDUAL", False, True),
    ("COT_MARGEN_BAJO", "Cotización emitida con margen bajo", True, True, {"roles": ["pricing", "gerencia"]},
     {"umbral_pct": 15}, "INTERNO", "INDIVIDUAL", False, True),
    ("TARIFA_POR_VENCER", "Tarifas por vencer (correo diario)", True, True, {"roles": ["pricing"]}, {}, "INTERNO",
     "RESUMEN", False, True),
    ("TARIFA_SIN_REEMPLAZO", "Tarifa vencida sin reemplazo", True, True, {"roles": ["pricing"]}, {"ventana": 7},
     "INTERNO", "INDIVIDUAL", False, True),
    ("TASA_DESACTUALIZADA", "Tasa de cambio desactualizada", True, True, {"roles": ["pricing"]}, {"dias": 7}, "INTERNO",
     "INDIVIDUAL", False, True),
    ("ENVIO_FALLIDO", "Envío de correo fallido", True, True, {"tipos": ["ACTOR"], "roles": ["admin"]}, {}, "INTERNO",
     "INDIVIDUAL", True, True),
    ("CAMPANA_TERMINADA", "Campaña terminada", False, True, {"tipos": ["ACTOR"], "roles": ["admin"]}, {}, "INTERNO",
     "INDIVIDUAL", False, True),
    ("CAMPANA_REBOTE_ALTO", "Campaña con rebote alto", True, True, {"tipos": ["ACTOR"], "roles": ["admin"]},
     {"umbral_pct": 5}, "INTERNO", "INDIVIDUAL", False, True),
    ("CUOTA_TENCENT_CERCA", "Cupo diario de correo cerca del tope", True, True, {"roles": ["admin"]}, {"umbral_pct": 80},
     "INTERNO", "INDIVIDUAL", True, True),
    ("USUARIO_BLOQUEADO", "Usuario bloqueado por intentos fallidos", True, True, {"roles": ["admin"]}, {}, "INTERNO",
     "INDIVIDUAL", True, True),
    ("RESUMEN_DIARIO", "Resumen diario", True, True, {"roles": ["gerencia"]}, {"hora": 7}, "RESUMEN", "INDIVIDUAL",
     False, True),
    ("RESUMEN_SEMANAL", "Resumen semanal", True, True, {"roles": ["gerencia"]}, {"hora": 7, "dia_semana": 1}, "RESUMEN",
     "INDIVIDUAL", False, True),
]


def _ahora():
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "config_avisos",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("modo_externo", sa.String(10), nullable=False, server_default="SIMULACION"),
        sa.Column("aplicar_desde", sa.Date(), nullable=True),
        sa.Column("tope_semanal_cliente", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("dias_habiles", sa.String(20), nullable=False, server_default="1,2,3,4,5"),
        sa.Column("hora_desde", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("hora_hasta", sa.SmallInteger(), nullable=False, server_default="18"),
        sa.Column("ultima_evaluacion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_config_avisos"),
        sa.CheckConstraint("id = 1", name="ck_config_avisos_una_fila"),
        sa.CheckConstraint("modo_externo IN ('SIMULACION', 'ACTIVO', 'APAGADO')", name="ck_config_avisos_modo"),
        sa.CheckConstraint("tope_semanal_cliente BETWEEN 0 AND 100", name="ck_config_avisos_tope"),
        sa.CheckConstraint("hora_desde BETWEEN 0 AND 23 AND hora_hasta BETWEEN 0 AND 23 AND hora_desde <= hora_hasta",
                           name="ck_config_avisos_horario"),
        sa.ForeignKeyConstraint(["actualizado_por"], ["usuario.id"], name="fk_config_avisos_actualizado_por_usuario"),
    )
    op.execute(f"INSERT INTO config_avisos (id, aplicar_desde) VALUES (1, DATE '{APLICAR_DESDE}')")

    op.create_table(
        "regla_notificacion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("canal_correo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("canal_interno", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("destinatarios", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parametros", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("plantilla_id", sa.Integer(), nullable=True),
        sa.Column("agrupacion", sa.String(10), nullable=False, server_default="INDIVIDUAL"),
        sa.Column("obligatoria", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_regla_notificacion"),
        sa.CheckConstraint("agrupacion IN ('INDIVIDUAL', 'RESUMEN')", name="ck_regla_notificacion_agrupacion"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_regla_notificacion_nombre_no_vacio"),
        sa.CheckConstraint("canal_correo OR canal_interno", name="ck_regla_notificacion_algun_canal"),
        sa.ForeignKeyConstraint(["plantilla_id"], ["plantilla_correo.id"],
                                name="fk_regla_notificacion_plantilla_id_plantilla_correo", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name="fk_regla_notificacion_creado_por_usuario"),
    )
    op.create_index("ix_regla_notificacion_evento", "regla_notificacion", ["evento"])
    conexion = op.get_bind()
    for evento, nombre, correo, interno, destinatarios, parametros, plantilla, agrupacion, obligatoria, activa in REGLAS:
        conexion.execute(sa.text(
            "INSERT INTO regla_notificacion (evento, nombre, canal_correo, canal_interno, destinatarios, parametros, "
            "plantilla_id, agrupacion, obligatoria, activo) VALUES (:evento, :nombre, :correo, :interno, "
            "CAST(:destinatarios AS jsonb), CAST(:parametros AS jsonb), "
            "(SELECT id FROM plantilla_correo WHERE uso = 'AVISO' AND evento_o_servicio = :plantilla ORDER BY id LIMIT 1), "
            ":agrupacion, :obligatoria, :activa)"
        ), {"evento": evento, "nombre": nombre, "correo": correo, "interno": interno,
            "destinatarios": json.dumps(destinatarios), "parametros": json.dumps(parametros, ensure_ascii=False),
            "plantilla": plantilla, "agrupacion": agrupacion, "obligatoria": obligatoria, "activa": activa})

    op.create_table(
        "notificacion",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("regla_id", sa.Integer(), nullable=True),
        sa.Column("audiencia", sa.String(8), nullable=False),
        sa.Column("entidad_tipo", sa.String(30), nullable=False),
        sa.Column("entidad_id", sa.String(40), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        sa.Column("comercial_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("canal", sa.String(8), nullable=False),
        sa.Column("estado", sa.String(10), nullable=False, server_default="PENDIENTE"),
        sa.Column("motivo_omision", sa.String(200), nullable=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False, server_default=""),
        sa.Column("enlace", sa.String(300), nullable=True),
        sa.Column("asunto", sa.String(300), nullable=True),
        sa.Column("plantilla_id", sa.Integer(), nullable=True),
        sa.Column("variables", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("adjuntar_pdf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("programada_para", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("clave_idempotencia", sa.String(250), nullable=False),
        sa.Column("intentos", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("message_id", sa.String(120), nullable=True),
        sa.Column("ultimo_error", sa.String(300), nullable=True),
        sa.Column("leida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name="pk_notificacion"),
        sa.UniqueConstraint("clave_idempotencia", name="uq_notificacion_clave_idempotencia"),
        sa.CheckConstraint(f"estado IN ({ESTADOS})", name="ck_notificacion_estado"),
        sa.CheckConstraint("canal IN ('CORREO', 'INTERNO')", name="ck_notificacion_canal"),
        sa.CheckConstraint("audiencia IN ('EXTERNA', 'INTERNA')", name="ck_notificacion_audiencia"),
        sa.CheckConstraint("usuario_id IS NOT NULL OR email IS NOT NULL", name="ck_notificacion_con_destinatario"),
        sa.CheckConstraint("canal = 'CORREO' OR usuario_id IS NOT NULL", name="ck_notificacion_interna_a_usuario"),
        sa.ForeignKeyConstraint(["regla_id"], ["regla_notificacion.id"], name="fk_notificacion_regla_id_regla_notificacion",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cliente_id"], ["cliente.id"], name="fk_notificacion_cliente_id_cliente", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["comercial_id"], ["usuario.id"], name="fk_notificacion_comercial_id_usuario"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_notificacion_usuario_id_usuario"),
        sa.ForeignKeyConstraint(["plantilla_id"], ["plantilla_correo.id"],
                                name="fk_notificacion_plantilla_id_plantilla_correo", ondelete="SET NULL"),
    )
    op.create_index("ix_notificacion_pendientes", "notificacion", ["programada_para"],
                    postgresql_where=sa.text("estado = 'PENDIENTE' AND canal = 'CORREO'"))
    op.create_index("ix_notificacion_entidad", "notificacion", ["entidad_tipo", "entidad_id"])
    op.create_index("ix_notificacion_usuario_interno", "notificacion", ["usuario_id", "leida_en"],
                    postgresql_where=sa.text("canal = 'INTERNO'"))
    op.create_index("ix_notificacion_creado_en", "notificacion", ["creado_en"])

    op.create_table(
        "preferencia_notificacion",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("correo", sa.Boolean(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("usuario_id", "evento", name="pk_preferencia_notificacion"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_preferencia_notificacion_usuario_id_usuario",
                                ondelete="CASCADE"),
    )

    op.add_column("cotizacion", sa.Column("avisos_activos", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("cliente", sa.Column("avisos_activos", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("contacto_cliente", sa.Column("recibir_avisos", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.bulk_insert(sa.table("permiso", sa.column("codigo"), sa.column("descripcion")),
                   [{"codigo": codigo, "descripcion": descripcion} for codigo, descripcion, _ in PERMISOS])
    for codigo, _, roles in PERMISOS:
        conexion.execute(sa.text(
            "INSERT INTO rol_permiso (rol_id, permiso_id) SELECT r.id, p.id FROM rol r JOIN permiso p ON p.codigo = :c "
            "WHERE r.codigo = ANY(:roles)"
        ), {"c": codigo, "roles": list(roles)})


def downgrade() -> None:
    conexion = op.get_bind()
    enviadas = conexion.execute(sa.text("SELECT count(*) FROM notificacion WHERE estado = 'ENVIADO' AND audiencia = 'EXTERNA'")).scalar_one()
    if enviadas:
        raise RuntimeError(f"No se revierte 0010: ya se enviaron {enviadas} avisos a clientes (la bitácora se perdería).")
    codigos = [codigo for codigo, _, _ in PERMISOS]
    conexion.execute(sa.text("DELETE FROM rol_permiso WHERE permiso_id IN (SELECT id FROM permiso WHERE codigo = ANY(:c))"),
                     {"c": codigos})
    conexion.execute(sa.text("DELETE FROM permiso WHERE codigo = ANY(:c)"), {"c": codigos})
    op.drop_column("contacto_cliente", "recibir_avisos")
    op.drop_column("cliente", "avisos_activos")
    op.drop_column("cotizacion", "avisos_activos")
    op.drop_table("preferencia_notificacion")
    op.drop_table("notificacion")
    op.drop_index("ix_regla_notificacion_evento", table_name="regla_notificacion")
    op.drop_table("regla_notificacion")
    op.drop_table("config_avisos")

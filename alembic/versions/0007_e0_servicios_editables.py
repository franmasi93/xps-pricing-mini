"""E0: servicios editables (servicio, tipo de ubicación, tramos por servicio e Incoterms por servicio).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17

Migración escrita a mano. Conserva todos los datos y valores existentes:
- tipo_ubicacion: siembra MARITIMO y AEREO con sus reglas de código actuales y TERRESTRE inactivo. puerto.tipo
  pasa a FK por código; puerto.codigo admite 10 caracteres. Se quitan ck_puerto_tipo y ck_puerto_codigo_formato.
- servicio: siembra AEREO, LCL y FCL con los textos actuales del PDF. Las columnas "modo" de tarifa, recargo y
  cotización conservan nombre y valores y pasan a FK a servicio.codigo (se quitan los CHECK por modo).
- tipo_equipo.servicio_id: los existentes quedan en FCL.
- servicio_tramo: siembra los tramos actuales de AEREO en KG y en LB. tramo_aereo.desde_kg pasa a NUMERIC(10,3)
  (mismos valores) y su CHECK fijo se reemplaza por la validación contra los tramos activos del servicio.
- incoterm_servicio: reemplaza a incoterm.solo_maritimo con el mismo comportamiento (AEREO solo en los
  Incoterms que no eran solo marítimos; LCL y FCL en todos).
- Permiso configuracion.servicios.gestionar, solo para admin.
El downgrade vuelve exactamente al esquema de 0006 y se niega (sin tocar nada) si ya hay datos que la 0006 no
puede representar (servicios o tipos de ubicación nuevos, tramos con decimales, códigos largos).
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

FORMAS_COBRO = "'PESO_TRAMOS', 'VOLUMEN_WM', 'UNIDAD_EQUIPO', 'TARIFA_PLANA'"
MODOS = "'AEREO', 'LCL', 'FCL'"
DESDE_0005 = "0, 45, 100, 220, 300, 500, 660, 1000, 1100, 2200"
TIPOS_UBICACION = [
    # codigo, nombre, regex, ayuda, prefijo_pais, activo
    ("MARITIMO", "Puerto marítimo", "^[A-Z]{2}[A-Z0-9]{3}$", "Un puerto marítimo usa UN/LOCODE: 5 caracteres, como ECGYE",
     True, True),
    ("AEREO", "Aeropuerto", "^[A-Z]{3}$", "Un aeropuerto usa el código IATA: 3 letras, como GYE", False, True),
    ("TERRESTRE", "Terminal terrestre", None, "Código de la ciudad o terminal: de 2 a 10 letras o números", False, False),
]
SERVICIOS = [
    # codigo, nombre, forma, origen, destino, usa_tipo_equipo, permite_libras, orden, descripcion_pdf, etiqueta, aviso
    ("AEREO", "Aéreo", "PESO_TRAMOS", "AEREO", "AEREO", False, True, 10, "vía aérea", "Aerolínea",
     "es solo marítimo. Para aéreo use FCA, CPT o CIP"),
    ("LCL", "Marítimo LCL", "VOLUMEN_WM", "MARITIMO", "MARITIMO", False, False, 20,
     "vía marítima · carga consolidada (LCL)", "Naviera / Motonave", None),
    ("FCL", "Marítimo FCL", "UNIDAD_EQUIPO", "MARITIMO", "MARITIMO", True, False, 30,
     "vía marítima · contenedor completo (FCL)", "Naviera / Motonave", None),
]
TRAMOS_AEREO = {"KG": (0, 45, 100, 300, 500, 1000), "LB": (0, 100, 220, 660, 1100, 2200)}
PERMISO = ("configuracion.servicios.gestionar", "Gestionar servicios, sus tramos de peso y los tipos de ubicación")


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def _columnas_catalogo(tabla: str) -> list:
    """activo, creado_en, actualizado_en y creado_por, igual que en 0002 y 0003."""
    return [
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["creado_por"], ["usuario.id"], name=f"fk_{tabla}_creado_por_usuario"),
    ]


def upgrade() -> None:
    # --- Tipos de ubicación ---
    op.create_table(
        "tipo_ubicacion",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("regex_codigo", sa.Text(), nullable=True),
        sa.Column("ayuda_codigo", sa.String(200), nullable=True),
        sa.Column("prefijo_pais", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_columnas_catalogo("tipo_ubicacion"),
        sa.PrimaryKeyConstraint("id", name="pk_tipo_ubicacion"),
        sa.UniqueConstraint("codigo", name="uq_tipo_ubicacion_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{1,9}$'", name="ck_tipo_ubicacion_codigo_formato"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_tipo_ubicacion_nombre_no_vacio"),
    )
    tabla_ubicacion = sa.table(
        "tipo_ubicacion", sa.column("codigo"), sa.column("nombre"), sa.column("regex_codigo"),
        sa.column("ayuda_codigo"), sa.column("prefijo_pais"), sa.column("activo"),
    )
    op.bulk_insert(tabla_ubicacion, [
        {"codigo": c, "nombre": n, "regex_codigo": r, "ayuda_codigo": a, "prefijo_pais": p, "activo": act}
        for c, n, r, a, p, act in TIPOS_UBICACION
    ])
    op.drop_constraint("ck_puerto_codigo_formato", "puerto", type_="check")
    op.drop_constraint("ck_puerto_tipo", "puerto", type_="check")
    op.alter_column("puerto", "codigo", type_=sa.String(10), existing_type=sa.String(5), existing_nullable=False)
    op.create_foreign_key(
        "fk_puerto_tipo_tipo_ubicacion", "puerto", "tipo_ubicacion", ["tipo"], ["codigo"], ondelete="RESTRICT"
    )

    # --- Servicios ---
    op.create_table(
        "servicio",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("forma_cobro", sa.String(20), nullable=False),
        sa.Column("tipo_ubicacion_origen", sa.String(10), nullable=False),
        sa.Column("tipo_ubicacion_destino", sa.String(10), nullable=False),
        sa.Column("usa_tipo_equipo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permite_libras", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("descripcion_pdf", sa.String(120), nullable=False),
        sa.Column("etiqueta_transportista", sa.String(40), nullable=False),
        sa.Column("aviso_incoterm", sa.String(200), nullable=True),
        *_columnas_catalogo("servicio"),
        sa.PrimaryKeyConstraint("id", name="pk_servicio"),
        sa.UniqueConstraint("codigo", name="uq_servicio_codigo"),
        sa.CheckConstraint("codigo ~ '^[A-Z][A-Z0-9_]{1,9}$'", name="ck_servicio_codigo_formato"),
        sa.CheckConstraint("btrim(nombre) <> ''", name="ck_servicio_nombre_no_vacio"),
        sa.CheckConstraint(f"forma_cobro IN ({FORMAS_COBRO})", name="ck_servicio_forma_cobro"),
        sa.CheckConstraint("(forma_cobro = 'UNIDAD_EQUIPO') = usa_tipo_equipo", name="ck_servicio_tipo_equipo_segun_forma"),
        sa.CheckConstraint("NOT permite_libras OR forma_cobro = 'PESO_TRAMOS'", name="ck_servicio_libras_solo_por_peso"),
        sa.CheckConstraint("orden BETWEEN 0 AND 999", name="ck_servicio_orden"),
        sa.ForeignKeyConstraint(["tipo_ubicacion_origen"], ["tipo_ubicacion.codigo"],
                                name="fk_servicio_tipo_ubicacion_origen_tipo_ubicacion", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tipo_ubicacion_destino"], ["tipo_ubicacion.codigo"],
                                name="fk_servicio_tipo_ubicacion_destino_tipo_ubicacion", ondelete="RESTRICT"),
    )
    tabla_servicio = sa.table(
        "servicio", sa.column("codigo"), sa.column("nombre"), sa.column("forma_cobro"),
        sa.column("tipo_ubicacion_origen"), sa.column("tipo_ubicacion_destino"), sa.column("usa_tipo_equipo"),
        sa.column("permite_libras"), sa.column("orden"), sa.column("descripcion_pdf"),
        sa.column("etiqueta_transportista"), sa.column("aviso_incoterm"),
    )
    op.bulk_insert(tabla_servicio, [
        {"codigo": c, "nombre": n, "forma_cobro": f, "tipo_ubicacion_origen": o, "tipo_ubicacion_destino": d,
         "usa_tipo_equipo": e, "permite_libras": lb, "orden": orden, "descripcion_pdf": pdf,
         "etiqueta_transportista": et, "aviso_incoterm": av}
        for c, n, f, o, d, e, lb, orden, pdf, et, av in SERVICIOS
    ])

    # --- Tipo de equipo → servicio (los existentes quedan en FCL) ---
    op.add_column("tipo_equipo", sa.Column("servicio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE tipo_equipo SET servicio_id = (SELECT id FROM servicio WHERE codigo = 'FCL')")
    op.alter_column("tipo_equipo", "servicio_id", nullable=False, existing_type=sa.Integer())
    op.create_foreign_key(
        "fk_tipo_equipo_servicio_id_servicio", "tipo_equipo", "servicio", ["servicio_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_tipo_equipo_servicio_id", "tipo_equipo", ["servicio_id"])

    # --- Tramos por servicio ---
    op.create_table(
        "servicio_tramo",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.Column("unidad_peso", sa.String(2), nullable=False),
        sa.Column("desde", sa.Numeric(10, 3), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False, server_default="0"),
        *_columnas_catalogo("servicio_tramo"),
        sa.PrimaryKeyConstraint("id", name="pk_servicio_tramo"),
        sa.UniqueConstraint("servicio_id", "unidad_peso", "desde", name="uq_servicio_tramo_servicio_unidad_desde"),
        sa.CheckConstraint("unidad_peso IN ('KG', 'LB')", name="ck_servicio_tramo_unidad_peso"),
        sa.CheckConstraint("desde >= 0", name="ck_servicio_tramo_desde_no_negativo"),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"], name="fk_servicio_tramo_servicio_id_servicio",
                                ondelete="RESTRICT"),
    )
    op.create_index("ix_servicio_tramo_servicio_id", "servicio_tramo", ["servicio_id"])
    for unidad, desdes in TRAMOS_AEREO.items():
        for orden, desde in enumerate(desdes, start=1):
            op.execute(
                sa.text(
                    "INSERT INTO servicio_tramo (servicio_id, unidad_peso, desde, orden) "
                    "SELECT id, :unidad, :desde, :orden FROM servicio WHERE codigo = 'AEREO'"
                ).bindparams(unidad=unidad, desde=desde, orden=orden * 10)
            )
    op.drop_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", type_="check")
    op.alter_column(
        "tramo_aereo", "desde_kg", type_=sa.Numeric(10, 3), existing_type=sa.SmallInteger(),
        existing_nullable=False, postgresql_using="desde_kg::numeric(10,3)",
    )
    op.create_check_constraint("ck_tramo_aereo_desde_no_negativo", "tramo_aereo", "desde_kg >= 0")

    # --- Incoterms por servicio (reemplaza solo_maritimo) ---
    op.create_table(
        "incoterm_servicio",
        sa.Column("incoterm_id", sa.Integer(), nullable=False),
        sa.Column("servicio_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("incoterm_id", "servicio_id", name="pk_incoterm_servicio"),
        sa.ForeignKeyConstraint(["incoterm_id"], ["incoterm.id"], name="fk_incoterm_servicio_incoterm_id_incoterm",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["servicio_id"], ["servicio.id"], name="fk_incoterm_servicio_servicio_id_servicio",
                                ondelete="CASCADE"),
    )
    op.execute(
        "INSERT INTO incoterm_servicio (incoterm_id, servicio_id) "
        "SELECT i.id, s.id FROM incoterm i CROSS JOIN servicio s "
        "WHERE s.codigo IN ('LCL', 'FCL') OR (s.codigo = 'AEREO' AND NOT i.solo_maritimo)"
    )
    op.drop_column("incoterm", "solo_maritimo")

    # --- Columnas "modo" → FK a servicio.codigo ---
    for constraint, tabla in (
        ("ck_tarifa_modo", "tarifa"),
        ("ck_tarifa_tipo_equipo_segun_modo", "tarifa"),
        ("ck_tarifa_rate_unit_segun_modo", "tarifa"),
        ("ck_tarifa_lb_solo_aereo_por_peso", "tarifa"),
        ("ck_recargo_modo", "recargo"),
        ("ck_recargo_tipo_equipo_solo_fcl", "recargo"),
        ("ck_recargo_contenedor_solo_fcl", "recargo"),
        ("ck_cotizacion_modo", "cotizacion"),
    ):
        op.drop_constraint(constraint, tabla, type_="check")
    for tabla, nula in (("tarifa", False), ("recargo", True), ("cotizacion", False)):
        op.alter_column(tabla, "modo", type_=sa.String(10), existing_type=sa.String(5), existing_nullable=nula)
        op.create_foreign_key(f"fk_{tabla}_modo_servicio", tabla, "servicio", ["modo"], ["codigo"], ondelete="RESTRICT")
    # Respaldo genérico en la base: el tipo de equipo y la unidad CONTENEDOR siempre van con un servicio.
    op.create_check_constraint(
        "ck_recargo_tipo_equipo_con_servicio", "recargo", "tipo_equipo_id IS NULL OR modo IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_recargo_contenedor_con_servicio", "recargo", "rate_unit <> 'CONTENEDOR' OR modo IS NOT NULL"
    )

    # --- Permiso nuevo (solo admin) ---
    op.execute(
        sa.text("INSERT INTO permiso (codigo, descripcion) VALUES (:codigo, :descripcion)").bindparams(
            codigo=PERMISO[0], descripcion=PERMISO[1]
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO rol_permiso (rol_id, permiso_id) "
            "SELECT r.id, p.id FROM rol r JOIN permiso p ON p.codigo = :codigo WHERE r.codigo = 'admin'"
        ).bindparams(codigo=PERMISO[0])
    )


def _exigir(conexion, consulta: str, motivo: str) -> None:
    cantidad = conexion.execute(sa.text(consulta)).scalar_one()
    if cantidad:
        raise RuntimeError(
            f"Downgrade de 0007 rechazado sin cambios: {cantidad} {motivo}. La 0006 no puede representarlo; "
            "restaure el respaldo previo a la migración si necesita volver."
        )


def downgrade() -> None:
    conexion = op.get_bind()
    _exigir(conexion, f"SELECT count(*) FROM servicio WHERE codigo NOT IN ({MODOS})", "servicio(s) nuevos")
    _exigir(conexion, "SELECT count(*) FROM tipo_ubicacion WHERE codigo NOT IN ('MARITIMO', 'AEREO', 'TERRESTRE')",
            "tipo(s) de ubicación nuevos")
    _exigir(conexion, "SELECT count(*) FROM puerto WHERE tipo NOT IN ('MARITIMO', 'AEREO') OR length(codigo) > 5",
            "puerto(s) de un tipo nuevo o con código largo")
    _exigir(conexion, f"SELECT count(*) FROM tramo_aereo WHERE desde_kg NOT IN ({DESDE_0005})",
            "tramo(s) con un desde que la 0006 no admite")
    _exigir(conexion, "SELECT count(*) FROM tipo_equipo t JOIN servicio s ON s.id = t.servicio_id WHERE s.codigo <> 'FCL'",
            "tipo(s) de equipo de otro servicio")

    op.execute(
        sa.text(
            "DELETE FROM rol_permiso WHERE permiso_id IN (SELECT id FROM permiso WHERE codigo = :codigo)"
        ).bindparams(codigo=PERMISO[0])
    )
    op.execute(sa.text("DELETE FROM permiso WHERE codigo = :codigo").bindparams(codigo=PERMISO[0]))

    op.drop_constraint("ck_recargo_contenedor_con_servicio", "recargo", type_="check")
    op.drop_constraint("ck_recargo_tipo_equipo_con_servicio", "recargo", type_="check")
    for tabla, nula in (("cotizacion", False), ("recargo", True), ("tarifa", False)):
        op.drop_constraint(f"fk_{tabla}_modo_servicio", tabla, type_="foreignkey")
        op.alter_column(tabla, "modo", type_=sa.String(5), existing_type=sa.String(10), existing_nullable=nula)
    op.create_check_constraint("ck_cotizacion_modo", "cotizacion", f"modo IN ({MODOS})")
    op.create_check_constraint(
        "ck_recargo_contenedor_solo_fcl", "recargo", "rate_unit <> 'CONTENEDOR' OR modo IS NOT DISTINCT FROM 'FCL'"
    )
    op.create_check_constraint(
        "ck_recargo_tipo_equipo_solo_fcl", "recargo", "tipo_equipo_id IS NULL OR modo IS NOT DISTINCT FROM 'FCL'"
    )
    op.create_check_constraint("ck_recargo_modo", "recargo", f"modo IS NULL OR modo IN ({MODOS})")
    op.create_check_constraint(
        "ck_tarifa_lb_solo_aereo_por_peso", "tarifa", "unidad_peso = 'KG' OR (modo = 'AEREO' AND rate_unit = 'KG')"
    )
    op.create_check_constraint(
        "ck_tarifa_rate_unit_segun_modo",
        "tarifa",
        "(modo = 'AEREO' AND rate_unit IN ('KG', 'ENVIO'))"
        " OR (modo = 'LCL' AND rate_unit IN ('WM', 'CBM', 'ENVIO'))"
        " OR (modo = 'FCL' AND rate_unit = 'CONTENEDOR')",
    )
    op.create_check_constraint(
        "ck_tarifa_tipo_equipo_segun_modo", "tarifa", "(modo = 'FCL') = (tipo_equipo_id IS NOT NULL)"
    )
    op.create_check_constraint("ck_tarifa_modo", "tarifa", f"modo IN ({MODOS})")

    op.add_column("incoterm", sa.Column("solo_maritimo", sa.Boolean(), nullable=True))
    op.execute(
        "UPDATE incoterm i SET solo_maritimo = NOT EXISTS ("
        "SELECT 1 FROM incoterm_servicio x JOIN servicio s ON s.id = x.servicio_id "
        "WHERE x.incoterm_id = i.id AND s.codigo = 'AEREO')"
    )
    op.alter_column("incoterm", "solo_maritimo", nullable=False, existing_type=sa.Boolean())
    op.drop_table("incoterm_servicio")

    op.drop_constraint("ck_tramo_aereo_desde_no_negativo", "tramo_aereo", type_="check")
    op.alter_column(
        "tramo_aereo", "desde_kg", type_=sa.SmallInteger(), existing_type=sa.Numeric(10, 3),
        existing_nullable=False, postgresql_using="desde_kg::smallint",
    )
    op.create_check_constraint("ck_tramo_aereo_desde_kg_permitido", "tramo_aereo", f"desde_kg IN ({DESDE_0005})")
    op.drop_index("ix_servicio_tramo_servicio_id", table_name="servicio_tramo")
    op.drop_table("servicio_tramo")

    op.drop_index("ix_tipo_equipo_servicio_id", table_name="tipo_equipo")
    op.drop_constraint("fk_tipo_equipo_servicio_id_servicio", "tipo_equipo", type_="foreignkey")
    op.drop_column("tipo_equipo", "servicio_id")
    op.drop_table("servicio")

    op.drop_constraint("fk_puerto_tipo_tipo_ubicacion", "puerto", type_="foreignkey")
    op.alter_column("puerto", "codigo", type_=sa.String(5), existing_type=sa.String(10), existing_nullable=False)
    op.create_check_constraint("ck_puerto_tipo", "puerto", "tipo IN ('MARITIMO', 'AEREO')")
    op.create_check_constraint(
        "ck_puerto_codigo_formato",
        "puerto",
        "(tipo = 'MARITIMO' AND codigo ~ '^[A-Z]{2}[A-Z0-9]{3}$') OR (tipo = 'AEREO' AND codigo ~ '^[A-Z]{3}$')",
    )
    op.drop_table("tipo_ubicacion")

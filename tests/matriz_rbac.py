"""Matriz de permisos ESPERADA, copiada de §6.2 del documento rector.

Se escribe aparte (no se importa de la migración) para que el test compare dos
fuentes independientes.
"""
PERMISOS_6_2 = {
    "usuario.admin",
    "config.editar",
    "catalogo.editar",
    "tarifa.ver",
    "tarifa.editar",
    "costo.ver",
    "margen.ver",
    "tasa.editar",
    "cliente.ver",
    "cliente.editar",
    "cotizacion.crear",
    "cotizacion.emitir",
    "cotizacion.enviar",
    "cotizacion.ver_todas",
    "auditoria.ver",
}

MATRIZ_6_2 = {
    "admin": set(PERMISOS_6_2),
    "pricing": {
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
    },
    "comercial": {
        "tarifa.ver",
        "cliente.ver",
        "cliente.editar",
        "cotizacion.crear",
        "cotizacion.emitir",
        "cotizacion.enviar",
    },
    "gerencia": {
        "tarifa.ver",
        "costo.ver",
        "margen.ver",
        "cliente.ver",
        "cotizacion.ver_todas",
        "auditoria.ver",
    },
}

# Desvío D-E0-1: permisos que agregan las extensiones (E0–E3), fuera de §6.2: {código: roles que lo tienen}.
# Las pruebas de §6.2 los excluyen (la matriz §6.2 sigue idéntica) y test_e0_servicios verifica estos aparte.
PERMISOS_EXTENSIONES = {
    "configuracion.servicios.gestionar": {"admin"},
}


def sin_extensiones(matriz: dict[str, set[str]]) -> dict[str, set[str]]:
    return {rol: permisos - set(PERMISOS_EXTENSIONES) for rol, permisos in matriz.items()}


def conteo_rbac_base(db_session) -> tuple[int, int, int]:
    """(roles, permisos, asignaciones) sin los permisos de las extensiones."""
    from sqlalchemy import text

    extensiones = {"codigos": list(PERMISOS_EXTENSIONES)}
    roles = db_session.execute(text("SELECT COUNT(*) FROM rol")).scalar_one()
    permisos = db_session.execute(
        text("SELECT COUNT(*) FROM permiso WHERE NOT (codigo = ANY(:codigos))"), extensiones
    ).scalar_one()
    asignaciones = db_session.execute(
        text(
            "SELECT COUNT(*) FROM rol_permiso rp JOIN permiso p ON p.id = rp.permiso_id "
            "WHERE NOT (p.codigo = ANY(:codigos))"
        ),
        extensiones,
    ).scalar_one()
    return roles, permisos, asignaciones

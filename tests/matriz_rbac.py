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

"""Errores de negocio y traducción de IntegrityError a 409/422 (nunca 500).

Formato de respuesta: {"detail": {"codigo": "...", "mensaje": "...", ...datos extra}}
"""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

MENSAJES_POR_CONSTRAINT = {
    "uq_usuario_email_lower": (409, "EMAIL_DUPLICADO", "Ya existe un usuario con ese email"),
    "uq_region_codigo": (409, "REGION_DUPLICADA", "Ya existe una región con ese código"),
    "uq_pais_iso2": (409, "PAIS_DUPLICADO", "Ya existe un país con ese código ISO"),
    "uq_puerto_codigo": (409, "PUERTO_DUPLICADO", "Ya existe un puerto con ese código"),
    "uq_moneda_codigo": (409, "MONEDA_DUPLICADA", "Ya existe una moneda con ese código"),
    "uq_tasa_cambio_moneda_fecha": (
        409,
        "TASA_DUPLICADA",
        "Ya existe una tasa para esa moneda en esa fecha; corríjala en lugar de crear otra",
    ),
    "uq_proveedor_nombre_lower": (409, "PROVEEDOR_DUPLICADO", "Ya existe un proveedor con ese nombre"),
    "uq_tipo_equipo_codigo": (409, "TIPO_EQUIPO_DUPLICADO", "Ya existe un tipo de equipo con ese código"),
    # D-F2-7: sin revelar la razón social ni el comercial del cliente existente.
    "uq_cliente_tipo_identificacion": (
        409,
        "CLIENTE_DUPLICADO",
        "Ya existe un cliente con esa identificación; solicite su asignación al administrador",
    ),
    "uq_contacto_cliente_principal": (409, "PRINCIPAL_DUPLICADO", "El cliente ya tiene un contacto principal"),
    "uq_cotizacion_numero": (409, "NUMERO_DUPLICADO", "El número de cotización ya existe; intente emitir de nuevo"),
    "uq_cotizacion_contenedor_cotizacion_tipo": (422, "CONTENEDOR_DUPLICADO", "Cada tipo de contenedor va una sola vez"),
    "uq_linea_cotizacion_cotizacion_orden": (409, "ORDEN_DUPLICADO", "Ya existe una línea con ese orden"),
    "ex_tarifa_vigencia_sin_superposicion": (
        409,
        "VIGENCIA_SUPERPUESTA",
        "La vigencia se superpone con otra tarifa activa con la misma clave",
    ),
    "ex_recargo_vigencia_sin_superposicion": (
        409,
        "VIGENCIA_SUPERPUESTA",
        "La vigencia se superpone con otro recargo activo con la misma clave",
    ),
}
SQLSTATE_EXCLUSION = "23P01"  # exclusion_violation (D-F2-1)


class ErrorNegocio(Exception):
    def __init__(
        self,
        status_code: int,
        codigo: str,
        mensaje: str,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(mensaje)
        self.status_code = status_code
        self.codigo = codigo
        self.mensaje = mensaje
        self.headers = headers
        self.extra = extra or {}


def traducir_integrity_error(exc: IntegrityError) -> ErrorNegocio:
    diag = getattr(exc.orig, "diag", None)
    nombre = getattr(diag, "constraint_name", None) or ""
    if nombre in MENSAJES_POR_CONSTRAINT:
        return ErrorNegocio(*MENSAJES_POR_CONSTRAINT[nombre])
    if getattr(exc.orig, "sqlstate", None) == SQLSTATE_EXCLUSION:
        return ErrorNegocio(409, "VIGENCIA_SUPERPUESTA", "La vigencia se superpone con otro registro activo")
    if nombre.startswith("uq_") or nombre.startswith("pk_"):
        return ErrorNegocio(409, "DUPLICADO", "Ya existe un registro con esos datos")
    return ErrorNegocio(422, "DATOS_INVALIDOS", "Los datos no cumplen las reglas de la base de datos")


def confirmar(db: Session) -> None:
    """Commit que traduce IntegrityError a ErrorNegocio."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise traducir_integrity_error(exc) from None


def enviar(db: Session) -> None:
    """Flush que traduce IntegrityError (para obtener IDs antes de auditar, sin cerrar la transacción)."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise traducir_integrity_error(exc) from None


# D-AUT-7: la base se apaga fuera del horario (L–V 07:00–20:00). Una falla de CONEXIÓN no es un 500.
HORARIO_SISTEMA = "lunes a viernes de 07:00 a 20:00 (hora de Ecuador)"
SQLSTATE_CONEXION = ("08", "57P01", "57P02", "57P03")  # clase 08 y apagado o arranque del servidor


def es_falla_de_conexion(exc: DBAPIError) -> bool:
    """Solo fallas de conexión: sin conexión, conexión rota o servidor apagándose. Un deadlock u otro error
    operativo de una consulta sigue siendo un error del sistema."""
    if exc.connection_invalidated:
        return True
    estado = getattr(exc.orig, "sqlstate", None)
    if estado is None:
        return isinstance(exc, OperationalError)
    return estado.startswith(SQLSTATE_CONEXION[0]) or estado in SQLSTATE_CONEXION[1:]


def fuera_de_horario() -> "ErrorNegocio":
    return ErrorNegocio(
        503,
        "SISTEMA_FUERA_DE_HORARIO",
        f"Sistema fuera de horario: atiende {HORARIO_SISTEMA}. Si es horario de atención, intente de nuevo en unos minutos.",
        headers={"Retry-After": "300"},
        extra={"horario": HORARIO_SISTEMA},
    )


def _respuesta(error: ErrorNegocio) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"codigo": error.codigo, "mensaje": error.mensaje, **error.extra}},
        headers=error.headers,
    )


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorNegocio)
    async def _manejar_error_negocio(request: Request, exc: ErrorNegocio) -> JSONResponse:
        return _respuesta(exc)

    @app.exception_handler(IntegrityError)
    async def _manejar_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return _respuesta(traducir_integrity_error(exc))

    @app.exception_handler(DBAPIError)
    async def _manejar_falla_bd(request: Request, exc: DBAPIError) -> JSONResponse:
        if es_falla_de_conexion(exc):
            return _respuesta(fuera_de_horario())
        raise exc

    @app.exception_handler(StarletteHTTPException)
    async def _manejar_http(request: Request, exc: StarletteHTTPException):
        # Sin DELETE en ningún recurso: la baja es activo=false.
        if exc.status_code == 405:
            return _respuesta(
                ErrorNegocio(405, "METODO_NO_PERMITIDO", "Método no permitido", headers=exc.headers)
            )
        return await http_exception_handler(request, exc)

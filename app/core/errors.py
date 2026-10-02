"""Errores de negocio y traducción de IntegrityError a 409/422 (nunca 500).

Formato de respuesta: {"detail": {"codigo": "...", "mensaje": "..."}}
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MENSAJES_POR_CONSTRAINT = {
    "uq_usuario_email_lower": (409, "EMAIL_DUPLICADO", "Ya existe un usuario con ese email"),
}


class ErrorNegocio(Exception):
    def __init__(self, status_code: int, codigo: str, mensaje: str, headers: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.status_code = status_code
        self.codigo = codigo
        self.mensaje = mensaje
        self.headers = headers


def traducir_integrity_error(exc: IntegrityError) -> ErrorNegocio:
    diag = getattr(exc.orig, "diag", None)
    nombre = getattr(diag, "constraint_name", None) or ""
    if nombre in MENSAJES_POR_CONSTRAINT:
        return ErrorNegocio(*MENSAJES_POR_CONSTRAINT[nombre])
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


def _respuesta(error: ErrorNegocio) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"codigo": error.codigo, "mensaje": error.mensaje}},
        headers=error.headers,
    )


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorNegocio)
    async def _manejar_error_negocio(request: Request, exc: ErrorNegocio) -> JSONResponse:
        return _respuesta(exc)

    @app.exception_handler(IntegrityError)
    async def _manejar_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return _respuesta(traducir_integrity_error(exc))

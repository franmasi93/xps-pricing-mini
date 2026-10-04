"""Autenticación por token y control de acceso por permisos (RBAC).

Los permisos se leen de la BD (rol -> rol_permiso -> permiso); no hay matriz en código.
"""
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio
from app.core.security import decodificar_token
from app.db import get_db
from app.models import Usuario

_bearer = HTTPBearer(auto_error=False)


def _token_invalido() -> ErrorNegocio:
    return ErrorNegocio(
        401,
        "TOKEN_INVALIDO",
        "Sesión inválida o expirada; inicie sesión nuevamente",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    """Token válido + usuario existente, activo y con token_version vigente. Si no, 401."""
    if credenciales is None:
        raise _token_invalido()
    try:
        payload = decodificar_token(credenciales.credentials)
        usuario_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise _token_invalido() from None
    version = payload["tv"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise _token_invalido()
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or usuario.token_version != version:
        raise _token_invalido()
    return usuario


def get_usuario_habilitado(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
    """Como get_usuario_actual, pero bloquea a quien debe cambiar su contraseña."""
    if usuario.forzar_cambio_password:
        raise ErrorNegocio(
            403, "PASSWORD_CAMBIO_REQUERIDO", "Debe cambiar su contraseña antes de continuar"
        )
    return usuario


def permisos_de(usuario: Usuario) -> set[str]:
    return {permiso.codigo for permiso in usuario.rol.permisos}


def tiene_permiso(usuario: Usuario, codigo: str) -> bool:
    """Gating en services (se usará desde M5)."""
    return codigo in permisos_de(usuario)


def _permiso_denegado() -> ErrorNegocio:
    return ErrorNegocio(403, "PERMISO_DENEGADO", "No tiene permiso para esta acción")


def require_permiso(codigo: str) -> Callable[..., Usuario]:
    """Dependencia para routers: exige usuario habilitado con el permiso indicado."""

    def _dependencia(usuario: Usuario = Depends(get_usuario_habilitado)) -> Usuario:
        if not tiene_permiso(usuario, codigo):
            raise _permiso_denegado()
        return usuario

    return _dependencia


def require_alguno_permiso(*codigos: str) -> Callable[..., Usuario]:
    """Dependencia para routers: exige al menos uno de los permisos indicados."""

    def _dependencia(usuario: Usuario = Depends(get_usuario_habilitado)) -> Usuario:
        if permisos_de(usuario).isdisjoint(codigos):
            raise _permiso_denegado()
        return usuario

    return _dependencia


def exigir_permiso(usuario: Usuario, codigo: str) -> None:
    """Gating en services cuando el permiso depende del dato (por ejemplo, la clave de configuración)."""
    if not tiene_permiso(usuario, codigo):
        raise _permiso_denegado()

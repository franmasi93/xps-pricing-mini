"""Usuarios: sin DELETE (la baja es activo=false). Rutas fijas antes de /{usuario_id}."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.usuarios import RestablecerPassword, UsuarioActualizar, UsuarioCrear, UsuarioSalida
from app.services import usuarios as servicio

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

solo_admin = require_permiso("usuario.admin")


@router.get("", response_model=list[UsuarioSalida])
def listar(
    activo: bool | None = None,
    rol: str | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(solo_admin),
):
    return servicio.listar_usuarios(db, activo=activo, rol_codigo=rol)


@router.post("", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioCrear, db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    return servicio.crear_usuario(
        db, actor, datos.email, datos.nombre, datos.rol_codigo, datos.password_temporal
    )


@router.get("/{usuario_id}", response_model=UsuarioSalida)
def detalle(usuario_id: int, db: Session = Depends(get_db), _: Usuario = Depends(solo_admin)):
    return servicio.obtener_usuario(db, usuario_id)


@router.patch("/{usuario_id}", response_model=UsuarioSalida)
def actualizar(
    usuario_id: int,
    datos: UsuarioActualizar,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(solo_admin),
):
    return servicio.actualizar_usuario(db, actor, usuario_id, datos.model_dump(exclude_unset=True))


@router.post("/{usuario_id}/restablecer-password", response_model=UsuarioSalida)
def restablecer_password(
    usuario_id: int,
    datos: RestablecerPassword,
    db: Session = Depends(get_db),
    _: Usuario = Depends(solo_admin),
):
    return servicio.restablecer_password(db, usuario_id, datos.password_temporal)

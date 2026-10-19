"""Roles y su matriz de permisos (E2: editables por usuario.admin)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.models import Rol, Usuario
from app.schemas.administracion import PermisoSalida, RolActualizar, RolCrear, RolDetalle
from app.services import administracion

router = APIRouter(prefix="/roles", tags=["roles"])
admin = require_permiso("usuario.admin")


def _detalle(db: Session, roles: list[Rol]) -> list[RolDetalle]:
    conteo = administracion.usuarios_por_rol(db)
    return [
        RolDetalle.model_validate(rol).model_copy(update={"usuarios_activos": conteo.get(rol.id, 0)}) for rol in roles
    ]


@router.get("", response_model=list[RolDetalle], dependencies=[Depends(admin)])
def listar(activo: bool | None = None, db: Session = Depends(get_db)):
    return _detalle(db, administracion.listar_roles(db, activo=activo))


@router.get("/permisos", response_model=list[PermisoSalida], dependencies=[Depends(admin)])
def listar_permisos(db: Session = Depends(get_db)):
    return administracion.listar_permisos(db)


@router.post("", response_model=RolDetalle, status_code=status.HTTP_201_CREATED)
def crear(datos: RolCrear, db: Session = Depends(get_db), actor: Usuario = Depends(admin)):
    return _detalle(db, [administracion.crear_rol(db, actor, datos.model_dump())])[0]


@router.patch("/{rol_id}", response_model=RolDetalle)
def actualizar(rol_id: int, datos: RolActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(admin)):
    return _detalle(db, [administracion.actualizar_rol(db, actor, rol_id, datos.model_dump(exclude_unset=True))])[0]

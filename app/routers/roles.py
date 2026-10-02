from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.schemas.usuarios import RolSalida
from app.services.roles import listar_roles

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RolSalida], dependencies=[Depends(require_permiso("usuario.admin"))])
def listar(db: Session = Depends(get_db)):
    return listar_roles(db)

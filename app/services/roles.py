"""Roles con sus permisos (solo lectura)."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Rol


def listar_roles(db: Session) -> list[Rol]:
    return list(db.scalars(select(Rol).options(selectinload(Rol.permisos)).order_by(Rol.id)))

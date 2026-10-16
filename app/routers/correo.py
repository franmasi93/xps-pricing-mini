"""Administración del correo Tencent (B3 de F4). Todo exige usuario.admin. Las llaves nunca salen en claro."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.correo import ConfigCorreoEntrada, EnviarPruebaEntrada
from app.services import correo as servicio

router = APIRouter(prefix="/correo", tags=["correo"])

solo_admin = require_permiso("usuario.admin")


@router.get("/config", response_model=None)
def leer_config(db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    return servicio.presentar_config(db)


@router.put("/config", response_model=None)
def guardar_config(datos: ConfigCorreoEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    """Con habilitado=true valida contra Tencent ANTES de guardar; si falla, 422 y no guarda."""
    return servicio.actualizar_config(db, actor, datos.model_dump(exclude_unset=True))


@router.post("/probar", response_model=None)
def probar(refrescar: bool = False, db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    """B10: chequeo de salud con caché de 10 minutos."""
    return servicio.salud(db, refrescar=refrescar)


@router.get("/plantillas", response_model=None)
def plantillas(db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    return servicio.plantillas(db)


@router.post("/enviar-prueba", response_model=None)
def enviar_prueba(datos: EnviarPruebaEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(solo_admin)):
    return servicio.enviar_prueba(db, actor, datos.email)

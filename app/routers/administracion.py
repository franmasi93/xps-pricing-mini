"""E2: motivos de rechazo, tipos de identificación y textos del PDF.

Las listas las lee cualquier usuario habilitado (las usan las pantallas); las edita config.editar (hoy, el administrador).
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.administracion import (
    MotivoRechazoActualizar,
    MotivoRechazoCrear,
    MotivoRechazoSalida,
    SistemaActualizar,
    TextosPdf,
    TextosPdfActualizar,
    TipoIdentificacionActualizar,
    TipoIdentificacionCrear,
    TipoIdentificacionSalida,
)
from app.services import administracion, sistema

router = APIRouter(tags=["administracion"])
editor = require_permiso("config.editar")
lector = [Depends(get_usuario_habilitado)]


@router.get("/motivos-rechazo", response_model=list[MotivoRechazoSalida], dependencies=lector)
def listar_motivos(activo: bool | None = None, db: Session = Depends(get_db)):
    return administracion.listar_motivos(db, activo=activo)


@router.post("/motivos-rechazo", response_model=MotivoRechazoSalida, status_code=status.HTTP_201_CREATED)
def crear_motivo(datos: MotivoRechazoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return administracion.crear_motivo(db, actor, datos.model_dump())


@router.patch("/motivos-rechazo/{motivo_id}", response_model=MotivoRechazoSalida)
def actualizar_motivo(
    motivo_id: int, datos: MotivoRechazoActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return administracion.actualizar_motivo(db, actor, motivo_id, datos.model_dump(exclude_unset=True))


@router.get("/tipos-identificacion", response_model=list[TipoIdentificacionSalida], dependencies=lector)
def listar_tipos(activo: bool | None = None, db: Session = Depends(get_db)):
    return administracion.listar_tipos_identificacion(db, activo=activo)


@router.post("/tipos-identificacion", response_model=TipoIdentificacionSalida, status_code=status.HTTP_201_CREATED)
def crear_tipo(datos: TipoIdentificacionCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return administracion.crear_tipo_identificacion(db, actor, datos.model_dump())


@router.patch("/tipos-identificacion/{tipo_id}", response_model=TipoIdentificacionSalida)
def actualizar_tipo(
    tipo_id: int, datos: TipoIdentificacionActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return administracion.actualizar_tipo_identificacion(db, actor, tipo_id, datos.model_dump(exclude_unset=True))


@router.get("/configuracion/sistema", tags=["configuracion"], dependencies=[Depends(editor)])
def leer_sistema(db: Session = Depends(get_db)):
    """E4: URL pública del sistema (con la que se arman todos los enlaces)."""
    return sistema.presentar(db)


@router.put("/configuracion/sistema", tags=["configuracion"])
def guardar_sistema(datos: SistemaActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return sistema.actualizar(db, actor, datos.model_dump(exclude_unset=True))


@router.get("/textos-pdf", response_model=TextosPdf, dependencies=[Depends(editor)])
def leer_textos(db: Session = Depends(get_db)):
    return administracion.textos_pdf(db)


@router.put("/textos-pdf", response_model=TextosPdf)
def guardar_textos(datos: TextosPdfActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return administracion.actualizar_textos_pdf(db, actor, datos.model_dump(exclude_unset=True))

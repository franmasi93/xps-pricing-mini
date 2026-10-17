"""E0: servicios, tramos de peso, tipos de ubicación y formas de cobro.

Leer: cualquier usuario habilitado (el cotizador, tarifas y recargos los necesitan).
Escribir: configuracion.servicios.gestionar (solo admin). Borrar: solo lo que nunca se usó.
"""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.servicios import (
    FormaCobroSalida,
    ServicioActualizar,
    ServicioCrear,
    ServicioSalida,
    TipoUbicacionActualizar,
    TipoUbicacionCrear,
    TipoUbicacionSalida,
    TramoServicioActualizar,
    TramoServicioCrear,
    TramoServicioSalida,
)
from app.services import formas_cobro
from app.services import servicios as servicio

router = APIRouter()

PERMISO = "configuracion.servicios.gestionar"
gestor = require_permiso(PERMISO)
lector = [Depends(get_usuario_habilitado)]


# ---------- Formas de cobro (catálogo cerrado) ----------


@router.get("/formas-cobro", response_model=list[FormaCobroSalida], tags=["servicios"], dependencies=lector)
def listar_formas_cobro():
    return formas_cobro.listar()


# ---------- Servicios ----------


@router.get("/servicios", response_model=list[ServicioSalida], tags=["servicios"], dependencies=lector)
def listar_servicios(activo: bool | None = None, db: Session = Depends(get_db)):
    """activo=true es la fuente única de servicios ofrecidos (orden de pantalla)."""
    return servicio.listar_servicios(db, activo=activo)


@router.get("/servicios/{servicio_id}", response_model=ServicioSalida, tags=["servicios"], dependencies=lector)
def detalle_servicio(servicio_id: int, db: Session = Depends(get_db)):
    return servicio.obtener_servicio(db, servicio_id)


@router.post("/servicios", response_model=ServicioSalida, status_code=status.HTTP_201_CREATED, tags=["servicios"])
def crear_servicio(datos: ServicioCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    creado = servicio.crear_servicio(db, actor, datos.model_dump())
    db.refresh(creado)
    return creado


@router.patch("/servicios/{servicio_id}", response_model=ServicioSalida, tags=["servicios"])
def actualizar_servicio(
    servicio_id: int, datos: ServicioActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)
):
    actualizado = servicio.actualizar_servicio(db, actor, servicio_id, datos.model_dump(exclude_unset=True))
    db.refresh(actualizado)
    return actualizado


@router.delete("/servicios/{servicio_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["servicios"])
def borrar_servicio(servicio_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    servicio.borrar_servicio(db, actor, servicio_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Tramos del servicio ----------


@router.post(
    "/servicios/{servicio_id}/tramos",
    response_model=TramoServicioSalida,
    status_code=status.HTTP_201_CREATED,
    tags=["servicios"],
)
def crear_tramo(
    servicio_id: int, datos: TramoServicioCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)
):
    return servicio.crear_tramo(db, actor, servicio_id, datos.model_dump())


@router.patch("/servicio-tramos/{tramo_id}", response_model=TramoServicioSalida, tags=["servicios"])
def actualizar_tramo(
    tramo_id: int, datos: TramoServicioActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)
):
    return servicio.actualizar_tramo(db, actor, tramo_id, datos.model_dump(exclude_unset=True))


@router.delete("/servicio-tramos/{tramo_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["servicios"])
def borrar_tramo(tramo_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    servicio.borrar_tramo(db, actor, tramo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Tipos de ubicación ----------


@router.get("/tipos-ubicacion", response_model=list[TipoUbicacionSalida], tags=["servicios"], dependencies=lector)
def listar_tipos_ubicacion(activo: bool | None = None, db: Session = Depends(get_db)):
    return servicio.listar_tipos_ubicacion(db, activo=activo)


@router.post(
    "/tipos-ubicacion", response_model=TipoUbicacionSalida, status_code=status.HTTP_201_CREATED, tags=["servicios"]
)
def crear_tipo_ubicacion(datos: TipoUbicacionCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    return servicio.crear_tipo_ubicacion(db, actor, datos.model_dump())


@router.patch("/tipos-ubicacion/{tipo_id}", response_model=TipoUbicacionSalida, tags=["servicios"])
def actualizar_tipo_ubicacion(
    tipo_id: int, datos: TipoUbicacionActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)
):
    return servicio.actualizar_tipo_ubicacion(db, actor, tipo_id, datos.model_dump(exclude_unset=True))

"""M2 Geografía. Leer: cualquier token válido. Escribir: catalogo.editar. Sin DELETE."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.geografia import (
    PaisActualizar,
    PaisCrear,
    PaisSalida,
    PuertoActualizar,
    PuertoCrear,
    PuertoSalida,
    RegionActualizar,
    RegionCrear,
    RegionSalida,
    TipoPuerto,
)
from app.services import geografia as servicio

router = APIRouter(tags=["geografia"])

lector = Depends(get_usuario_habilitado)
editor = require_permiso("catalogo.editar")


# ---------- Regiones ----------


@router.get("/regiones", response_model=list[RegionSalida], dependencies=[lector])
def listar_regiones(activo: bool | None = None, db: Session = Depends(get_db)):
    return servicio.listar_regiones(db, activo=activo)


@router.post("/regiones", response_model=RegionSalida, status_code=status.HTTP_201_CREATED)
def crear_region(datos: RegionCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio.crear_region(db, actor, datos.codigo, datos.nombre)


@router.get("/regiones/{region_id}", response_model=RegionSalida, dependencies=[lector])
def detalle_region(region_id: int, db: Session = Depends(get_db)):
    return servicio.obtener_region(db, region_id)


@router.patch("/regiones/{region_id}", response_model=RegionSalida, dependencies=[Depends(editor)])
def actualizar_region(region_id: int, datos: RegionActualizar, db: Session = Depends(get_db)):
    return servicio.actualizar_region(db, region_id, datos.model_dump(exclude_unset=True))


# ---------- Países ----------


@router.get("/paises", response_model=list[PaisSalida], dependencies=[lector])
def listar_paises(region_id: int | None = None, activo: bool | None = None, db: Session = Depends(get_db)):
    return servicio.listar_paises(db, region_id=region_id, activo=activo)


@router.post("/paises", response_model=PaisSalida, status_code=status.HTTP_201_CREATED)
def crear_pais(datos: PaisCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio.crear_pais(db, actor, datos.iso2, datos.nombre, datos.region_id)


@router.get("/paises/{pais_id}", response_model=PaisSalida, dependencies=[lector])
def detalle_pais(pais_id: int, db: Session = Depends(get_db)):
    return servicio.obtener_pais(db, pais_id)


@router.patch("/paises/{pais_id}", response_model=PaisSalida, dependencies=[Depends(editor)])
def actualizar_pais(pais_id: int, datos: PaisActualizar, db: Session = Depends(get_db)):
    return servicio.actualizar_pais(db, pais_id, datos.model_dump(exclude_unset=True))


# ---------- Puertos ----------


@router.get("/puertos", response_model=list[PuertoSalida], dependencies=[lector])
def listar_puertos(
    tipo: TipoPuerto | None = None,
    pais_id: int | None = None,
    activo: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    return servicio.listar_puertos(db, tipo=tipo, pais_id=pais_id, activo=activo, q=q)


@router.post("/puertos", response_model=PuertoSalida, status_code=status.HTTP_201_CREATED)
def crear_puerto(datos: PuertoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio.crear_puerto(db, actor, datos.codigo, datos.nombre, datos.pais_id, datos.tipo)


@router.get("/puertos/{puerto_id}", response_model=PuertoSalida, dependencies=[lector])
def detalle_puerto(puerto_id: int, db: Session = Depends(get_db)):
    return servicio.obtener_puerto(db, puerto_id)


@router.patch("/puertos/{puerto_id}", response_model=PuertoSalida, dependencies=[Depends(editor)])
def actualizar_puerto(puerto_id: int, datos: PuertoActualizar, db: Session = Depends(get_db)):
    return servicio.actualizar_puerto(db, puerto_id, datos.model_dump(exclude_unset=True))

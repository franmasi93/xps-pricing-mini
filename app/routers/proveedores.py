"""M4 Proveedores. Leer: catalogo.editar o costo.ver (admin, pricing, gerencia). Escribir: catalogo.editar."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import require_alguno_permiso, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.proveedores import ProveedorActualizar, ProveedorCrear, ProveedorSalida
from app.services import proveedores as servicio

router = APIRouter(prefix="/proveedores", tags=["proveedores"])

lector = require_alguno_permiso("catalogo.editar", "costo.ver")
editor = require_permiso("catalogo.editar")


@router.get("", response_model=list[ProveedorSalida], dependencies=[Depends(lector)])
def listar(pais_id: int | None = None, activo: bool | None = None, q: str | None = None, db: Session = Depends(get_db)):
    return servicio.listar_proveedores(db, pais_id=pais_id, activo=activo, q=q)


@router.post("", response_model=ProveedorSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: ProveedorCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio.crear_proveedor(db, actor, datos.model_dump())


@router.get("/{proveedor_id}", response_model=ProveedorSalida, dependencies=[Depends(lector)])
def detalle(proveedor_id: int, db: Session = Depends(get_db)):
    return servicio.obtener_proveedor(db, proveedor_id)


@router.patch("/{proveedor_id}", response_model=ProveedorSalida, dependencies=[Depends(editor)])
def actualizar(proveedor_id: int, datos: ProveedorActualizar, db: Session = Depends(get_db)):
    return servicio.actualizar_proveedor(db, proveedor_id, datos.model_dump(exclude_unset=True))

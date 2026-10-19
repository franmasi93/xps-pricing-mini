"""M6 Clientes y contactos. Leer: cliente.ver (con alcance); escribir: cliente.editar.
Rutas fijas (/clientes/buscar) antes de /{id}. Sin DELETE (405).
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.clientes import (
    ClienteActualizar,
    ClienteCrear,
    ClienteSalida,
    ContactoActualizar,
    ContactoCrear,
    ContactoSalida,
)
from app.services import clientes as servicio

router = APIRouter(prefix="/clientes", tags=["clientes"])

lector = require_permiso("cliente.ver")
editor = require_permiso("cliente.editar")


@router.get("", response_model=list[ClienteSalida])
def listar(
    activo: bool | None = None,
    comercial: int | None = None,
    estado: str | None = None,
    tipo: str | None = None,
    sector: str | None = None,
    servicio_interes: str | None = Query(default=None, alias="servicio"),
    ruta: str | None = None,
    etiqueta: str | None = None,
    acepta_promociones: str | None = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(lector),
):
    """E1-B: filtros del perfil comercial (varios valores separados por |, combinados con Y entre filtros)."""
    filtros = {"estado": estado, "tipo": tipo, "sector": sector, "servicio": servicio_interes, "ruta": ruta, "etiqueta": etiqueta,
               "acepta_promociones": acepta_promociones}
    return servicio.listar_clientes(db, usuario, activo=activo, comercial=comercial, filtros=filtros)


@router.get("/buscar", response_model=list[ClienteSalida])
def buscar(q: str = "", db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio.buscar_clientes(db, usuario, q)


@router.post("", response_model=ClienteSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: ClienteCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio.crear_cliente(db, actor, datos.model_dump(exclude_unset=True))


@router.get("/{cliente_id}", response_model=ClienteSalida)
def detalle(cliente_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio.detalle_cliente(db, usuario, cliente_id)


@router.patch("/{cliente_id}", response_model=ClienteSalida)
def actualizar(
    cliente_id: int, datos: ClienteActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio.actualizar_cliente(db, actor, cliente_id, datos.model_dump(exclude_unset=True))


@router.get("/{cliente_id}/contactos", response_model=list[ContactoSalida])
def listar_contactos(cliente_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio.listar_contactos(db, usuario, cliente_id)


@router.post("/{cliente_id}/contactos", response_model=ContactoSalida, status_code=status.HTTP_201_CREATED)
def crear_contacto(
    cliente_id: int, datos: ContactoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio.crear_contacto(db, actor, cliente_id, datos.model_dump(exclude_unset=True))


@router.patch("/{cliente_id}/contactos/{contacto_id}", response_model=ContactoSalida)
def actualizar_contacto(
    cliente_id: int,
    contacto_id: int,
    datos: ContactoActualizar,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(editor),
):
    return servicio.actualizar_contacto(db, actor, cliente_id, contacto_id, datos.model_dump(exclude_unset=True))

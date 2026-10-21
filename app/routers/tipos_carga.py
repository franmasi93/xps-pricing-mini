"""D-T2: catálogo "Tipo de carga" (GENERAL, IMO, REFRIGERADA, SOBREDIMENSIONADA, PERECIBLE, ALTO_VALOR…).

Leer: cualquier usuario habilitado (el cotizador lo necesita). Crear y editar: catalogo.editar, con auditoría.
El código no cambia una vez creado (lo guardan las cotizaciones, las tarifas y el alcance de los recargos).
"""
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import TipoCarga, Usuario
from app.schemas.comunes import Entrada
from app.services import auditoria

router = APIRouter(tags=["tipos de carga"])
editor = require_permiso("catalogo.editar")
CAMPOS = ("codigo", "nombre", "pide_imo", "orden", "activo")


class TipoCargaSalida(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    codigo: str
    nombre: str
    pide_imo: bool
    orden: int
    activo: bool


class TipoCargaCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=60)
    pide_imo: bool = False
    orden: int = Field(default=0, ge=0, le=999)


class TipoCargaActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=60)
    pide_imo: bool | None = None
    orden: int | None = Field(default=None, ge=0, le=999)
    activo: bool | None = None


def _foto(tipo: TipoCarga) -> dict:
    return {campo: getattr(tipo, campo) for campo in CAMPOS}


@router.get("/tipos-carga", response_model=list[TipoCargaSalida], dependencies=[Depends(get_usuario_habilitado)])
def listar(activo: bool | None = None, db: Session = Depends(get_db)):
    consulta = select(TipoCarga).order_by(TipoCarga.orden, TipoCarga.codigo)
    if activo is not None:
        consulta = consulta.where(TipoCarga.activo.is_(activo))
    return list(db.scalars(consulta))


@router.post("/tipos-carga", response_model=TipoCargaSalida, status_code=201)
def crear(datos: TipoCargaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    codigo = "_".join(datos.codigo.strip().upper().split())
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,19}", codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código va en mayúsculas, sin espacios (por ejemplo IMO)")
    if db.scalars(select(TipoCarga).where(TipoCarga.codigo == codigo)).one_or_none() is not None:
        raise ErrorNegocio(409, "CODIGO_REPETIDO", f"Ya existe el tipo de carga {codigo}")
    nombre = " ".join(datos.nombre.split())
    if not nombre:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre es obligatorio")
    tipo = TipoCarga(codigo=codigo, nombre=nombre, pide_imo=datos.pide_imo, orden=datos.orden,
                     creado_por=auditoria.id_de(actor))
    db.add(tipo)
    enviar(db)
    auditoria.registrar(db, actor, "tipo_carga", tipo.id, "CREAR", despues=_foto(tipo))
    confirmar(db)
    return tipo


@router.patch("/tipos-carga/{tipo_id}", response_model=TipoCargaSalida)
def actualizar(tipo_id: int, datos: TipoCargaActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    tipo = db.get(TipoCarga, tipo_id)
    if tipo is None:
        raise ErrorNegocio(404, "TIPO_CARGA_NO_ENCONTRADO", "Tipo de carga no encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    if tipo.codigo == "GENERAL" and (cambios.get("activo") is False or cambios.get("pide_imo") is True):
        raise ErrorNegocio(409, "TIPO_CARGA_FIJO", "GENERAL es el tipo por defecto: no se desactiva ni pide datos IMO")
    antes = _foto(tipo)
    if "nombre" in cambios:
        cambios["nombre"] = " ".join((cambios["nombre"] or "").split())
        if not cambios["nombre"]:
            raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre es obligatorio")
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(tipo, campo, valor)
    despues = _foto(tipo)
    if despues != antes:
        accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
        auditoria.registrar(db, actor, "tipo_carga", tipo.id, accion, antes=antes, despues=despues)
    confirmar(db)
    return tipo

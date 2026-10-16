"""Incoterms (leer: token válido; PATCH: config.editar), configuración (PATCH: el permiso de la clave)
y auditoría (auditoria.ver). Sin POST ni DELETE de Incoterms (405).
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Configuracion, Incoterm, Usuario
from app.schemas.catalogos import (
    AuditoriaItem,
    AuditoriaPagina,
    ConfiguracionActualizar,
    ConfiguracionSalida,
    IncotermActualizar,
    IncotermSalida,
)
from app.schemas.catalogos import EmpresaDatos
from app.services import auditoria as servicio_auditoria
from app.services import configuracion as servicio_config
from app.services import empresa as servicio_empresa
from app.services import incoterms as servicio_incoterms

router = APIRouter()


def _incoterm_salida(incoterm: Incoterm) -> IncotermSalida:
    importacion, aviso_importacion = servicio_incoterms.bloques_incluidos(incoterm, "IMPORTACION")
    exportacion, aviso_exportacion = servicio_incoterms.bloques_incluidos(incoterm, "EXPORTACION")
    return IncotermSalida(
        **{campo: getattr(incoterm, campo) for campo in ("id", "codigo", "actualizado_en")},
        **{campo: getattr(incoterm, campo) for campo in servicio_incoterms.CAMPOS_EDITABLES},
        bloques_importacion=importacion,
        bloques_exportacion=exportacion,
        advertencia_importacion=aviso_importacion,
        advertencia_exportacion=aviso_exportacion,
    )


def _config_salida(config: Configuracion, editable: bool) -> ConfiguracionSalida:
    return ConfiguracionSalida(
        clave=config.clave,
        valor=config.valor,
        tipo=config.tipo,
        permiso_edicion=config.permiso_edicion,
        editable=editable,
        actualizado_en=config.actualizado_en,
    )


# ---------- Incoterms ----------


@router.get("/incoterms", response_model=list[IncotermSalida], tags=["incoterms"], dependencies=[Depends(get_usuario_habilitado)])
def listar_incoterms(db: Session = Depends(get_db)):
    return [_incoterm_salida(i) for i in servicio_incoterms.listar_incoterms(db)]


@router.get("/incoterms/{codigo}", response_model=IncotermSalida, tags=["incoterms"], dependencies=[Depends(get_usuario_habilitado)])
def detalle_incoterm(codigo: str, db: Session = Depends(get_db)):
    return _incoterm_salida(servicio_incoterms.obtener_incoterm(db, codigo))


@router.patch("/incoterms/{codigo}", response_model=IncotermSalida, tags=["incoterms"])
def actualizar_incoterm(
    codigo: str,
    datos: IncotermActualizar,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(require_permiso("config.editar")),
):
    incoterm = servicio_incoterms.actualizar_incoterm(db, actor, codigo, datos.model_dump(exclude_unset=True))
    return _incoterm_salida(incoterm)


# ---------- Configuración ----------


@router.get("/configuracion", response_model=list[ConfiguracionSalida], tags=["configuracion"])
def listar_configuracion(db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_habilitado)):
    return [_config_salida(c, editable) for c, editable in servicio_config.listar_config(db, usuario)]


@router.get("/configuracion/empresa", response_model=EmpresaDatos, tags=["configuracion"])
def leer_empresa(db: Session = Depends(get_db), actor: Usuario = Depends(get_usuario_habilitado)):
    """A4: datos de la empresa para el PDF (config.editar)."""
    return servicio_empresa.leer_empresa(db, actor)


@router.put("/configuracion/empresa", response_model=EmpresaDatos, tags=["configuracion"])
def actualizar_empresa(
    datos: EmpresaDatos, db: Session = Depends(get_db), actor: Usuario = Depends(get_usuario_habilitado)
):
    return servicio_empresa.actualizar_empresa(db, actor, datos.model_dump(exclude_unset=True))


@router.patch("/configuracion/{clave}", response_model=ConfiguracionSalida, tags=["configuracion"])
def actualizar_configuracion(
    clave: str,
    datos: ConfiguracionActualizar,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(get_usuario_habilitado),
):
    config = servicio_config.actualizar_config(db, actor, clave, datos.valor)
    return _config_salida(config, True)


# ---------- Auditoría ----------


@router.get(
    "/auditoria",
    response_model=AuditoriaPagina,
    tags=["auditoria"],
    dependencies=[Depends(require_permiso("auditoria.ver"))],
)
def listar_auditoria(
    entidad: str | None = None,
    entidad_id: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(default=50, ge=1, le=servicio_auditoria.LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    filas, total = servicio_auditoria.listar(db, entidad, entidad_id, desde, hasta, limit, offset)
    items = [
        AuditoriaItem(
            id=registro.id,
            fecha=registro.fecha,
            usuario_id=registro.usuario_id,
            usuario_nombre=nombre,
            entidad=registro.entidad,
            entidad_id=registro.entidad_id,
            accion=registro.accion,
            valores_antes=registro.valores_antes,
            valores_despues=registro.valores_despues,
            nota=registro.nota,
        )
        for registro, nombre in filas
    ]
    return AuditoriaPagina(items=items, total=total, limit=limit, offset=offset)

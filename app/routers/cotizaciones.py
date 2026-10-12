"""M7 Cotizaciones. Leer: token válido + alcance (sin ver_todas solo las propias; ajena → 404).
Crear, editar, proponer, ajustar y duplicar: cotizacion.crear. Emitir, estado y descartar: cotizacion.emitir.
Rutas fijas antes de /{id}. Sin DELETE (405). El router solo recibe y responde (response_model=None:
el service arma el JSON con el gating de costos).
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.cotizaciones import (
    CotizacionActualizar,
    CotizacionCrear,
    EmitirEntrada,
    EstadoEntrada,
    LineaActualizar,
    ProponerEntrada,
)
from app.services import cotizaciones as servicio

router = APIRouter(prefix="/cotizaciones", tags=["cotizaciones"])

creador = require_permiso("cotizacion.crear")
emisor = require_permiso("cotizacion.emitir")
LIMITE_MAXIMO = 200


@router.get("", response_model=None)
def listar(
    estado: str | None = None,
    cliente_id: int | None = None,
    comercial_id: int | None = None,
    vencidas: bool | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(default=50, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_habilitado),
):
    return servicio.listar_cotizaciones(
        db, usuario, estado=estado, cliente_id=cliente_id, comercial_id=comercial_id, vencidas=vencidas,
        desde=desde, hasta=hasta, limit=limit, offset=offset,
    )


@router.post("", response_model=None, status_code=status.HTTP_201_CREATED)
def crear(datos: CotizacionCrear, db: Session = Depends(get_db), actor: Usuario = Depends(creador)):
    return servicio.crear_cotizacion(db, actor, datos.model_dump(exclude_unset=True, mode="json"))


@router.get("/{cotizacion_id}/opciones-flete", response_model=None)
def opciones_flete(cotizacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_habilitado)):
    return servicio.opciones_flete(db, usuario, cotizacion_id)


@router.post("/{cotizacion_id}/proponer-lineas", response_model=None)
def proponer_lineas(
    cotizacion_id: int, datos: ProponerEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(creador)
):
    return servicio.proponer_lineas(db, actor, cotizacion_id, datos.model_dump())


@router.patch("/{cotizacion_id}/lineas/{linea_id}", response_model=None)
def actualizar_linea(
    cotizacion_id: int,
    linea_id: int,
    datos: LineaActualizar,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(creador),
):
    return servicio.actualizar_linea(db, actor, cotizacion_id, linea_id, datos.model_dump(exclude_unset=True))


@router.post("/{cotizacion_id}/emitir", response_model=None)
def emitir(cotizacion_id: int, datos: EmitirEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(emisor)):
    return servicio.emitir_cotizacion(db, actor, cotizacion_id, datos.valida_hasta)


@router.post("/{cotizacion_id}/duplicar", response_model=None, status_code=status.HTTP_201_CREATED)
def duplicar(cotizacion_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(creador)):
    return servicio.duplicar_cotizacion(db, actor, cotizacion_id)


@router.post("/{cotizacion_id}/descartar", response_model=None)
def descartar(cotizacion_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(emisor)):
    return servicio.descartar_cotizacion(db, actor, cotizacion_id)


@router.patch("/{cotizacion_id}/estado", response_model=None)
def cambiar_estado(
    cotizacion_id: int, datos: EstadoEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(emisor)
):
    return servicio.cambiar_estado(db, actor, cotizacion_id, datos.model_dump())


@router.get("/{cotizacion_id}/pdf", response_class=Response)
def descargar_pdf(cotizacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_habilitado)):
    """Endpoint "def": Playwright síncrono corre en el threadpool (compatible con Windows)."""
    contenido, nombre = servicio.pdf_cotizacion(db, usuario, cotizacion_id)
    return Response(
        content=contenido, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"'}
    )


@router.get("/{cotizacion_id}", response_model=None)
def detalle(cotizacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_habilitado)):
    return servicio.detalle_cotizacion(db, usuario, cotizacion_id)


@router.patch("/{cotizacion_id}", response_model=None)
def actualizar(
    cotizacion_id: int, datos: CotizacionActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(creador)
):
    return servicio.actualizar_cotizacion(db, actor, cotizacion_id, datos.model_dump(exclude_unset=True, mode="json"))

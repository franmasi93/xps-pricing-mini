"""M5: tipos de equipo, tarifas, tramos y recargos.

Leer tarifas, tramos y recargos: tarifa.ver (con gating de costos en el service).
Escribir: tarifa.editar. Tipos de equipo: leer con token válido, escribir con catalogo.editar.
El router no elige esquemas ni filtra campos: devuelve lo que arma el service (response_model=None).
Sin DELETE (405). Rutas fijas antes de /{id}.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.tarifas import (
    BloqueRecargo,
    Lado,
    Modo,
    RecargoActualizar,
    RecargoCrear,
    TarifaActualizar,
    TarifaCrear,
    TarifaDuplicar,
    TipoEquipoActualizar,
    TipoEquipoCrear,
    TipoEquipoSalida,
    TramosEntrada,
)
from app.services import recargos as servicio_recargos
from app.services import tarifas as servicio_tarifas
from app.services import tipos_equipo as servicio_tipos

router = APIRouter()

lector = require_permiso("tarifa.ver")
editor = require_permiso("tarifa.editar")
editor_catalogo = require_permiso("catalogo.editar")


# ---------- Tipos de equipo ----------


@router.get("/tipos-equipo", response_model=list[TipoEquipoSalida], tags=["tarifas"], dependencies=[Depends(get_usuario_habilitado)])
def listar_tipos_equipo(activo: bool | None = None, servicio_id: int | None = None, db: Session = Depends(get_db)):
    return servicio_tipos.listar_tipos_equipo(db, activo=activo, servicio_id=servicio_id)


@router.post("/tipos-equipo", response_model=TipoEquipoSalida, status_code=status.HTTP_201_CREATED, tags=["tarifas"])
def crear_tipo_equipo(datos: TipoEquipoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor_catalogo)):
    return servicio_tipos.crear_tipo_equipo(db, actor, datos.codigo, datos.nombre, datos.servicio_id)


@router.get("/tipos-equipo/{tipo_id}", response_model=TipoEquipoSalida, tags=["tarifas"], dependencies=[Depends(get_usuario_habilitado)])
def detalle_tipo_equipo(tipo_id: int, db: Session = Depends(get_db)):
    return servicio_tipos.obtener_tipo_equipo(db, tipo_id)


@router.patch("/tipos-equipo/{tipo_id}", response_model=TipoEquipoSalida, tags=["tarifas"], dependencies=[Depends(editor_catalogo)])
def actualizar_tipo_equipo(tipo_id: int, datos: TipoEquipoActualizar, db: Session = Depends(get_db)):
    return servicio_tipos.actualizar_tipo_equipo(db, tipo_id, datos.model_dump(exclude_unset=True))

LIMITE_MAXIMO = 200


# ---------- Tarifas ----------


@router.get("/tarifas", response_model=None, tags=["tarifas"])
def listar_tarifas(
    modo: Modo | None = None,
    origen: int | None = None,
    destino: int | None = None,
    proveedor: int | None = None,
    tipo_equipo: int | None = None,
    vigente_en: date | None = None,
    por_vencer: bool | None = None,
    activo: bool | None = None,
    limit: int | None = Query(default=None, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
    respuesta: Response = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(lector),
):
    """F5-A2: sin limit, la lista completa (como en F2); con limit/offset, una página. El total va en X-Total-Count."""
    total: list[int] = []
    items = servicio_tarifas.listar_tarifas(
        db, usuario, modo, origen, destino, proveedor, tipo_equipo, vigente_en, por_vencer, activo,
        limit=limit, offset=offset, total=total,
    )
    respuesta.headers["X-Total-Count"] = str(total[0])
    return items


@router.post("/tarifas", response_model=None, status_code=status.HTTP_201_CREATED, tags=["tarifas"])
def crear_tarifa(datos: TarifaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio_tarifas.crear_tarifa(db, actor, datos.model_dump())


@router.post("/tarifas/{tarifa_id}/duplicar", response_model=None, status_code=status.HTTP_201_CREATED, tags=["tarifas"])
def duplicar_tarifa(
    tarifa_id: int, datos: TarifaDuplicar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio_tarifas.duplicar_tarifa(db, actor, tarifa_id, datos.valido_desde, datos.valido_hasta)


@router.get("/tarifas/{tarifa_id}/tramos", response_model=None, tags=["tarifas"])
def obtener_tramos(tarifa_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio_tarifas.obtener_tramos(db, usuario, tarifa_id)


@router.put("/tarifas/{tarifa_id}/tramos", response_model=None, tags=["tarifas"])
def reemplazar_tramos(
    tarifa_id: int, datos: TramosEntrada, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio_tarifas.reemplazar_tramos(db, actor, tarifa_id, [t.model_dump() for t in datos.tramos])


@router.get("/tarifas/{tarifa_id}", response_model=None, tags=["tarifas"])
def detalle_tarifa(tarifa_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio_tarifas.detalle_tarifa(db, usuario, tarifa_id)


@router.patch("/tarifas/{tarifa_id}", response_model=None, tags=["tarifas"])
def actualizar_tarifa(
    tarifa_id: int, datos: TarifaActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio_tarifas.actualizar_tarifa(db, actor, tarifa_id, datos.model_dump(exclude_unset=True))


# ---------- Recargos ----------


@router.get("/recargos", response_model=None, tags=["recargos"])
def listar_recargos(
    puerto: int | None = None,
    lado: Lado | None = None,
    bloque: BloqueRecargo | None = None,
    proveedor: int | None = None,
    modo: Modo | None = None,
    vigente_en: date | None = None,
    por_vencer: bool | None = None,
    activo: bool | None = None,
    limit: int | None = Query(default=None, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(default=0, ge=0),
    respuesta: Response = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(lector),
):
    """F5-A2: sin limit, la lista completa (como en F2); con limit/offset, una página. El total va en X-Total-Count."""
    total: list[int] = []
    items = servicio_recargos.listar_recargos(
        db, usuario, puerto, lado, bloque, proveedor, modo, vigente_en, por_vencer, activo,
        limit=limit, offset=offset, total=total,
    )
    respuesta.headers["X-Total-Count"] = str(total[0])
    return items


@router.post("/recargos", response_model=None, status_code=status.HTTP_201_CREATED, tags=["recargos"])
def crear_recargo(datos: RecargoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio_recargos.crear_recargo(db, actor, datos.model_dump())


@router.get("/recargos/{recargo_id}", response_model=None, tags=["recargos"])
def detalle_recargo(recargo_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return servicio_recargos.detalle_recargo(db, usuario, recargo_id)


@router.patch("/recargos/{recargo_id}", response_model=None, tags=["recargos"])
def actualizar_recargo(
    recargo_id: int, datos: RecargoActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio_recargos.actualizar_recargo(db, actor, recargo_id, datos.model_dump(exclude_unset=True))

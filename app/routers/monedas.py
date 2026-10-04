"""M3 Monedas y tasas. Monedas: leer con token válido, escribir con tasa.editar.
Tasas: leer con costo.ver, escribir con tasa.editar. /tasas/vigente va ANTES de /tasas/{id}.
"""
from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.rbac import get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import TasaCambio, Usuario
from app.schemas.monedas import (
    MonedaActualizar,
    MonedaCrear,
    MonedaSalida,
    TasaCorregir,
    TasaCrear,
    TasaSalida,
    TasaVigenteSalida,
)
from app.services import monedas as servicio_monedas
from app.services import tasas as servicio_tasas

router = APIRouter(tags=["monedas"])

editor = require_permiso("tasa.editar")
lector_costos = require_permiso("costo.ver")


def _tasa_salida(tasa: TasaCambio) -> TasaSalida:
    return TasaSalida(
        id=tasa.id,
        moneda_id=tasa.moneda_id,
        moneda=tasa.moneda.codigo,
        tasa_a_usd=tasa.tasa_a_usd,
        fecha_vigencia=tasa.fecha_vigencia,
        registrado_por=tasa.registrado_por,
        creado_en=tasa.creado_en,
        actualizado_en=tasa.actualizado_en,
    )


# ---------- Monedas ----------


@router.get("/monedas", response_model=list[MonedaSalida], dependencies=[Depends(get_usuario_habilitado)])
def listar_monedas(activo: bool | None = None, db: Session = Depends(get_db)):
    return servicio_monedas.listar_monedas(db, activo=activo)


@router.post("/monedas", response_model=MonedaSalida, status_code=status.HTTP_201_CREATED)
def crear_moneda(datos: MonedaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    return servicio_monedas.crear_moneda(db, actor, datos.codigo, datos.nombre, datos.simbolo)


@router.get("/monedas/{moneda_id}", response_model=MonedaSalida, dependencies=[Depends(get_usuario_habilitado)])
def detalle_moneda(moneda_id: int, db: Session = Depends(get_db)):
    return servicio_monedas.obtener_moneda(db, moneda_id)


@router.patch("/monedas/{moneda_id}", response_model=MonedaSalida)
def actualizar_moneda(
    moneda_id: int, datos: MonedaActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(editor)
):
    return servicio_monedas.actualizar_moneda(db, actor, moneda_id, datos.model_dump(exclude_unset=True))


# ---------- Tasas (rutas fijas primero) ----------


@router.get("/tasas/vigente", response_model=TasaVigenteSalida, dependencies=[Depends(lector_costos)])
def tasa_vigente(moneda: str, fecha: date, db: Session = Depends(get_db)):
    valor = servicio_tasas.obtener_tasa_vigente(db, moneda, fecha)
    return TasaVigenteSalida(moneda="".join(moneda.split()).upper(), fecha=fecha, tasa_a_usd=valor)


@router.get("/tasas", response_model=list[TasaSalida], dependencies=[Depends(lector_costos)])
def listar_tasas(
    moneda: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    db: Session = Depends(get_db),
):
    return [_tasa_salida(t) for t in servicio_tasas.listar_tasas(db, moneda=moneda, desde=desde, hasta=hasta)]


@router.post("/tasas", response_model=TasaSalida, status_code=status.HTTP_201_CREATED)
def registrar_tasa(datos: TasaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    tasa = servicio_tasas.registrar_tasa(
        db, actor, datos.moneda, datos.tasa_a_usd, datos.fecha_vigencia, datos.confirmar_desvio
    )
    return _tasa_salida(tasa)


@router.get("/tasas/{tasa_id}", response_model=TasaSalida, dependencies=[Depends(lector_costos)])
def detalle_tasa(tasa_id: int, db: Session = Depends(get_db)):
    return _tasa_salida(servicio_tasas.obtener_tasa(db, tasa_id))


@router.patch("/tasas/{tasa_id}", response_model=TasaSalida)
def corregir_tasa(tasa_id: int, datos: TasaCorregir, db: Session = Depends(get_db), actor: Usuario = Depends(editor)):
    tasa = servicio_tasas.corregir_tasa(db, actor, tasa_id, datos.tasa_a_usd, datos.confirmar_desvio)
    return _tasa_salida(tasa)

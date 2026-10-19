"""E3 Notificaciones y avisos.

- Configuración, eventos y reglas: notificaciones.reglas.gestionar (administrador).
- Bitácora y reenvío de fallidas: notificaciones.bitacora.ver (administrador y Pricing).
- Campana, "Mis notificaciones" y "Mis preferencias": notificaciones.ver (todos).
- Interruptores de la cotización (quien la ve y puede cotizar) y del cliente y sus contactos (cliente.editar).
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio
from app.core.rbac import require_alguno_permiso, require_permiso
from app.db import get_db
from app.models import ContactoCliente, Usuario
from app.schemas.notificaciones import (
    AvisosCliente,
    AvisosContacto,
    AvisosCotizacion,
    AvisosInterruptor,
    ConfigAvisosActualizar,
    ConfigAvisosSalida,
    EventoSalida,
    NotificacionDetalle,
    NotificacionSalida,
    Preferencia,
    PreferenciasActualizar,
    ReglaActualizar,
    ReglaCrear,
    ReglaSalida,
)
from app.services import clientes, cotizaciones, notificaciones

router = APIRouter(tags=["notificaciones"])
gestor = require_permiso("notificaciones.reglas.gestionar")
bitacora = require_permiso("notificaciones.bitacora.ver")
lector = require_permiso("notificaciones.ver")


@router.get("/notificaciones/config", response_model=ConfigAvisosSalida, dependencies=[Depends(gestor)])
def leer_config(db: Session = Depends(get_db)):
    return notificaciones.presentar_config(db)


@router.put("/notificaciones/config", response_model=ConfigAvisosSalida)
def guardar_config(datos: ConfigAvisosActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    return notificaciones.actualizar_config(db, actor, datos.model_dump(exclude_unset=True))


@router.get("/notificaciones/eventos", response_model=list[EventoSalida], dependencies=[Depends(gestor)])
def listar_eventos(db: Session = Depends(get_db)):
    return notificaciones.listar_eventos(db)


@router.post("/notificaciones/reglas", response_model=ReglaSalida, status_code=201)
def crear_regla(datos: ReglaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    return notificaciones.crear_regla(db, actor, datos.model_dump())


@router.patch("/notificaciones/reglas/{regla_id}", response_model=ReglaSalida)
def actualizar_regla(regla_id: int, datos: ReglaActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(gestor)):
    return notificaciones.actualizar_regla(db, actor, regla_id, datos.model_dump(exclude_unset=True))


@router.get("/notificaciones/bitacora", response_model=list[NotificacionSalida], dependencies=[Depends(bitacora)])
def listar_bitacora(
    evento: str | None = None, estado: str | None = None, canal: str | None = None, audiencia: str | None = None,
    cliente_id: int | None = None, comercial_id: int | None = None, desde: date | None = None, hasta: date | None = None,
    db: Session = Depends(get_db),
):
    filtros = {"evento": evento, "estado": estado, "canal": canal, "audiencia": audiencia, "cliente_id": cliente_id,
               "comercial_id": comercial_id, "desde": desde, "hasta": hasta}
    return notificaciones.bitacora(db, filtros)


def _detalle(notificacion) -> NotificacionDetalle:
    return NotificacionDetalle(**NotificacionSalida.model_validate(notificacion).model_dump(),
                               contenido=notificaciones.contenido(notificacion),
                               plantilla=notificacion.plantilla.nombre if notificacion.plantilla else None)


@router.get("/notificaciones/bitacora/{notificacion_id}", response_model=NotificacionDetalle, dependencies=[Depends(bitacora)])
def ver_notificacion(notificacion_id: int, db: Session = Depends(get_db)):
    return _detalle(notificaciones.obtener(db, notificacion_id))


@router.post("/notificaciones/bitacora/{notificacion_id}/reenviar", response_model=NotificacionSalida)
def reenviar(notificacion_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(bitacora)):
    return notificaciones.reenviar(db, actor, notificacion_id)


@router.get("/notificaciones/mias", response_model=list[NotificacionSalida])
def mias(solo_no_leidas: bool = False, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return notificaciones.mias(db, usuario, solo_no_leidas)


@router.get("/notificaciones/mias/conteo")
def conteo(db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return {"no_leidas": notificaciones.no_leidas(db, usuario)}


@router.post("/notificaciones/mias/leer-todas")
def leer_todas(db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return {"marcadas": notificaciones.marcar_todas(db, usuario)}


@router.post("/notificaciones/mias/{notificacion_id}/leida", response_model=NotificacionSalida)
def leida(notificacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return notificaciones.marcar_leida(db, usuario, notificacion_id)


@router.get("/notificaciones/preferencias", response_model=list[Preferencia])
def ver_preferencias(db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return notificaciones.preferencias(db, usuario)


@router.put("/notificaciones/preferencias", response_model=list[Preferencia])
def guardar_preferencias(datos: PreferenciasActualizar, db: Session = Depends(get_db), usuario: Usuario = Depends(lector)):
    return notificaciones.guardar_preferencias(db, usuario, datos.correo)


# ---------- Interruptores ----------

cotiza = require_alguno_permiso("cotizacion.crear", "cotizacion.ver_todas")


@router.get("/cotizaciones/{cotizacion_id}/avisos", response_model=AvisosCotizacion, tags=["cotizaciones"])
def avisos_cotizacion(cotizacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(cotiza)):
    return notificaciones.avisos_de_cotizacion(db, cotizaciones.obtener_cotizacion(db, usuario, cotizacion_id))


@router.patch("/cotizaciones/{cotizacion_id}/avisos", response_model=AvisosCotizacion, tags=["cotizaciones"])
def cambiar_avisos_cotizacion(cotizacion_id: int, datos: AvisosInterruptor, db: Session = Depends(get_db),
                              actor: Usuario = Depends(require_permiso("cotizacion.crear"))):
    cotizacion = cotizaciones.obtener_cotizacion(db, actor, cotizacion_id)
    notificaciones.cambiar_avisos_cotizacion(db, actor, cotizacion, datos.activos)
    return notificaciones.avisos_de_cotizacion(db, cotizaciones.obtener_cotizacion(db, actor, cotizacion_id))


def _avisos_cliente(db: Session, cliente) -> AvisosCliente:
    contactos = db.scalars(select(ContactoCliente).where(ContactoCliente.cliente_id == cliente.id, ContactoCliente.activo.is_(True))
                           .order_by(ContactoCliente.id))
    return AvisosCliente(activos=cliente.avisos_activos, contactos=[
        {"id": c.id, "nombre": c.nombre, "email": c.email, "recibir_avisos": c.recibir_avisos} for c in contactos])


@router.get("/clientes/{cliente_id}/avisos", response_model=AvisosCliente, tags=["clientes"])
def avisos_cliente(cliente_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(require_permiso("cliente.ver"))):
    return _avisos_cliente(db, clientes.obtener_cliente(db, usuario, cliente_id))


@router.patch("/clientes/{cliente_id}/avisos", response_model=AvisosCliente, tags=["clientes"])
def cambiar_avisos_cliente(cliente_id: int, datos: AvisosInterruptor, db: Session = Depends(get_db),
                           actor: Usuario = Depends(require_permiso("cliente.editar"))):
    cliente = clientes.obtener_cliente(db, actor, cliente_id)
    notificaciones.cambiar_avisos_cliente(db, actor, cliente, datos.activos)
    return _avisos_cliente(db, clientes.obtener_cliente(db, actor, cliente_id))


@router.patch("/clientes/{cliente_id}/contactos/{contacto_id}/avisos", response_model=AvisosCliente, tags=["clientes"])
def cambiar_avisos_contacto(cliente_id: int, contacto_id: int, datos: AvisosContacto, db: Session = Depends(get_db),
                            actor: Usuario = Depends(require_permiso("cliente.editar"))):
    cliente = clientes.obtener_cliente(db, actor, cliente_id)
    contacto = db.get(ContactoCliente, contacto_id)
    if contacto is None or contacto.cliente_id != cliente.id:
        raise ErrorNegocio(404, "CONTACTO_NO_ENCONTRADO", "Contacto no encontrado")
    notificaciones.cambiar_avisos_contacto(db, actor, contacto, datos.recibir)
    return _avisos_cliente(db, clientes.obtener_cliente(db, actor, cliente_id))

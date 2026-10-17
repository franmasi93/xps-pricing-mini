"""Tipos de equipo (20GP, 40GP, 40HC, 20RF, 40RF y los que agregue Pricing).

E0: cada tipo es de un servicio que cobra por unidad de equipo (los 5 iniciales son de FCL). Sin servicio
indicado, se usa el primer servicio activo con tipo de equipo. Un tipo usado no cambia de servicio.
"""
import re
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.models import CotizacionContenedor, Recargo, Servicio, Tarifa, TipoEquipo, Usuario
from app.services import auditoria

PATRON_CODIGO = re.compile(r"^[0-9]{2}[A-Z]{2}$")


def _codigo(codigo: str) -> str:
    codigo = "".join(codigo.split()).upper()
    if not PATRON_CODIGO.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código del tipo de equipo es 2 dígitos y 2 letras, como 40HC")
    return codigo


def _nombre(nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
    return nombre


def _servicio(db: Session, servicio_id: int | None) -> Servicio:
    if servicio_id is None:
        servicio = db.scalars(
            select(Servicio)
            .where(Servicio.usa_tipo_equipo.is_(True), Servicio.activo.is_(True))
            .order_by(Servicio.orden, Servicio.id)
            .limit(1)
        ).one_or_none()
        if servicio is None:
            raise ErrorNegocio(422, "SERVICIO_REQUERIDO", "No hay un servicio activo con tipo de equipo")
        return servicio
    servicio = db.get(Servicio, servicio_id)
    if servicio is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "No existe el servicio indicado")
    if not servicio.usa_tipo_equipo:
        raise ErrorNegocio(422, "SERVICIO_INCOHERENTE", f"El servicio {servicio.codigo} no usa tipos de equipo")
    if not servicio.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", f"No se puede usar el servicio {servicio.codigo} inactivo; actívelo primero")
    return servicio


def listar_tipos_equipo(db: Session, activo: bool | None = None, servicio_id: int | None = None) -> list[TipoEquipo]:
    consulta = select(TipoEquipo)
    if activo is not None:
        consulta = consulta.where(TipoEquipo.activo.is_(activo))
    if servicio_id is not None:
        consulta = consulta.where(TipoEquipo.servicio_id == servicio_id)
    return list(db.scalars(consulta.order_by(TipoEquipo.codigo)))


def obtener_tipo_equipo(db: Session, tipo_id: int) -> TipoEquipo:
    tipo = db.get(TipoEquipo, tipo_id)
    if tipo is None:
        raise ErrorNegocio(404, "TIPO_EQUIPO_NO_ENCONTRADO", "Tipo de equipo no encontrado")
    return tipo


def crear_tipo_equipo(db: Session, actor: Usuario, codigo: str, nombre: str, servicio_id: int | None = None) -> TipoEquipo:
    servicio = _servicio(db, servicio_id)
    tipo = TipoEquipo(
        codigo=_codigo(codigo), nombre=_nombre(nombre), servicio_id=servicio.id, creado_por=auditoria.id_de(actor)
    )
    db.add(tipo)
    confirmar(db)
    return tipo


def actualizar_tipo_equipo(db: Session, tipo_id: int, cambios: dict[str, Any]) -> TipoEquipo:
    tipo = obtener_tipo_equipo(db, tipo_id)
    with db.no_autoflush:
        if "codigo" in cambios:
            tipo.codigo = _codigo(cambios["codigo"])
        if "nombre" in cambios:
            tipo.nombre = _nombre(cambios["nombre"])
        if cambios.get("servicio_id") is not None and cambios["servicio_id"] != tipo.servicio_id:
            servicio = _servicio(db, cambios["servicio_id"])
            usado = db.scalar(
                select(
                    or_(
                        exists().where(Tarifa.tipo_equipo_id == tipo.id),
                        exists().where(Recargo.tipo_equipo_id == tipo.id),
                        exists().where(CotizacionContenedor.tipo_equipo_id == tipo.id),
                    )
                )
            )
            if usado:
                raise ErrorNegocio(
                    409, "TIENE_DEPENDIENTES", "El tipo de equipo ya se usó en tarifas, recargos o cotizaciones: no cambia de servicio"
                )
            tipo.servicio_id = servicio.id
        if cambios.get("activo") is False and tipo.activo:
            en_uso = db.scalar(
                select(
                    or_(
                        exists().where(Tarifa.tipo_equipo_id == tipo.id, Tarifa.activo.is_(True)),
                        exists().where(Recargo.tipo_equipo_id == tipo.id, Recargo.activo.is_(True)),
                    )
                )
            )
            if en_uso:
                raise ErrorNegocio(
                    409, "TIENE_DEPENDIENTES", "Hay tarifas o recargos activos con este tipo de equipo"
                )
        if "activo" in cambios:
            tipo.activo = cambios["activo"]
    confirmar(db)
    return tipo

"""Tipos de equipo FCL (20GP, 40GP, 40HC, 20RF, 40RF y los que agregue Pricing)."""
import re
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.models import Recargo, Tarifa, TipoEquipo, Usuario
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


def listar_tipos_equipo(db: Session, activo: bool | None = None) -> list[TipoEquipo]:
    consulta = select(TipoEquipo)
    if activo is not None:
        consulta = consulta.where(TipoEquipo.activo.is_(activo))
    return list(db.scalars(consulta.order_by(TipoEquipo.codigo)))


def obtener_tipo_equipo(db: Session, tipo_id: int) -> TipoEquipo:
    tipo = db.get(TipoEquipo, tipo_id)
    if tipo is None:
        raise ErrorNegocio(404, "TIPO_EQUIPO_NO_ENCONTRADO", "Tipo de equipo no encontrado")
    return tipo


def crear_tipo_equipo(db: Session, actor: Usuario, codigo: str, nombre: str) -> TipoEquipo:
    tipo = TipoEquipo(codigo=_codigo(codigo), nombre=_nombre(nombre), creado_por=auditoria.id_de(actor))
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

"""Auditoría de cambios (D-F1-4).

`registrar` NO hace commit: agrega el registro a la sesión para que viaje en la MISMA
transacción que el cambio auditado. Si el cambio falla, tampoco queda el registro.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models import Auditoria, Usuario

LIMITE_MAXIMO = 200


def _serializable(valor: Any) -> Any:
    """JSONB no acepta Decimal ni fechas: se guardan como texto (sin perder precisión)."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def _limpiar(valores: dict[str, Any] | None) -> dict[str, Any] | None:
    if valores is None:
        return None
    return {clave: _serializable(valor) for clave, valor in valores.items()}


def id_de(usuario: Usuario) -> int:
    """PK del usuario sin consultar la BD.

    Leer `usuario.id` de un objeto vencido dispara un SELECT, y con él un autoflush de los
    cambios pendientes: un duplicado saldría como IntegrityError crudo y no como ErrorNegocio.
    """
    return inspect(usuario).identity[0]


def registrar(
    db: Session,
    usuario: Usuario | None,
    entidad: str,
    entidad_id: Any,
    accion: str,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
    nota: str | None = None,
) -> Auditoria:
    registro = Auditoria(
        usuario_id=id_de(usuario) if usuario is not None else None,
        entidad=entidad,
        entidad_id=str(entidad_id),
        accion=accion,
        valores_antes=_limpiar(antes),
        valores_despues=_limpiar(despues),
        nota=nota,
    )
    db.add(registro)
    return registro


def listar(
    db: Session,
    entidad: str | None = None,
    entidad_id: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Auditoria, str | None]], int]:
    """Devuelve (registros con el nombre del usuario, total). Fechas inclusivas, en UTC."""
    filtros = []
    if entidad is not None:
        filtros.append(Auditoria.entidad == entidad)
    if entidad_id is not None:
        filtros.append(Auditoria.entidad_id == entidad_id)
    if desde is not None:
        filtros.append(Auditoria.fecha >= datetime.combine(desde, time.min, tzinfo=timezone.utc))
    if hasta is not None:
        filtros.append(Auditoria.fecha < datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=timezone.utc))

    total = db.scalar(select(func.count()).select_from(Auditoria).where(*filtros))
    filas = db.execute(
        select(Auditoria, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == Auditoria.usuario_id)
        .where(*filtros)
        .order_by(Auditoria.fecha.desc(), Auditoria.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(fila[0], fila[1]) for fila in filas], total

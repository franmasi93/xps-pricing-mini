"""M3 Tasas de cambio (NIC 21, §10.3). Única fuente de conversión para el cotizador de F3.

tasa_a_usd = cuántos USD vale 1 unidad de la moneda (EUR ≈ 1.08; CNY ≈ 0.14, no 7.1).
Si la tasa nueva se aleja más de 20 % de su vecina, se exige confirmación (D-F1-3).
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import Moneda, TasaCambio, Usuario
from app.models.monedas import MONEDA_BASE
from app.services import auditoria
from app.services.monedas import moneda_por_codigo

UMBRAL_DESVIO = Decimal("0.20")
DECIMALES_MAXIMOS = 6
ENTEROS_MAXIMOS = 8  # Numeric(14, 6)
NOTA_DESVIO = "desvío >20% confirmado"


def _validar_tasa(valor: Any) -> Decimal:
    """Nunca se redondea en silencio: más de 6 decimales es un error (A1)."""
    try:
        tasa = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorNegocio(422, "TASA_INVALIDA", "La tasa debe ser un número") from None
    if not tasa.is_finite() or tasa <= 0:
        raise ErrorNegocio(422, "TASA_INVALIDA", "La tasa debe ser mayor que 0")
    normalizada = tasa.normalize()
    if normalizada.as_tuple().exponent < -DECIMALES_MAXIMOS:
        raise ErrorNegocio(422, "TASA_INVALIDA", f"La tasa admite como máximo {DECIMALES_MAXIMOS} decimales")
    if normalizada.adjusted() >= ENTEROS_MAXIMOS:
        raise ErrorNegocio(422, "TASA_INVALIDA", "La tasa es demasiado grande")
    return tasa


def _foto(tasa: TasaCambio) -> dict[str, Any]:
    # Con la escala de la columna (6 decimales): la auditoría muestra lo mismo que queda guardado.
    return {
        "moneda": tasa.moneda.codigo,
        "tasa_a_usd": Decimal(tasa.tasa_a_usd).quantize(Decimal(1).scaleb(-DECIMALES_MAXIMOS)),
        "fecha_vigencia": tasa.fecha_vigencia,
    }


def _moneda_con_tasas(db: Session, codigo: str) -> Moneda:
    moneda = moneda_por_codigo(db, codigo)
    if moneda is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"No existe la moneda {codigo}")
    if moneda.codigo == MONEDA_BASE:
        raise ErrorNegocio(422, "MONEDA_BASE_PROTEGIDA", "La moneda base USD no admite tasas: siempre vale 1")
    if not moneda.activo:
        raise ErrorNegocio(422, "MONEDA_INACTIVA", f"La moneda {moneda.codigo} está desactivada")
    return moneda


def tasa_vecina(db: Session, moneda_id: int, fecha: date, excluir_id: int | None = None) -> TasaCambio | None:
    """La anterior más cercana a `fecha`; si no hay, la posterior más cercana; si no hay, None."""
    base = select(TasaCambio).where(TasaCambio.moneda_id == moneda_id)
    if excluir_id is not None:
        base = base.where(TasaCambio.id != excluir_id)
    anterior = db.scalars(
        base.where(TasaCambio.fecha_vigencia < fecha).order_by(TasaCambio.fecha_vigencia.desc()).limit(1)
    ).first()
    if anterior is not None:
        return anterior
    return db.scalars(
        base.where(TasaCambio.fecha_vigencia > fecha).order_by(TasaCambio.fecha_vigencia.asc()).limit(1)
    ).first()


def _hay_desvio(nueva: Decimal, vecina: TasaCambio | None) -> bool:
    if vecina is None:
        return False
    return abs(nueva - vecina.tasa_a_usd) / vecina.tasa_a_usd > UMBRAL_DESVIO


def _exigir_confirmacion(vecina: TasaCambio) -> ErrorNegocio:
    return ErrorNegocio(
        409,
        "TASA_DESVIO_REQUIERE_CONFIRMACION",
        "La tasa se aleja más de 20 % de la tasa vecina. ¿Seguro? Puede estar invertida",
        extra={
            "tasa_anterior": str(vecina.tasa_a_usd),
            "fecha_anterior": vecina.fecha_vigencia.isoformat(),
        },
    )


def obtener_tasa_vigente(db: Session, moneda_codigo: str, fecha: date) -> Decimal:
    """Tasa con la fecha_vigencia más reciente <= fecha. Sin tasa → 422; nunca se asume 1 (§10.3).

    Devuelve también las tasas históricas de una moneda inactiva (decisión 5 del diseño).
    """
    codigo = "".join(moneda_codigo.split()).upper()
    if codigo == MONEDA_BASE:
        return Decimal("1")
    moneda = moneda_por_codigo(db, codigo)
    if moneda is None:
        raise ErrorNegocio(404, "MONEDA_NO_ENCONTRADA", f"No existe la moneda {codigo}")
    tasa = db.scalar(
        select(TasaCambio.tasa_a_usd)
        .where(TasaCambio.moneda_id == moneda.id, TasaCambio.fecha_vigencia <= fecha)
        .order_by(TasaCambio.fecha_vigencia.desc())
        .limit(1)
    )
    if tasa is None:
        raise ErrorNegocio(
            422, "TASA_NO_DISPONIBLE", f"No hay tasa de {codigo} vigente al {fecha.isoformat()}; regístrela primero"
        )
    return tasa


def listar_tasas(
    db: Session, moneda: str | None = None, desde: date | None = None, hasta: date | None = None
) -> list[TasaCambio]:
    consulta = select(TasaCambio).join(Moneda, Moneda.id == TasaCambio.moneda_id).options(selectinload(TasaCambio.moneda))
    if moneda is not None:
        consulta = consulta.where(Moneda.codigo == "".join(moneda.split()).upper())
    if desde is not None:
        consulta = consulta.where(TasaCambio.fecha_vigencia >= desde)
    if hasta is not None:
        consulta = consulta.where(TasaCambio.fecha_vigencia <= hasta)
    return list(db.scalars(consulta.order_by(Moneda.codigo, TasaCambio.fecha_vigencia.desc())))


def obtener_tasa(db: Session, tasa_id: int) -> TasaCambio:
    tasa = db.get(TasaCambio, tasa_id)
    if tasa is None:
        raise ErrorNegocio(404, "TASA_NO_ENCONTRADA", "Tasa de cambio no encontrada")
    return tasa


def registrar_tasa(
    db: Session,
    actor: Usuario,
    moneda_codigo: str,
    tasa_a_usd: Any,
    fecha_vigencia: date,
    confirmar_desvio: bool = False,
) -> TasaCambio:
    moneda = _moneda_con_tasas(db, moneda_codigo)
    valor = _validar_tasa(tasa_a_usd)
    vecina = tasa_vecina(db, moneda.id, fecha_vigencia)
    desvio = _hay_desvio(valor, vecina)
    if desvio and not confirmar_desvio:
        raise _exigir_confirmacion(vecina)

    tasa = TasaCambio(moneda=moneda, tasa_a_usd=valor, fecha_vigencia=fecha_vigencia, registrado_por=actor.id)
    db.add(tasa)
    enviar(db)
    auditoria.registrar(
        db, actor, "tasa_cambio", tasa.id, "CREAR", despues=_foto(tasa), nota=NOTA_DESVIO if desvio else None
    )
    confirmar(db)
    return tasa


def corregir_tasa(
    db: Session, actor: Usuario, tasa_id: int, tasa_a_usd: Any, confirmar_desvio: bool = False
) -> TasaCambio:
    """Cambia solo el valor. El desvío se mide contra las vecinas, excluyendo la propia fila (decisión 6)."""
    tasa = obtener_tasa(db, tasa_id)
    valor = _validar_tasa(tasa_a_usd)
    vecina = tasa_vecina(db, tasa.moneda_id, tasa.fecha_vigencia, excluir_id=tasa.id)
    desvio = _hay_desvio(valor, vecina)
    if desvio and not confirmar_desvio:
        raise _exigir_confirmacion(vecina)

    antes = _foto(tasa)
    tasa.tasa_a_usd = valor
    auditoria.registrar(
        db,
        actor,
        "tasa_cambio",
        tasa.id,
        "EDITAR",
        antes=antes,
        despues=_foto(tasa),
        nota=NOTA_DESVIO if desvio else None,
    )
    confirmar(db)
    return tasa

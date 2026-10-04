"""M3 Monedas. USD es la moneda base: no se desactiva ni cambia de código, y no admite tasas."""
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import Moneda, Usuario
from app.models.monedas import MONEDA_BASE
from app.services import auditoria

PATRON_ISO4217 = re.compile(r"^[A-Z]{3}$")
CAMPOS_AUDITADOS = ("codigo", "nombre", "simbolo", "activo")


def _foto(moneda: Moneda) -> dict[str, Any]:
    return {campo: getattr(moneda, campo) for campo in CAMPOS_AUDITADOS}


def _validar_codigo(codigo: str) -> str:
    codigo = "".join(codigo.split()).upper()
    if not PATRON_ISO4217.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código de moneda ISO 4217 debe tener exactamente 3 letras")
    return codigo


def _texto(valor: str, campo: str) -> str:
    valor = valor.strip()
    if not valor:
        raise ErrorNegocio(422, "DATOS_INVALIDOS", f"El campo {campo} no puede estar vacío")
    return valor


def listar_monedas(db: Session, activo: bool | None = None) -> list[Moneda]:
    consulta = select(Moneda)
    if activo is not None:
        consulta = consulta.where(Moneda.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Moneda.codigo)))


def obtener_moneda(db: Session, moneda_id: int) -> Moneda:
    moneda = db.get(Moneda, moneda_id)
    if moneda is None:
        raise ErrorNegocio(404, "MONEDA_NO_ENCONTRADA", "Moneda no encontrada")
    return moneda


def moneda_por_codigo(db: Session, codigo: str) -> Moneda | None:
    return db.scalars(select(Moneda).where(Moneda.codigo == "".join(codigo.split()).upper())).one_or_none()


def crear_moneda(db: Session, actor: Usuario, codigo: str, nombre: str, simbolo: str) -> Moneda:
    moneda = Moneda(
        codigo=_validar_codigo(codigo),
        nombre=_texto(nombre, "nombre"),
        simbolo=_texto(simbolo, "simbolo"),
        creado_por=actor.id,
    )
    db.add(moneda)
    enviar(db)
    auditoria.registrar(db, actor, "moneda", moneda.id, "CREAR", despues=_foto(moneda))
    confirmar(db)
    return moneda


def actualizar_moneda(db: Session, actor: Usuario, moneda_id: int, cambios: dict[str, Any]) -> Moneda:
    moneda = obtener_moneda(db, moneda_id)
    antes = _foto(moneda)
    es_base = moneda.codigo == MONEDA_BASE

    with db.no_autoflush:  # nada se escribe antes de confirmar(), que traduce los duplicados
        if "codigo" in cambios:
            nuevo = _validar_codigo(cambios["codigo"])
            if es_base and nuevo != MONEDA_BASE:
                raise ErrorNegocio(409, "MONEDA_BASE_PROTEGIDA", "No se puede cambiar el código de la moneda base USD")
            moneda.codigo = nuevo
        if cambios.get("activo") is False and es_base:
            raise ErrorNegocio(409, "MONEDA_BASE_PROTEGIDA", "No se puede desactivar la moneda base USD")
        if "nombre" in cambios:
            moneda.nombre = _texto(cambios["nombre"], "nombre")
        if "simbolo" in cambios:
            moneda.simbolo = _texto(cambios["simbolo"], "simbolo")
        if "activo" in cambios:
            moneda.activo = cambios["activo"]

        despues = _foto(moneda)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "moneda", moneda_id, accion, antes=antes, despues=despues)
    confirmar(db)
    return moneda

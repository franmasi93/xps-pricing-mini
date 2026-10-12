"""Incoterms 2020 (§9). La matriz de la BD describe la IMPORTACIÓN; la exportación es su complemento.

`bloques_incluidos` y `validar_incoterm_modo` son funciones puras (no tocan la BD): las reutiliza
el motor de cotización de F3. El seguro, cuando aplica, siempre se propone apagado (§9.3.2).
"""
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.models import Incoterm, Usuario
from app.models.incoterms import BLOQUES
from app.services import auditoria

Sentido = Literal["IMPORTACION", "EXPORTACION"]

ADVERTENCIA_DDP_IMPORTACION = (
    "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación"
)
ADVERTENCIA_EXW_EXPORTACION = (
    "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación"
)
CAMPOS_EDITABLES = ("nombre", "solo_maritimo", *BLOQUES, "activo")


def bloques_incluidos(incoterm: Any, sentido: Sentido) -> tuple[list[str], str | None]:
    """IMPORTACION = los bloques en true; EXPORTACION = el complemento (los bloques en false)."""
    if sentido == "IMPORTACION":
        bloques = [bloque for bloque in BLOQUES if getattr(incoterm, bloque)]
    elif sentido == "EXPORTACION":
        bloques = [bloque for bloque in BLOQUES if not getattr(incoterm, bloque)]
    else:
        raise ErrorNegocio(422, "SENTIDO_INVALIDO", "El sentido debe ser IMPORTACION o EXPORTACION")
    advertencia = None
    if not bloques:
        advertencia = ADVERTENCIA_DDP_IMPORTACION if sentido == "IMPORTACION" else ADVERTENCIA_EXW_EXPORTACION
    return bloques, advertencia


def validar_incoterm_modo(incoterm: Any, modo: str) -> None:
    """§9.3.1: FAS, FOB, CFR y CIF solo con LCL o FCL."""
    if incoterm.solo_maritimo and modo == "AEREO":
        raise ErrorNegocio(
            422,
            "INCOTERM_MODO_INVALIDO",
            f"{incoterm.codigo} es solo marítimo. Para aéreo use FCA, CPT o CIP",
        )


def _foto(incoterm: Incoterm) -> dict[str, Any]:
    return {campo: getattr(incoterm, campo) for campo in CAMPOS_EDITABLES}


def listar_incoterms(db: Session) -> list[Incoterm]:
    return list(db.scalars(select(Incoterm).order_by(Incoterm.id)))


def obtener_incoterm(db: Session, codigo: str) -> Incoterm:
    incoterm = db.scalars(select(Incoterm).where(Incoterm.codigo == codigo.strip().upper())).one_or_none()
    if incoterm is None:
        raise ErrorNegocio(404, "INCOTERM_NO_ENCONTRADO", "Incoterm no encontrado")
    return incoterm


def actualizar_incoterm(db: Session, actor: Usuario, codigo: str, cambios: dict[str, Any]) -> Incoterm:
    """§9.3.3: solo admin ajusta la matriz, con auditoría de antes y después."""
    incoterm = obtener_incoterm(db, codigo)
    actor_id = auditoria.id_de(actor)
    antes = _foto(incoterm)
    for campo, valor in cambios.items():
        if campo == "nombre":
            valor = valor.strip()
            if not valor:
                raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
        setattr(incoterm, campo, valor)
    despues = _foto(incoterm)
    if despues != antes:
        incoterm.actualizado_por = actor_id
        accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
        auditoria.registrar(db, actor, "incoterm", incoterm.codigo, accion, antes=antes, despues=despues)
    confirmar(db)
    return incoterm

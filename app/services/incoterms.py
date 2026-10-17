"""Incoterms 2020 (§9). La matriz de la BD describe la IMPORTACIÓN; la exportación es su complemento.

`bloques_incluidos` es pura (no toca la BD) y la reutiliza el motor de cotización de F3. El seguro, cuando
aplica, siempre se propone apagado (§9.3.2).
E0: los servicios permitidos de cada Incoterm viven en incoterm_servicio (antes, solo_maritimo); el aviso cuando
un servicio no está permitido sale del servicio (antes fijo: "Para aéreo use FCA, CPT o CIP").
"""
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.errors import ErrorNegocio, confirmar
from app.models import Incoterm, Usuario
from app.models.incoterms import BLOQUES
from app.services import auditoria, servicios as catalogo_servicios

Sentido = Literal["IMPORTACION", "EXPORTACION"]

ADVERTENCIA_DDP_IMPORTACION = (
    "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación"
)
ADVERTENCIA_EXW_EXPORTACION = (
    "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación"
)
CAMPOS_EDITABLES = ("nombre", *BLOQUES, "activo")


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
    """§9.3.1 (E0): el servicio debe estar entre los permitidos del Incoterm (antes: FAS, FOB, CFR y CIF solo
    con LCL o FCL, que es lo que siembra la 0007)."""
    if any(servicio.codigo == modo for servicio in incoterm.servicios):
        return
    sesion = object_session(incoterm)
    servicio = catalogo_servicios.servicio_por_codigo(sesion, modo) if sesion is not None else None
    if servicio is not None and servicio.aviso_incoterm:
        mensaje = f"{incoterm.codigo} {servicio.aviso_incoterm}"
    else:
        mensaje = f"{incoterm.codigo} no está habilitado para el servicio {servicio.nombre if servicio else modo}"
    raise ErrorNegocio(422, "INCOTERM_MODO_INVALIDO", mensaje)


def _foto(incoterm: Incoterm) -> dict[str, Any]:
    foto = {campo: getattr(incoterm, campo) for campo in CAMPOS_EDITABLES}
    foto["servicios"] = [servicio.codigo for servicio in incoterm.servicios]
    return foto


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
    codigos = cambios.pop("servicios", None)
    if codigos is not None:
        codigos = sorted({"".join(codigo.split()).upper() for codigo in codigos})
        elegidos = [catalogo_servicios.servicio_por_codigo(db, codigo) for codigo in codigos]
        if any(servicio is None for servicio in elegidos):
            raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "Algún servicio indicado no existe")
        incoterm.servicios = sorted(elegidos, key=lambda s: (s.orden, s.id))
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

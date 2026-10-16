"""Datos de la empresa para el PDF (A4 de F4): una sola fila en config_empresa (H-F4-17).

- Los edita quien tenga config.editar (hoy solo admin); cada cambio va a Auditoria.
- Todos admiten vacío (H-F4-8): una tarjeta sin datos no aparece en el PDF.
- Al emitir se COPIAN a la foto de la cotización: un PDF emitido nunca cambia aunque luego se editen.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.rbac import exigir_permiso
from app.models import ConfigEmpresa, Usuario
from app.models.correo import CLAVES_EMPRESA
from app.services import auditoria

PERMISO = "config.editar"
TEXTO_MAXIMO = 2000


def _fila(db: Session) -> ConfigEmpresa:
    return db.get(ConfigEmpresa, 1)


def datos_empresa(db: Session) -> dict[str, str]:
    """Los 14 valores tal como están hoy (se copian a la foto al emitir)."""
    fila = _fila(db)
    return {clave: getattr(fila, clave) for clave in CLAVES_EMPRESA}


def leer_empresa(db: Session, actor: Usuario) -> dict[str, str]:
    exigir_permiso(actor, PERMISO)
    return datos_empresa(db)


def actualizar_empresa(db: Session, actor: Usuario, cambios: dict[str, Any]) -> dict[str, str]:
    exigir_permiso(actor, PERMISO)
    fila = _fila(db)
    antes, despues = {}, {}
    for clave, valor in cambios.items():
        if clave not in CLAVES_EMPRESA:
            continue
        texto = " ".join(str(valor or "").split()) if clave not in ("empresa_horario", "texto_legal_pie",
                                                                    "clausula_fundamental") else str(valor or "").strip()
        if len(texto) > TEXTO_MAXIMO:
            raise ErrorNegocio(422, "CONFIG_VALOR_INVALIDO", f"{clave}: máximo {TEXTO_MAXIMO} caracteres")
        if texto != getattr(fila, clave):
            antes[clave], despues[clave] = getattr(fila, clave), texto
            setattr(fila, clave, texto)
    if despues:
        fila.actualizado_por = auditoria.id_de(actor)
        auditoria.registrar(db, actor, "config_empresa", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return datos_empresa(db)

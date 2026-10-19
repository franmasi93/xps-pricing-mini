"""Datos de la empresa para el PDF (A4 de F4): una sola fila en config_empresa (H-F4-17).

- Los edita quien tenga config.editar (hoy solo admin); cada cambio va a Auditoria.
- Todos admiten vacío (H-F4-8): una tarjeta sin datos no aparece en el PDF.
- Al emitir se COPIAN a la foto de la cotización: un PDF emitido nunca cambia aunque luego se editen.
- E1: whatsapp_numero no es un campo aparte: se calcula del WhatsApp guardado (sin espacios, guiones, paréntesis ni "+";
  con 593 si no trae código de país). Al guardar se valida y se devuelve la vista previa del enlace https://wa.me/….
"""
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.rbac import exigir_permiso
from app.models import ConfigEmpresa, Usuario
from app.models.correo import CLAVES_EMPRESA
from app.services import auditoria

PERMISO = "config.editar"
TEXTO_MAXIMO = 2000


def whatsapp_numero(texto: str | None) -> str:
    """El número para https://wa.me/…: sin espacios, guiones, paréntesis ni "+", y con código de país. Si no lo trae,
    se antepone 593 (Ecuador): 0989154770 → 593989154770; 989154770 → 593989154770."""
    digitos = re.sub(r"[\s\-()+.]", "", texto or "")
    if not digitos or digitos.startswith("593"):
        return digitos
    if digitos.startswith("0"):
        return "593" + digitos[1:]
    if len(digitos) <= 9:
        return "593" + digitos
    return digitos


def whatsapp_valido(numero: str) -> bool:
    """Solo dígitos; uno de Ecuador es 593 + 9 dígitos; otro país, de 11 a 15 dígitos (E.164)."""
    if not numero.isdigit():
        return False
    if numero.startswith("593"):
        return len(numero) == 12
    return 11 <= len(numero) <= 15


def enlace_whatsapp(texto: str | None) -> str | None:
    numero = whatsapp_numero(texto)
    return f"https://wa.me/{numero}" if numero and whatsapp_valido(numero) else None


def _fila(db: Session) -> ConfigEmpresa:
    return db.get(ConfigEmpresa, 1)


def datos_empresa(db: Session) -> dict[str, str]:
    """Los 14 valores tal como están hoy (se copian a la foto al emitir)."""
    fila = _fila(db)
    return {clave: getattr(fila, clave) for clave in CLAVES_EMPRESA}


def _con_enlace(datos: dict[str, str]) -> dict[str, Any]:
    return datos | {"whatsapp_enlace": enlace_whatsapp(datos.get("empresa_whatsapp"))}


def leer_empresa(db: Session, actor: Usuario) -> dict[str, str]:
    exigir_permiso(actor, PERMISO)
    return _con_enlace(datos_empresa(db))


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
        if clave == "empresa_whatsapp" and texto and not whatsapp_valido(whatsapp_numero(texto)):
            raise ErrorNegocio(
                422, "WHATSAPP_INVALIDO",
                "El WhatsApp no forma un número válido (por ejemplo 098 915 4770 o +593 98 915 4770)",
            )
        if texto != getattr(fila, clave):
            antes[clave], despues[clave] = getattr(fila, clave), texto
            setattr(fila, clave, texto)
    if despues:
        fila.actualizado_por = auditoria.id_de(actor)
        auditoria.registrar(db, actor, "config_empresa", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return _con_enlace(datos_empresa(db))

"""Configuración editable por pantalla (§5.2).

La tasa de IVA SIEMPRE se lee de aquí (leer_iva_tasa); la variable IVA_TASA del .env no se usa.
Cada clave declara el permiso que la edita (permiso_edicion), leído de la BD.
"""
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.rbac import exigir_permiso, permisos_de
from app.models import Configuracion, Usuario
from app.services import auditoria

TEXTO_MAXIMO = 5000
RANGOS_DECIMAL = {"iva_tasa": (Decimal("0"), Decimal("100"))}
RANGOS_ENTERO = {"dias_alerta_vencimiento": (1, 365)}


def _invalido(mensaje: str) -> ErrorNegocio:
    return ErrorNegocio(422, "CONFIG_VALOR_INVALIDO", mensaje)


def _normalizar(config: Configuracion, valor: Any) -> str:
    """Valida el valor según la clave y su tipo; devuelve el texto que se guarda."""
    texto = str(valor).strip()
    if config.tipo == "DECIMAL":
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            raise _invalido("Debe ser un número") from None
        minimo, maximo = RANGOS_DECIMAL.get(config.clave, (None, None))
        if not numero.is_finite() or (minimo is not None and not minimo <= numero <= maximo):
            raise _invalido(f"Debe estar entre {minimo} y {maximo}")
        if numero.normalize().as_tuple().exponent < -2:
            raise _invalido("Admite como máximo 2 decimales")
        return str(numero.quantize(Decimal("0.01")))
    if config.tipo == "ENTERO":
        if not texto.lstrip("-").isdigit():
            raise _invalido("Debe ser un número entero")
        numero = int(texto)
        minimo, maximo = RANGOS_ENTERO.get(config.clave, (None, None))
        if minimo is not None and not minimo <= numero <= maximo:
            raise _invalido(f"Debe estar entre {minimo} y {maximo}")
        return str(numero)
    if not texto or len(texto) > TEXTO_MAXIMO:
        raise _invalido(f"Debe tener entre 1 y {TEXTO_MAXIMO} caracteres")
    return texto


def obtener_config(db: Session, clave: str) -> Configuracion:
    config = db.scalars(select(Configuracion).where(Configuracion.clave == clave)).one_or_none()
    if config is None:
        raise ErrorNegocio(404, "CONFIG_NO_ENCONTRADA", f"No existe la clave de configuración {clave}")
    return config


def leer_config(db: Session, clave: str) -> str:
    return obtener_config(db, clave).valor


def leer_iva_tasa(db: Session) -> Decimal:
    """Única fuente de la tasa de IVA para los cálculos (§5.2)."""
    return Decimal(leer_config(db, "iva_tasa")).quantize(Decimal("0.01"))


def listar_config(db: Session, usuario: Usuario) -> list[tuple[Configuracion, bool]]:
    """Cada clave con un indicador de si el usuario puede editarla."""
    permisos = permisos_de(usuario)
    claves = db.scalars(select(Configuracion).order_by(Configuracion.clave))
    return [(config, config.permiso_edicion in permisos) for config in claves]


def actualizar_config(db: Session, actor: Usuario, clave: str, valor: Any) -> Configuracion:
    config = obtener_config(db, clave)
    exigir_permiso(actor, config.permiso_edicion)
    nuevo = _normalizar(config, valor)
    if nuevo != config.valor:
        antes = {"valor": config.valor}
        config.valor = nuevo
        config.actualizado_por = auditoria.id_de(actor)
        auditoria.registrar(db, actor, "configuracion", config.clave, "EDITAR", antes=antes, despues={"valor": nuevo})
    confirmar(db)
    return config

"""E4 "URL pública del sistema" (config_sistema, una fila): la única fuente de los enlaces que salen del sistema.

Enlaces de baja de boletines y avisos, enlaces de los avisos internos y resúmenes, y botones de las plantillas: todos se
arman con url_publica, nunca con una dirección fija en el código. La edita config.editar, con auditoría.
"""
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.rbac import exigir_permiso
from app.models import ConfigSistema, Usuario
from app.services import auditoria

PERMISO = "config.editar"
PATRON_URL = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(:[0-9]{2,5})?$")


def _fila(db: Session, *, bloquear: bool = False) -> ConfigSistema:
    consulta = select(ConfigSistema).where(ConfigSistema.id == 1)
    if bloquear:
        consulta = consulta.with_for_update()
    return db.scalars(consulta.execution_options(populate_existing=True)).one()


def url_publica(db: Session) -> str:
    return _fila(db).url_publica.rstrip("/")


def enlace(db: Session, ruta: str | None = None) -> str:
    """La URL completa de una ruta del sistema (por ejemplo, /app/cotizacion.html?id=5)."""
    ruta = ruta or "/app/inicio.html"
    return f"{url_publica(db)}{ruta if ruta.startswith('/') else '/' + ruta}"


def presentar(db: Session) -> dict[str, Any]:
    fila = _fila(db)
    return {"url_publica": fila.url_publica,
            "actualizado_en": fila.actualizado_en.isoformat() if fila.actualizado_en else None}


def actualizar(db: Session, actor: Usuario, cambios: dict[str, Any]) -> dict[str, Any]:
    exigir_permiso(actor, PERMISO)
    fila = _fila(db, bloquear=True)
    if "url_publica" in cambios:
        url = (cambios["url_publica"] or "").strip().rstrip("/")
        if not PATRON_URL.match(url):
            raise ErrorNegocio(
                422, "URL_PUBLICA_INVALIDA",
                "La URL pública debe empezar con https:// y tener solo el dominio, sin ruta "
                "(por ejemplo, https://pricing.xpress.ec)",
            )
        if url != fila.url_publica:
            auditoria.registrar(db, actor, "config_sistema", 1, "EDITAR", antes={"url_publica": fila.url_publica},
                                despues={"url_publica": url})
            fila.url_publica = url
            fila.actualizado_por = auditoria.id_de(actor)
    confirmar(db)
    return presentar(db)

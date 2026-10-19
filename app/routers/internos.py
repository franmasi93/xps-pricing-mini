"""E1 Endpoints sin JWT: tareas de Cloud Scheduler, callback de Tencent y baja pública.

- POST /internal/boletines/procesar-lote: encabezado X-Tarea-Secreto = TAREAS_SECRETO (comparado en tiempo constante).
  Sin la variable configurada: 503 (deshabilitado).
- POST /internal/tencent/eventos/{token}: el token secreto va en la URL que se registra en la consola de Tencent
  (TENCENT_EVENTOS_TOKEN). Idempotente por MessageId + evento. Con la base apagada responde 503
  SISTEMA_FUERA_DE_HORARIO (el manejador global de F5), para que Tencent reintente si su callback lo hace.
- GET /b/{token} y /baja/{token}: llevan a la página pública /app/baja.html (sin menú ni login).
- GET /v1/publico/baja/{token}: email enmascarado y estado; POST registra la baja; POST …/deshacer la revierte.
  Token inválido o desconocido: mensaje genérico.
"""
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ErrorNegocio
from app.db import get_db
from app.models import BajaCorreo, CampanaDestinatario
from app.services import boletines, motor_envios

router_internos = APIRouter()
router_publico = APIRouter()
GENERICO = "El enlace no es válido o ya no está disponible. Si desea darse de baja, responda el correo con la palabra BAJA."


def _exigir_secreto(recibido: str | None, configurado) -> None:
    if configurado is None or not configurado.get_secret_value():
        raise ErrorNegocio(503, "TAREAS_NO_CONFIGURADAS", "Las tareas internas no están configuradas en este servidor")
    if not recibido or not hmac.compare_digest(recibido, configurado.get_secret_value()):
        raise ErrorNegocio(401, "SECRETO_INVALIDO", "No autorizado")


@router_internos.post("/internal/boletines/procesar-lote", tags=["internos"])
def procesar_lote(x_tarea_secreto: str | None = Header(default=None), db: Session = Depends(get_db)):
    _exigir_secreto(x_tarea_secreto, get_settings().TAREAS_SECRETO)
    return motor_envios.procesar_lote(db)


@router_internos.post("/internal/tencent/eventos/{token}", tags=["internos"])
async def eventos_tencent(token: str, request: Request, db: Session = Depends(get_db)):
    _exigir_secreto(token, get_settings().TENCENT_EVENTOS_TOKEN)
    try:
        cuerpo: Any = await request.json()
    except ValueError:
        raise ErrorNegocio(422, "EVENTO_INVALIDO", "El cuerpo debe ser JSON") from None
    eventos = cuerpo if isinstance(cuerpo, list) else [cuerpo]
    return {"procesados": [motor_envios.registrar_evento(db, e) for e in eventos if isinstance(e, dict)]}


@router_publico.get("/b/{token}", include_in_schema=False)
@router_publico.get("/baja/{token}", include_in_schema=False)
def ir_a_baja(token: str):
    return RedirectResponse(f"/app/baja.html?t={token}", status_code=307)


def _destinatario(db: Session, token: str) -> CampanaDestinatario:
    if not boletines.token_valido(token):
        raise ErrorNegocio(404, "ENLACE_INVALIDO", GENERICO)
    destinatario = db.scalars(select(CampanaDestinatario).where(CampanaDestinatario.token_baja == token)).first()
    if destinatario is None:
        raise ErrorNegocio(404, "ENLACE_INVALIDO", GENERICO)
    return destinatario


def _enmascarar(email: str) -> str:
    usuario, _, dominio = email.partition("@")
    return f"{usuario[:2]}{'•' * max(1, len(usuario) - 2)}@{dominio}"


def _estado(db: Session, destinatario: CampanaDestinatario) -> dict[str, Any]:
    baja = db.scalars(select(BajaCorreo).where(BajaCorreo.email == destinatario.email)).first()
    return {"email": _enmascarar(destinatario.email), "de_baja": bool(baja and not baja.revertida)}


@router_publico.get("/v1/publico/baja/{token}", tags=["publico"])
def ver_baja(token: str, db: Session = Depends(get_db)):
    return _estado(db, _destinatario(db, token))


@router_publico.post("/v1/publico/baja/{token}", tags=["publico"])
def confirmar_baja(token: str, db: Session = Depends(get_db)):
    destinatario = _destinatario(db, token)
    boletines.registrar_baja(db, destinatario.email, "ENLACE", campana_id=destinatario.campana_id)
    db.commit()
    return _estado(db, destinatario)


@router_publico.post("/v1/publico/baja/{token}/deshacer", tags=["publico"])
def deshacer_baja(token: str, db: Session = Depends(get_db)):
    destinatario = _destinatario(db, token)
    baja = db.scalars(select(BajaCorreo).where(BajaCorreo.email == destinatario.email)).first()
    if baja is not None and not baja.revertida:
        boletines.revertir_baja(db, None, baja.id)
    return _estado(db, destinatario)

"""E1 Motor de envíos por lotes (compatible con Cloud Run: cada llamada procesa un lote y termina).

Lo llama Cloud Scheduler cada minuto, dentro del horario de la base, por POST /internal/boletines/procesar-lote con el
secreto en el encabezado. En cada llamada:
1. Sincroniza el estado de las plantillas con Tencent si pasó más de una hora.
2. Activa las campañas PROGRAMADAS cuya hora llegó.
3. Respeta el horario permitido, la pausa entre lotes y los cupos (diario de boletines con reserva, diario total y por
   hora: services/masivos).
4. Toma hasta "tamaño de lote" destinatarios PENDIENTES de campañas ENVIANDO con SELECT … FOR UPDATE SKIP LOCKED,
   UNO POR TRANSACCIÓN: dos llamadas a la vez nunca envían dos veces al mismo (idempotente).
5. Envía con el proveedor de F4 (TriggerType 0), revisa la baja justo antes de enviar y marca el resultado:
   - ENVIADO, con message_id;
   - REBOTADO: dirección inválida o bloqueada;
   - OMITIDO_BAJA, si Tencent dice que se dio de baja (y la registra);
   - error temporal: se reintenta hasta 3 intentos; luego FALLIDO;
   - otro error permanente: FALLIDO.
6. Marca ENVIADA la campaña que se queda sin pendientes.
E3 reutiliza `enviar_uno` y los cupos.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio
from app.models import BajaCorreo, Campana, CampanaDestinatario, PlantillaCorreo
from app.services import boletines, campanas, correo, masivos, plantillas_correo
from app.services.proveedor_correo import Mensaje, traducir

registro = logging.getLogger("xps.motor_envios")
MAXIMO_INTENTOS = 3
REBOTE = {"EMAIL_INVALIDO", "DESTINATARIO_BLOQUEADO"}
SINCRONIZAR_CADA = timedelta(hours=1)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def activar_programadas(db: Session) -> int:
    campanas_listas = list(db.scalars(select(Campana).where(Campana.estado == "PROGRAMADA",
                                                            Campana.programada_para <= _ahora()).with_for_update(skip_locked=True)))
    for campana in campanas_listas:
        campana.estado = "ENVIANDO"
        campana.enviada_en = campana.enviada_en or _ahora()
    db.commit()
    return len(campanas_listas)


def _siguiente(db: Session) -> CampanaDestinatario | None:
    return db.scalars(
        select(CampanaDestinatario)
        .join(Campana, Campana.id == CampanaDestinatario.campana_id)
        .where(Campana.estado == "ENVIANDO", CampanaDestinatario.estado == "PENDIENTE")
        .order_by(CampanaDestinatario.campana_id, CampanaDestinatario.id)
        .limit(1)
        .with_for_update(of=CampanaDestinatario, skip_locked=True)
    ).first()


def _preparado(db: Session, campana: Campana, cache: dict[int, Any]) -> dict[str, Any]:
    """Variables fijas, filas y plantilla de la campaña (una vez por lote)."""
    if campana.id not in cache:
        plantilla = db.get(PlantillaCorreo, campana.plantilla_id)
        fila = masivos.config(db)
        snapshot = campana.snapshot_tarifas
        fijas = campanas.variables_fijas(db, campana, snapshot, campanas._comercial_de(db, campana, None))
        filas = campanas.ajustar_filas(plantilla, fijas, snapshot, fila.url_publica, campana.adjuntar_pdf, fila.limite_filas)
        adjunto = db.scalar(select(Campana.adjunto_pdf).where(Campana.id == campana.id)) or b""
        cache[campana.id] = {"plantilla": plantilla, "fijas": fijas, "filas": filas, "masivos": fila, "adjunto": adjunto}
    return cache[campana.id]


def enviar_uno(db: Session, destinatario: CampanaDestinatario, preparado: dict[str, Any]) -> str:
    """Envía a un destinatario y deja su estado. Devuelve el estado final."""
    if boletines.esta_de_baja(db, destinatario.email):
        destinatario.estado = "OMITIDO_BAJA"
        return destinatario.estado
    vigente = correo.config_vigente(db)
    fila = preparado["masivos"]
    plantilla = preparado["plantilla"]
    variables = campanas.variables_destinatario(
        preparado["fijas"], preparado["filas"], destinatario.nombre, destinatario.empresa,
        campanas._url_baja(fila, destinatario.token_baja),
    )
    campana = destinatario.campana
    resultado = correo._llamar(vigente, Mensaje(
        remitente=fila.remitente or vigente.remitente, destinatario=destinatario.email,
        asunto=campana.asunto or campana.nombre, reply_to=fila.reply_to or vigente.reply_to,
        plantilla_id=plantilla.tencent_id, datos_plantilla=campanas.solo_esperadas(plantilla, variables),
        adjunto_nombre=campanas.nombre_pdf(campana) if preparado["adjunto"] else "", adjunto=preparado["adjunto"],
        trigger_type=0,
    ))
    destinatario.intentos += 1
    if resultado.ok:
        destinatario.estado, destinatario.message_id = "ENVIADO", resultado.message_id
        destinatario.enviado_en, destinatario.ultimo_error = _ahora(), None
        return destinatario.estado
    traduccion = traducir(resultado.codigo_error)
    destinatario.ultimo_error = f"{traduccion.codigo}: {traduccion.mensaje}"[:300]
    if traduccion.codigo == "DESTINATARIO_DADO_DE_BAJA":
        destinatario.estado = "OMITIDO_BAJA"
        boletines.registrar_baja(db, destinatario.email, "TENCENT", campana_id=destinatario.campana_id)
    elif traduccion.codigo in REBOTE:
        destinatario.estado = "REBOTADO"
    elif traduccion.reintentable and destinatario.intentos < MAXIMO_INTENTOS:
        destinatario.estado = "PENDIENTE"
    else:
        destinatario.estado = "FALLIDO"
    return destinatario.estado


def _cerrar_terminadas(db: Session) -> int:
    pendientes = (
        select(func.count()).select_from(CampanaDestinatario)
        .where(CampanaDestinatario.campana_id == Campana.id, CampanaDestinatario.estado == "PENDIENTE")
        .scalar_subquery()
    )
    terminadas = list(db.scalars(select(Campana).where(Campana.estado == "ENVIANDO", pendientes == 0)
                                 .with_for_update(skip_locked=True)))
    for campana in terminadas:
        campanas.recontar(db, campana)
        campana.estado = "ENVIADA"
        campana.terminada_en = _ahora()
    db.commit()
    return len(terminadas)


def _sincronizar_si_toca(db: Session) -> bool:
    fila = masivos.config(db)
    if fila.ultima_sincronizacion and _ahora() - fila.ultima_sincronizacion < SINCRONIZAR_CADA:
        return False
    try:
        plantillas_correo.sincronizar(db, None, silenciosa=True)
    except ErrorNegocio:
        db.rollback()
    return True


def procesar_lote(db: Session) -> dict[str, Any]:
    resumen: dict[str, Any] = {"sincronizo": _sincronizar_si_toca(db), "activadas": activar_programadas(db),
                               "enviados": 0, "rebotados": 0, "fallidos": 0, "omitidos": 0, "reintentos": 0}
    fila = masivos.config(db)
    if not masivos.en_horario(fila):
        resumen["motivo"] = "FUERA_DEL_HORARIO_DE_ENVIO"
        resumen["terminadas"] = _cerrar_terminadas(db)
        return resumen
    if fila.ultimo_lote_en and _ahora() - fila.ultimo_lote_en < timedelta(seconds=fila.pausa_segundos):
        resumen["motivo"] = "PAUSA_ENTRE_LOTES"
        resumen["terminadas"] = _cerrar_terminadas(db)
        return resumen
    disponibles = min(fila.tamano_lote, masivos.disponibles_para_boletines(db, fila))
    if disponibles <= 0:
        resumen["motivo"] = "CUPO_AGOTADO"
    if not correo.config_vigente(db).configurado:
        resumen["motivo"] = "CORREO_NO_CONFIGURADO"
        disponibles = 0
    cache: dict[int, Any] = {}
    procesados = 0
    while procesados < disponibles:
        destinatario = _siguiente(db)
        if destinatario is None:
            break
        estado = enviar_uno(db, destinatario, _preparado(db, destinatario.campana, cache))
        clave = {"ENVIADO": "enviados", "REBOTADO": "rebotados", "FALLIDO": "fallidos", "OMITIDO_BAJA": "omitidos",
                 "PENDIENTE": "reintentos"}[estado]
        resumen[clave] += 1
        campanas.recontar(db, destinatario.campana)
        db.commit()  # una fila por transacción: el bloqueo se libera al confirmar
        procesados += 1
    if procesados:
        masivos.config(db, bloquear=True).ultimo_lote_en = _ahora()
        db.commit()
    resumen["terminadas"] = _cerrar_terminadas(db)
    registro.info("lote de boletines", extra={"resumen": json.dumps(resumen)})
    return resumen


# ---------- Callback de Tencent (eventos) ----------


def registrar_evento(db: Session, evento: dict[str, Any]) -> dict[str, Any]:
    """Un evento del callback de Tencent: idempotente por MessageId + evento.

    - bounce hard → REBOTADO, y el correo queda excluido de futuros masivos (baja TENCENT);
    - bounce soft → se deja para reintento si aún hay intentos;
    - spamreport o unsubscribe → baja;
    - delivered, open y click → solo estadística (sin cambio de estado).
    """
    tipo = str(evento.get("event") or "").lower()
    message_id = str(evento.get("bulkId") or evento.get("bulkid") or evento.get("messageId") or "")
    email = str(evento.get("email") or "").strip().lower()
    destinatario = db.scalars(select(CampanaDestinatario).where(CampanaDestinatario.message_id == message_id)
                              .with_for_update()).first() if message_id else None
    resultado = {"evento": tipo, "encontrado": destinatario is not None, "cambio": None}
    if tipo == "bounce":
        if (evento.get("bounceType") or "").lower() == "hard_bounce":
            if destinatario is not None and destinatario.estado != "REBOTADO":
                destinatario.estado = "REBOTADO"
                destinatario.ultimo_error = f"Rebote definitivo: {str(evento.get('reason') or '')[:200]}"
                campanas.recontar(db, destinatario.campana)
                resultado["cambio"] = "REBOTADO"
            if email and not boletines.esta_de_baja(db, email):
                boletines.registrar_baja(db, email, "TENCENT", campana_id=destinatario.campana_id if destinatario else None)
                resultado["cambio"] = (resultado["cambio"] or "") + "+BAJA"
        elif destinatario is not None and destinatario.estado == "ENVIADO" and destinatario.intentos < MAXIMO_INTENTOS:
            destinatario.estado, destinatario.message_id = "PENDIENTE", None
            destinatario.ultimo_error = f"Rebote temporal: {str(evento.get('reason') or '')[:200]}"
            resultado["cambio"] = "REINTENTO"
    elif tipo in ("spamreport", "unsubscribe") and email:
        if not boletines.esta_de_baja(db, email):
            boletines.registrar_baja(db, email, "TENCENT", campana_id=destinatario.campana_id if destinatario else None)
            resultado["cambio"] = "BAJA"
    db.commit()
    return resultado


_ = BajaCorreo

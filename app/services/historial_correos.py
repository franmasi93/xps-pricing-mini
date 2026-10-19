"""E1-B (6-B) Historial de correos del cliente y eventos de entrega del callback de Tencent.

- Historial: todo lo enviado a los contactos de un cliente, de las tres bitácoras (cotizaciones de F4 en envio_correo,
  boletines de E1 en campana_destinatario y avisos de E3 en notificacion), del más reciente al más antiguo.
- Eventos: cada evento del callback se guarda en tencent_evento y se vincula por MessageId al envío que lo originó
  (COTIZACION, BOLETIN o AVISO); si no hay envío con ese MessageId queda SIN_VINCULAR. Es idempotente por
  MessageId + evento.
- Estado de entrega de un envío: el evento más importante recibido (baja > spam > rebote definitivo > clic > abierto >
  entregado > rebote temporal).
"""
from html import escape
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Campana,
    CampanaDestinatario,
    Cliente,
    Cotizacion,
    EnvioCorreo,
    EnvioCorreoPrueba,
    Notificacion,
    PlantillaCorreo,
    TencentEvento,
)
from app.services import plantillas_diseno

TIPOS = {"COTIZACION": "Cotización", "BOLETIN": "Boletín", "AVISO": "Aviso"}
# evento de Tencent → estado de entrega (con su prioridad: mayor gana).
ENTREGA = {
    "delivery": ("ENTREGADO", 2), "delivered": ("ENTREGADO", 2), "open": ("ABIERTO", 3), "click": ("CLIC", 4),
    "bounce_soft": ("REBOTE_SOFT", 1), "bounce_hard": ("REBOTE_HARD", 5), "spamreport": ("SPAM", 6),
    "unsubscribe": ("BAJA", 7),
}
NOMBRES_ENTREGA = {"ENTREGADO": "Entregado", "ABIERTO": "Abierto", "CLIC": "Clic", "REBOTE_SOFT": "Rebote temporal",
                   "REBOTE_HARD": "Rebote definitivo", "SPAM": "Spam", "BAJA": "Baja", "SIN_EVENTOS": "Sin eventos"}


def tipo_evento(evento: dict[str, Any]) -> str:
    tipo = str(evento.get("event") or "").lower()
    if tipo == "bounce":
        return "bounce_hard" if (evento.get("bounceType") or "").lower() == "hard_bounce" else "bounce_soft"
    return tipo or "desconocido"


def message_id_de(evento: dict[str, Any]) -> str:
    return str(evento.get("bulkId") or evento.get("bulkid") or evento.get("messageId") or evento.get("MessageId") or "")


def vincular(db: Session, message_id: str) -> tuple[str, int | None]:
    if not message_id:
        return "SIN_VINCULAR", None
    # "Enviarme una prueba" (EnvioCorreoPrueba) también se vincula: origen PRUEBA (migración 0013).
    for origen, modelo in (("BOLETIN", CampanaDestinatario), ("AVISO", Notificacion), ("COTIZACION", EnvioCorreo),
                           ("PRUEBA", EnvioCorreoPrueba)):
        encontrado = db.scalar(select(modelo.id).where(modelo.message_id == message_id).limit(1))
        if encontrado is not None:
            return origen, encontrado
    return "SIN_VINCULAR", None


def guardar_evento(db: Session, evento: dict[str, Any]) -> dict[str, Any]:
    """Guarda el evento (idempotente) vinculado a su envío. No hace commit."""
    message_id = message_id_de(evento) or None
    tipo = tipo_evento(evento)
    origen, origen_id = vincular(db, message_id or "")
    datos = {k: v for k, v in evento.items() if isinstance(v, (str, int, float, bool)) or v is None}
    sentencia = insert(TencentEvento).values(
        message_id=message_id, evento=tipo, email=(str(evento.get("email") or "").strip().lower() or None),
        origen=origen, origen_id=origen_id, datos=datos,
    )
    if message_id:
        sentencia = sentencia.on_conflict_do_nothing(index_elements=["message_id", "evento"],
                                                     index_where=TencentEvento.message_id.is_not(None))
    # RETURNING y no rowcount: con psycopg 3 este INSERT da rowcount = -1 (sin conflicto devuelve el id; con conflicto, nada).
    nuevo = db.execute(sentencia.returning(TencentEvento.id)).scalar_one_or_none() is not None
    return {"origen": origen, "origen_id": origen_id, "evento": tipo, "nuevo": nuevo}


def estados_entrega(db: Session, message_ids: list[str]) -> dict[str, str]:
    ids = [m for m in message_ids if m]
    if not ids:
        return {}
    salida: dict[str, tuple[str, int]] = {}
    for message_id, evento in db.execute(select(TencentEvento.message_id, TencentEvento.evento)
                                         .where(TencentEvento.message_id.in_(ids))):
        estado = ENTREGA.get(evento)
        if estado and (message_id not in salida or estado[1] > salida[message_id][1]):
            salida[message_id] = estado
    return {m: e[0] for m, e in salida.items()}


def contadores_campana(db: Session, campana_id: int) -> dict[str, int]:
    """Entregados, abiertos y clics (destinatarios distintos; un abierto cuenta como entregado)."""
    filas = db.execute(select(TencentEvento.origen_id, TencentEvento.evento).join(
        CampanaDestinatario, CampanaDestinatario.id == TencentEvento.origen_id).where(
        TencentEvento.origen == "BOLETIN", CampanaDestinatario.campana_id == campana_id)).all()
    por_destinatario: dict[int, set[str]] = {}
    for origen_id, evento in filas:
        por_destinatario.setdefault(origen_id, set()).add(evento)
    abiertos = {d for d, e in por_destinatario.items() if e & {"open", "click"}}
    return {
        "entregados": sum(1 for e in por_destinatario.values() if e & {"delivery", "delivered", "open", "click"}),
        "abiertos": len(abiertos),
        "clics": sum(1 for e in por_destinatario.values() if "click" in e),
    }


def _plantilla_nombre(db: Session, plantilla_id: int | None, tencent_id: int | None = None) -> str:
    if plantilla_id:
        plantilla = db.get(PlantillaCorreo, plantilla_id)
        if plantilla:
            return f"{plantilla.nombre} ({plantilla.tencent_id})" if plantilla.tencent_id else plantilla.nombre
    if tencent_id:
        plantilla = db.scalars(select(PlantillaCorreo).where(PlantillaCorreo.tencent_id == tencent_id)).first()
        return f"{plantilla.nombre} ({tencent_id})" if plantilla else str(tencent_id)
    return ""


def historial_cliente(db: Session, cliente: Cliente, tipo: str | None = None, estado: str | None = None) -> list[dict[str, Any]]:
    from app.services import correo

    contactos = {c.email.strip().lower(): c for c in cliente.contactos if c.email}
    items: list[dict[str, Any]] = []
    if tipo in (None, "", "COTIZACION"):
        plantilla_f4 = correo.config_vigente(db).plantilla_cotizacion_id
        for envio, numero in db.execute(select(EnvioCorreo, Cotizacion.numero).join(
                Cotizacion, Cotizacion.id == EnvioCorreo.cotizacion_id).where(Cotizacion.cliente_id == cliente.id)):
            items.append({"tipo": "COTIZACION", "id": envio.id, "fecha": envio.fecha, "email": envio.destinatario,
                          "asunto": envio.asunto, "origen": numero, "plantilla": _plantilla_nombre(db, None, plantilla_f4),
                          "estado_envio": envio.estado, "message_id": envio.message_id,
                          "enlace": f"/app/cotizacion.html?id={envio.cotizacion_id}"})
    if tipo in (None, "", "BOLETIN"):
        ids = [c.id for c in cliente.contactos]
        emails = list(contactos)
        if ids or emails:
            consulta = select(CampanaDestinatario, Campana).join(Campana, Campana.id == CampanaDestinatario.campana_id).where(
                (CampanaDestinatario.contacto_id.in_(ids)) | (func.lower(CampanaDestinatario.email).in_(emails)))
            for destinatario, campana in db.execute(consulta):
                items.append({"tipo": "BOLETIN", "id": destinatario.id, "fecha": destinatario.enviado_en or campana.enviada_en,
                              "email": destinatario.email, "asunto": campana.asunto or campana.nombre,
                              "origen": campana.nombre, "plantilla": _plantilla_nombre(db, campana.plantilla_id),
                              "estado_envio": destinatario.estado, "message_id": destinatario.message_id,
                              "enlace": f"/app/campana.html?id={campana.id}"})
    if tipo in (None, "", "AVISO"):
        for aviso in db.scalars(select(Notificacion).where(Notificacion.cliente_id == cliente.id,
                                                           Notificacion.canal == "CORREO",
                                                           Notificacion.audiencia == "EXTERNA")):
            enlace = aviso.enlace if aviso.entidad_tipo == "cotizacion" else "/app/notificaciones-bitacora.html"
            items.append({"tipo": "AVISO", "id": aviso.id, "fecha": aviso.enviado_en or aviso.creado_en, "email": aviso.email or "",
                          "asunto": aviso.asunto or aviso.titulo, "origen": aviso.titulo,
                          "plantilla": _plantilla_nombre(db, aviso.plantilla_id), "estado_envio": aviso.estado,
                          "message_id": aviso.message_id, "enlace": enlace})
    entregas = estados_entrega(db, [i["message_id"] for i in items])
    salida = []
    for item in items:
        contacto = contactos.get((item["email"] or "").strip().lower())
        item["contacto"] = contacto.nombre if contacto else ""
        item["tipo_nombre"] = TIPOS[item["tipo"]]
        item["estado_entrega"] = entregas.get(item["message_id"] or "", "SIN_EVENTOS")
        item["estado_entrega_nombre"] = NOMBRES_ENTREGA[item["estado_entrega"]]
        if estado and estado not in (item["estado_envio"], item["estado_entrega"]):
            continue
        salida.append(item)
    salida.sort(key=lambda i: i["fecha"].timestamp() if i["fecha"] else 0, reverse=True)
    return salida


def _render(plantilla: PlantillaCorreo | None, variables: dict[str, str]) -> str:
    if plantilla is None or not plantilla.html:
        return "<p>(La plantilla de este correo no está disponible en el sistema.)</p>"
    return plantillas_diseno.PATRON_VARIABLE.sub(lambda m: escape(str(variables.get(m.group(1), ""))), plantilla.html)


def vista_previa(db: Session, cliente: Cliente, tipo: str, envio_id: int) -> dict[str, Any]:
    """El correo tal como salió (variables reales), con el enlace a su origen."""
    from app.core.errors import ErrorNegocio
    from app.services import campanas, correo, masivos, pdf, sistema

    item = next((i for i in historial_cliente(db, cliente, tipo) if i["id"] == envio_id and i["tipo"] == tipo), None)
    if item is None:
        raise ErrorNegocio(404, "ENVIO_NO_ENCONTRADO", "Ese envío no es de este cliente")
    variables: dict[str, str] = {}
    if tipo == "AVISO":
        aviso = db.get(Notificacion, envio_id)
        variables = dict(aviso.variables or {})
        html = _render(aviso.plantilla, variables)
    elif tipo == "COTIZACION":
        envio = db.get(EnvioCorreo, envio_id)
        cotizacion = db.get(Cotizacion, envio.cotizacion_id)
        foto = cotizacion.snapshot_emision or {}
        contacto = next((c for c in cliente.contactos if (c.email or "").lower() == envio.destinatario.lower()), None)
        variables = {"contacto": contacto.nombre if contacto else "", "numero": cotizacion.numero or "",
                     "valida_hasta": pdf.fecha_corta(cotizacion.valida_hasta),
                     "comercial": (foto.get("comercial") or {}).get("nombre", "")}
        plantilla = db.scalars(select(PlantillaCorreo).where(
            PlantillaCorreo.tencent_id == correo.config_vigente(db).plantilla_cotizacion_id)).first()
        html = _render(plantilla, variables)
    else:
        destinatario = db.get(CampanaDestinatario, envio_id)
        campana = db.get(Campana, destinatario.campana_id)
        plantilla = db.get(PlantillaCorreo, campana.plantilla_id) if campana.plantilla_id else None
        if campana.snapshot_tarifas and plantilla is not None:
            fila = masivos.config(db)
            fijas = campanas.variables_fijas(db, campana, campana.snapshot_tarifas, campanas._comercial_de(db, campana, None))
            filas = campanas.ajustar_filas(plantilla, fijas, campana.snapshot_tarifas, sistema.url_publica(db),
                                           campana.adjuntar_pdf, fila.limite_filas)
            variables = campanas.variables_destinatario(fijas, filas, destinatario.nombre, destinatario.empresa,
                                                        campanas._url_baja(sistema.url_publica(db), destinatario.token_baja))
            variables["comercial"] = campanas.comercial_del_contacto(db, destinatario.contacto_id, variables.get("comercial", ""))
            html = _render(plantilla, variables)
        else:
            html = _render(plantilla, {})
    # Las variables reales también van aparte: se ven aunque el HTML de la plantilla no esté guardado en el sistema.
    return {"tipo": tipo, "id": envio_id, "asunto": item["asunto"], "plantilla": item["plantilla"], "html": html,
            "variables": {k: str(v) for k, v in variables.items()}, "enlace": item["enlace"], "estado_envio": item["estado_envio"], "estado_entrega": item["estado_entrega_nombre"]}


def eventos(db: Session, origen: str | None = None, limite: int = 200) -> list[TencentEvento]:
    consulta = select(TencentEvento)
    if origen:
        consulta = consulta.where(TencentEvento.origen == origen)
    return list(db.scalars(consulta.order_by(TencentEvento.id.desc()).limit(limite)))


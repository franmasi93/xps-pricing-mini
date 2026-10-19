"""E1 Campañas de boletines: borradores, tarifas, destinatarios, vista previa, prueba, envío o programación y estados.

Regla de oro: no se duplican tarifas. El borrador guarda solo los IDs; al enviar o programar se congela una copia de
venta (snapshot_tarifas) de lo que se manda. Nunca lleva costo, margen ni proveedor: solo la aerolínea o naviera.

Variables (Tencent: valores de texto plano, sin HTML; todo el JSON ≤ plantillas_diseno.LIMITE_TEMPLATE_DATA): titulo, intro, vigencia, comercial,
contacto, empresa, baja, f1…fN y mas. Las filas que no caben (o que superan las de la plantilla) van en el PDF adjunto.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import (
    Campana,
    CampanaDestinatario,
    Cliente,
    ContactoCliente,
    EnvioCorreoPrueba,
    ListaEnvio,
    Puerto,
    Tarifa,
    Usuario,
)
from app.services import (
    auditoria, boletines, correo, masivos, pdf, plantillas_correo, plantillas_diseno, servicios, sistema,
)
from app.services.configuracion import leer_config
from app.services.empresa import whatsapp_numero
from app.services.proveedor_correo import Mensaje
from app.services.tarifas import precio_venta_kg, precios_de

ZONA = ZoneInfo("America/Guayaquil")
DIR_PLANTILLAS = Path(__file__).resolve().parent.parent / "templates"
MAXIMO_INTRO = 160
MAXIMO_TITULO = 80
MAXIMO_CONTACTO = 40
MAXIMO_EMPRESA = 50
PATRON_FILA = re.compile(r"^(?:f|fila_)(\d+)$")
OPCIONALES = {"mas", "mas_tarifas", "empresa_direccion", "empresa_telefono", "empresa_whatsapp", "empresa_horario",
              "whatsapp_numero"}


# ---------- Foto de venta de una tarifa (para el boletín) ----------


def _corto(nombre: str) -> str:
    return (nombre or "").split(" (")[0].strip()[:18]


def foto_tarifa(tarifa: Tarifa) -> dict[str, Any]:
    """Lo que sale en el boletín: venta (nunca costo), ruta, vigencia y transportista (nunca el proveedor)."""
    venta, minimo = precios_de(tarifa)
    servicio = tarifa.servicio
    forma = servicios.forma_de(servicio)
    datos = {
        "tarifa_id": tarifa.id,
        "servicio": servicio.codigo,
        "servicio_nombre": servicio.nombre,
        "etiqueta_transportista": servicio.etiqueta_transportista,
        "forma_cobro": servicio.forma_cobro,
        "origen": tarifa.origen.codigo, "origen_nombre": tarifa.origen.nombre,
        "destino": tarifa.destino.codigo, "destino_nombre": tarifa.destino.nombre,
        "moneda": tarifa.moneda.codigo,
        "precio_venta": str(venta),
        "minimo_venta": str(minimo),
        "rate_unit": tarifa.rate_unit,
        "unidad_peso": tarifa.unidad_peso,
        "tramos": [[str(t.desde_kg), str(precio_venta_kg(tarifa, t))] for t in tarifa.tramos],
        "tipo_equipo": tarifa.tipo_equipo.codigo if tarifa.tipo_equipo else None,
        "tipo_equipo_nombre": tarifa.tipo_equipo.nombre if tarifa.tipo_equipo else None,
        "transit_time_dias": tarifa.transit_time_dias,
        "dias_libres": tarifa.dias_libres,
        "valido_hasta": tarifa.valido_hasta.isoformat(),
        "transportista": tarifa.transportista,
    }
    datos["texto_tarifa"] = forma.texto_tarifa(datos)
    datos["detalle"] = forma.detalle(datos)
    partes = [f"{_corto(datos['origen_nombre'])} → {_corto(datos['destino_nombre'])}", datos["texto_tarifa"]]
    if tarifa.transit_time_dias is not None:
        partes.append(f"{tarifa.transit_time_dias} días")
    partes.append(f"vigente al {tarifa.valido_hasta.strftime('%d/%m/%Y')}")
    if tarifa.transportista:
        partes.append(tarifa.transportista)
    datos["fila"] = " · ".join(partes)
    return datos


def _consulta_tarifas():
    return select(Tarifa).options(
        selectinload(Tarifa.origen), selectinload(Tarifa.destino), selectinload(Tarifa.moneda),
        selectinload(Tarifa.tipo_equipo), selectinload(Tarifa.tramos),
    )


def tarifas_disponibles(db: Session, fecha: date | None = None) -> list[dict[str, Any]]:
    """Las tarifas activas y vigentes en la fecha, agrupadas por servicio activo (fuente única de E0), en su orden."""
    fecha = fecha or fechas.hoy_ecuador()
    dias = max(7, int(leer_config(db, "dias_alerta_vencimiento")))
    grupos = []
    for servicio in servicios.servicios_activos(db):
        tarifas = db.scalars(_consulta_tarifas().where(
            Tarifa.activo.is_(True), Tarifa.modo == servicio.codigo, Tarifa.valido_desde <= fecha,
            Tarifa.valido_hasta >= fecha).order_by(Tarifa.origen_puerto_id, Tarifa.destino_puerto_id, Tarifa.id))
        filas = []
        for tarifa in tarifas:
            foto = foto_tarifa(tarifa)
            foto["por_vencer"] = tarifa.valido_hasta < fecha + timedelta(days=dias)
            foto["origen_id"], foto["destino_id"] = tarifa.origen_puerto_id, tarifa.destino_puerto_id
            foto["tipo_equipo_id"] = tarifa.tipo_equipo_id
            filas.append(foto)
        grupos.append({"servicio": servicio.codigo, "nombre": servicio.nombre, "forma_cobro": servicio.forma_cobro,
                       "usa_tipo_equipo": servicio.usa_tipo_equipo, "tarifas": filas})
    return grupos


# ---------- Borradores ----------


CAMPOS_BORRADOR = ("nombre", "asunto", "texto_intro", "plantilla_id", "servicios", "tipos_equipo", "tarifas_ids",
                   "listas_ids", "adjuntar_pdf")


def _foto(campana: Campana) -> dict[str, Any]:
    return {campo: getattr(campana, campo) for campo in (*CAMPOS_BORRADOR, "estado", "programada_para")}


def obtener(db: Session, campana_id: int, *, bloquear: bool = False) -> Campana:
    consulta = select(Campana).where(Campana.id == campana_id)
    if bloquear:
        consulta = consulta.with_for_update()
    campana = db.scalars(consulta).one_or_none()
    if campana is None:
        raise ErrorNegocio(404, "CAMPANA_NO_ENCONTRADA", "Campaña no encontrada")
    return campana


def _validar_borrador(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    datos["nombre"] = " ".join((datos.get("nombre") or "").split())
    if not datos["nombre"]:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre interno no puede estar vacío")
    datos["asunto"] = " ".join((datos.get("asunto") or "").split())
    if len(datos["asunto"]) > MAXIMO_TITULO:
        raise ErrorNegocio(422, "CAMPANA_INVALIDA", f"El asunto admite como máximo {MAXIMO_TITULO} caracteres")
    datos["texto_intro"] = " ".join((datos.get("texto_intro") or "").split())
    if len(datos["texto_intro"]) > MAXIMO_INTRO:
        raise ErrorNegocio(
            422, "CAMPANA_INVALIDA",
            f"El texto de introducción admite como máximo {MAXIMO_INTRO} caracteres (límite de las plantillas de Tencent)",
        )
    for campo in ("tarifas_ids", "listas_ids", "tipos_equipo"):
        datos[campo] = sorted({int(v) for v in datos.get(campo) or []})
    datos["servicios"] = sorted({str(v) for v in datos.get("servicios") or []})
    datos["adjuntar_pdf"] = bool(datos.get("adjuntar_pdf", True))
    if datos.get("plantilla_id") is not None:
        plantilla = plantillas_correo.obtener(db, datos["plantilla_id"])
        if plantilla.uso != "BOLETIN":
            raise ErrorNegocio(422, "PLANTILLA_NO_DISPONIBLE", "Elija una plantilla de uso BOLETIN")
    return datos


def _editable(db: Session, campana_id: int) -> Campana:
    campana = obtener(db, campana_id, bloquear=True)
    if campana.estado != "BORRADOR":
        raise ErrorNegocio(409, "CAMPANA_NO_EDITABLE", "Solo se edita una campaña en borrador")
    return campana


def crear(db: Session, actor: Usuario, datos: dict[str, Any]) -> Campana:
    fila = masivos.config(db)
    base = {"asunto": "", "texto_intro": "", "plantilla_id": None, "servicios": [], "tipos_equipo": [], "tarifas_ids": [],
            "listas_ids": [], "adjuntar_pdf": fila.adjuntar_pdf}
    datos = _validar_borrador(db, base | dict(datos))
    campana = Campana(**{campo: datos[campo] for campo in CAMPOS_BORRADOR}, creado_por=auditoria.id_de(actor))
    db.add(campana)
    enviar(db)
    auditoria.registrar(db, actor, "campana", campana.id, "CREAR", despues=_foto(campana))
    confirmar(db)
    return campana


def actualizar(db: Session, actor: Usuario, campana_id: int, cambios: dict[str, Any]) -> Campana:
    campana = _editable(db, campana_id)
    antes = _foto(campana)
    final = _validar_borrador(db, {campo: getattr(campana, campo) for campo in CAMPOS_BORRADOR} | cambios)
    with db.no_autoflush:
        for campo in CAMPOS_BORRADOR:
            setattr(campana, campo, final[campo])
        despues = _foto(campana)
        if despues != antes:
            auditoria.registrar(db, actor, "campana", campana.id, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return campana


def descartar(db: Session, actor: Usuario, campana_id: int) -> None:
    campana = _editable(db, campana_id)
    antes = _foto(campana)
    db.delete(campana)
    auditoria.registrar(db, actor, "campana", campana_id, "DESACTIVAR", antes=antes, nota="BORRADOR DESCARTADO")
    confirmar(db)


# ---------- Tarifas de la campaña ----------


def _tarifas_de(db: Session, campana: Campana) -> list[Tarifa]:
    if not campana.tarifas_ids:
        return []
    return list(db.scalars(_consulta_tarifas().where(Tarifa.id.in_(campana.tarifas_ids))
                           .order_by(Tarifa.modo, Tarifa.origen_puerto_id, Tarifa.destino_puerto_id, Tarifa.id)))


def revisar_tarifas(db: Session, campana: Campana, fecha: date) -> tuple[list[Tarifa], list[str]]:
    """Exige al menos una tarifa, todas activas y vigentes en la fecha de envío; avisa las que vencen pronto."""
    tarifas = _tarifas_de(db, campana)
    if not tarifas:
        raise ErrorNegocio(422, "SIN_TARIFAS", "Elija al menos una tarifa vigente")
    if len(tarifas) != len(campana.tarifas_ids):
        raise ErrorNegocio(422, "TARIFA_INEXISTENTE", "Alguna tarifa de la campaña ya no existe")
    vencidas = [t for t in tarifas if not (t.activo and t.valido_desde <= fecha <= t.valido_hasta)]
    if vencidas:
        detalle = ", ".join(f"#{t.id} {t.origen.codigo}→{t.destino.codigo}" for t in vencidas[:10])
        raise ErrorNegocio(
            422, "TARIFA_NO_VIGENTE",
            f"Hay {len(vencidas)} tarifas inactivas o no vigentes al {fecha.strftime('%d/%m/%Y')}: {detalle}. Quítelas de la campaña.",
            extra={"tarifas": [t.id for t in vencidas]},
        )
    dias = max(7, int(leer_config(db, "dias_alerta_vencimiento")))
    pronto = [t for t in tarifas if t.valido_hasta < fecha + timedelta(days=dias)]
    avisos = [
        f"La tarifa #{t.id} {t.origen.codigo}→{t.destino.codigo} vence el {t.valido_hasta.strftime('%d/%m/%Y')}"
        for t in pronto
    ]
    return tarifas, avisos


def snapshot_de(db: Session, campana: Campana, tarifas: list[Tarifa], fecha: date) -> dict[str, Any]:
    orden = {s.codigo: i for i, s in enumerate(servicios.servicios_activos(db))}
    fotos = sorted((foto_tarifa(t) for t in tarifas), key=lambda f: (orden.get(f["servicio"], 999), f["origen"],
                                                                     f["destino"], f["tarifa_id"]))
    vigencia = min(date.fromisoformat(f["valido_hasta"]) for f in fotos)
    return {"fecha": fecha.isoformat(), "vigencia": vigencia.isoformat(), "tarifas": fotos}


# ---------- Variables (texto plano, con tope de tamaño) ----------


def _bytes(datos: dict[str, str]) -> int:
    return len(json.dumps(datos, ensure_ascii=False).encode("utf-8"))


def _filas_de_plantilla(plantilla) -> list[str]:
    """Las variables de filas de la plantilla (fila_01…fila_15 en la 72746; f1…fN también sirve), en orden."""
    return sorted((v for v in plantilla.variables_esperadas if PATRON_FILA.match(v)),
                  key=lambda v: int(PATRON_FILA.match(v).group(1)))


def _url_baja(url_publica: str, token: str) -> str:
    """E4: la URL pública sale de config_sistema (sistema.url_publica), nunca fija."""
    return f"{url_publica.rstrip('/')}/b/{token}"


def datos_empresa(db: Session) -> dict[str, str]:
    """Las variables empresa_* y whatsapp_numero, desde los datos de la empresa de F4 (config_empresa)."""
    from app.models import ConfigEmpresa

    fila = db.get(ConfigEmpresa, 1)
    valor = lambda campo: (getattr(fila, campo) or "").strip() if fila else ""  # noqa: E731
    return {
        "empresa_direccion": valor("empresa_direccion_matriz"),
        "empresa_telefono": " · ".join(v for v in (valor("empresa_telefono"), valor("empresa_celular")) if v),
        "empresa_whatsapp": valor("empresa_whatsapp"),
        "empresa_horario": valor("empresa_horario"),
        "whatsapp_numero": whatsapp_numero(valor("empresa_whatsapp")),
    }


def variables_fijas(db: Session, campana: Campana, snapshot: dict[str, Any], comercial: str) -> dict[str, str]:
    intro = campana.texto_intro or "Le compartimos nuestras tarifas vigentes."
    return {
        "titulo": campana.asunto or campana.nombre,
        "texto_intro": intro, "intro": intro,
        "vigencia": date.fromisoformat(snapshot["vigencia"]).strftime("%d/%m/%Y"),
        "comercial": comercial[:MAXIMO_CONTACTO],
    } | datos_empresa(db)


def _con_alias(datos: dict[str, str]) -> dict[str, str]:
    """Los nombres de variable que usan las plantillas (72746: nombre_contacto, enlace_baja, mas_tarifas)."""
    return datos | {"nombre_contacto": datos.get("contacto", ""), "enlace_baja": datos.get("baja", ""),
                    "mas_tarifas": datos.get("mas", "")}


def ajustar_filas(plantilla, fijas: dict[str, str], snapshot: dict[str, Any], url_publica: str, adjuntar_pdf: bool,
                  limite_filas: int) -> dict[str, str]:
    """Las filas que caben en el tope de tamaño de Tencent con el peor caso de contacto, empresa y enlace de baja, contando
    solo las variables que la plantilla tiene. Devuelve las filas (vacías las que no se usan) y "mas"."""
    huecos = _filas_de_plantilla(plantilla)[:limite_filas]
    peor = fijas | {"contacto": "x" * MAXIMO_CONTACTO, "empresa": "x" * MAXIMO_EMPRESA,
                    "baja": f"{url_publica.rstrip('/')}/b/" + "x" * 33}
    filas = {hueco: "" for hueco in _filas_de_plantilla(plantilla)}
    textos = [f"• {t['fila']}" for t in snapshot["tarifas"]]
    mas_peor = f"Y {len(textos)} tarifas más en el PDF adjunto"
    usadas = 0
    for hueco, texto in zip(huecos, textos):
        prueba = solo_esperadas(plantilla, _con_alias(peor | filas | {hueco: texto, "mas": mas_peor}))
        if _bytes(prueba) > plantillas_diseno.LIMITE_TEMPLATE_DATA:
            break
        filas[hueco] = texto
        usadas += 1
    resto = len(textos) - usadas
    if resto and not adjuntar_pdf:
        raise ErrorNegocio(
            422, "FILAS_INSUFICIENTES",
            f"En el correo caben {usadas} de {len(textos)} tarifas (límite de tamaño de las variables de Tencent). Active "
            "\"Adjuntar PDF\" o reduzca las tarifas.",
        )
    return filas | {"mas": f"Y {resto} tarifas más en el PDF adjunto" if resto else ""}


def variables_destinatario(fijas: dict[str, str], filas: dict[str, str], nombre: str, empresa: str, baja: str) -> dict[str, str]:
    return _con_alias(fijas | filas | {"contacto": (nombre or "cliente")[:MAXIMO_CONTACTO],
                                       "empresa": (empresa or "")[:MAXIMO_EMPRESA], "baja": baja})


def solo_esperadas(plantilla, datos: dict[str, str]) -> dict[str, str]:
    return {clave: datos.get(clave, "") for clave in plantilla.variables_esperadas}


# ---------- Destinatarios ----------


def resolver_destinatarios(db: Session, listas_ids: list[int]) -> tuple[list[tuple[ContactoCliente, Cliente]], int]:
    """Contactos de las listas activas, deduplicados por email (el primero gana). Devuelve (únicos, duplicados)."""
    if not listas_ids:
        return [], 0
    listas = list(db.scalars(select(ListaEnvio).where(ListaEnvio.id.in_(listas_ids))))
    if len(listas) != len(set(listas_ids)):
        raise ErrorNegocio(422, "LISTA_INEXISTENTE", "Alguna lista de la campaña ya no existe")
    vistos: dict[str, tuple[ContactoCliente, Cliente]] = {}
    duplicados = 0
    for lista in sorted(listas, key=lambda l: l.id):
        if not lista.activo:
            raise ErrorNegocio(422, "LISTA_INACTIVA", f"La lista «{lista.nombre}» está inactiva")
        for contacto in boletines.contactos_de(db, lista):
            email = contacto.email.strip().lower()
            if email in vistos:
                duplicados += 1
                continue
            vistos[email] = (contacto, db.get(Cliente, contacto.cliente_id))
    return list(vistos.values()), duplicados


def conteo(db: Session, campana_id: int) -> dict[str, Any]:
    campana = obtener(db, campana_id)
    unicos, duplicados = resolver_destinatarios(db, campana.listas_ids)
    emails = [c.email.strip().lower() for c, _ in unicos]
    bajas = boletines.bajas_activas(db, emails)
    total = len(unicos) + duplicados
    return {"total": total, "omitidos_baja": len(bajas), "duplicados": duplicados, "recibiran": len(unicos) - len(bajas)}


# ---------- Vista previa y PDF ----------


def _render(plantilla, datos: dict[str, str]) -> str:
    """El HTML de la plantilla con las variables reemplazadas (escapadas), como lo arma Tencent."""
    html = plantilla.html or ""
    return plantillas_diseno.PATRON_VARIABLE.sub(lambda m: escape(datos.get(m.group(1), "")), html)


def _comercial_de(db: Session, campana: Campana, actor: Usuario | None) -> str:
    usuario = db.get(Usuario, campana.enviado_por or campana.creado_por) if (campana.enviado_por or campana.creado_por) else actor
    return usuario.nombre if usuario else "el equipo de Pricing"


def preparar(db: Session, campana: Campana, actor: Usuario | None, fecha: date) -> dict[str, Any]:
    """Todo lo que necesita la vista previa, la prueba y el envío: snapshot, variables fijas y filas."""
    if campana.plantilla_id is None:
        raise ErrorNegocio(422, "PLANTILLA_REQUERIDA", "Elija una plantilla")
    plantilla = plantillas_correo.obtener(db, campana.plantilla_id)
    tarifas, avisos = revisar_tarifas(db, campana, fecha)
    snapshot = campana.snapshot_tarifas if campana.estado != "BORRADOR" and campana.snapshot_tarifas else snapshot_de(
        db, campana, tarifas, fecha)
    fila = masivos.config(db)
    url = sistema.url_publica(db)
    fijas = variables_fijas(db, campana, snapshot, _comercial_de(db, campana, actor))
    filas = ajustar_filas(plantilla, fijas, snapshot, url, campana.adjuntar_pdf, fila.limite_filas)
    return {"plantilla": plantilla, "snapshot": snapshot, "fijas": fijas, "filas": filas, "avisos": avisos,
            "masivos": fila, "url_publica": url}


def vista_previa(db: Session, actor: Usuario, campana_id: int) -> dict[str, Any]:
    campana = obtener(db, campana_id)
    hoy = fechas.hoy_ecuador()
    datos = preparar(db, campana, actor, hoy)
    ejemplo = variables_destinatario(datos["fijas"], datos["filas"], "Nombre del contacto", "Empresa del cliente",
                                     _url_baja(datos["url_publica"], "token-de-ejemplo"))
    plantilla = datos["plantilla"]
    if not plantilla.html:
        html = ("<p>Esta plantilla no tiene una copia del HTML en el sistema; la vista previa muestra solo las "
                "variables.</p>" + "".join(f"<p><b>{escape(k)}</b>: {escape(v)}</p>" for k, v in ejemplo.items()))
    else:
        html = _render(plantilla, ejemplo)
    return {"html": html, "variables": solo_esperadas(plantilla, ejemplo), "bytes": _bytes(solo_esperadas(plantilla, ejemplo)),
            "filas_en_correo": sum(1 for k, v in datos["filas"].items() if PATRON_FILA.match(k) and v),
            "tarifas": len(datos["snapshot"]["tarifas"]), "avisos": datos["avisos"],
            "plantilla": {"id": plantilla.id, "nombre": plantilla.nombre, "tencent_id": plantilla.tencent_id,
                          "estado_tencent": plantilla.estado_tencent}}


def _entorno() -> Environment:
    entorno = Environment(loader=FileSystemLoader(DIR_PLANTILLAS), autoescape=select_autoescape(["html"]))
    entorno.filters["fecha"] = pdf.fecha_corta
    return entorno


def generar_pdf(db: Session, snapshot: dict[str, Any], titulo: str) -> bytes:
    """PDF con todas las tarifas de la campaña, una tabla por servicio (formateador de su forma de cobro)."""
    secciones: list[dict[str, Any]] = []
    for foto in snapshot["tarifas"]:
        if not secciones or secciones[-1]["servicio"] != foto["servicio"]:
            secciones.append({"servicio": foto["servicio"], "nombre": foto["servicio_nombre"],
                              "etiqueta": foto["etiqueta_transportista"], "filas": []})
        secciones[-1]["filas"].append(foto)
    html = _entorno().get_template("boletin_tarifas.html").render(
        titulo=titulo, secciones=secciones, vigencia=snapshot["vigencia"], fecha=snapshot["fecha"],
        logo=pdf._base64(pdf.LOGO), fuente_inter=pdf._base64(pdf.FUENTE_INTER), razon_social=pdf.RAZON_SOCIAL,
    )
    return pdf.generar_pdf(html, pdf.pie_de_pagina({"fecha_emision": snapshot["fecha"]}).replace(
        "Cotización de servicios logísticos", "Tarifas vigentes"))


def nombre_pdf(campana: Campana) -> str:
    return f"Tarifas_XPRESS_{campana.id}.pdf"


# ---------- Prueba ----------


def enviar_prueba(db: Session, actor: Usuario, campana_id: int, email: str | None) -> dict[str, Any]:
    """Solo al correo del usuario o a los correos internos de prueba configurados. Nunca a clientes."""
    campana = obtener(db, campana_id)
    fila = masivos.config(db)
    permitidos = {actor.email.strip().lower(), *masivos.correos_prueba(fila)}
    destino = (email or actor.email).strip().lower()
    if destino not in permitidos:
        raise ErrorNegocio(403, "PRUEBA_NO_PERMITIDA",
                           "La prueba solo se envía a su propio correo o a los correos internos de prueba configurados")
    hoy = fechas.hoy_ecuador()
    datos = preparar(db, campana, actor, hoy)
    plantilla = plantillas_correo.plantilla_utilizable(db, campana.plantilla_id, "BOLETIN")
    variables = variables_destinatario(datos["fijas"], datos["filas"], actor.nombre, "Prueba interna",
                                       _url_baja(datos["url_publica"], "prueba"))
    plantillas_correo.exigir_variables(plantilla, variables, OPCIONALES | set(_filas_de_plantilla(plantilla)))
    vigente = correo.config_vigente(db)
    if not vigente.configurado:
        raise ErrorNegocio(503, "CORREO_NO_CONFIGURADO", "El correo no está configurado: cargue las llaves en Configuración.")
    adjunto = generar_pdf(db, datos["snapshot"], campana.asunto or campana.nombre) if campana.adjuntar_pdf else b""
    asunto = f"[PRUEBA] {campana.asunto or campana.nombre}"
    resultado = correo._llamar(vigente, Mensaje(
        remitente=fila.remitente or vigente.remitente, destinatario=destino, asunto=asunto,
        reply_to=fila.reply_to or vigente.reply_to, plantilla_id=plantilla.tencent_id,
        datos_plantilla=solo_esperadas(plantilla, variables), adjunto_nombre=nombre_pdf(campana) if adjunto else "",
        adjunto=adjunto, trigger_type=0,
    ))
    from app.services.proveedor_correo import traducir

    traduccion = None if resultado.ok else traducir(resultado.codigo_error)
    db.add(EnvioCorreoPrueba(
        destinatario=destino, asunto=asunto[:300], adjunto_nombre=nombre_pdf(campana) if adjunto else "",
        adjunto_bytes=len(adjunto), estado="ENVIADO" if resultado.ok else "FALLIDO", message_id=resultado.message_id,
        request_id=resultado.request_id, codigo_error=traduccion.codigo if traduccion else None,
        reintentable=traduccion.reintentable if traduccion else False,
        respuesta_proveedor=correo._respuesta_proveedor(resultado), enviado_por=auditoria.id_de(actor),
    ))
    auditoria.registrar(db, actor, "campana", campana.id, "EDITAR", despues={"prueba_a": destino, "ok": resultado.ok},
                        nota="ENVIAR PRUEBA")
    confirmar(db)
    if not resultado.ok:
        raise ErrorNegocio(422, traduccion.codigo, traduccion.mensaje, extra={"reintentable": traduccion.reintentable})
    return {"ok": True, "destinatario": destino, "message_id": resultado.message_id}


# ---------- Enviar o programar ----------


def enviar_o_programar(db: Session, actor: Usuario, campana_id: int, datos: dict[str, Any]) -> dict[str, Any]:
    """Valida, congela el snapshot, genera los destinatarios y pasa a ENVIANDO o PROGRAMADA, en una transacción."""
    campana = _editable(db, campana_id)
    programar = datos.get("programada_para")
    ahora = datetime.now(timezone.utc)
    if programar is not None:
        programar = programar if programar.tzinfo else programar.replace(tzinfo=ZONA)
        if programar <= ahora:
            raise ErrorNegocio(422, "FECHA_INVALIDA", "La fecha programada debe ser futura")
        fecha_envio = programar.astimezone(ZONA).date()
    else:
        fecha_envio = fechas.hoy_ecuador()
    plantilla = plantillas_correo.plantilla_utilizable(db, campana.plantilla_id, "BOLETIN")
    preparado = preparar(db, campana, actor, fecha_envio)
    fila = preparado["masivos"]
    ejemplo = variables_destinatario(preparado["fijas"], preparado["filas"], "x", "x", _url_baja(preparado["url_publica"], "x"))
    plantillas_correo.exigir_variables(plantilla, ejemplo, OPCIONALES | set(_filas_de_plantilla(plantilla)))
    unicos, duplicados = resolver_destinatarios(db, campana.listas_ids)
    emails = [c.email.strip().lower() for c, _ in unicos]
    bajas = boletines.bajas_activas(db, emails)
    recibiran = len(unicos) - len(bajas)
    if recibiran < 1:
        raise ErrorNegocio(422, "SIN_DESTINATARIOS", "La campaña no tiene destinatarios (revise las listas y las bajas)")
    if datos.get("destinatarios_confirmados") != recibiran:
        raise ErrorNegocio(
            409, "CONTEO_CAMBIO",
            f"Recibirán {recibiran} destinatarios; confirme ese número exacto para continuar",
            extra={"recibiran": recibiran},
        )
    with db.no_autoflush:
        campana.snapshot_tarifas = preparado["snapshot"]
        campana.adjunto_pdf = generar_pdf(db, preparado["snapshot"], campana.asunto or campana.nombre) if campana.adjuntar_pdf else None
        if campana.adjunto_pdf and len(campana.adjunto_pdf) > correo.config_vigente(db).adjunto_max_bytes:
            raise ErrorNegocio(422, "ADJUNTO_DEMASIADO_GRANDE",
                               "El PDF de tarifas supera el tamaño máximo de adjunto; reduzca las tarifas")
        for contacto, cliente in unicos:
            email = contacto.email.strip().lower()
            db.add(CampanaDestinatario(
                campana_id=campana.id, contacto_id=contacto.id, email=email, nombre=contacto.nombre,
                empresa=cliente.razon_social if cliente else "", token_baja=boletines.nuevo_token(),
                estado="OMITIDO_BAJA" if email in bajas else "PENDIENTE",
            ))
        campana.total_destinatarios = len(unicos) + duplicados
        campana.omitidos = len(bajas) + duplicados
        campana.enviado_por = auditoria.id_de(actor)
        campana.estado = "PROGRAMADA" if programar else "ENVIANDO"
        campana.programada_para = programar
        campana.enviada_en = None if programar else ahora
        auditoria.registrar(
            db, actor, "campana", campana.id, "EDITAR",
            antes={"estado": "BORRADOR"},
            despues={"estado": campana.estado, "destinatarios": recibiran, "tarifas": len(preparado["snapshot"]["tarifas"]),
                     "programada_para": programar},
            nota=("PROGRAMAR" if programar else "ENVIAR") + f" A {recibiran} DESTINATARIOS",
        )
    confirmar(db)
    return {"estado": campana.estado, "recibiran": recibiran, "avisos": preparado["avisos"]}


def cambiar_estado(db: Session, actor: Usuario, campana_id: int, accion: str) -> Campana:
    campana = obtener(db, campana_id, bloquear=True)
    transiciones = {
        "pausar": ({"ENVIANDO"}, "PAUSADA"),
        "reanudar": ({"PAUSADA"}, "ENVIANDO"),
        "cancelar": ({"PROGRAMADA", "ENVIANDO", "PAUSADA"}, "CANCELADA"),
    }
    if accion not in transiciones:
        raise ErrorNegocio(422, "ACCION_INVALIDA", "La acción debe ser pausar, reanudar o cancelar")
    desde, hacia = transiciones[accion]
    if campana.estado not in desde:
        raise ErrorNegocio(409, "TRANSICION_INVALIDA", f"Una campaña {campana.estado} no se puede {accion}")
    antes = campana.estado
    campana.estado = hacia
    if hacia == "CANCELADA":
        pendientes = db.scalars(select(CampanaDestinatario).where(CampanaDestinatario.campana_id == campana.id,
                                                                  CampanaDestinatario.estado == "PENDIENTE"))
        for destinatario in pendientes:
            destinatario.estado = "CANCELADO"
        campana.terminada_en = datetime.now(timezone.utc)
    if accion == "reanudar" and campana.enviada_en is None:
        campana.enviada_en = datetime.now(timezone.utc)
    auditoria.registrar(db, actor, "campana", campana.id, "EDITAR", antes={"estado": antes}, despues={"estado": hacia},
                        nota=accion.upper())
    confirmar(db)
    return campana


# ---------- Lectura ----------


def recontar(db: Session, campana: Campana) -> None:
    """Los totales salen siempre de los destinatarios (enviados, rebotados, fallidos y omitidos)."""
    filas = dict(db.execute(select(CampanaDestinatario.estado, func.count()).where(
        CampanaDestinatario.campana_id == campana.id).group_by(CampanaDestinatario.estado)).all())
    duplicados = max(0, campana.total_destinatarios - sum(filas.values()))
    campana.enviados = filas.get("ENVIADO", 0)
    campana.rebotados = filas.get("REBOTADO", 0)
    campana.fallidos = filas.get("FALLIDO", 0)
    campana.omitidos = filas.get("OMITIDO_BAJA", 0) + filas.get("OMITIDO_DUPLICADO", 0) + duplicados


def presentar(campana: Campana, db: Session) -> dict[str, Any]:
    plantilla = campana.plantilla
    pendientes = db.scalar(select(func.count()).select_from(CampanaDestinatario).where(
        CampanaDestinatario.campana_id == campana.id, CampanaDestinatario.estado == "PENDIENTE")) or 0
    return {
        **{campo: getattr(campana, campo) for campo in CAMPOS_BORRADOR},
        "id": campana.id, "estado": campana.estado,
        "programada_para": campana.programada_para.isoformat() if campana.programada_para else None,
        "total_destinatarios": campana.total_destinatarios, "enviados": campana.enviados,
        "rebotados": campana.rebotados, "fallidos": campana.fallidos, "omitidos": campana.omitidos,
        "pendientes": pendientes,
        "plantilla": {"id": plantilla.id, "nombre": plantilla.nombre, "tencent_id": plantilla.tencent_id,
                      "estado_tencent": plantilla.estado_tencent} if plantilla else None,
        "snapshot_tarifas": campana.snapshot_tarifas,
        "creado_en": campana.creado_en.isoformat(), "enviada_en": campana.enviada_en.isoformat() if campana.enviada_en else None,
        "terminada_en": campana.terminada_en.isoformat() if campana.terminada_en else None,
    }


def listar(db: Session, estado: str | None = None, servicio: str | None = None, desde: date | None = None,
           hasta: date | None = None) -> list[dict[str, Any]]:
    consulta = select(Campana).options(selectinload(Campana.plantilla))
    if estado:
        consulta = consulta.where(Campana.estado == estado)
    if servicio:
        consulta = consulta.where(Campana.servicios.contains([servicio]))
    if desde:
        consulta = consulta.where(func.date(Campana.creado_en) >= desde)
    if hasta:
        consulta = consulta.where(func.date(Campana.creado_en) <= hasta)
    return [
        {"id": c.id, "nombre": c.nombre, "estado": c.estado, "total_destinatarios": c.total_destinatarios,
         "enviados": c.enviados, "rebotados": c.rebotados, "fallidos": c.fallidos, "omitidos": c.omitidos,
         "servicios": c.servicios, "programada_para": c.programada_para.isoformat() if c.programada_para else None,
         "creado_en": c.creado_en.isoformat(), "enviada_en": c.enviada_en.isoformat() if c.enviada_en else None}
        for c in db.scalars(consulta.order_by(Campana.id.desc()).limit(300))
    ]


def destinatarios(db: Session, campana_id: int, estado: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    obtener(db, campana_id)
    consulta = select(CampanaDestinatario).where(CampanaDestinatario.campana_id == campana_id)
    if estado:
        consulta = consulta.where(CampanaDestinatario.estado == estado)
    if q:
        consulta = consulta.where(CampanaDestinatario.email.ilike(f"%{q.strip().lower()}%"))
    return [
        {"id": d.id, "email": d.email, "nombre": d.nombre, "empresa": d.empresa, "estado": d.estado, "intentos": d.intentos,
         "ultimo_error": d.ultimo_error, "enviado_en": d.enviado_en.isoformat() if d.enviado_en else None}
        for d in db.scalars(consulta.order_by(CampanaDestinatario.id).limit(1000))
    ]


_ = Puerto

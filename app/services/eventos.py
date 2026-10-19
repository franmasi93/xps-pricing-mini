"""E3 Catálogo de eventos (en código, porque los dispara el sistema) y sus detectores.

Cada evento declara código, nombre, audiencia (EXTERNA: al cliente; INTERNA: a usuarios), tipo (INMEDIATO, POR_FECHA o
RESUMEN) y las variables que ofrece. Agregar un evento futuro = registrarlo aquí con su detector (si es por fecha); el
motor (services/notificaciones.py) no cambia.

- Los INMEDIATOS los emiten los servicios existentes (aceptar, rechazar, emitir, fallo de envío, bloqueo) dentro de su
  transacción: notificaciones.emitir(…), patrón outbox.
- Los POR_FECHA y RESUMEN los busca su detector en cada evaluación (POST /internal/notificaciones/evaluar, cada hora);
  la ocurrencia que devuelve el detector forma la clave de idempotencia: evaluar varias veces nunca duplica.

Los avisos nunca muestran el agente o proveedor: solo el transportista (aerolínea o naviera).
"""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core import fechas
from app.models import (
    Auditoria,
    Campana,
    Cliente,
    ConfigAvisos,
    Cotizacion,
    EnvioCorreo,
    Moneda,
    ReglaNotificacion,
    Tarifa,
    TasaCambio,
)
from app.services import pdf

EXTERNA, INTERNA = "EXTERNA", "INTERNA"
INMEDIATO, POR_FECHA, RESUMEN = "INMEDIATO", "POR_FECHA", "RESUMEN"
VARIABLES_COTIZACION = ("nombre_contacto", "numero", "ruta", "servicio", "total", "valida_hasta", "comercial")
VARIABLES_EMPRESA = ("whatsapp_numero", "empresa_direccion", "empresa_telefono", "empresa_whatsapp", "empresa_horario")
# Las de las plantillas aprobadas (2026-10-19): 72752 y 72753 llevan el enlace fijo en el botón, sin variable.
VARIABLES_INTERNO = ("evento", "referencia", "fecha")
VARIABLES_RESUMEN = ("periodo", "kpi_emitidas", "kpi_enviadas", "kpi_aceptadas", "kpi_rechazadas", "kpi_tasa_cierre",
                     "kpi_monto", "kpi_margen")


@dataclass
class Ocurrencia:
    """Lo que un detector (o un servicio, si es inmediato) encontró. `clave` distingue ocurrencias de la misma entidad
    (el recordatorio 1 y el 2, el día del resumen…)."""

    entidad_tipo: str
    entidad_id: str
    clave: str
    titulo: str
    mensaje: str = ""
    detalles: list[str] = field(default_factory=list)
    enlace: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    asunto: dict[str, str] = field(default_factory=dict)  # valores para el asunto sugerido ({numero}…)
    cotizacion: Cotizacion | None = None
    cliente_id: int | None = None
    comercial_id: int | None = None
    actor_id: int | None = None  # "quien lo envió" o el creador de la campaña
    contactos: list[Any] = field(default_factory=list)  # destinatarios externos fuera de una cotización (TARIFA_RUTA_INTERES)
    resumen: bool = False
    referencia: str = ""  # E4: identificador del registro para la plantilla interna 72752 ({{referencia}})


@dataclass
class Contexto:
    hoy: date
    ahora: datetime
    config: ConfigAvisos


@dataclass(frozen=True)
class Evento:
    codigo: str
    nombre: str
    audiencia: str
    tipo: str
    descripcion: str
    variables: tuple[str, ...]
    comercial: bool = False  # True: es promocional y respeta las bajas de E1 (baja_correo)
    de_cotizacion: bool = False  # externos ligados a una cotización: interruptores, "aplicar desde" y tope semanal
    detector: Callable[[Session, ReglaNotificacion, Contexto], list[Ocurrencia]] | None = None


EVENTOS: dict[str, Evento] = {}
_DETECTORES: dict[str, Callable] = {}


def _registrar(codigo, nombre, audiencia, tipo, descripcion, variables, **extra) -> None:
    EVENTOS[codigo] = Evento(codigo, nombre, audiencia, tipo, descripcion, tuple(variables), **extra)


def detector(codigo: str):
    def _decorador(funcion):
        _DETECTORES[codigo] = funcion
        return funcion

    return _decorador


def detector_de(codigo: str):
    return _DETECTORES.get(codigo)


# ---------- Ayudas para los textos ----------


def dinero(valor: Any) -> str:
    return f"USD {pdf._dinero(valor)}"


def porcentaje(valor: Decimal | None, sin_datos: str = "Sin datos") -> str:
    """Un porcentaje con 1 decimal y coma decimal: 18,5 %. Sin valor: "Sin datos"."""
    if valor is None:
        return sin_datos
    return f"{Decimal(valor).quantize(Decimal('0.1')):.1f}".replace(".", ",") + " %"


def fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def ruta(cotizacion_o_tarifa) -> str:
    return f"{cotizacion_o_tarifa.origen.nombre} → {cotizacion_o_tarifa.destino.nombre}"


def enlace_cotizacion(cotizacion: Cotizacion) -> str:
    return f"/app/cotizacion.html?id={cotizacion.id}"


def variables_cotizacion(cotizacion: Cotizacion) -> dict[str, str]:
    contacto = cotizacion.contacto
    return {
        "nombre_contacto": contacto.nombre if contacto else "",
        "numero": cotizacion.numero or "",
        "ruta": ruta(cotizacion),
        "servicio": cotizacion.servicio.nombre,
        "total": dinero(cotizacion.total_general),
        "valida_hasta": fecha(cotizacion.valida_hasta),
        # E1-B: el comercial asignado al cliente (si no tiene, el de la cotización).
        "comercial": (cotizacion.cliente.comercial_asignado or cotizacion.comercial).nombre,
    }


def detalles_cotizacion(cotizacion: Cotizacion) -> list[str]:
    return [
        f"Cliente: {cotizacion.cliente.razon_social}",
        f"Ruta: {ruta(cotizacion)} · {cotizacion.servicio.nombre}",
        f"Total: {dinero(cotizacion.total_general)}",
        f"Válida hasta: {fecha(cotizacion.valida_hasta)}",
        f"Comercial: {cotizacion.comercial.nombre}",
    ]


def ocurrencia_cotizacion(cotizacion: Cotizacion, clave: str, titulo: str, mensaje: str, **extra) -> Ocurrencia:
    return Ocurrencia(
        entidad_tipo="cotizacion", entidad_id=str(cotizacion.id), clave=clave, titulo=titulo, mensaje=mensaje,
        detalles=extra.pop("detalles", None) or detalles_cotizacion(cotizacion), enlace=enlace_cotizacion(cotizacion),
        variables=variables_cotizacion(cotizacion) | extra.pop("variables", {}),
        asunto={"numero": cotizacion.numero or ""}, cotizacion=cotizacion, cliente_id=cotizacion.cliente_id,
        comercial_id=cotizacion.comercial_id, referencia=cotizacion.numero or f"Cotización #{cotizacion.id}", **extra,
    )


def linea_tarifa(tarifa: Tarifa) -> str:
    """Una tarifa en un aviso interno: ruta, servicio, equipo, vigencia y transportista (nunca el proveedor)."""
    partes = [ruta(tarifa), tarifa.servicio.nombre]
    if tarifa.tipo_equipo:
        partes.append(tarifa.tipo_equipo.codigo)
    partes.append(f"vence {fecha(tarifa.valido_hasta)}")
    if tarifa.transportista:
        partes.append(tarifa.transportista)
    return " · ".join(partes)


# ---------- Cotizaciones enviadas (base de los avisos externos por fecha) ----------


def primer_envio():
    """Fecha (Ecuador) del primer envío correcto de cada cotización."""
    return (
        select(EnvioCorreo.cotizacion_id, func.min(EnvioCorreo.fecha).label("enviada_en"))
        .where(EnvioCorreo.estado == "ENVIADO").group_by(EnvioCorreo.cotizacion_id).subquery()
    )


def fecha_envio(db: Session, cotizacion_id: int) -> date | None:
    primero = db.scalar(select(func.min(EnvioCorreo.fecha)).where(
        EnvioCorreo.cotizacion_id == cotizacion_id, EnvioCorreo.estado == "ENVIADO"))
    return primero.astimezone(fechas.ZONA_ECUADOR).date() if primero else None


def reemplazada():
    hija = aliased(Cotizacion)
    return exists().where(hija.cotizacion_origen_id == Cotizacion.id, hija.estado != "BORRADOR", hija.activo.is_(True))


def cotizaciones_enviadas(db: Session, contexto: Contexto) -> list[tuple[Cotizacion, date]]:
    """ENVIADAS (sin aceptar ni rechazar), activas, con avisos activos (cotización y cliente), no reemplazadas y enviadas desde "aplicar desde"."""
    envios = primer_envio()
    consulta = (
        select(Cotizacion, envios.c.enviada_en)
        .join(envios, envios.c.cotizacion_id == Cotizacion.id)
        .join(Cliente, Cliente.id == Cotizacion.cliente_id)
        .where(Cotizacion.estado == "ENVIADA", Cotizacion.activo.is_(True), Cotizacion.avisos_activos.is_(True),
               Cliente.avisos_activos.is_(True), ~reemplazada())
        .options(selectinload(Cotizacion.contacto), selectinload(Cotizacion.cliente), selectinload(Cotizacion.comercial),
                 selectinload(Cotizacion.origen), selectinload(Cotizacion.destino))
        .order_by(Cotizacion.id)
    )
    salida = []
    for cotizacion, enviada_en in db.execute(consulta):
        dia = enviada_en.astimezone(fechas.ZONA_ECUADOR).date()
        if contexto.config.aplicar_desde is None or dia >= contexto.config.aplicar_desde:
            salida.append((cotizacion, dia))
    return salida


def _param(regla: ReglaNotificacion, clave: str, defecto: Any) -> Any:
    valor = (regla.parametros or {}).get(clave, defecto)
    return defecto if valor is None else valor


def _regla_seguimiento(db: Session) -> ReglaNotificacion | None:
    return db.scalars(select(ReglaNotificacion).where(ReglaNotificacion.evento == "COT_SEGUIMIENTO")
                      .order_by(ReglaNotificacion.id)).first()


def calendario_seguimiento(db: Session, regla: ReglaNotificacion | None) -> tuple[int, int, int]:
    regla = regla or _regla_seguimiento(db)
    if regla is None:
        return 3, 2, 4
    return int(_param(regla, "dias", 3)), int(_param(regla, "repeticiones", 2)), int(_param(regla, "intervalo", 4))


# ---------- Externos ----------

_registrar("COT_SEGUIMIENTO", "Seguimiento de cotización enviada", EXTERNA, POR_FECHA,
           "Cotización ENVIADA sin respuesta tras X días; hasta N recordatorios cada Y días.",
           VARIABLES_COTIZACION + VARIABLES_EMPRESA, de_cotizacion=True)
_registrar("COT_POR_VENCER", "Cotización por vencer", EXTERNA, POR_FECHA,
           "X días antes de que venza una cotización ENVIADA.", VARIABLES_COTIZACION + VARIABLES_EMPRESA,
           de_cotizacion=True)
_registrar("COT_VENCIDA", "Cotización vencida", EXTERNA, POR_FECHA,
           "Al día siguiente del vencimiento sin respuesta, ofreciendo actualizarla.",
           VARIABLES_COTIZACION + VARIABLES_EMPRESA, de_cotizacion=True)
_registrar("COT_ACEPTADA_CLIENTE", "Confirmación al cliente que aceptó", EXTERNA, INMEDIATO,
           "Al marcar ACEPTADA: confirmación al cliente con los siguientes pasos.",
           VARIABLES_COTIZACION + ("paso_1", "paso_2", "paso_3") + VARIABLES_EMPRESA, de_cotizacion=True)
_registrar("TARIFA_RUTA_INTERES", "Nueva tarifa en una ruta de interés", EXTERNA, POR_FECHA,
           "Nueva tarifa vigente en una ruta y servicio que el cliente cotizó en los últimos N meses (comercial: respeta "
           "las bajas).", ("nombre_contacto", "servicio", "ruta", *[f"fila_{n:02d}" for n in range(1, 6)], "vigencia",
                           "comercial", *VARIABLES_EMPRESA, "enlace_baja"), comercial=True)


@detector("COT_SEGUIMIENTO")
def _seguimiento(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    dias, repeticiones, intervalo = calendario_seguimiento(db, regla)
    salida = []
    for cotizacion, enviada in cotizaciones_enviadas(db, contexto):
        if cotizacion.valida_hasta and cotizacion.valida_hasta < contexto.hoy:
            continue  # vencida: la atiende COT_VENCIDA
        vencidos = [k for k in range(1, repeticiones + 1) if contexto.hoy >= enviada + timedelta(days=dias + (k - 1) * intervalo)]
        if vencidos:  # solo el último que tocó: nunca una ráfaga de recordatorios atrasados
            k = vencidos[-1]
            salida.append(ocurrencia_cotizacion(
                cotizacion, f"r{k}", f"Recordatorio {k} de {cotizacion.numero}",
                f"Recordatorio {k} de {repeticiones} al cliente por la cotización {cotizacion.numero}, enviada el "
                f"{fecha(enviada)}."))
    return salida


@detector("COT_POR_VENCER")
def _por_vencer(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    dias = int(_param(regla, "dias", 3))
    return [
        ocurrencia_cotizacion(cotizacion, "1", f"{cotizacion.numero} vence el {fecha(cotizacion.valida_hasta)}",
                              f"La cotización {cotizacion.numero} vence en {(cotizacion.valida_hasta - contexto.hoy).days} día(s).")
        for cotizacion, _ in cotizaciones_enviadas(db, contexto)
        if cotizacion.valida_hasta and cotizacion.valida_hasta - timedelta(days=dias) <= contexto.hoy <= cotizacion.valida_hasta
    ]


@detector("COT_VENCIDA")
def _vencida(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    ventana = int(_param(regla, "ventana", 7))
    return [
        ocurrencia_cotizacion(cotizacion, "1", f"{cotizacion.numero} venció",
                              f"La cotización {cotizacion.numero} venció el {fecha(cotizacion.valida_hasta)} sin respuesta.")
        for cotizacion, _ in cotizaciones_enviadas(db, contexto)
        if cotizacion.valida_hasta
        and cotizacion.valida_hasta + timedelta(days=1) <= contexto.hoy <= cotizacion.valida_hasta + timedelta(days=ventana)
    ]


@detector("TARIFA_RUTA_INTERES")
def _ruta_interes(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    from app.services import campanas

    meses, dias_nueva = int(_param(regla, "meses", 6)), int(_param(regla, "dias_nueva", 1))
    desde = datetime.combine(contexto.hoy - timedelta(days=dias_nueva), time.min, tzinfo=fechas.ZONA_ECUADOR)
    nuevas = list(db.scalars(
        select(Tarifa).where(Tarifa.activo.is_(True), Tarifa.creado_en >= desde, Tarifa.valido_desde <= contexto.hoy,
                             Tarifa.valido_hasta >= contexto.hoy).order_by(Tarifa.id)
    ))
    salida = []
    for tarifa in nuevas:
        cotizadas = db.scalars(
            select(Cotizacion).where(
                Cotizacion.origen_puerto_id == tarifa.origen_puerto_id, Cotizacion.destino_puerto_id == tarifa.destino_puerto_id,
                Cotizacion.modo == tarifa.modo, Cotizacion.estado != "BORRADOR", Cotizacion.activo.is_(True),
                Cotizacion.contacto_id.is_not(None),
                Cotizacion.fecha_emision >= contexto.hoy - timedelta(days=30 * meses),
            ).order_by(Cotizacion.id)
        )
        contactos = {}
        for cotizacion in cotizadas:
            # E1-B: promocional: solo contactos con consentimiento (cliente acepta y contacto recibe promociones).
            if (cotizacion.cliente.avisos_activos and cotizacion.cliente.acepta_promociones and cotizacion.contacto
                    and cotizacion.contacto.activo and cotizacion.contacto.recibe_promociones):
                contactos.setdefault(cotizacion.contacto.id, (cotizacion.contacto, cotizacion))
        if not contactos:
            continue
        fila = campanas.foto_tarifa(tarifa)["fila"]
        for contacto, cotizacion in contactos.values():
            salida.append(Ocurrencia(
                entidad_tipo="tarifa", entidad_id=str(tarifa.id), clave=f"c{contacto.id}",
                titulo=f"Nueva tarifa {ruta(tarifa)}", mensaje=f"Nueva tarifa vigente en {ruta(tarifa)} ({tarifa.servicio.nombre}).",
                detalles=[fila], enlace="/app/tarifas.html",
                variables={"nombre_contacto": contacto.nombre, "servicio": tarifa.servicio.nombre, "ruta": ruta(tarifa),
                           "fila_01": f"• {fila}", "vigencia": fecha(tarifa.valido_hasta),
                           "comercial": (cotizacion.cliente.comercial_asignado or cotizacion.comercial).nombre},
                cliente_id=cotizacion.cliente_id, comercial_id=cotizacion.comercial_id, contactos=[contacto],
            ))
    return salida


# ---------- Internos ----------

_registrar("COT_ACEPTADA", "Cotización aceptada", INTERNA, INMEDIATO,
           "Al marcar ACEPTADA: al comercial de la cotización y a Pricing.", VARIABLES_INTERNO)
_registrar("COT_RECHAZADA", "Cotización rechazada", INTERNA, INMEDIATO,
           "Al marcar RECHAZADA, con el motivo: al comercial y a Pricing.", VARIABLES_INTERNO)
_registrar("COT_SIN_RESPUESTA", "Cotización sin respuesta", INTERNA, POR_FECHA,
           "Al comercial, cuando se agotan los recordatorios al cliente.", VARIABLES_INTERNO)
_registrar("COT_MARGEN_BAJO", "Margen bajo", INTERNA, INMEDIATO,
           "Al emitir con margen bajo el umbral o con alguna línea bajo costo: a Pricing y Gerencia.", VARIABLES_INTERNO)
_registrar("TARIFA_POR_VENCER", "Tarifas por vencer", INTERNA, POR_FECHA,
           "Tarifas que vencen dentro de los días de alerta: a Pricing, agrupadas en un correo diario.", VARIABLES_INTERNO)
_registrar("TARIFA_SIN_REEMPLAZO", "Tarifa vencida sin reemplazo", INTERNA, POR_FECHA,
           "Tarifa vencida sin otra vigente en la misma ruta, servicio y tipo de equipo.", VARIABLES_INTERNO)
_registrar("TASA_DESACTUALIZADA", "Tasa de cambio desactualizada", INTERNA, POR_FECHA,
           "Moneda activa sin tasa nueva en X días.", VARIABLES_INTERNO)
_registrar("ENVIO_FALLIDO", "Envío de correo fallido", INTERNA, INMEDIATO,
           "Fallo de un correo de cotización, campaña o aviso: al administrador y a quien lo envió.", VARIABLES_INTERNO)
_registrar("CAMPANA_TERMINADA", "Campaña terminada", INTERNA, POR_FECHA,
           "Resumen de una campaña terminada: a quien la creó y al administrador.", VARIABLES_INTERNO)
_registrar("CAMPANA_REBOTE_ALTO", "Campaña con rebote alto", INTERNA, POR_FECHA,
           "Campaña terminada con rebotes sobre X %.", VARIABLES_INTERNO)
_registrar("CUOTA_TENCENT_CERCA", "Cupo diario cerca del tope", INTERNA, POR_FECHA,
           "Correos del día sobre X % del tope diario.", VARIABLES_INTERNO)
_registrar("USUARIO_BLOQUEADO", "Usuario bloqueado", INTERNA, INMEDIATO,
           "Bloqueo por intentos fallidos de ingreso: al administrador.", VARIABLES_INTERNO)
_registrar("RESUMEN_DIARIO", "Resumen diario", INTERNA, RESUMEN,
           "Cifras del día anterior a la Gerencia, a la hora configurada.", VARIABLES_RESUMEN)
_registrar("RESUMEN_SEMANAL", "Resumen semanal", INTERNA, RESUMEN,
           "Cifras de los 7 días anteriores a la Gerencia, el día y la hora configurados.", VARIABLES_RESUMEN)


@detector("COT_SIN_RESPUESTA")
def _sin_respuesta(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    dias, repeticiones, intervalo = calendario_seguimiento(db, None)
    agotado = dias + repeticiones * intervalo  # el último recordatorio más un intervalo de espera
    return [
        ocurrencia_cotizacion(cotizacion, "1", f"Sin respuesta: {cotizacion.numero}",
                              f"{cotizacion.cliente.razon_social} no respondió la cotización {cotizacion.numero} después de "
                              f"{repeticiones} recordatorio(s).")
        for cotizacion, enviada in cotizaciones_enviadas(db, contexto)
        if contexto.hoy >= enviada + timedelta(days=agotado)
    ]


def _tarifas_vigentes():
    return select(Tarifa).options(selectinload(Tarifa.origen), selectinload(Tarifa.destino),
                                  selectinload(Tarifa.tipo_equipo)).where(Tarifa.activo.is_(True))


@detector("TARIFA_POR_VENCER")
def _tarifas_por_vencer(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    from app.services.configuracion import leer_config

    dias = int(_param(regla, "dias", int(leer_config(db, "dias_alerta_vencimiento"))))
    tarifas = db.scalars(_tarifas_vigentes().where(
        Tarifa.valido_hasta >= contexto.hoy, Tarifa.valido_hasta <= contexto.hoy + timedelta(days=dias),
        Tarifa.valido_desde <= contexto.hoy).order_by(Tarifa.valido_hasta, Tarifa.id))
    return [
        Ocurrencia(entidad_tipo="tarifa", entidad_id=str(t.id), clave=t.valido_hasta.isoformat(),
                   titulo=f"Tarifa por vencer: {ruta(t)}", mensaje=f"La tarifa {ruta(t)} vence el {fecha(t.valido_hasta)}.",
                   detalles=[linea_tarifa(t)], enlace="/app/tarifas.html")
        for t in tarifas
    ]


@detector("TARIFA_SIN_REEMPLAZO")
def _sin_reemplazo(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    ventana = int(_param(regla, "ventana", 7))
    otra = aliased(Tarifa)
    reemplazo = exists().where(
        otra.id != Tarifa.id, otra.activo.is_(True), otra.origen_puerto_id == Tarifa.origen_puerto_id,
        otra.destino_puerto_id == Tarifa.destino_puerto_id, otra.modo == Tarifa.modo,
        or_(otra.tipo_equipo_id == Tarifa.tipo_equipo_id, (otra.tipo_equipo_id.is_(None)) & (Tarifa.tipo_equipo_id.is_(None))),
        otra.valido_desde <= contexto.hoy, otra.valido_hasta >= contexto.hoy,
    )
    tarifas = db.scalars(_tarifas_vigentes().where(
        Tarifa.valido_hasta < contexto.hoy, Tarifa.valido_hasta >= contexto.hoy - timedelta(days=ventana), ~reemplazo,
    ).order_by(Tarifa.id))
    return [
        Ocurrencia(entidad_tipo="tarifa", entidad_id=str(t.id), clave="1", titulo=f"Sin reemplazo: {ruta(t)}",
                   mensaje=f"La tarifa {ruta(t)} venció el {fecha(t.valido_hasta)} y no hay otra vigente.",
                   detalles=[linea_tarifa(t)], enlace="/app/tarifas.html")
        for t in tarifas
    ]


@detector("TASA_DESACTUALIZADA")
def _tasa_desactualizada(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    dias = int(_param(regla, "dias", 7))
    salida = []
    for moneda in db.scalars(select(Moneda).where(Moneda.activo.is_(True), Moneda.codigo != "USD").order_by(Moneda.codigo)):
        ultima = db.scalar(select(func.max(TasaCambio.fecha_vigencia)).where(TasaCambio.moneda_id == moneda.id))
        if ultima is None or ultima < contexto.hoy - timedelta(days=dias):
            texto = f"última tasa del {fecha(ultima)}" if ultima else "sin tasas registradas"
            salida.append(Ocurrencia(
                entidad_tipo="moneda", entidad_id=moneda.codigo, clave=ultima.isoformat() if ultima else "ninguna",
                titulo=f"Tasa desactualizada: {moneda.codigo}", mensaje=f"{moneda.nombre} ({moneda.codigo}): {texto}.",
                detalles=[f"Moneda: {moneda.codigo}", f"Días permitidos sin tasa nueva: {dias}"], enlace="/app/monedas.html"))
    return salida


def _campanas_terminadas(db: Session, contexto: Contexto) -> list[Campana]:
    return list(db.scalars(select(Campana).where(
        Campana.estado == "ENVIADA", Campana.terminada_en >= contexto.ahora - timedelta(days=7)).order_by(Campana.id)))


def _detalles_campana(campana: Campana) -> list[str]:
    return [f"Destinatarios: {campana.total_destinatarios}", f"Enviados: {campana.enviados}",
            f"Rebotados: {campana.rebotados}", f"Fallidos: {campana.fallidos}", f"Omitidos: {campana.omitidos}"]


@detector("CAMPANA_TERMINADA")
def _campana_terminada(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    return [
        Ocurrencia(entidad_tipo="campana", entidad_id=str(c.id), clave="1", titulo=f"Campaña terminada: {c.nombre}",
                   mensaje=f"La campaña «{c.nombre}» terminó: {c.enviados} enviados de {c.total_destinatarios}.",
                   detalles=_detalles_campana(c), enlace=f"/app/campana.html?id={c.id}", actor_id=c.creado_por)
        for c in _campanas_terminadas(db, contexto)
    ]


@detector("CAMPANA_REBOTE_ALTO")
def _rebote_alto(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    umbral = Decimal(str(_param(regla, "umbral_pct", 5)))
    salida = []
    for c in _campanas_terminadas(db, contexto):
        intentados = c.enviados + c.rebotados
        if intentados and Decimal(c.rebotados * 100) / intentados > umbral:
            pct = (Decimal(c.rebotados * 100) / intentados).quantize(Decimal("0.1"))
            salida.append(Ocurrencia(
                entidad_tipo="campana", entidad_id=str(c.id), clave="1", titulo=f"Rebote alto: {c.nombre}",
                mensaje=f"La campaña «{c.nombre}» tuvo {pct} % de rebotes (umbral {umbral} %).",
                detalles=_detalles_campana(c), enlace=f"/app/campana.html?id={c.id}", actor_id=c.creado_por))
    return salida


@detector("CUOTA_TENCENT_CERCA")
def _cuota(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    from app.services import masivos

    umbral = int(_param(regla, "umbral_pct", 80))
    fila = masivos.config(db)
    tope = masivos.tope_diario_efectivo(fila, contexto.hoy)
    enviados = masivos.enviados_hoy(db)
    if not tope or enviados["total"] * 100 < tope * umbral:
        return []
    return [Ocurrencia(
        entidad_tipo="cupo", entidad_id=contexto.hoy.isoformat(), clave="1", titulo="Cupo de correo cerca del tope",
        mensaje=f"Hoy salieron {enviados['total']} correos de un tope de {tope} ({umbral} % o más).",
        detalles=[f"{clave}: {valor}" for clave, valor in enviados.items()], enlace="/app/configuracion.html")]


# ---------- Resúmenes ----------


def _rango(desde: date, hasta: date) -> tuple[datetime, datetime]:
    return (datetime.combine(desde, time.min, tzinfo=fechas.ZONA_ECUADOR),
            datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=fechas.ZONA_ECUADOR))


def cifras(db: Session, desde: date, hasta: date) -> dict[str, Any]:
    """Las cifras del resumen, todas leídas de la base (las mismas que verifica la prueba)."""
    inicio, fin = _rango(desde, hasta)
    emitidas = list(db.scalars(select(Cotizacion).where(
        Cotizacion.fecha_emision >= desde, Cotizacion.fecha_emision <= hasta, Cotizacion.activo.is_(True),
        Cotizacion.estado != "BORRADOR").options(selectinload(Cotizacion.origen), selectinload(Cotizacion.destino))))
    enviadas = db.scalar(select(func.count(func.distinct(EnvioCorreo.cotizacion_id))).where(
        EnvioCorreo.estado == "ENVIADO", EnvioCorreo.fecha >= inicio, EnvioCorreo.fecha < fin)) or 0

    def cambios(destino: str) -> list[Auditoria]:
        return list(db.scalars(select(Auditoria).where(
            Auditoria.entidad == "cotizacion", Auditoria.nota.like(f"ESTADO %→{destino}%"),
            Auditoria.fecha >= inicio, Auditoria.fecha < fin)))

    aceptadas, rechazadas = cambios("ACEPTADA"), cambios("RECHAZADA")
    cerradas = len(aceptadas) + len(rechazadas)
    monto = sum((c.total_general or Decimal("0")) for c in emitidas)
    margen = sum((c.margen_total or Decimal("0")) for c in emitidas)
    base_margen = sum(((c.margen_total or Decimal("0")) + (c.costo_total or Decimal("0"))) for c in emitidas)
    motivos = Counter((a.valores_despues or {}).get("motivo_rechazo") or "SIN_MOTIVO" for a in rechazadas)
    rutas = Counter(ruta(c) for c in emitidas)
    servicios = Counter(c.modo for c in emitidas)
    return {
        "emitidas": len(emitidas), "enviadas": enviadas, "aceptadas": len(aceptadas), "rechazadas": len(rechazadas),
        "tasa_cierre": (Decimal(len(aceptadas) * 100) / cerradas).quantize(Decimal("0.1")) if cerradas else None,
        "monto": monto, "margen": margen,
        "margen_pct": (margen * 100 / base_margen).quantize(Decimal("0.1")) if base_margen else None,
        "motivos": motivos, "rutas": rutas, "servicios": servicios,
    }


def _resumen(db: Session, contexto: Contexto, desde: date, hasta: date, clave: str, nombre: str) -> Ocurrencia:
    from app.services.configuracion import leer_config

    datos = cifras(db, desde, hasta)
    dias_alerta = int(leer_config(db, "dias_alerta_vencimiento"))
    por_vencer = db.scalar(select(func.count()).select_from(Cotizacion).where(
        Cotizacion.estado.in_(("EMITIDA", "ENVIADA")), Cotizacion.activo.is_(True),
        Cotizacion.valida_hasta >= contexto.hoy, Cotizacion.valida_hasta <= contexto.hoy + timedelta(days=3))) or 0
    tarifas_por_vencer = db.scalar(select(func.count()).select_from(Tarifa).where(
        Tarifa.activo.is_(True), Tarifa.valido_hasta >= contexto.hoy,
        Tarifa.valido_hasta <= contexto.hoy + timedelta(days=dias_alerta))) or 0
    inicio, fin = _rango(desde, hasta)
    campanas = list(db.scalars(select(Campana).where(Campana.terminada_en >= inicio, Campana.terminada_en < fin)))
    periodo = fecha(desde) if desde == hasta else f"{fecha(desde)} al {fecha(hasta)}"
    tasa = porcentaje(datos["tasa_cierre"])  # sin cotizaciones cerradas en el periodo: "Sin datos"
    margen = porcentaje(datos["margen_pct"])  # el margen va como porcentaje (no en USD)
    top = lambda contador: " · ".join(f"{k} ({v})" for k, v in contador.most_common(3)) or "—"  # noqa: E731
    lineas = [
        f"Motivos de rechazo: {top(datos['motivos'])}",
        f"Rutas más cotizadas: {top(datos['rutas'])}",
        f"Servicios más cotizados: {top(datos['servicios'])}",
        f"Cotizaciones que vencen en 3 días: {por_vencer}",
        f"Tarifas que vencen en {dias_alerta} días: {tarifas_por_vencer}",
        f"Campañas terminadas: {len(campanas)} ({sum(c.enviados for c in campanas)} correos enviados)",
    ]
    variables = {
        "periodo": periodo, "kpi_emitidas": str(datos["emitidas"]), "kpi_enviadas": str(datos["enviadas"]),
        "kpi_aceptadas": str(datos["aceptadas"]), "kpi_rechazadas": str(datos["rechazadas"]), "kpi_tasa_cierre": tasa,
        "kpi_monto": dinero(datos["monto"]), "kpi_margen": margen,
    } | {f"linea_{n:02d}": (lineas[n - 1] if n <= len(lineas) else "") for n in range(1, 13)}
    return Ocurrencia(
        entidad_tipo="resumen", entidad_id=nombre, clave=clave, titulo=f"{'Resumen diario' if desde == hasta else 'Resumen semanal'}: {periodo}",
        mensaje=(f"Emitidas {datos['emitidas']} · enviadas {datos['enviadas']} · aceptadas {datos['aceptadas']} · "
                 f"rechazadas {datos['rechazadas']} · cierre {tasa} · monto {dinero(datos['monto'])} · margen {margen}"),
        detalles=lineas, enlace="/app/cotizaciones.html", variables=variables, resumen=True,
    )


@detector("RESUMEN_DIARIO")
def _resumen_diario(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    if contexto.ahora.hour < int(_param(regla, "hora", 7)):
        return []
    ayer = contexto.hoy - timedelta(days=1)
    return [_resumen(db, contexto, ayer, ayer, contexto.hoy.isoformat(), "diario")]


@detector("RESUMEN_SEMANAL")
def _resumen_semanal(db: Session, regla: ReglaNotificacion, contexto: Contexto) -> list[Ocurrencia]:
    if contexto.hoy.isoweekday() != int(_param(regla, "dia_semana", 1)) or contexto.ahora.hour < int(_param(regla, "hora", 7)):
        return []
    anio, semana, _ = contexto.hoy.isocalendar()
    return [_resumen(db, contexto, contexto.hoy - timedelta(days=7), contexto.hoy - timedelta(days=1),
                     f"{anio}-S{semana:02d}", "semanal")]

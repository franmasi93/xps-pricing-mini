"""E3 Motor de notificaciones y avisos.

Generación (outbox):
- Los eventos INMEDIATOS se emiten desde los servicios existentes con `emitir(...)`, en la misma transacción y justo
  antes de su commit. Nunca cambian el resultado del servicio: si algo falla al generar, se registra en el log y el
  servicio sigue igual (savepoint).
- Los POR_FECHA y RESUMEN los busca `evaluar(db)` (Cloud Scheduler cada hora) con los detectores de services/eventos.
- Cada notificación tiene una clave_idempotencia única (regla + entidad + ocurrencia + canal + destinatario):
  INSERT … ON CONFLICT DO NOTHING. Evaluar varias veces nunca duplica.

Filtros de los avisos EXTERNOS (al cliente), en este orden:
1. Interruptor global: APAGADO no genera nada; SIMULACIÓN registra "SIMULADO" (con el contenido) sin enviar; ACTIVO
   deja "PENDIENTE" para el envío.
2. "Aplicar desde": solo cotizaciones enviadas desde esa fecha (nunca el histórico).
3. Interruptores "no enviar avisos" de la cotización y del cliente, y la preferencia del contacto "recibir avisos".
4. Los eventos comerciales (TARIFA_RUTA_INTERES) respetan las bajas de E1.
5. Tope de avisos por cliente por semana.
Al pasar una cotización a ACEPTADA o RECHAZADA, o al emitirse una que la reemplaza, se cancelan sus avisos pendientes.

INTERNOS: el canal "centro de notificaciones" se entrega al instante (campana); el correo respeta la preferencia del
usuario (salvo reglas obligatorias) y la plantilla de avisos internos.

Envío: `entregar(db)` con el proveedor de F4 (TriggerType 1) y el cupo compartido de E1 (los avisos usan el tope total
del día, es decir, la reserva que los boletines no pueden usar). procesar-lote de E1 llama primero a `entregar`:
los avisos salen antes que las campañas.
"""
import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.core.rbac import tiene_permiso
from app.models import (
    ConfigAvisos,
    ContactoCliente,
    Cotizacion,
    Notificacion,
    PlantillaCorreo,
    PreferenciaNotificacion,
    ReglaNotificacion,
    Rol,
    Usuario,
)
from app.models.notificaciones import MODOS_EXTERNOS
from app.services import auditoria, eventos
from app.services.eventos import EXTERNA, INTERNA, Contexto, Ocurrencia

registro = logging.getLogger("xps.notificaciones")
MAXIMO_INTENTOS = 3
TIPOS_EXTERNOS = ("CONTACTO_COTIZACION", "CONTACTO_PRINCIPAL")
TIPOS_INTERNOS = ("COMERCIAL", "ACTOR")
PATRON_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
CAMPOS_CONFIG = ("modo_externo", "aplicar_desde", "tope_semanal_cliente", "dias_habiles", "hora_desde", "hora_hasta")
CAMPOS_REGLA = ("evento", "nombre", "canal_correo", "canal_interno", "destinatarios", "parametros", "plantilla_id",
                "agrupacion", "obligatoria", "activo")


# ---------- Configuración ----------


def config(db: Session, *, bloquear: bool = False) -> ConfigAvisos:
    consulta = select(ConfigAvisos).where(ConfigAvisos.id == 1)
    if bloquear:
        consulta = consulta.with_for_update()
    return db.scalars(consulta.execution_options(populate_existing=True)).one()


def contexto(db: Session) -> Contexto:
    return Contexto(hoy=fechas.hoy_ecuador(), ahora=fechas.ahora_ecuador(), config=config(db))


def presentar_config(db: Session) -> dict[str, Any]:
    fila = config(db)
    datos = {campo: getattr(fila, campo) for campo in CAMPOS_CONFIG}
    datos["aplicar_desde"] = fila.aplicar_desde.isoformat() if fila.aplicar_desde else None
    datos["ultima_evaluacion"] = fila.ultima_evaluacion.isoformat() if fila.ultima_evaluacion else None
    return datos


def actualizar_config(db: Session, actor: Usuario, cambios: dict[str, Any]) -> dict[str, Any]:
    fila = config(db, bloquear=True)
    antes = {campo: getattr(fila, campo) for campo in CAMPOS_CONFIG}
    final = antes | cambios
    if final["modo_externo"] not in MODOS_EXTERNOS:
        raise ErrorNegocio(422, "AVISOS_INVALIDO", "El modo de avisos externos es SIMULACION, ACTIVO o APAGADO")
    if isinstance(final["aplicar_desde"], str):
        final["aplicar_desde"] = date.fromisoformat(final["aplicar_desde"])
    if final["modo_externo"] == "ACTIVO" and antes["modo_externo"] != "ACTIVO" and "aplicar_desde" not in cambios:
        final["aplicar_desde"] = fechas.hoy_ecuador()  # al activar, nunca se reprocesa el histórico
    if not 0 <= int(final["tope_semanal_cliente"]) <= 100:
        raise ErrorNegocio(422, "AVISOS_INVALIDO", "El tope semanal por cliente va de 0 a 100")
    dias = ",".join(sorted({d.strip() for d in str(final["dias_habiles"]).split(",") if d.strip()}))
    if not re.fullmatch(r"[1-7](,[1-7])*", dias):
        raise ErrorNegocio(422, "AVISOS_INVALIDO", "Los días hábiles van de 1 (lunes) a 7 (domingo), separados por coma")
    final["dias_habiles"] = dias
    if not 0 <= int(final["hora_desde"]) <= int(final["hora_hasta"]) <= 23:
        raise ErrorNegocio(422, "AVISOS_INVALIDO", "La franja horaria va de 0 a 23 y el inicio no puede pasar el fin")
    for campo in CAMPOS_CONFIG:
        setattr(fila, campo, final[campo])
    despues = {campo: getattr(fila, campo) for campo in CAMPOS_CONFIG}
    if despues != antes:
        fila.actualizado_por = auditoria.id_de(actor)
        auditoria.registrar(db, actor, "config_avisos", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return presentar_config(db)


def siguiente_horario(fila: ConfigAvisos, ahora: datetime) -> datetime:
    """El primer momento dentro de los días hábiles y la franja horaria (America/Guayaquil)."""
    dias = {int(d) for d in fila.dias_habiles.split(",") if d}
    momento = ahora.astimezone(fechas.ZONA_ECUADOR)
    for _ in range(15):
        if momento.isoweekday() in dias:
            if momento.hour < fila.hora_desde:
                return momento.replace(hour=fila.hora_desde, minute=0, second=0, microsecond=0)
            if momento.hour <= fila.hora_hasta:
                return momento
        momento = (momento + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return ahora


# ---------- Reglas ----------


def reglas_activas(db: Session, evento: str) -> list[ReglaNotificacion]:
    return list(db.scalars(select(ReglaNotificacion).where(
        ReglaNotificacion.evento == evento, ReglaNotificacion.activo.is_(True)).order_by(ReglaNotificacion.id)))


def listar_eventos(db: Session) -> list[dict[str, Any]]:
    reglas = list(db.scalars(select(ReglaNotificacion).order_by(ReglaNotificacion.id)))
    return [
        {"codigo": e.codigo, "nombre": e.nombre, "audiencia": e.audiencia, "tipo": e.tipo, "descripcion": e.descripcion,
         "variables": list(e.variables), "comercial": e.comercial,
         "reglas": [r for r in reglas if r.evento == e.codigo]}
        for e in eventos.EVENTOS.values()
    ]


def obtener_regla(db: Session, regla_id: int) -> ReglaNotificacion:
    regla = db.get(ReglaNotificacion, regla_id)
    if regla is None:
        raise ErrorNegocio(404, "REGLA_NO_ENCONTRADA", "Regla no encontrada")
    return regla


def _validar_regla(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    evento = eventos.EVENTOS.get(datos["evento"])
    if evento is None:
        raise ErrorNegocio(422, "EVENTO_INEXISTENTE", f"No existe el evento {datos['evento']}")
    nombre = " ".join(str(datos.get("nombre") or "").split())
    if not nombre or len(nombre) > 120:
        raise ErrorNegocio(422, "DATOS_INVALIDOS", "El nombre es obligatorio (hasta 120 caracteres)")
    datos["nombre"] = nombre
    if evento.audiencia == EXTERNA and datos.get("canal_interno"):
        raise ErrorNegocio(422, "CANAL_INVALIDO", "Los avisos a clientes solo van por correo")
    if not datos.get("canal_correo") and not datos.get("canal_interno"):
        raise ErrorNegocio(422, "CANAL_INVALIDO", "Elija al menos un canal")
    destinatarios = dict(datos.get("destinatarios") or {})
    permitidos = TIPOS_EXTERNOS if evento.audiencia == EXTERNA else TIPOS_INTERNOS
    tipos = [t for t in destinatarios.get("tipos") or []]
    if any(t not in permitidos for t in tipos):
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", f"Destinatarios permitidos para este evento: {', '.join(permitidos)}")
    roles = [r for r in destinatarios.get("roles") or []]
    usuarios = [int(u) for u in destinatarios.get("usuarios") or []]
    if evento.audiencia == EXTERNA and (roles or usuarios):
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", "Un aviso al cliente no va a roles ni usuarios internos")
    existentes = set(db.scalars(select(Rol.codigo).where(Rol.codigo.in_(roles))))
    if set(roles) - existentes:
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", f"No existen los roles: {', '.join(sorted(set(roles) - existentes))}")
    if len(set(db.scalars(select(Usuario.id).where(Usuario.id.in_(usuarios))))) != len(set(usuarios)):
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", "Algún usuario no existe")
    correos = [c.strip().lower() for c in destinatarios.get("correos") or [] if c.strip()]
    if any(not PATRON_EMAIL.match(c) for c in correos):
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", "Algún correo fijo no es válido")
    if not (tipos or roles or usuarios or correos):
        raise ErrorNegocio(422, "DESTINATARIOS_INVALIDOS", "Elija al menos un destinatario")
    datos["destinatarios"] = {"tipos": tipos, "roles": roles, "usuarios": usuarios, "correos": correos}
    parametros = datos.get("parametros") or {}
    if not isinstance(parametros, dict):
        raise ErrorNegocio(422, "PARAMETROS_INVALIDOS", "Los parámetros deben ser un objeto")
    for clave, valor in parametros.items():
        if isinstance(valor, (int, float)) and not isinstance(valor, bool) and not 0 <= valor <= 1000:
            raise ErrorNegocio(422, "PARAMETROS_INVALIDOS", f"{clave} va de 0 a 1000")
    datos["parametros"] = parametros
    if datos.get("plantilla_id") is not None:
        plantilla = db.get(PlantillaCorreo, datos["plantilla_id"])
        if plantilla is None or plantilla.uso != "AVISO":
            raise ErrorNegocio(422, "PLANTILLA_NO_DISPONIBLE", "La plantilla debe ser de uso AVISO")
    if datos.get("agrupacion", "INDIVIDUAL") not in ("INDIVIDUAL", "RESUMEN"):
        raise ErrorNegocio(422, "DATOS_INVALIDOS", "La agrupación es INDIVIDUAL o RESUMEN")
    return datos


def _foto_regla(regla: ReglaNotificacion) -> dict[str, Any]:
    return {campo: getattr(regla, campo) for campo in CAMPOS_REGLA}


def crear_regla(db: Session, actor: Usuario, datos: dict[str, Any]) -> ReglaNotificacion:
    datos = _validar_regla(db, {"canal_correo": True, "canal_interno": False, "agrupacion": "INDIVIDUAL"} | datos)
    regla = ReglaNotificacion(**{c: datos[c] for c in CAMPOS_REGLA if c in datos and c != "activo"},
                              activo=datos.get("activo", True), creado_por=auditoria.id_de(actor))
    db.add(regla)
    enviar(db)
    auditoria.registrar(db, actor, "regla_notificacion", regla.id, "CREAR", despues=_foto_regla(regla))
    confirmar(db)
    return regla


def actualizar_regla(db: Session, actor: Usuario, regla_id: int, cambios: dict[str, Any]) -> ReglaNotificacion:
    regla = obtener_regla(db, regla_id)
    antes = _foto_regla(regla)
    if "evento" in cambios and cambios["evento"] != regla.evento:
        raise ErrorNegocio(422, "EVENTO_NO_EDITABLE", "El evento de una regla no cambia; cree otra regla")
    final = _validar_regla(db, antes | cambios)
    for campo in CAMPOS_REGLA:
        setattr(regla, campo, final[campo])
    despues = _foto_regla(regla)
    if despues != antes:
        accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
        auditoria.registrar(db, actor, "regla_notificacion", regla.id, accion, antes=antes, despues=despues)
    confirmar(db)
    return regla


# ---------- Destinatarios ----------


class Destino:
    def __init__(self, usuario: Usuario | None = None, email: str | None = None, contacto: ContactoCliente | None = None):
        self.usuario, self.contacto = usuario, contacto
        self.email = (email or (usuario.email if usuario else None) or (contacto.email if contacto else None) or "").strip().lower() or None

    @property
    def clave(self) -> str:
        return f"u{self.usuario.id}" if self.usuario else f"e{self.email}"


def _usuarios_de_roles(db: Session, roles: list[str]) -> list[Usuario]:
    if not roles:
        return []
    return list(db.scalars(select(Usuario).join(Rol, Usuario.rol_id == Rol.id).where(
        Rol.codigo.in_(roles), Usuario.activo.is_(True)).order_by(Usuario.id)))


def destinatarios(db: Session, regla: ReglaNotificacion, evento, ocurrencia: Ocurrencia) -> list[Destino]:
    config_dest = regla.destinatarios or {}
    tipos = config_dest.get("tipos") or []
    salida: list[Destino] = []
    if evento.audiencia == EXTERNA:
        if ocurrencia.contactos:
            salida += [Destino(contacto=c) for c in ocurrencia.contactos]
        elif ocurrencia.cotizacion is not None:
            if "CONTACTO_COTIZACION" in tipos and ocurrencia.cotizacion.contacto is not None:
                salida.append(Destino(contacto=ocurrencia.cotizacion.contacto))
            if "CONTACTO_PRINCIPAL" in tipos:
                principal = db.scalars(select(ContactoCliente).where(
                    ContactoCliente.cliente_id == ocurrencia.cotizacion.cliente_id, ContactoCliente.principal.is_(True),
                    ContactoCliente.activo.is_(True))).first()
                if principal is not None:
                    salida.append(Destino(contacto=principal))
    else:
        if "COMERCIAL" in tipos and ocurrencia.comercial_id:
            salida.append(Destino(usuario=db.get(Usuario, ocurrencia.comercial_id)))
        if "ACTOR" in tipos and ocurrencia.actor_id:
            salida.append(Destino(usuario=db.get(Usuario, ocurrencia.actor_id)))
        salida += [Destino(usuario=u) for u in _usuarios_de_roles(db, config_dest.get("roles") or [])]
        salida += [Destino(usuario=u) for u in db.scalars(select(Usuario).where(
            Usuario.id.in_(config_dest.get("usuarios") or []), Usuario.activo.is_(True)))]
    salida += [Destino(email=c) for c in config_dest.get("correos") or []]
    unicos: dict[str, Destino] = {}
    for destino in salida:
        if destino.usuario is not None and not destino.usuario.activo:
            continue
        if destino.usuario is None and not destino.email:
            continue  # un contacto sin correo no recibe avisos
        unicos.setdefault(destino.clave, destino)
    return list(unicos.values())


# ---------- Generación ----------


def _clave(regla: ReglaNotificacion, ocurrencia: Ocurrencia, canal: str, destino: Destino) -> str:
    texto = f"{regla.id}|{ocurrencia.entidad_tipo}:{ocurrencia.entidad_id}|{ocurrencia.clave}|{canal}|{destino.clave}"
    return texto if len(texto) <= 250 else hashlib.sha256(texto.encode()).hexdigest()


def _agrupar(evento, ocurrencias: list[Ocurrencia], contexto: Contexto) -> list[Ocurrencia]:
    """Agrupación "resumen": una sola notificación por día con todas las ocurrencias (TARIFA_POR_VENCER)."""
    if not ocurrencias:
        return []
    lineas = [linea for o in ocurrencias for linea in (o.detalles or [o.titulo])]
    visibles = lineas[:5] + ([f"Y {len(lineas) - 5} más en el sistema"] if len(lineas) > 6 else lineas[5:6])
    return [Ocurrencia(
        entidad_tipo="grupo", entidad_id=evento.codigo, clave=contexto.hoy.isoformat(),
        titulo=f"{evento.nombre}: {len(ocurrencias)}", mensaje="\n".join(lineas), detalles=visibles,
        enlace=ocurrencias[0].enlace,
    )]


def plantilla_lista(plantilla: PlantillaCorreo | None) -> bool:
    return bool(plantilla and plantilla.activo and plantilla.estado_tencent == "APROBADA" and plantilla.tencent_id)


def _url(db: Session, ruta: str | None) -> str:
    """E4: los enlaces salen de la URL pública del sistema (config_sistema), nunca de una dirección fija."""
    from app.services import sistema

    return sistema.enlace(db, ruta)


# E4: nombre corto de cada aviso interno ({{evento}} de la 72752 aprobada).
NOMBRE_CORTO = {
    "COT_ACEPTADA": "Cotización aceptada", "COT_RECHAZADA": "Cotización rechazada",
    "COT_SIN_RESPUESTA": "Cotización sin respuesta", "COT_MARGEN_BAJO": "Margen bajo",
    "TARIFA_POR_VENCER": "Tarifa por vencer", "TARIFA_SIN_REEMPLAZO": "Tarifa sin reemplazo",
    "TASA_DESACTUALIZADA": "Tasa desactualizada", "ENVIO_FALLIDO": "Envío fallido",
    "CAMPANA_TERMINADA": "Campaña terminada", "CAMPANA_REBOTE_ALTO": "Campaña con rebote alto",
    "CUOTA_TENCENT_CERCA": "Cupo de correo cerca del tope", "USUARIO_BLOQUEADO": "Usuario bloqueado",
    "RESUMEN_DIARIO": "Resumen diario", "RESUMEN_SEMANAL": "Resumen semanal",
}


def ruta_interna(ruta: str | None) -> str:
    """La ruta de la pantalla del registro, empezando con "/" (campana y bitácora). Las plantillas internas aprobadas
    llevan el enlace fijo en el botón; las URL completas (baja) se arman con la URL pública del sistema."""
    ruta = ruta or "/app/inicio.html"
    return ruta if ruta.startswith("/") else "/" + ruta


def referencia(db: Session, ocurrencia: Ocurrencia) -> str:
    """{{referencia}}: el identificador del registro (COT-2026-00012, Tarifa GYE→MIA LATAM, Campaña …, el usuario…)."""
    from app.models import Campana, Tarifa

    if ocurrencia.referencia:
        return ocurrencia.referencia[:120]
    tipo, ident = ocurrencia.entidad_tipo, ocurrencia.entidad_id
    try:
        if tipo == "tarifa":
            tarifa = db.get(Tarifa, int(ident))
            if tarifa is not None:
                quien = tarifa.transportista or tarifa.servicio.nombre
                return f"Tarifa {tarifa.origen.codigo}→{tarifa.destino.codigo} {quien}"[:120]
        if tipo == "campana":
            campana = db.get(Campana, int(ident))
            if campana is not None:
                return f"Campaña {campana.nombre}"[:120]
        if tipo == "usuario":
            usuario = db.get(Usuario, int(ident))
            if usuario is not None:
                return usuario.email
        if tipo == "cotizacion":
            cotizacion = db.get(Cotizacion, int(ident))
            if cotizacion is not None:
                return cotizacion.numero or f"Cotización #{cotizacion.id}"
        if tipo == "moneda":
            return f"Moneda {ident}"
    except (TypeError, ValueError):
        pass
    return ocurrencia.titulo[:120]


def _variables(db: Session, regla: ReglaNotificacion, evento, ocurrencia: Ocurrencia, destino: Destino,
               plantilla: PlantillaCorreo | None, token_baja: str | None) -> dict[str, str]:
    from app.services import campanas

    if evento.audiencia == EXTERNA:
        datos = dict(ocurrencia.variables) | campanas.datos_empresa(db)
        if destino.contacto is not None:
            datos["nombre_contacto"] = destino.contacto.nombre
        pasos = list((regla.parametros or {}).get("pasos") or [])
        datos |= {f"paso_{n}": (pasos[n - 1] if n <= len(pasos) else "") for n in range(1, 4)}
        for n in range(1, 6):
            datos.setdefault(f"fila_{n:02d}", "")
        if token_baja:
            datos["enlace_baja"] = _url(db, f"/b/{token_baja}")
        return {clave: str(valor) for clave, valor in datos.items()}
    if ocurrencia.resumen:
        return dict(ocurrencia.variables)
    detalles = list(ocurrencia.detalles)[:6]
    # 72752 aprobada: evento, referencia y fecha; el botón lleva el enlace fijo (sin variable {{enlace}}). Se mantienen
    # las de la versión anterior (titulo, mensaje, detalle_NN): solo se envían las que tenga la plantilla del catálogo.
    # La ruta de la pantalla sigue en la notificación (campana y bitácora).
    return {"evento": NOMBRE_CORTO.get(evento.codigo, evento.nombre), "referencia": referencia(db, ocurrencia),
            "titulo": ocurrencia.titulo, "mensaje": ocurrencia.mensaje[:600],
            "fecha": fechas.ahora_ecuador().strftime("%d/%m/%Y %H:%M")} | {
        f"detalle_{n:02d}": (detalles[n - 1] if n <= len(detalles) else "") for n in range(1, 7)}


def _asunto(plantilla: PlantillaCorreo | None, ocurrencia: Ocurrencia, evento) -> str:
    base = (plantilla.asunto_sugerido if plantilla and plantilla.asunto_sugerido else None) or (
        f"XPS Pricing · {ocurrencia.titulo}" if evento.audiencia == INTERNA else ocurrencia.titulo)
    for clave, valor in ocurrencia.asunto.items():
        base = base.replace("{" + clave + "}", valor)
    return base[:300]


def _tope_semanal_lleno(db: Session, cliente_id: int | None, contexto: Contexto) -> bool:
    if cliente_id is None:
        return False
    usados = db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.audiencia == EXTERNA, Notificacion.cliente_id == cliente_id, Notificacion.canal == "CORREO",
        Notificacion.estado.in_(("ENVIADO", "SIMULADO", "PENDIENTE")),
        Notificacion.creado_en >= contexto.ahora - timedelta(days=7))) or 0
    return usados >= contexto.config.tope_semanal_cliente


def _prefiere_correo(db: Session, usuario: Usuario, regla: ReglaNotificacion) -> bool:
    if regla.obligatoria:
        return True
    preferencia = db.get(PreferenciaNotificacion, (usuario.id, regla.evento))
    return preferencia.correo if preferencia is not None else True


def _estado_externo(db: Session, evento, ocurrencia: Ocurrencia, destino: Destino, contexto: Contexto) -> tuple[str, str | None]:
    from app.services import boletines

    modo = contexto.config.modo_externo
    cotizacion = ocurrencia.cotizacion
    if cotizacion is not None and (not cotizacion.avisos_activos or not cotizacion.cliente.avisos_activos):
        return "OMITIDO", "Avisos desactivados para la cotización o el cliente"
    if destino.contacto is not None and not destino.contacto.recibir_avisos:
        return "OMITIDO", "El contacto no recibe avisos de sus cotizaciones"
    if evento.comercial and boletines.esta_de_baja(db, destino.email):
        return "OMITIDO", "Dado de baja de correos comerciales"
    if _tope_semanal_lleno(db, ocurrencia.cliente_id, contexto):
        return "OMITIDO", f"Tope semanal de {contexto.config.tope_semanal_cliente} avisos por cliente"
    return ("SIMULADO", "Modo SIMULACIÓN: no se envió") if modo == "SIMULACION" else ("PENDIENTE", None)


def generar(db: Session, codigo_evento: str, ocurrencias: list[Ocurrencia], regla: ReglaNotificacion,
            contexto: Contexto) -> int:
    """Crea las notificaciones de una regla (idempotente). Devuelve cuántas son nuevas."""
    from app.services import boletines

    evento = eventos.EVENTOS[codigo_evento]
    if evento.audiencia == EXTERNA and contexto.config.modo_externo == "APAGADO":
        return 0
    if regla.agrupacion == "RESUMEN":
        ocurrencias = _agrupar(evento, ocurrencias, contexto)
    plantilla = regla.plantilla
    nuevas = 0
    for ocurrencia in ocurrencias:
        for destino in destinatarios(db, regla, evento, ocurrencia):
            canales = []
            if regla.canal_correo:
                canales.append("CORREO")
            if regla.canal_interno and destino.usuario is not None:
                canales.append("INTERNO")
            for canal in canales:
                ahora = contexto.ahora
                estado, motivo, programada, enviado_en = "PENDIENTE", None, ahora, None
                token = None
                if canal == "INTERNO":
                    estado, enviado_en = "ENVIADO", ahora
                elif evento.audiencia == EXTERNA:
                    estado, motivo = _estado_externo(db, evento, ocurrencia, destino, contexto)
                    if evento.comercial:
                        token = boletines.nuevo_token()
                elif destino.usuario is not None and not _prefiere_correo(db, destino.usuario, regla):
                    estado, motivo = "OMITIDO", "El usuario eligió recibirlo solo en la campana"
                if canal == "CORREO" and estado in ("PENDIENTE", "SIMULADO") and not plantilla_lista(plantilla):
                    if estado == "PENDIENTE":
                        estado, motivo = "OMITIDO", "Plantilla no aprobada en Tencent"
                    else:
                        motivo = "Modo SIMULACIÓN (la plantilla aún no está aprobada en Tencent)"
                if estado == "PENDIENTE":
                    programada = siguiente_horario(contexto.config, ahora)
                variables = _variables(db, regla, evento, ocurrencia, destino, plantilla, token) if canal == "CORREO" else {}
                if token:
                    variables["token_baja"] = token
                fila = {
                    "evento": codigo_evento, "regla_id": regla.id, "audiencia": evento.audiencia,
                    "entidad_tipo": ocurrencia.entidad_tipo, "entidad_id": ocurrencia.entidad_id,
                    "cliente_id": ocurrencia.cliente_id, "comercial_id": ocurrencia.comercial_id,
                    "usuario_id": destino.usuario.id if destino.usuario else None, "email": destino.email,
                    "canal": canal, "estado": estado, "motivo_omision": motivo, "titulo": ocurrencia.titulo[:200],
                    "mensaje": ocurrencia.mensaje, "enlace": ruta_interna(ocurrencia.enlace),
                    "asunto": _asunto(plantilla, ocurrencia, evento) if canal == "CORREO" else None,
                    "plantilla_id": plantilla.id if plantilla and canal == "CORREO" else None, "variables": variables,
                    "adjuntar_pdf": bool((regla.parametros or {}).get("adjuntar_pdf")) and ocurrencia.cotizacion is not None,
                    "programada_para": programada, "enviado_en": enviado_en, "creado_en": ahora,
                    "clave_idempotencia": _clave(regla, ocurrencia, canal, destino),
                }
                resultado = db.execute(insert(Notificacion).values(**fila).on_conflict_do_nothing(
                    index_elements=["clave_idempotencia"]))
                nuevas += resultado.rowcount or 0
    return nuevas


def emitir(db: Session, codigo_evento: str, ocurrencia: Ocurrencia) -> int:
    """Evento INMEDIATO, en la transacción del servicio que lo dispara (outbox). Nunca lanza."""
    try:
        enviar(db)  # lo del servicio queda fuera del savepoint
    except ErrorNegocio:
        raise
    try:
        with db.begin_nested():
            ctx = contexto(db)
            if ocurrencia.cotizacion is not None and eventos.EVENTOS[codigo_evento].de_cotizacion:
                envio = eventos.fecha_envio(db, ocurrencia.cotizacion.id)
                if envio is None or (ctx.config.aplicar_desde and envio < ctx.config.aplicar_desde):
                    return 0
            return sum(generar(db, codigo_evento, [ocurrencia], regla, ctx) for regla in reglas_activas(db, codigo_evento))
    except Exception:  # noqa: BLE001 - un aviso nunca cambia el resultado del servicio que lo dispara
        registro.exception("no se pudo generar el aviso %s", codigo_evento)
        return 0


def cancelar(db: Session, entidad_tipo: str, entidad_id: Any, motivo: str) -> int:
    resultado = db.execute(
        update(Notificacion).where(Notificacion.entidad_tipo == entidad_tipo, Notificacion.entidad_id == str(entidad_id),
                                   Notificacion.estado == "PENDIENTE", Notificacion.audiencia == EXTERNA)
        .values(estado="CANCELADO", motivo_omision=motivo[:200]).execution_options(synchronize_session=False)
    )
    return resultado.rowcount or 0


# ---------- Ganchos de los servicios existentes (inmediatos) ----------


def al_cerrar_cotizacion(db: Session, cotizacion: Cotizacion, estado: str) -> None:
    """ACEPTADA o RECHAZADA: cancela los avisos pendientes al cliente y avisa."""
    try:
        cancelar(db, "cotizacion", cotizacion.id, f"La cotización pasó a {estado}")
    except Exception:  # noqa: BLE001
        registro.exception("no se pudieron cancelar los avisos de la cotización %s", cotizacion.id)
    numero = cotizacion.numero
    if estado == "ACEPTADA":
        emitir(db, "COT_ACEPTADA", eventos.ocurrencia_cotizacion(
            cotizacion, "1", f"{numero} aceptada",
            f"{cotizacion.cliente.razon_social} aceptó la cotización {numero} por {eventos.dinero(cotizacion.total_general)}."))
        emitir(db, "COT_ACEPTADA_CLIENTE", eventos.ocurrencia_cotizacion(
            cotizacion, "1", f"Confirmación de aceptación de {numero}", f"Confirmación al cliente por {numero}."))
    elif estado == "RECHAZADA":
        from app.services import administracion

        motivo = administracion.motivo_por_codigo(db, cotizacion.motivo_rechazo) if cotizacion.motivo_rechazo else None
        texto = (motivo.nombre if motivo else cotizacion.motivo_rechazo or "") + (
            f" · {cotizacion.detalle_rechazo}" if cotizacion.detalle_rechazo else "")
        emitir(db, "COT_RECHAZADA", eventos.ocurrencia_cotizacion(
            cotizacion, "1", f"{numero} rechazada", f"{cotizacion.cliente.razon_social} rechazó la cotización {numero}: {texto}.",
            detalles=[f"Motivo: {texto}", *eventos.detalles_cotizacion(cotizacion)]))


def al_emitir(db: Session, cotizacion: Cotizacion, lineas_bajo_costo: int) -> None:
    """Margen bajo y reemplazo: la emisión de una copia cancela los avisos pendientes de la original."""
    if cotizacion.cotizacion_origen_id:
        try:
            cancelar(db, "cotizacion", cotizacion.cotizacion_origen_id, f"Reemplazada por {cotizacion.numero}")
        except Exception:  # noqa: BLE001
            registro.exception("no se pudieron cancelar los avisos de la cotización %s", cotizacion.cotizacion_origen_id)
    for regla in reglas_activas(db, "COT_MARGEN_BAJO"):
        umbral = float((regla.parametros or {}).get("umbral_pct", 15))
        margen = float(cotizacion.margen_pct) if cotizacion.margen_pct is not None else None
        if lineas_bajo_costo or (margen is not None and margen < umbral):
            emitir(db, "COT_MARGEN_BAJO", eventos.ocurrencia_cotizacion(
                cotizacion, "1", f"Margen bajo en {cotizacion.numero}",
                f"La cotización {cotizacion.numero} se emitió con margen {margen if margen is not None else '—'} % "
                f"(umbral {umbral:g} %)" + (f" y {lineas_bajo_costo} línea(s) bajo costo." if lineas_bajo_costo else "."),
                detalles=[f"Margen: {margen if margen is not None else '—'} %", f"Líneas bajo costo: {lineas_bajo_costo}",
                          *eventos.detalles_cotizacion(cotizacion)[:4]]))
            return


def envio_fallido(db: Session, entidad_tipo: str, entidad_id: Any, clave: str, titulo: str, mensaje: str,
                  actor_id: int | None, enlace: str | None) -> None:
    emitir(db, "ENVIO_FALLIDO", Ocurrencia(entidad_tipo=entidad_tipo, entidad_id=str(entidad_id), clave=clave, titulo=titulo,
                                           mensaje=mensaje, detalles=[mensaje], enlace=enlace, actor_id=actor_id))


def usuario_bloqueado(db: Session, usuario: Usuario) -> None:
    emitir(db, "USUARIO_BLOQUEADO", Ocurrencia(
        entidad_tipo="usuario", entidad_id=str(usuario.id), clave=usuario.bloqueado_hasta.isoformat(),
        titulo=f"Usuario bloqueado: {usuario.email}",
        mensaje=f"{usuario.nombre} ({usuario.email}) quedó bloqueado por intentos fallidos de ingreso.",
        detalles=[f"Usuario: {usuario.email}", f"Bloqueado hasta: {usuario.bloqueado_hasta.astimezone(fechas.ZONA_ECUADOR):%d/%m/%Y %H:%M}"],
        enlace="/app/usuarios.html"))


# ---------- Evaluación (Cloud Scheduler cada hora) ----------


def evaluar(db: Session) -> dict[str, Any]:
    ctx = contexto(db)
    creadas: dict[str, int] = {}
    for codigo, evento in eventos.EVENTOS.items():
        buscar = eventos.detector_de(codigo)
        if buscar is None or (evento.audiencia == EXTERNA and ctx.config.modo_externo == "APAGADO"):
            continue
        for regla in reglas_activas(db, codigo):
            try:
                nuevas = generar(db, codigo, buscar(db, regla, ctx), regla, ctx)
                db.commit()
            except Exception:  # noqa: BLE001 - un detector con problemas no frena a los demás
                db.rollback()
                registro.exception("falló el detector %s", codigo)
                continue
            if nuevas:
                creadas[codigo] = creadas.get(codigo, 0) + nuevas
    fila = config(db, bloquear=True)
    fila.ultima_evaluacion = ctx.ahora
    db.commit()
    return {"creadas": creadas, "entregas": entregar(db)}


# ---------- Envío ----------


def _siguiente(db: Session, ahora: datetime) -> Notificacion | None:
    return db.scalars(
        select(Notificacion).where(Notificacion.estado == "PENDIENTE", Notificacion.canal == "CORREO",
                                   Notificacion.programada_para <= ahora)
        .order_by(Notificacion.programada_para, Notificacion.id).limit(1).with_for_update(skip_locked=True)
    ).first()


def _adjunto(db: Session, notificacion: Notificacion, maximo: int) -> tuple[str, bytes]:
    from app.services import pdf

    if not notificacion.adjuntar_pdf or notificacion.entidad_tipo != "cotizacion":
        return "", b""
    cotizacion = db.get(Cotizacion, int(notificacion.entidad_id))
    if cotizacion is None or not cotizacion.snapshot_emision:
        return "", b""
    contenido = pdf.generar_pdf_de(cotizacion.snapshot_emision, False)
    if len(contenido) > maximo:
        return "", b""  # respeta adjunto_max_bytes: el aviso sale sin el PDF
    return pdf.nombre_archivo(cotizacion.numero, cotizacion.id, cotizacion.snapshot_emision["cliente"]["razon_social"]), contenido


def entregar(db: Session, limite: int | None = None) -> dict[str, Any]:
    from app.services import correo, masivos
    from app.services.proveedor_correo import Mensaje, traducir

    resumen: dict[str, Any] = {"enviados": 0, "fallidos": 0, "omitidos": 0, "reintentos": 0}
    vigente = correo.config_vigente(db)
    if not vigente.configurado or vigente.estado != "HABILITADO":
        resumen["motivo"] = "CORREO_NO_CONFIGURADO"
        return resumen
    disponibles = masivos.disponibles_para_avisos(db, masivos.config(db))
    if limite is not None:
        disponibles = min(disponibles, limite)
    procesados = 0
    while procesados < disponibles:
        notificacion = _siguiente(db, fechas.ahora_ecuador())
        if notificacion is None:
            break
        procesados += 1
        plantilla = notificacion.plantilla
        if not plantilla_lista(plantilla):
            notificacion.estado, notificacion.motivo_omision = "OMITIDO", "Plantilla no aprobada en Tencent"
            resumen["omitidos"] += 1
            db.commit()
            continue
        if notificacion.audiencia == EXTERNA and notificacion.entidad_tipo == "cotizacion":
            cotizacion = db.get(Cotizacion, int(notificacion.entidad_id))
            if cotizacion is None or not cotizacion.avisos_activos or not cotizacion.cliente.avisos_activos:
                notificacion.estado, notificacion.motivo_omision = "CANCELADO", "Avisos desactivados"
                db.commit()
                continue
        nombre, adjunto = _adjunto(db, notificacion, vigente.adjunto_max_bytes)
        datos = {clave: str(notificacion.variables.get(clave, "")) for clave in plantilla.variables_esperadas}
        resultado = correo._llamar(vigente, Mensaje(
            remitente=vigente.remitente, destinatario=notificacion.email, asunto=notificacion.asunto or notificacion.titulo,
            reply_to=vigente.reply_to, plantilla_id=plantilla.tencent_id, datos_plantilla=datos,
            adjunto_nombre=nombre, adjunto=adjunto, trigger_type=1,
        ))
        notificacion.intentos += 1
        if resultado.ok:
            notificacion.estado, notificacion.message_id = "ENVIADO", resultado.message_id
            notificacion.enviado_en, notificacion.ultimo_error = fechas.ahora_ecuador(), None
            resumen["enviados"] += 1
        else:
            traduccion = traducir(resultado.codigo_error)
            notificacion.ultimo_error = f"{traduccion.codigo}: {traduccion.mensaje}"[:300]
            if traduccion.reintentable and notificacion.intentos < MAXIMO_INTENTOS:
                notificacion.programada_para = fechas.ahora_ecuador() + timedelta(minutes=10)
                resumen["reintentos"] += 1
            else:
                notificacion.estado = "FALLIDO"
                resumen["fallidos"] += 1
                if notificacion.evento != "ENVIO_FALLIDO":
                    envio_fallido(db, "notificacion", notificacion.id, "1", f"Aviso no enviado: {notificacion.titulo}"[:200],
                                  f"El aviso «{notificacion.titulo}» a {notificacion.email} falló: {traduccion.mensaje}",
                                  None, "/app/notificaciones-bitacora.html")
        db.commit()
    return resumen


# ---------- Bitácora (notificaciones.bitacora.ver) ----------


def contenido(notificacion: Notificacion) -> str:
    """El texto que se envió o se habría enviado: la versión de texto de la plantilla con las variables."""
    from app.services import plantillas_diseno

    if notificacion.canal == "INTERNO" or notificacion.plantilla is None:
        return notificacion.mensaje
    base = notificacion.plantilla.texto or plantillas_diseno.texto_plano(notificacion.plantilla.html or "")
    if not base.strip():  # plantilla aún sin sincronizar: las variables tal cual
        return "\n".join(f"{clave}: {valor}" for clave, valor in notificacion.variables.items() if clave != "token_baja" and valor)
    return plantillas_diseno.PATRON_VARIABLE.sub(lambda m: str(notificacion.variables.get(m.group(1), "")), base)


def bitacora(db: Session, filtros: dict[str, Any], limite: int = 200) -> list[Notificacion]:
    consulta = select(Notificacion)
    for campo in ("evento", "estado", "canal", "audiencia", "cliente_id", "comercial_id"):
        if filtros.get(campo) not in (None, ""):
            consulta = consulta.where(getattr(Notificacion, campo) == filtros[campo])
    if filtros.get("desde"):
        consulta = consulta.where(Notificacion.creado_en >= datetime.combine(filtros["desde"], datetime.min.time(), tzinfo=fechas.ZONA_ECUADOR))
    if filtros.get("hasta"):
        consulta = consulta.where(Notificacion.creado_en < datetime.combine(filtros["hasta"] + timedelta(days=1), datetime.min.time(), tzinfo=fechas.ZONA_ECUADOR))
    return list(db.scalars(consulta.order_by(Notificacion.id.desc()).limit(limite)))


def obtener(db: Session, notificacion_id: int) -> Notificacion:
    notificacion = db.get(Notificacion, notificacion_id)
    if notificacion is None:
        raise ErrorNegocio(404, "NOTIFICACION_NO_ENCONTRADA", "Notificación no encontrada")
    return notificacion


def reenviar(db: Session, actor: Usuario, notificacion_id: int) -> Notificacion:
    notificacion = obtener(db, notificacion_id)
    if notificacion.estado != "FALLIDO" or notificacion.canal != "CORREO":
        raise ErrorNegocio(409, "NO_REENVIABLE", "Solo se reenvían los correos fallidos")
    notificacion.estado, notificacion.intentos, notificacion.ultimo_error = "PENDIENTE", 0, None
    notificacion.programada_para = fechas.ahora_ecuador()
    auditoria.registrar(db, actor, "notificacion", notificacion.id, "EDITAR", antes={"estado": "FALLIDO"},
                        despues={"estado": "PENDIENTE"}, nota="REENVIAR")
    confirmar(db)
    return notificacion


# ---------- Centro de notificaciones (campana) ----------


def mias(db: Session, usuario: Usuario, solo_no_leidas: bool = False, limite: int = 100) -> list[Notificacion]:
    consulta = select(Notificacion).where(Notificacion.usuario_id == usuario.id, Notificacion.canal == "INTERNO")
    if solo_no_leidas:
        consulta = consulta.where(Notificacion.leida_en.is_(None))
    return list(db.scalars(consulta.order_by(Notificacion.id.desc()).limit(limite)))


def no_leidas(db: Session, usuario: Usuario) -> int:
    return db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.usuario_id == usuario.id, Notificacion.canal == "INTERNO", Notificacion.leida_en.is_(None))) or 0


def marcar_leida(db: Session, usuario: Usuario, notificacion_id: int) -> Notificacion:
    notificacion = db.get(Notificacion, notificacion_id)
    if notificacion is None or notificacion.usuario_id != usuario.id or notificacion.canal != "INTERNO":
        raise ErrorNegocio(404, "NOTIFICACION_NO_ENCONTRADA", "Notificación no encontrada")
    if notificacion.leida_en is None:
        notificacion.leida_en = fechas.ahora_ecuador()
        confirmar(db)
    return notificacion


def marcar_todas(db: Session, usuario: Usuario) -> int:
    resultado = db.execute(update(Notificacion).where(
        Notificacion.usuario_id == usuario.id, Notificacion.canal == "INTERNO", Notificacion.leida_en.is_(None))
        .values(leida_en=fechas.ahora_ecuador()).execution_options(synchronize_session=False))
    confirmar(db)
    return resultado.rowcount or 0


# ---------- Preferencias ----------


def preferencias(db: Session, usuario: Usuario) -> list[dict[str, Any]]:
    salida = []
    for evento in eventos.EVENTOS.values():
        if evento.audiencia != INTERNA:
            continue
        reglas = [r for r in reglas_activas(db, evento.codigo) if r.canal_correo]
        if not reglas:
            continue
        obligatoria = any(r.obligatoria for r in reglas)
        preferencia = db.get(PreferenciaNotificacion, (usuario.id, evento.codigo))
        salida.append({"evento": evento.codigo, "nombre": evento.nombre, "descripcion": evento.descripcion,
                       "obligatoria": obligatoria,
                       "correo": True if obligatoria else (preferencia.correo if preferencia else True)})
    return salida


def guardar_preferencias(db: Session, usuario: Usuario, cambios: dict[str, bool]) -> list[dict[str, Any]]:
    actuales = {p["evento"]: p for p in preferencias(db, usuario)}
    for evento, correo_si in cambios.items():
        if evento not in actuales:
            raise ErrorNegocio(422, "EVENTO_INEXISTENTE", f"No hay preferencias para {evento}")
        if actuales[evento]["obligatoria"] and not correo_si:
            raise ErrorNegocio(409, "PREFERENCIA_OBLIGATORIA", f"«{actuales[evento]['nombre']}» es obligatorio por correo")
        fila = db.get(PreferenciaNotificacion, (usuario.id, evento))
        if fila is None:
            db.add(PreferenciaNotificacion(usuario_id=usuario.id, evento=evento, correo=bool(correo_si)))
        else:
            fila.correo = bool(correo_si)
    confirmar(db)
    return preferencias(db, usuario)


# ---------- Interruptores de cotización, cliente y contacto ----------


def avisos_de_cotizacion(db: Session, cotizacion: Cotizacion) -> dict[str, Any]:
    lista = list(db.scalars(select(Notificacion).where(
        Notificacion.entidad_tipo == "cotizacion", Notificacion.entidad_id == str(cotizacion.id),
        Notificacion.audiencia == EXTERNA).order_by(Notificacion.programada_para, Notificacion.id)))
    return {"activos": cotizacion.avisos_activos, "cliente_activos": cotizacion.cliente.avisos_activos, "avisos": lista}


def cambiar_avisos_cotizacion(db: Session, actor: Usuario, cotizacion: Cotizacion, activos: bool) -> None:
    if cotizacion.avisos_activos != activos:
        auditoria.registrar(db, actor, "cotizacion", cotizacion.id, "EDITAR", antes={"avisos_activos": cotizacion.avisos_activos},
                            despues={"avisos_activos": activos}, nota=f"AVISOS {'ACTIVADOS' if activos else 'DESACTIVADOS'}")
        cotizacion.avisos_activos = activos
        if not activos:
            cancelar(db, "cotizacion", cotizacion.id, "Avisos desactivados en la cotización")
    confirmar(db)


def cambiar_avisos_cliente(db: Session, actor: Usuario, cliente, activos: bool) -> None:
    if cliente.avisos_activos != activos:
        auditoria.registrar(db, actor, "cliente", cliente.id, "EDITAR", antes={"avisos_activos": cliente.avisos_activos},
                            despues={"avisos_activos": activos}, nota=f"AVISOS {'ACTIVADOS' if activos else 'DESACTIVADOS'}")
        cliente.avisos_activos = activos
        if not activos:
            db.execute(update(Notificacion).where(
                Notificacion.cliente_id == cliente.id, Notificacion.estado == "PENDIENTE", Notificacion.audiencia == EXTERNA)
                .values(estado="CANCELADO", motivo_omision="Avisos desactivados en el cliente")
                .execution_options(synchronize_session=False))
    confirmar(db)


def cambiar_avisos_contacto(db: Session, actor: Usuario, contacto: ContactoCliente, recibir: bool) -> None:
    if contacto.recibir_avisos != recibir:
        auditoria.registrar(db, actor, "contacto_cliente", contacto.id, "EDITAR",
                            antes={"recibir_avisos": contacto.recibir_avisos}, despues={"recibir_avisos": recibir})
        contacto.recibir_avisos = recibir
    confirmar(db)


def puede_ver_bitacora(usuario: Usuario) -> bool:
    return tiene_permiso(usuario, "notificaciones.bitacora.ver")

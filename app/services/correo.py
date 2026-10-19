"""Correo Tencent administrable (bloque B de F4): configuración, salud, plantillas, prueba y envío.

- La configuración vive en config_correo (una fila). Las llaves van cifradas (core/cifrado) y nunca salen por
  la API ni a la auditoría: solo enmascaradas. Se lee con caché de 60 s que se invalida al guardar.
- "No configurado": faltan las llaves, falta CONFIG_CIFRADO_KEY o no descifran. El sistema arranca igual.
- H-F4-10: probar, plantillas y el correo de prueba funcionan con llaves válidas aunque el interruptor esté
  apagado; solo el envío de cotizaciones exige habilitado=true.
- Envío (B6, H-F4-14): validaciones → PDF desde la foto congelada FUERA del bloqueo → SELECT … FOR UPDATE,
  revalidar y enviar → bitácora, auditoría y commit. Síncrono, sin BackgroundTasks.
"""
import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import cifrado, fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import ConfigCorreo, ContactoCliente, Cotizacion, EnvioCorreo, EnvioCorreoPrueba, Usuario
from app.services import auditoria, cotizaciones, pdf
from app.services.proveedor_correo import (
    ConfigProveedor,
    ErrorProveedor,
    Mensaje,
    ProveedorCorreo,
    Resultado,
    mensaje_de,
    traducir,
)

CACHE_CONFIG_S = 60
CACHE_SALUD_S = 600
MAXIMO_CC = 5
ESTADOS_ENVIABLES = ("EMITIDA", "ENVIADA")
PATRON_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
CAMPOS_EDITABLES = (
    "habilitado",
    "region",
    "endpoint",
    "remitente",
    "reply_to",
    "bcc",
    "plantilla_cotizacion_id",
    "timeout_s",
    "adjunto_max_bytes",
)
ESTADOS_PLANTILLA = {0: "Aprobada", 1: "En revisión", 2: "Rechazada"}


# ---------- Proveedor (los tests sustituyen la fábrica por el falso) ----------


def _proveedor_real(config: ConfigProveedor) -> ProveedorCorreo:
    from app.services.tencent_ses import TencentSES

    return TencentSES(config)


fabrica_proveedor = _proveedor_real


# ---------- Configuración con caché ----------


@dataclass(frozen=True)
class ConfigCorreoVigente:
    habilitado: bool
    region: str
    endpoint: str
    remitente: str
    reply_to: str
    bcc: str | None
    plantilla_cotizacion_id: int
    timeout_s: int
    adjunto_max_bytes: int
    secret_id: str | None
    secret_key: str | None

    @property
    def configurado(self) -> bool:
        return bool(self.secret_id and self.secret_key)

    @property
    def estado(self) -> str:
        if not self.configurado:
            return "NO_CONFIGURADO"
        return "HABILITADO" if self.habilitado else "DESHABILITADO"

    def proveedor(self) -> ConfigProveedor:
        return ConfigProveedor(self.region, self.endpoint, self.timeout_s, self.secret_id, self.secret_key)


_cache: dict[str, Any] = {}


def invalidar_cache() -> None:
    _cache.clear()


def _fila(db: Session, *, bloquear: bool = False) -> ConfigCorreo:
    consulta = select(ConfigCorreo).where(ConfigCorreo.id == 1)
    if bloquear:
        consulta = consulta.with_for_update()
    return db.scalars(consulta.execution_options(populate_existing=True)).one()


def _vigente_de(fila: ConfigCorreo) -> ConfigCorreoVigente:
    return ConfigCorreoVigente(
        habilitado=fila.habilitado,
        region=fila.region,
        endpoint=fila.endpoint,
        remitente=fila.remitente,
        reply_to=fila.reply_to,
        bcc=fila.bcc,
        plantilla_cotizacion_id=fila.plantilla_cotizacion_id,
        timeout_s=fila.timeout_s,
        adjunto_max_bytes=fila.adjunto_max_bytes,
        secret_id=cifrado.descifrar(fila.secret_id_cifrado),
        secret_key=cifrado.descifrar(fila.secret_key_cifrado),
    )


def config_vigente(db: Session) -> ConfigCorreoVigente:
    """La configuración descifrada, con caché de 60 s (se invalida al guardar)."""
    ahora = time.monotonic()
    if _cache.get("config") is not None and _cache["config_hasta"] > ahora:
        return _cache["config"]
    vigente = _vigente_de(_fila(db))
    _cache["config"], _cache["config_hasta"] = vigente, ahora + CACHE_CONFIG_S
    return vigente


def _email_de(remitente: str) -> str:
    """'Nombre <correo@dominio>' o 'correo@dominio' → correo@dominio."""
    encontrado = re.search(r"<([^<>]+)>", remitente)
    return (encontrado.group(1) if encontrado else remitente).strip()


def _dominio_de(remitente: str) -> str:
    return _email_de(remitente).rsplit("@", 1)[-1].lower()  # H-F4-12: del remitente, no fijo en el código


def presentar_config(db: Session) -> dict[str, Any]:
    """GET /v1/correo/config: las llaves solo enmascaradas."""
    fila = _fila(db)
    vigente = _vigente_de(fila)
    actualizado_por = db.get(Usuario, fila.actualizado_por) if fila.actualizado_por else None
    return {
        **{campo: getattr(fila, campo) for campo in CAMPOS_EDITABLES},
        "secret_id": cifrado.enmascarar(vigente.secret_id),
        "secret_key": cifrado.enmascarar(vigente.secret_key),
        "llaves_guardadas": bool(fila.secret_id_cifrado and fila.secret_key_cifrado),
        "cifrado_disponible": cifrado.disponible(),
        "estado": vigente.estado,
        "dominio": _dominio_de(fila.remitente),
        "actualizado_por": actualizado_por.nombre if actualizado_por else None,
        "fecha": fila.fecha.isoformat(),
    }


def _foto_config(fila: ConfigCorreo) -> dict[str, Any]:
    """Para la auditoría: las llaves SIEMPRE enmascaradas, jamás en claro."""
    return {campo: getattr(fila, campo) for campo in CAMPOS_EDITABLES} | {
        "secret_id": cifrado.enmascarar(cifrado.descifrar(fila.secret_id_cifrado)) or (
            "(cifrada)" if fila.secret_id_cifrado else None
        ),
        "secret_key": cifrado.enmascarar(cifrado.descifrar(fila.secret_key_cifrado)) or (
            "(cifrada)" if fila.secret_key_cifrado else None
        ),
    }


def _validar_email(valor: str, campo: str) -> str:
    valor = (valor or "").strip()
    if not PATRON_EMAIL.match(valor):
        raise ErrorNegocio(422, "CORREO_CONFIG_INVALIDA", f"{campo}: dirección de correo no válida")
    return valor


def _error_proveedor(error: ErrorProveedor) -> ErrorNegocio:
    traduccion = traducir(error.codigo)
    return ErrorNegocio(
        422, traduccion.codigo, traduccion.mensaje, extra={"reintentable": traduccion.reintentable}
    )


def _validar_contra_proveedor(vigente: ConfigCorreoVigente) -> None:
    """B3: dominio verificado, remitente existente y plantilla aprobada; si algo falla, 422 y no se guarda."""
    proveedor = fabrica_proveedor(vigente.proveedor())
    try:
        if not proveedor.dominio_verificado(_dominio_de(vigente.remitente)):
            raise ErrorNegocio(422, "DOMINIO_NO_VERIFICADO", "El dominio del remitente no está verificado en Tencent.")
        if not proveedor.remitente_existe(_email_de(vigente.remitente)):
            raise ErrorNegocio(422, "REMITENTE_NO_VALIDO", "El remitente no está verificado. Avise al administrador.")
        if proveedor.estado_plantilla(vigente.plantilla_cotizacion_id) != 0:
            raise ErrorNegocio(
                422, "PLANTILLA_NO_DISPONIBLE",
                "La plantilla de correo no está aprobada o no coincide. Avise al administrador.",
            )
    except ErrorProveedor as error:
        raise _error_proveedor(error) from None


def actualizar_config(db: Session, actor: Usuario, datos: dict[str, Any]) -> dict[str, Any]:
    """PUT /v1/correo/config. Con habilitado=true valida contra Tencent ANTES de guardar (H-F4-11)."""
    fila = _fila(db, bloquear=True)
    antes = _foto_config(fila)
    nuevos = {campo: datos[campo] for campo in CAMPOS_EDITABLES if campo in datos}
    for campo in ("region", "endpoint", "remitente"):
        if campo in nuevos:
            nuevos[campo] = (nuevos[campo] or "").strip()
            if not nuevos[campo]:
                raise ErrorNegocio(422, "CORREO_CONFIG_INVALIDA", f"{campo}: es obligatorio")
    if "remitente" in nuevos:
        _validar_email(_email_de(nuevos["remitente"]), "remitente")
    if "reply_to" in nuevos:
        nuevos["reply_to"] = _validar_email(nuevos["reply_to"], "reply_to")
    if "bcc" in nuevos:
        nuevos["bcc"] = _validar_email(nuevos["bcc"], "bcc") if (nuevos["bcc"] or "").strip() else None

    llaves = {campo: (datos.get(campo) or "").strip() for campo in ("secret_id", "secret_key")}
    if any(llaves.values()):
        if not cifrado.disponible():
            raise ErrorNegocio(
                422, "CIFRADO_NO_CONFIGURADO", "Falta CONFIG_CIFRADO_KEY en el servidor: no se pueden guardar las llaves."
            )
        if not all(llaves.values()):
            raise ErrorNegocio(422, "LLAVES_INCOMPLETAS", "Envíe el SecretId y la SecretKey juntos")

    # Se valida la configuración PROPUESTA antes de tocar la fila: si algo falla, no queda nada a medias.
    actual = _vigente_de(fila)
    propuesta = ConfigCorreoVigente(**(
        {campo: getattr(actual, campo) for campo in ConfigCorreoVigente.__dataclass_fields__}
        | nuevos
        | ({"secret_id": llaves["secret_id"], "secret_key": llaves["secret_key"]} if all(llaves.values()) else {})
    ))
    if propuesta.habilitado:
        if not propuesta.configurado:
            raise ErrorNegocio(422, "CORREO_NO_CONFIGURADO", "Para habilitar el correo, cargue primero llaves válidas.")
        _validar_contra_proveedor(propuesta)

    with db.no_autoflush:
        for campo, valor in nuevos.items():
            setattr(fila, campo, valor)
        if all(llaves.values()):
            fila.secret_id_cifrado = cifrado.cifrar(llaves["secret_id"])
            fila.secret_key_cifrado = cifrado.cifrar(llaves["secret_key"])
        despues = _foto_config(fila)
        if despues != antes:
            fila.actualizado_por = auditoria.id_de(actor)
            fila.fecha = func.now()
            auditoria.registrar(db, actor, "config_correo", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    invalidar_cache()
    return presentar_config(db)


def _exigir_llaves(vigente: ConfigCorreoVigente) -> None:
    if not vigente.configurado:
        raise ErrorNegocio(
            503, "CORREO_NO_CONFIGURADO", "El correo no está configurado: cargue las llaves en Configuración."
        )


# ---------- Salud (B10) y plantillas (B3) ----------


def salud(db: Session, *, refrescar: bool = False) -> dict[str, Any]:
    vigente = config_vigente(db)
    base = {"estado": vigente.estado, "dominio": _dominio_de(vigente.remitente),
            "remitente": _email_de(vigente.remitente), "plantilla_id": vigente.plantilla_cotizacion_id}
    if not vigente.configurado:
        return base | {"consultado": False, "mensaje": "El correo no está configurado: no se consultó a Tencent."}
    clave = (vigente.region, vigente.endpoint, vigente.remitente, vigente.plantilla_cotizacion_id, vigente.secret_id)
    ahora = time.monotonic()
    guardada = _cache.get("salud")
    if not refrescar and guardada and guardada[0] == clave and guardada[1] > ahora:
        return guardada[2]
    proveedor = fabrica_proveedor(vigente.proveedor())
    resultado = base | {"consultado": True, "dominio_verificado": None, "remitente_existe": None,
                        "plantilla_estado": None, "plantilla_estado_texto": None, "error": None}
    try:
        resultado["dominio_verificado"] = proveedor.dominio_verificado(base["dominio"])
        resultado["remitente_existe"] = proveedor.remitente_existe(base["remitente"])
        estado = proveedor.estado_plantilla(vigente.plantilla_cotizacion_id)
        resultado["plantilla_estado"] = estado
        resultado["plantilla_estado_texto"] = ESTADOS_PLANTILLA.get(estado, "No encontrada")
    except ErrorProveedor as error:
        traduccion = traducir(error.codigo)
        resultado["error"] = {"codigo": traduccion.codigo, "mensaje": traduccion.mensaje,
                              "reintentable": traduccion.reintentable}
    resultado["todo_ok"] = (
        resultado["error"] is None and resultado["dominio_verificado"] is True
        and resultado["remitente_existe"] is True and resultado["plantilla_estado"] == 0
    )
    _cache["salud"] = (clave, ahora + CACHE_SALUD_S, resultado)
    return resultado


def plantillas(db: Session) -> list[dict[str, Any]]:
    vigente = config_vigente(db)
    _exigir_llaves(vigente)
    try:
        lista = fabrica_proveedor(vigente.proveedor()).plantillas()
    except ErrorProveedor as error:
        raise _error_proveedor(error) from None
    return [
        {"id": p.id, "nombre": p.nombre, "estado": p.estado, "estado_texto": ESTADOS_PLANTILLA.get(p.estado)}
        for p in lista
        if p.estado == 0
    ]


# ---------- Envío (comunes) ----------


def asunto_de(numero: str) -> str:
    return f"Cotización {numero} – XPRESS LOGISTICS XPS S.A."


def _llamar(vigente: ConfigCorreoVigente, mensaje: Mensaje) -> Resultado:
    """Nunca lanza: cualquier excepción del proveedor se vuelve un Resultado fallido."""
    try:
        return fabrica_proveedor(vigente.proveedor()).enviar(mensaje)
    except ErrorProveedor as error:
        return Resultado(ok=False, request_id=error.request_id, codigo_error=error.codigo,
                         mensaje_proveedor=error.mensaje)
    except Exception as error:  # noqa: BLE001 - el envío nunca deja la cotización a medias
        return Resultado(ok=False, codigo_error="SIN_CONEXION", mensaje_proveedor=type(error).__name__)


def _respuesta_proveedor(resultado: Resultado) -> str | None:
    if resultado.ok:
        return None
    return json.dumps({"codigo": resultado.codigo_error, "mensaje": (resultado.mensaje_proveedor or "")[:500]},
                      ensure_ascii=False)


def _bcc(vigente: ConfigCorreoVigente, destinatarios: list[str]) -> tuple[str, ...]:
    if not vigente.bcc:
        return ()
    usados = {d.lower() for d in destinatarios}
    return () if vigente.bcc.lower() in usados else (vigente.bcc,)


# ---------- Correo de prueba (B3) ----------


def _muestra(usuario: Usuario, hoy: date) -> dict[str, Any]:
    """Datos ficticios fijos para el PDF de prueba (H-F4-16); no usa ninguna cotización real."""
    return {
        "empresa": pdf.RAZON_SOCIAL, "numero": "COT-PRUEBA", "fecha_emision": hoy.isoformat(),
        "valida_hasta": (hoy + timedelta(days=15)).isoformat(),
        "cliente": {"razon_social": "Cliente de prueba S.A.", "tipo_id": "RUC", "ruc_o_id": "0999999999001",
                    "direccion": None, "ciudad": "Guayaquil", "pais": "Ecuador"},
        "contacto": {"nombre": usuario.nombre, "cargo": None, "email": usuario.email, "telefono": None},
        "comercial": {"nombre": usuario.nombre, "email": usuario.email},
        "origen": {"codigo": "MIA", "nombre": "Miami", "pais": "Estados Unidos"},
        "destino": {"codigo": "GYE", "nombre": "Guayaquil", "pais": "Ecuador"},
        "incoterm": {"codigo": "FCA", "nombre": "Free Carrier"}, "sentido": "IMPORTACION", "modo": "AEREO",
        "carga": {"unidad_peso": "KG", "peso_kg": "100.000", "bultos": 1, "dimensiones": None,
                  "peso_cobrable_kg": "100.000", "peso_volumetrico_kg": "0.000", "base_cobro": "REAL",
                  "contenedores": []},
        "transit_time": "3 días", "dias_libres": "—", "transportista": "Aerolínea de prueba",
        "descripcion_carga": "Mercancía de prueba", "condiciones": "Documento de PRUEBA, sin validez comercial.",
        "notas_cliente": None, "datos_empresa": {},
        "lineas": [{"orden": 1, "concepto": "Flete aéreo de prueba", "bloque_incoterm": "FLETE_PRINCIPAL",
                    "bloque_fiscal": "RECIBO_CAJA", "cantidad": "100.0000", "rate_unit": "KG",
                    "precio_venta_unit_usd": "1.0000", "subtotal_venta_usd": "100.0000", "aplica_iva": False,
                    "minimo_venta_usd": "0.0000", "cobro_minimo": False, "unidad_peso": "KG", "tipo_equipo": None}],
        "totales": {"subtotal_recibo_caja": "100.00", "subtotal_factura": "0.00", "iva": "0.00",
                    "total_general": "100.00", "iva_tasa": "15.00"},
    }


def enviar_prueba(db: Session, actor: Usuario, email: str) -> dict[str, Any]:
    destinatario = _validar_email(email, "email")
    vigente = config_vigente(db)
    _exigir_llaves(vigente)
    hoy = fechas.hoy_ecuador()
    datos = _muestra(actor, hoy)
    adjunto = pdf.generar_pdf_de(datos, False, marca="prueba")
    nombre = "COT-PRUEBA_Xpress.pdf"
    asunto = asunto_de("COT-PRUEBA")
    if len(adjunto) > vigente.adjunto_max_bytes:
        resultado = Resultado(ok=False, codigo_error="FailedOperation.AttachContentToolarge",
                              mensaje_proveedor="Validado antes de enviar")
    else:
        resultado = _llamar(vigente, Mensaje(
            remitente=vigente.remitente, destinatario=destinatario, asunto=asunto, reply_to=vigente.reply_to,
            plantilla_id=vigente.plantilla_cotizacion_id,
            datos_plantilla={"contacto": actor.nombre, "numero": "COT-PRUEBA", "valida_hasta": pdf.fecha_corta(datos["valida_hasta"]),
                             "comercial": actor.nombre},
            adjunto_nombre=nombre, adjunto=adjunto, bcc=_bcc(vigente, [destinatario]),
        ))
    traduccion = None if resultado.ok else traducir(resultado.codigo_error)
    fila = EnvioCorreoPrueba(
        destinatario=destinatario, asunto=asunto, adjunto_nombre=nombre, adjunto_bytes=len(adjunto),
        estado="ENVIADO" if resultado.ok else "FALLIDO", message_id=resultado.message_id,
        request_id=resultado.request_id, codigo_error=traduccion.codigo if traduccion else None,
        reintentable=traduccion.reintentable if traduccion else False,
        respuesta_proveedor=_respuesta_proveedor(resultado), enviado_por=auditoria.id_de(actor),
    )
    db.add(fila)
    confirmar(db)
    if traduccion is not None:
        raise ErrorNegocio(502, traduccion.codigo, traduccion.mensaje,
                           extra={"reintentable": traduccion.reintentable, "request_id": resultado.request_id})
    return {"estado": "ENVIADO", "destinatario": destinatario, "message_id": resultado.message_id,
            "adjunto_nombre": nombre, "adjunto_bytes": len(adjunto)}


# ---------- Envío de una cotización (B6) ----------


def _contacto_principal(cotizacion: Cotizacion) -> ContactoCliente:
    """H-F4-13: el registro ACTUAL del contacto de la cotización (una corrección en la libreta sirve)."""
    contacto = cotizacion.contacto
    if contacto is None or not contacto.activo or not (contacto.email or "").strip():
        raise ErrorNegocio(422, "CONTACTO_SIN_EMAIL", "El contacto de la cotización no tiene email o está inactivo.")
    return contacto


def _contactos_cc(db: Session, cotizacion: Cotizacion, ids: list[int]) -> list[ContactoCliente]:
    ids = list(dict.fromkeys(ids or []))
    if len(ids) > MAXIMO_CC:
        raise ErrorNegocio(422, "CC_INVALIDO", f"Se pueden copiar como máximo {MAXIMO_CC} contactos")
    salida = []
    for contacto_id in ids:
        contacto = db.get(ContactoCliente, contacto_id)
        if (contacto is None or contacto.cliente_id != cotizacion.cliente_id or not contacto.activo
                or contacto.id == cotizacion.contacto_id):
            raise ErrorNegocio(422, "CC_INVALIDO", "En copia solo van otros contactos activos del mismo cliente")
        if not (contacto.email or "").strip():
            raise ErrorNegocio(422, "CONTACTO_SIN_EMAIL", f"El contacto {contacto.nombre} no tiene email")
        salida.append(contacto)
    return salida


def _validar_envio(cotizacion: Cotizacion, hoy: date) -> None:
    if cotizacion.estado not in ESTADOS_ENVIABLES or not cotizacion.activo:
        raise ErrorNegocio(
            422, "ESTADO_NO_PERMITE_ENVIO", f"Una cotización {cotizacion.estado} no se puede enviar por correo"
        )
    if cotizaciones.vencida(cotizacion, hoy):
        raise ErrorNegocio(422, "COTIZACION_VENCIDA", "La cotización está vencida. Duplíquela para recotizar.")


def preparar_envio(db: Session, usuario: Usuario, cotizacion_id: int) -> dict[str, Any]:
    """Datos para la ventana de confirmación (C5): para, CC posibles, asunto y adjunto."""
    cotizacion = cotizaciones.obtener_cotizacion(db, usuario, cotizacion_id)
    contacto = cotizacion.contacto
    otros = [
        {"id": c.id, "nombre": c.nombre, "email": c.email}
        for c in cotizacion.cliente.contactos
        if c.activo and (c.email or "").strip() and c.id != cotizacion.contacto_id
    ]
    vigente = config_vigente(db)
    nombre = pdf.nombre_archivo(cotizacion.numero, cotizacion.id, cotizacion.cliente.razon_social)
    return {
        "para": {"nombre": contacto.nombre, "email": contacto.email} if contacto else None,
        "cc_posibles": otros,
        "copia_oculta_interna": bool(vigente.bcc),
        "asunto": asunto_de(cotizacion.numero) if cotizacion.numero else None,
        "adjunto_nombre": nombre,
        "correo_estado": vigente.estado,
    }


def enviar_cotizacion(db: Session, actor: Usuario, cotizacion_id: int, cc_ids: list[int]) -> dict[str, Any]:
    hoy = fechas.hoy_ecuador()
    # 1) Validaciones previas (estado, vencida, contacto, CC, configuración).
    cotizacion = cotizaciones.obtener_cotizacion(db, actor, cotizacion_id)  # ajena → 404
    _validar_envio(cotizacion, hoy)
    contacto = _contacto_principal(cotizacion)
    copias = _contactos_cc(db, cotizacion, cc_ids)
    vigente = config_vigente(db)
    if vigente.estado != "HABILITADO":
        raise ErrorNegocio(503, "CORREO_DESHABILITADO", "El envío de correos está deshabilitado o sin configurar.")
    datos = cotizacion.snapshot_emision
    numero = cotizacion.numero
    # 2) PDF desde la foto congelada, FUERA del bloqueo (la misma función del bloque A).
    adjunto = pdf.generar_pdf_de(datos, False)
    nombre = pdf.nombre_archivo(numero, cotizacion.id, datos["cliente"]["razon_social"])
    destinatario = contacto.email.strip()
    cc = [c.email.strip() for c in copias]
    bcc = _bcc(vigente, [destinatario, *cc])
    asunto = asunto_de(numero)
    # 3) SELECT … FOR UPDATE, volver a verificar el estado y enviar.
    bloqueada = db.scalars(
        select(Cotizacion).where(Cotizacion.id == cotizacion.id).with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    _validar_envio(bloqueada, hoy)
    if len(adjunto) > vigente.adjunto_max_bytes:
        resultado = Resultado(ok=False, codigo_error="FailedOperation.AttachContentToolarge",
                              mensaje_proveedor="Validado antes de enviar")
    else:
        resultado = _llamar(vigente, Mensaje(
            remitente=vigente.remitente, destinatario=destinatario, asunto=asunto, reply_to=vigente.reply_to,
            plantilla_id=vigente.plantilla_cotizacion_id,
            datos_plantilla={"contacto": contacto.nombre, "numero": numero,
                             "valida_hasta": pdf.fecha_corta(bloqueada.valida_hasta),
                             "comercial": datos["comercial"]["nombre"]},
            adjunto_nombre=nombre, adjunto=adjunto, cc=tuple(cc), bcc=bcc,
        ))
    # 4) Bitácora y auditoría; confirmar.
    traduccion = None if resultado.ok else traducir(resultado.codigo_error)
    envio = EnvioCorreo(
        cotizacion_id=bloqueada.id, destinatario=destinatario, cc=cc, bcc=bcc[0] if bcc else None, asunto=asunto,
        adjunto_nombre=nombre, adjunto_bytes=len(adjunto), estado="ENVIADO" if resultado.ok else "FALLIDO",
        message_id=resultado.message_id, request_id=resultado.request_id,
        codigo_error=traduccion.codigo if traduccion else None,
        reintentable=traduccion.reintentable if traduccion else False,
        respuesta_proveedor=_respuesta_proveedor(resultado), enviado_por=auditoria.id_de(actor),
    )
    db.add(envio)
    if resultado.ok and bloqueada.estado == "EMITIDA":
        bloqueada.estado = "ENVIADA"
        auditoria.registrar(
            db, actor, "cotizacion", bloqueada.id, "EDITAR", antes={"estado": "EMITIDA"},
            despues={"estado": "ENVIADA", "message_id": resultado.message_id},
            nota=f"ENVIAR {numero} a {destinatario}"[:300],
        )
    if traduccion is not None:  # E3: aviso interno ENVIO_FALLIDO (outbox, en esta misma transacción)
        from app.services import notificaciones

        enviar(db)
        notificaciones.envio_fallido(
            db, "envio_correo", envio.id, "1", f"No se envió {numero}",
            f"El correo de la cotización {numero} a {destinatario} falló: {traduccion.mensaje}",
            auditoria.id_de(actor), f"/app/cotizacion.html?id={bloqueada.id}")
    confirmar(db)
    if traduccion is not None:
        raise ErrorNegocio(502, traduccion.codigo, traduccion.mensaje,
                           extra={"reintentable": traduccion.reintentable, "request_id": resultado.request_id,
                                  "envio_id": envio.id})
    return {"envio": _envio_dict(envio, actor.nombre),
            "cotizacion": cotizaciones.detalle_cotizacion(db, actor, cotizacion_id)}


def _envio_dict(envio: EnvioCorreo, enviado_por: str | None) -> dict[str, Any]:
    mensaje = "Enviado"
    if envio.estado == "FALLIDO":
        crudo = json.loads(envio.respuesta_proveedor) if envio.respuesta_proveedor else {}
        mensaje = traducir(crudo.get("codigo")).mensaje if crudo.get("codigo") else mensaje_de(envio.codigo_error)
    return {
        "id": envio.id,
        "fecha": envio.fecha.isoformat() if envio.fecha else None,
        "enviado_por": enviado_por,
        "destinatario": envio.destinatario,
        "cc": envio.cc or [],
        "bcc": envio.bcc,
        "estado": envio.estado,
        "mensaje": mensaje,
        "message_id": envio.message_id,
        "request_id": envio.request_id,
        "codigo_error": envio.codigo_error,
        "reintentable": envio.reintentable,
        "adjunto_nombre": envio.adjunto_nombre,
        "adjunto_bytes": envio.adjunto_bytes,
    }


def listar_envios(db: Session, usuario: Usuario, cotizacion_id: int) -> list[dict[str, Any]]:
    """GET /v1/cotizaciones/{id}/envios: mismo permiso y alcance que ver la cotización."""
    cotizacion = cotizaciones.obtener_cotizacion(db, usuario, cotizacion_id)
    filas = db.execute(
        select(EnvioCorreo, Usuario.nombre)
        .join(Usuario, Usuario.id == EnvioCorreo.enviado_por)
        .where(EnvioCorreo.cotizacion_id == cotizacion.id)
        .order_by(EnvioCorreo.fecha.desc(), EnvioCorreo.id.desc())
    ).all()
    return [_envio_dict(envio, nombre) for envio, nombre in filas]

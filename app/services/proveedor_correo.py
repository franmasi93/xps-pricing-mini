"""Interfaz del proveedor de correo (B4 de F4) y traducción de errores por CÓDIGO (B9).

Dos implementaciones: TencentSES (services/tencent_ses.py, importa el SDK solo adentro) y la falsa de los tests
(tests/correo_falso.py). Las pruebas nunca llaman a Tencent ni abren conexiones de red.
"""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ConfigProveedor:
    """Configuración descifrada que recibe el proveedor. No se serializa ni se registra."""

    region: str
    endpoint: str
    timeout_s: int
    secret_id: str
    secret_key: str


@dataclass(frozen=True)
class Mensaje:
    remitente: str
    destinatario: str
    asunto: str
    reply_to: str
    plantilla_id: int
    datos_plantilla: dict[str, str]
    adjunto_nombre: str
    adjunto: bytes
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    trigger_type: int = 1  # E1: 0 = marketing (boletines); 1 = inmediato (cotizaciones y avisos)


@dataclass(frozen=True)
class Resultado:
    ok: bool
    message_id: str | None = None
    request_id: str | None = None
    codigo_error: str | None = None  # código del proveedor (o TIMEOUT / SIN_CONEXION)
    mensaje_proveedor: str | None = None


@dataclass(frozen=True)
class Plantilla:
    id: int
    nombre: str
    estado: int  # 0 aprobada · 1 en revisión · 2 rechazada
    motivo: str = ""  # E1: motivo de la revisión de Tencent (ReviewReason)


@dataclass
class ErrorProveedor(Exception):
    """Error de una consulta (salud, plantillas, validación al guardar)."""

    codigo: str
    mensaje: str = ""
    request_id: str | None = None
    extra: dict = field(default_factory=dict)


class ProveedorCorreo(Protocol):
    def enviar(self, mensaje: Mensaje) -> Resultado: ...

    def dominio_verificado(self, dominio: str) -> bool: ...

    def remitente_existe(self, email: str) -> bool: ...

    def estado_plantilla(self, plantilla_id: int) -> int | None: ...

    def plantillas(self) -> list[Plantilla]: ...

    # E1: catálogo de plantillas sincronizado con Tencent y remitentes de masivos.
    def crear_plantilla(self, nombre: str, html: str, texto: str) -> int: ...

    def actualizar_plantilla(self, plantilla_id: int, nombre: str, html: str, texto: str) -> None: ...

    def remitentes(self) -> list[str]: ...

    def crear_remitente(self, email: str, alias: str) -> None: ...


# ---------- B9: traducción por código, nunca por el texto ----------


@dataclass(frozen=True)
class Traduccion:
    codigo: str
    reintentable: bool
    mensaje: str


_SIN_PERMISO = Traduccion(
    "SIN_PERMISO_ADJUNTOS", False, "La cuenta de correo aún no tiene habilitados los adjuntos. Avise al administrador."
)
_GRANDE = Traduccion("ADJUNTO_DEMASIADO_GRANDE", False, "El PDF es demasiado grande para enviarse por correo.")
_NOMBRE = Traduccion("NOMBRE_ADJUNTO_INVALIDO", False, "Nombre de adjunto no aceptado. Avise al administrador.")
_BLOQUEADO = Traduccion(
    "DESTINATARIO_BLOQUEADO",
    False,
    "Este correo rebotó antes o está bloqueado en la cuenta. Verifique la dirección con el cliente; si es correcta, "
    "pida al administrador revisarla en la consola de Tencent.",
)
_BAJA = Traduccion("DESTINATARIO_DADO_DE_BAJA", False, "El destinatario se dio de baja de nuestros correos.")
_EMAIL = Traduccion(
    "EMAIL_INVALIDO", False, "La dirección del contacto no es válida. Corríjala en la libreta de clientes."
)
_PLANTILLA = Traduccion(
    "PLANTILLA_NO_DISPONIBLE", False, "La plantilla de correo no está aprobada o no coincide. Avise al administrador."
)
_REMITENTE = Traduccion("REMITENTE_NO_VALIDO", False, "El remitente no está verificado. Avise al administrador.")
_CUOTA = Traduccion(
    "SIN_CUOTA", False, "Se agotó la cuota o el saldo de la cuenta de correo. Avise al administrador."
)
_LIMITADO = Traduccion("ENVIO_LIMITADO", True, "Envío limitado temporalmente. Intente de nuevo en 10 minutos.")
_HORA = Traduccion("HORA_DESFASADA", True, "La hora del equipo está desfasada. Sincronícela e intente de nuevo.")
_CREDENCIALES = Traduccion(
    "CREDENCIALES_INVALIDAS", False, "Las credenciales de correo no son válidas. Avise al administrador."
)
_NO_DISPONIBLE = Traduccion(
    "PROVEEDOR_NO_DISPONIBLE", True, "El servicio de correo no respondió. Intente de nuevo en unos minutos."
)

TABLA_B9 = {
    "FailedOperation.NoAttachPermission": _SIN_PERMISO,
    "FailedOperation.AttachContentToolarge": _GRANDE,
    "FailedOperation.EmailContentToolarge": _GRANDE,
    "FailedOperation.InvalidAttachName": _NOMBRE,
    "FailedOperation.EmailAddrInBlacklist": _BLOQUEADO,
    "FailedOperation.ReceiverHasUnsubscribed": _BAJA,
    "FailedOperation.IncorrectEmail": _EMAIL,
    "InvalidParameterValue.ReceiverEmailInvalid": _EMAIL,
    "FailedOperation.InvalidTemplateID": _PLANTILLA,
    "FailedOperation.WithOutPermission": _PLANTILLA,
    "FailedOperation.WrongContentJson": _PLANTILLA,
    "FailedOperation.NotAuthenticatedSender": _REMITENTE,
    "FailedOperation.IncorrectSender": _REMITENTE,
    "InvalidParameterValue.NoSuchSender": _REMITENTE,
    "FailedOperation.InsufficientBalance": _CUOTA,
    "FailedOperation.InsufficientQuota": _CUOTA,
    "FailedOperation.ExceedSendLimit": _CUOTA,
    "FailedOperation.FrequencyLimit": _LIMITADO,
    "FailedOperation.TemporaryBlocked": _LIMITADO,
    "FailedOperation.HighRejectionRate": _LIMITADO,
    "AuthFailure.SignatureExpire": _HORA,
    "UnauthorizedOperation": _CREDENCIALES,
    "InternalError": _NO_DISPONIBLE,
    "FailedOperation.ServiceNotAvailable": _NO_DISPONIBLE,
    "TIMEOUT": _NO_DISPONIBLE,
    "SIN_CONEXION": _NO_DISPONIBLE,
    "ClientNetworkError": _NO_DISPONIBLE,  # timeout o sin conexión, según el SDK
    "ServerNetworkError": _NO_DISPONIBLE,
}
# Mensajes de los códigos internos (para la bitácora y la pantalla de envíos).
MENSAJES = {t.codigo: t.mensaje for t in TABLA_B9.values()}


def traducir(codigo: str | None) -> Traduccion:
    """Código de Tencent → código interno, si se puede reintentar y el mensaje en español (B9)."""
    codigo = codigo or "DESCONOCIDO"
    if codigo in TABLA_B9:
        return TABLA_B9[codigo]
    if codigo.startswith(("RequestLimitExceeded", "FailedOperation.RequestLimitExceeded")):
        return _LIMITADO
    if codigo.startswith(("AuthFailure", "UnauthorizedOperation")):
        return _CREDENCIALES
    if codigo.startswith("InternalError"):
        return _NO_DISPONIBLE
    return Traduccion("ERROR_CORREO", False, f"No se pudo enviar el correo. Código: {codigo}.")


def mensaje_de(codigo_interno: str | None) -> str:
    if codigo_interno is None:
        return "Enviado"
    return MENSAJES.get(codigo_interno, f"No se pudo enviar el correo. Código: {codigo_interno}.")

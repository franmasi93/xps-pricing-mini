"""Proveedor de correo real: Tencent Cloud SES (B4 de F4). El SDK se importa SOLO dentro de este módulo, y este
módulo solo se importa al enviar o consultar de verdad (services/correo._proveedor_real). Los tests usan el falso.

Errores: el SDK lanza TencentCloudSDKException con su código (p. ej. FailedOperation.NoAttachPermission) o
ClientNetworkError (timeout, sin conexión). Se traducen por CÓDIGO en services/proveedor_correo.traducir (B9).
"""
import base64
import json

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ses.v20201002 import models, ses_client

from app.services.proveedor_correo import ConfigProveedor, ErrorProveedor, Mensaje, Plantilla, Resultado

TAMANO_PAGINA = 100


class TencentSES:
    def __init__(self, config: ConfigProveedor) -> None:
        perfil_http = HttpProfile(endpoint=config.endpoint, reqTimeout=config.timeout_s)
        self._cliente = ses_client.SesClient(
            credential.Credential(config.secret_id, config.secret_key), config.region, ClientProfile(httpProfile=perfil_http)
        )

    def _llamar(self, metodo: str, solicitud):
        try:
            return getattr(self._cliente, metodo)(solicitud)
        except TencentCloudSDKException as error:
            raise ErrorProveedor(error.get_code() or "ERROR_CORREO", error.get_message() or "",
                                 error.get_request_id()) from None

    def enviar(self, mensaje: Mensaje) -> Resultado:
        solicitud = models.SendEmailRequest()
        solicitud.FromEmailAddress = mensaje.remitente
        solicitud.Destination = [mensaje.destinatario]  # un destinatario por llamada
        if mensaje.cc:
            solicitud.Cc = list(mensaje.cc)
        if mensaje.bcc:
            solicitud.Bcc = list(mensaje.bcc)
        solicitud.ReplyToAddresses = mensaje.reply_to
        solicitud.Subject = mensaje.asunto
        plantilla = models.Template()
        plantilla.TemplateID = mensaje.plantilla_id
        plantilla.TemplateData = json.dumps(mensaje.datos_plantilla, ensure_ascii=False)
        solicitud.Template = plantilla
        if mensaje.adjunto:  # E1: un boletín puede ir sin PDF adjunto
            adjunto = models.Attachment()
            adjunto.FileName = mensaje.adjunto_nombre
            adjunto.Content = base64.b64encode(mensaje.adjunto).decode("ascii")
            solicitud.Attachments = [adjunto]
        solicitud.TriggerType = mensaje.trigger_type
        solicitud.Unsubscribe = "0"  # el enlace de baja es el propio del sistema (E1)
        try:
            respuesta = self._llamar("SendEmail", solicitud)
        except ErrorProveedor as error:
            return Resultado(ok=False, request_id=error.request_id, codigo_error=error.codigo,
                             mensaje_proveedor=error.mensaje)
        return Resultado(ok=True, message_id=respuesta.MessageId, request_id=respuesta.RequestId)

    # ---------- E1: plantillas y remitentes (CreateEmailTemplate, UpdateEmailTemplate, CreateEmailAddress) ----------

    @staticmethod
    def _contenido(html: str, texto: str):
        contenido = models.TemplateContent()
        contenido.Html = base64.b64encode(html.encode("utf-8")).decode("ascii")
        contenido.Text = base64.b64encode(texto.encode("utf-8")).decode("ascii")
        return contenido

    def crear_plantilla(self, nombre: str, html: str, texto: str) -> int:
        solicitud = models.CreateEmailTemplateRequest()
        solicitud.TemplateName = nombre
        solicitud.TemplateContent = self._contenido(html, texto)
        return int(self._llamar("CreateEmailTemplate", solicitud).TemplateID)

    def actualizar_plantilla(self, plantilla_id: int, nombre: str, html: str, texto: str) -> None:
        solicitud = models.UpdateEmailTemplateRequest()
        solicitud.TemplateID = plantilla_id
        solicitud.TemplateName = nombre
        solicitud.TemplateContent = self._contenido(html, texto)
        self._llamar("UpdateEmailTemplate", solicitud)

    def remitentes(self) -> list[str]:
        respuesta = self._llamar("ListEmailAddress", models.ListEmailAddressRequest())
        return [s.EmailAddress for s in respuesta.EmailSenders or [] if s.EmailAddress]

    def crear_remitente(self, email: str, alias: str) -> None:
        solicitud = models.CreateEmailAddressRequest()
        solicitud.EmailAddress = email
        solicitud.EmailSenderName = alias
        self._llamar("CreateEmailAddress", solicitud)

    def dominio_verificado(self, dominio: str) -> bool:
        solicitud = models.GetEmailIdentityRequest()
        solicitud.EmailIdentity = dominio
        return bool(self._llamar("GetEmailIdentity", solicitud).VerifiedForSendingStatus)

    def remitente_existe(self, email: str) -> bool:
        respuesta = self._llamar("ListEmailAddress", models.ListEmailAddressRequest())
        return any((s.EmailAddress or "").lower() == email.lower() for s in respuesta.EmailSenders or [])

    def estado_plantilla(self, plantilla_id: int) -> int | None:
        solicitud = models.GetEmailTemplateRequest()
        solicitud.TemplateID = plantilla_id
        return self._llamar("GetEmailTemplate", solicitud).TemplateStatus

    def plantillas(self) -> list[Plantilla]:
        salida: list[Plantilla] = []
        desplazamiento = 0
        while True:
            solicitud = models.ListEmailTemplatesRequest()
            solicitud.Limit = TAMANO_PAGINA
            solicitud.Offset = desplazamiento
            respuesta = self._llamar("ListEmailTemplates", solicitud)
            pagina = respuesta.TemplatesMetadata or []
            salida += [Plantilla(p.TemplateID, p.TemplateName, p.TemplateStatus, p.ReviewReason or "") for p in pagina]
            desplazamiento += len(pagina)
            if not pagina or desplazamiento >= (respuesta.TotalCount or 0):
                return salida

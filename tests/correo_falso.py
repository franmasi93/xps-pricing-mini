"""Proveedor de correo FALSO para las pruebas de F4 (B4): registra lo que habría enviado y simula cualquier error.

Nunca importa el SDK de Tencent ni abre conexiones de red.
"""
import threading
import time
from dataclasses import dataclass, field

from app.services.proveedor_correo import ConfigProveedor, ErrorProveedor, Mensaje, Plantilla, Resultado


@dataclass
class CorreoFalso:
    dominio_ok: bool = True
    remitente_ok: bool = True
    plantilla_estado: int | None = 0
    lista_plantillas: list[Plantilla] = field(
        default_factory=lambda: [Plantilla(72669, "Cotización", 0), Plantilla(70000, "En revisión", 1),
                                 Plantilla(71000, "Rechazada", 2)]
    )
    error_envio: str | None = None  # código de Tencent a simular en SendEmail
    error_consulta: str | None = None  # código a simular en las consultas (salud, plantillas, validación)
    demora_s: float = 0.0
    errores_por_email: dict[str, str] = field(default_factory=dict)  # E1: código de Tencent a simular por destinatario
    permiso_plantillas: bool = True  # E1: False simula una llave sin CAM para CreateEmailTemplate
    lista_remitentes: list[str] = field(default_factory=lambda: ["pricing@notificaciones.xpress.ec"])
    enviados: list[Mensaje] = field(default_factory=list)
    configs: list[ConfigProveedor] = field(default_factory=list)
    consultas: int = 0
    en_vuelo: int = 0
    max_en_vuelo: int = 0
    _candado: threading.Lock = field(default_factory=threading.Lock)

    def fabrica(self, config: ConfigProveedor) -> "CorreoFalso":
        self.configs.append(config)
        return self

    def _consulta(self) -> None:
        self.consultas += 1
        if self.error_consulta:
            raise ErrorProveedor(self.error_consulta, "simulado", "req-consulta-falso")

    def enviar(self, mensaje: Mensaje) -> Resultado:
        with self._candado:
            self.en_vuelo += 1
            self.max_en_vuelo = max(self.max_en_vuelo, self.en_vuelo)
        try:
            if self.demora_s:
                time.sleep(self.demora_s)
            self.enviados.append(mensaje)
            numero = len(self.enviados)
            codigo = self.errores_por_email.get(mensaje.destinatario)
            if codigo:
                return Resultado(ok=False, request_id=f"req-falso-{numero}", codigo_error=codigo,
                                 mensaje_proveedor="Mensaje crudo del proveedor simulado")
            if self.error_envio:
                return Resultado(ok=False, request_id=f"req-falso-{numero}", codigo_error=self.error_envio,
                                 mensaje_proveedor="Mensaje crudo del proveedor simulado")
            return Resultado(ok=True, message_id=f"msg-falso-{numero:04d}-abcdef", request_id=f"req-falso-{numero}")
        finally:
            with self._candado:
                self.en_vuelo -= 1

    def dominio_verificado(self, dominio: str) -> bool:
        self._consulta()
        return self.dominio_ok

    def remitente_existe(self, email: str) -> bool:
        self._consulta()
        return self.remitente_ok

    def estado_plantilla(self, plantilla_id: int) -> int | None:
        self._consulta()
        return self.plantilla_estado

    def plantillas(self) -> list[Plantilla]:
        self._consulta()
        return list(self.lista_plantillas)

    # ---------- E1: plantillas y remitentes ----------

    def _exigir_permiso(self, accion: str) -> None:
        if not self.permiso_plantillas:
            raise ErrorProveedor("AuthFailure.UnauthorizedOperation", f"you are not authorized to perform operation ({accion})")

    def crear_plantilla(self, nombre: str, html: str, texto: str) -> int:
        self._exigir_permiso("ses:CreateEmailTemplate")
        nuevo = 90000 + len(self.lista_plantillas)
        self.lista_plantillas.append(Plantilla(nuevo, nombre, 1))
        return nuevo

    def actualizar_plantilla(self, plantilla_id: int, nombre: str, html: str, texto: str) -> None:
        self._exigir_permiso("ses:UpdateEmailTemplate")
        self.lista_plantillas = [Plantilla(p.id, nombre, 1) if p.id == plantilla_id else p for p in self.lista_plantillas]

    def aprobar(self, plantilla_id: int) -> None:
        self.lista_plantillas = [Plantilla(p.id, p.nombre, 0) if p.id == plantilla_id else p for p in self.lista_plantillas]

    def remitentes(self) -> list[str]:
        self._consulta()
        return list(self.lista_remitentes)

    def crear_remitente(self, email: str, alias: str) -> None:
        self._exigir_permiso("ses:CreateEmailAddress")
        self.lista_remitentes.append(email)

"""Schemas de entrada de E1 (boletines, plantillas de correo y envíos masivos). Las salidas las arma el service."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.comunes import Entrada, sin_null

UsoPlantilla = Literal["COTIZACION", "BOLETIN", "AVISO"]
DisenoPlantilla = Literal["GENERAL", "PESO_TRAMOS", "VOLUMEN_WM", "UNIDAD_EQUIPO", "TARIFA_PLANA", "AVISO", "LIBRE"]


class PlantillaCrear(Entrada):
    nombre: str = Field(max_length=120)
    uso: UsoPlantilla
    diseno: DisenoPlantilla = "LIBRE"
    evento_o_servicio: str | None = Field(default=None, max_length=40)
    asunto_sugerido: str | None = Field(default=None, max_length=200)
    html: str | None = Field(default=None, max_length=200_000)
    texto: str | None = Field(default=None, max_length=100_000)
    variables_esperadas: list[str] | None = Field(default=None, max_length=40)
    tencent_id: int | None = Field(default=None, gt=0)
    notas: str | None = Field(default=None, max_length=2000)


class PlantillaActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=120)
    uso: UsoPlantilla | None = None
    diseno: DisenoPlantilla | None = None
    evento_o_servicio: str | None = Field(default=None, max_length=40)
    asunto_sugerido: str | None = Field(default=None, max_length=200)
    html: str | None = Field(default=None, max_length=200_000)
    texto: str | None = Field(default=None, max_length=100_000)
    variables_esperadas: list[str] | None = Field(default=None, max_length=40)
    tencent_id: int | None = Field(default=None, gt=0)
    notas: str | None = Field(default=None, max_length=2000)
    activo: bool | None = None

    _sin_null = sin_null("nombre", "uso", "diseno", "activo")


class MasivosActualizar(Entrada):
    remitente: str | None = Field(default=None, max_length=300)
    reply_to: str | None = Field(default=None, max_length=254)
    tamano_lote: int | None = None
    pausa_segundos: int | None = None
    tope_diario: int | None = None
    tope_hora: int | None = None
    reserva_pct: int | None = None
    adjuntar_pdf: bool | None = None
    limite_filas: int | None = None
    texto_legal: str | None = Field(default=None, max_length=1000)
    correos_prueba: str | None = Field(default=None, max_length=1000)
    dias_envio: str | None = Field(default=None, max_length=20)
    hora_desde: int | None = None
    hora_hasta: int | None = None
    calentamiento: bool | None = None
    calentamiento_inicio: int | None = None
    calentamiento_incremento: int | None = None
    calentamiento_desde: date | None = None
    url_publica: str | None = Field(default=None, max_length=300)

    _sin_null = sin_null("tamano_lote", "pausa_segundos", "tope_diario", "tope_hora", "reserva_pct", "adjuntar_pdf",
                         "limite_filas", "dias_envio", "hora_desde", "hora_hasta", "calentamiento",
                         "calentamiento_inicio", "calentamiento_incremento")


class ListaCrear(Entrada):
    nombre: str = Field(max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    tipo: Literal["MANUAL", "FILTRO"]
    filtros: dict[str, Any] | None = None
    contactos: list[int] | None = Field(default=None, max_length=20000)


class ListaActualizar(Entrada):
    nombre: str | None = Field(default=None, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    tipo: Literal["MANUAL", "FILTRO"] | None = None
    filtros: dict[str, Any] | None = None
    contactos: list[int] | None = Field(default=None, max_length=20000)
    activo: bool | None = None

    _sin_null = sin_null("nombre", "tipo", "activo")


class ListaVistaPrevia(Entrada):
    tipo: Literal["MANUAL", "FILTRO"]
    filtros: dict[str, Any] | None = None
    contactos: list[int] | None = Field(default=None, max_length=20000)


class ImportarEmails(Entrada):
    emails: list[str] = Field(max_length=20000)


class BajaCrear(Entrada):
    email: str = Field(max_length=254)


class CampanaCrear(Entrada):
    nombre: str = Field(max_length=120)
    asunto: str | None = Field(default=None, max_length=200)
    texto_intro: str | None = Field(default=None, max_length=2000)
    plantilla_id: int | None = None
    servicios: list[str] | None = Field(default=None, max_length=50)
    tipos_equipo: list[int] | None = Field(default=None, max_length=200)
    tarifas_ids: list[int] | None = Field(default=None, max_length=2000)
    listas_ids: list[int] | None = Field(default=None, max_length=200)
    adjuntar_pdf: bool | None = None


class CampanaActualizar(CampanaCrear):
    nombre: str | None = Field(default=None, max_length=120)


class CampanaEnviar(Entrada):
    destinatarios_confirmados: int
    programada_para: datetime | None = None


class CampanaPrueba(Entrada):
    email: str | None = Field(default=None, max_length=254)

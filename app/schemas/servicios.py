"""Schemas de E0: servicios, sus tramos de peso, tipos de ubicación y formas de cobro."""
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null
from app.schemas.tarifas import Desde


class TramoServicioSalida(CatalogoSalida):
    servicio_id: int
    unidad_peso: str
    desde: Desde
    orden: int


class ServicioSalida(CatalogoSalida):
    codigo: str
    nombre: str
    forma_cobro: str
    tipo_ubicacion_origen: str
    tipo_ubicacion_destino: str
    usa_tipo_equipo: bool
    permite_libras: bool
    orden: int
    descripcion_pdf: str
    etiqueta_transportista: str
    aviso_incoterm: str | None
    tramos: list[TramoServicioSalida]


class ServicioCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=60)
    forma_cobro: str = Field(max_length=20)
    tipo_ubicacion_origen: str = Field(max_length=20)
    tipo_ubicacion_destino: str = Field(max_length=20)
    usa_tipo_equipo: bool | None = None  # sin indicar: el que exige la forma de cobro
    permite_libras: bool = False
    orden: int = Field(default=0, ge=0, le=999)
    descripcion_pdf: str | None = Field(default=None, max_length=120)
    etiqueta_transportista: str | None = Field(default=None, max_length=40)
    aviso_incoterm: str | None = Field(default=None, max_length=200)
    incoterms: list[str] | None = Field(default=None, max_length=50)  # sin indicar: los de un servicio gemelo


class ServicioActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=20)
    nombre: str | None = Field(default=None, max_length=60)
    forma_cobro: str | None = Field(default=None, max_length=20)
    tipo_ubicacion_origen: str | None = Field(default=None, max_length=20)
    tipo_ubicacion_destino: str | None = Field(default=None, max_length=20)
    usa_tipo_equipo: bool | None = None
    permite_libras: bool | None = None
    orden: int | None = Field(default=None, ge=0, le=999)
    descripcion_pdf: str | None = Field(default=None, max_length=120)
    etiqueta_transportista: str | None = Field(default=None, max_length=40)
    aviso_incoterm: str | None = Field(default=None, max_length=200)
    activo: bool | None = None

    _sin_null = sin_null(
        "codigo", "nombre", "forma_cobro", "tipo_ubicacion_origen", "tipo_ubicacion_destino", "usa_tipo_equipo",
        "permite_libras", "orden", "descripcion_pdf", "etiqueta_transportista", "activo",
    )


class TramoServicioCrear(Entrada):
    unidad_peso: str = Field(default="KG", max_length=2)
    desde: Decimal
    orden: int = Field(default=0, ge=0, le=9999)


class TramoServicioActualizar(Entrada):
    unidad_peso: str | None = Field(default=None, max_length=2)
    desde: Decimal | None = None
    orden: int | None = Field(default=None, ge=0, le=9999)
    activo: bool | None = None

    _sin_null = sin_null("unidad_peso", "desde", "orden", "activo")


class TipoUbicacionSalida(CatalogoSalida):
    codigo: str
    nombre: str
    regex_codigo: str | None
    ayuda_codigo: str | None
    prefijo_pais: bool


class TipoUbicacionCrear(Entrada):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=60)
    regex_codigo: str | None = Field(default=None, max_length=500)
    ayuda_codigo: str | None = Field(default=None, max_length=200)
    prefijo_pais: bool = False


class TipoUbicacionActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=20)
    nombre: str | None = Field(default=None, max_length=60)
    regex_codigo: str | None = Field(default=None, max_length=500)
    ayuda_codigo: str | None = Field(default=None, max_length=200)
    prefijo_pais: bool | None = None
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "prefijo_pais", "activo")


class FormaCobroSalida(BaseModel):
    codigo: str
    nombre: str
    descripcion: str
    unidades_tarifa: list[str]
    unidades_recargo: list[str]
    usa_tramos: bool
    usa_tipo_equipo: bool
    admite_libras: bool
    peso_obligatorio: bool
    columnas_tabla: list[str]

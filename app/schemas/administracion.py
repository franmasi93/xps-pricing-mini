"""Schemas de E2: roles editables, permisos, motivos de rechazo, tipos de identificación y textos del PDF."""
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.comunes import CatalogoSalida, Entrada, sin_null
from app.schemas.usuarios import RolSalida


class PermisoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    descripcion: str


class RolDetalle(RolSalida):
    usuarios_activos: int = 0


class RolCrear(Entrada):
    codigo: str = Field(max_length=30)
    nombre: str = Field(max_length=80)
    descripcion: str | None = Field(default=None, max_length=300)
    permisos: list[str] = Field(default_factory=list, max_length=200)


class RolActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=30)
    nombre: str | None = Field(default=None, max_length=80)
    descripcion: str | None = Field(default=None, max_length=300)
    permisos: list[str] | None = Field(default=None, max_length=200)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "permisos", "activo")


class MotivoRechazoSalida(CatalogoSalida):
    codigo: str
    nombre: str
    exige_detalle: bool
    orden: int


class MotivoRechazoCrear(Entrada):
    codigo: str = Field(max_length=30)
    nombre: str = Field(max_length=80)
    exige_detalle: bool = False
    orden: int = Field(default=0, ge=0, le=999)


class MotivoRechazoActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=30)
    nombre: str | None = Field(default=None, max_length=80)
    exige_detalle: bool | None = None
    orden: int | None = Field(default=None, ge=0, le=999)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "exige_detalle", "orden", "activo")


class TipoIdentificacionSalida(CatalogoSalida):
    codigo: str
    nombre: str
    regex: str
    formato: str
    orden: int


class TipoIdentificacionCrear(Entrada):
    codigo: str = Field(max_length=10)
    nombre: str = Field(max_length=60)
    regex: str = Field(max_length=300)
    formato: str = Field(max_length=120)
    orden: int = Field(default=0, ge=0, le=999)


class TipoIdentificacionActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=10)
    nombre: str | None = Field(default=None, max_length=60)
    regex: str | None = Field(default=None, max_length=300)
    formato: str | None = Field(default=None, max_length=120)
    orden: int | None = Field(default=None, ge=0, le=999)
    activo: bool | None = None

    _sin_null = sin_null("codigo", "nombre", "regex", "formato", "orden", "activo")


class TextosPdf(BaseModel):
    aceptacion_titulo: str
    aceptacion_texto: str
    firma_fecha: str
    firma_firma: str
    firma_sello: str
    advertencia_ddp: str
    advertencia_exw: str


class TextosPdfActualizar(Entrada):
    aceptacion_titulo: str | None = Field(default=None, max_length=1000)
    aceptacion_texto: str | None = Field(default=None, max_length=1000)
    firma_fecha: str | None = Field(default=None, max_length=1000)
    firma_firma: str | None = Field(default=None, max_length=1000)
    firma_sello: str | None = Field(default=None, max_length=1000)
    advertencia_ddp: str | None = Field(default=None, max_length=1000)
    advertencia_exw: str | None = Field(default=None, max_length=1000)

    _sin_null = sin_null(
        "aceptacion_titulo", "aceptacion_texto", "firma_fecha", "firma_firma", "firma_sello", "advertencia_ddp",
        "advertencia_exw",
    )

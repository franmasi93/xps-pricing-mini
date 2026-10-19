"""E1-B Perfil comercial, importación y exportación de clientes, historial de correos, eventos de Tencent y preferencias.

Se incluye ANTES del router de clientes: sus rutas fijas (/clientes/importacion/…, /clientes/exportar.xlsx) deben ganarle a
/clientes/{cliente_id}.
- Catálogos del perfil: leer, cualquier usuario habilitado; crear y editar, config.editar (el administrador).
- Importar y descargar la plantilla: cliente.editar. Exportar, interés e historial: cliente.ver (con su alcance).
- Importar a una lista de envío: boletines.listas.gestionar y cliente.editar (porque crea clientes).
- Eventos de Tencent: notificaciones.bitacora.ver. Preferencias de pantalla: cada usuario las suyas.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar
from app.core.rbac import exigir_permiso, get_usuario_habilitado, require_permiso
from app.db import get_db
from app.models import PreferenciaPantalla, Usuario
from app.schemas.comunes import Entrada
from app.services import clientes as servicio_clientes
from app.services import historial_correos, importacion_clientes, perfil_comercial

router = APIRouter(tags=["perfil comercial"])
lector_clientes = require_permiso("cliente.ver")
editor_clientes = require_permiso("cliente.editar")
editor_config = require_permiso("config.editar")
PREFERENCIAS = {"clientes.columnas"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class CatalogoSalida(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tipo: str
    codigo: str
    nombre: str
    orden: int
    fijo: bool
    activo: bool


class CatalogoCrear(Entrada):
    tipo: str = Field(max_length=30)
    codigo: str | None = Field(default=None, max_length=40)
    nombre: str = Field(max_length=120)
    orden: int = Field(default=0, ge=0, le=999)


class CatalogoActualizar(Entrada):
    codigo: str | None = Field(default=None, max_length=40)
    nombre: str | None = Field(default=None, max_length=120)
    orden: int | None = Field(default=None, ge=0, le=999)
    activo: bool | None = None


class ArchivoImportacion(Entrada):
    nombre: str = Field(max_length=200)
    contenido_base64: str = Field(max_length=12_000_000)
    modo: str = "CREAR_Y_ACTUALIZAR"


class Preferencia(Entrada):
    valor: Any


# ---------- Catálogos del perfil ----------


@router.get("/catalogos-perfil", response_model=list[CatalogoSalida], dependencies=[Depends(get_usuario_habilitado)])
def listar_catalogos(tipo: str | None = None, activo: bool | None = None, db: Session = Depends(get_db)):
    return perfil_comercial.listar_catalogo(db, tipo, activo)


@router.post("/catalogos-perfil", response_model=CatalogoSalida, status_code=201)
def crear_catalogo(datos: CatalogoCrear, db: Session = Depends(get_db), actor: Usuario = Depends(editor_config)):
    return perfil_comercial.crear_valor(db, actor, datos.model_dump())


@router.patch("/catalogos-perfil/{item_id}", response_model=CatalogoSalida)
def actualizar_catalogo(item_id: int, datos: CatalogoActualizar, db: Session = Depends(get_db),
                        actor: Usuario = Depends(editor_config)):
    return perfil_comercial.actualizar_valor(db, actor, item_id, datos.model_dump(exclude_unset=True))


# ---------- Importación y exportación ----------


def _archivo(contenido: bytes, nombre: str, tipo: str) -> Response:
    return Response(content=contenido, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/clientes/importacion/plantilla.xlsx", dependencies=[Depends(editor_clientes)])
def descargar_plantilla(db: Session = Depends(get_db)):
    return _archivo(importacion_clientes.plantilla_xlsx(db), "plantilla_importacion_clientes.xlsx", XLSX)


@router.get("/clientes/importacion/plantilla.csv", dependencies=[Depends(editor_clientes)])
def descargar_csv():
    return _archivo(importacion_clientes.plantilla_csv(), "plantilla_importacion_clientes.csv", "text/csv; charset=utf-8")


@router.post("/clientes/importacion/vista-previa")
def vista_previa_importacion(datos: ArchivoImportacion, db: Session = Depends(get_db),
                             actor: Usuario = Depends(editor_clientes)):
    return importacion_clientes.vista_previa(db, actor, datos.nombre, importacion_clientes.decodificar(datos.contenido_base64))


@router.post("/clientes/importacion/confirmar")
def confirmar_importacion(datos: ArchivoImportacion, db: Session = Depends(get_db),
                          actor: Usuario = Depends(editor_clientes)):
    return importacion_clientes.confirmar_importacion(
        db, actor, datos.nombre, importacion_clientes.decodificar(datos.contenido_base64), datos.modo)


@router.post("/boletines/listas/{lista_id}/importar-archivo", tags=["boletines"])
def importar_a_lista(lista_id: int, datos: ArchivoImportacion, db: Session = Depends(get_db),
                     actor: Usuario = Depends(require_permiso("boletines.listas.gestionar"))):
    exigir_permiso(actor, "cliente.editar")
    return importacion_clientes.confirmar_importacion(
        db, actor, datos.nombre, importacion_clientes.decodificar(datos.contenido_base64), datos.modo, lista_id=lista_id)


@router.get("/clientes/exportar.xlsx")
def exportar(
    activo: bool | None = None, comercial: int | None = None, estado: str | None = None, tipo: str | None = None,
    sector: str | None = None, servicio: str | None = None, ruta: str | None = None, etiqueta: str | None = None,
    acepta_promociones: str | None = None, db: Session = Depends(get_db), usuario: Usuario = Depends(lector_clientes),
):
    filtros = {"estado": estado, "tipo": tipo, "sector": sector, "servicio": servicio, "ruta": ruta, "etiqueta": etiqueta,
               "acepta_promociones": acepta_promociones}
    consulta = servicio_clientes.consulta_lista(usuario, activo, comercial, filtros)
    clientes = importacion_clientes.clientes_para_exportar(db, consulta)
    nombre = f"clientes_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return _archivo(importacion_clientes.exportar_xlsx(db, clientes), nombre, XLSX)


# ---------- Interés calculado e historial de correos ----------


@router.get("/clientes/{cliente_id}/interes")
def interes(cliente_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(lector_clientes)):
    cliente = servicio_clientes.obtener_cliente(db, usuario, cliente_id)
    return perfil_comercial.interes(db, cliente.id)


@router.get("/clientes/{cliente_id}/correos")
def correos(cliente_id: int, tipo: str | None = None, estado: str | None = None, db: Session = Depends(get_db),
            usuario: Usuario = Depends(lector_clientes)):
    cliente = servicio_clientes.obtener_cliente(db, usuario, cliente_id)
    return historial_correos.historial_cliente(db, cliente, tipo, estado)


@router.get("/clientes/{cliente_id}/correos/{tipo}/{envio_id}")
def vista_correo(cliente_id: int, tipo: str, envio_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(lector_clientes)):
    if tipo not in historial_correos.TIPOS:
        raise ErrorNegocio(422, "TIPO_INVALIDO", "El tipo es COTIZACION, BOLETIN o AVISO")
    cliente = servicio_clientes.obtener_cliente(db, usuario, cliente_id)
    return historial_correos.vista_previa(db, cliente, tipo, envio_id)


@router.get("/notificaciones/eventos-tencent", tags=["notificaciones"],
            dependencies=[Depends(require_permiso("notificaciones.bitacora.ver"))])
def eventos_tencent(origen: str | None = None, db: Session = Depends(get_db)):
    return [{"id": e.id, "recibido_en": e.recibido_en, "message_id": e.message_id, "evento": e.evento, "email": e.email,
             "origen": e.origen, "origen_id": e.origen_id} for e in historial_correos.eventos(db, origen)]


# ---------- Preferencias de pantalla ----------


def _clave(clave: str) -> str:
    if clave not in PREFERENCIAS:
        raise ErrorNegocio(404, "PREFERENCIA_INEXISTENTE", "Preferencia desconocida")
    return clave


@router.get("/preferencias/{clave}")
def leer_preferencia(clave: str, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_habilitado)):
    fila = db.get(PreferenciaPantalla, (usuario.id, _clave(clave)))
    return {"clave": clave, "valor": fila.valor if fila else None}


@router.put("/preferencias/{clave}")
def guardar_preferencia(clave: str, datos: Preferencia, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(get_usuario_habilitado)):
    if not isinstance(datos.valor, list) or len(datos.valor) > 30 or not all(isinstance(v, str) and len(v) <= 40 for v in datos.valor):
        raise ErrorNegocio(422, "PREFERENCIA_INVALIDA", "La preferencia es una lista de hasta 30 nombres de columna")
    fila = db.get(PreferenciaPantalla, (usuario.id, _clave(clave)))
    if fila is None:
        db.add(PreferenciaPantalla(usuario_id=usuario.id, clave=clave, valor=datos.valor))
    else:
        fila.valor = datos.valor
    confirmar(db)
    return {"clave": clave, "valor": datos.valor}

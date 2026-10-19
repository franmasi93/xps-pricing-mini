"""E1 Boletines: listas, bajas, campañas, plantillas de correo y envíos masivos.

Permisos: boletines.ver (los 4 roles) lee; boletines.listas.gestionar edita listas y bajas; boletines.campanas.gestionar
crea borradores y envía pruebas; boletines.campanas.enviar envía, programa, pausa, reanuda y cancela. Las plantillas y la
configuración de envíos masivos son solo del administrador (usuario.admin), como la configuración de correo de F4.
"""
from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.rbac import require_permiso
from app.db import get_db
from app.models import Usuario
from app.schemas.boletines import (
    BajaCrear,
    CampanaActualizar,
    CampanaCrear,
    CampanaEnviar,
    CampanaPrueba,
    ImportarEmails,
    ListaActualizar,
    ListaCrear,
    ListaVistaPrevia,
    MasivosActualizar,
    PlantillaActualizar,
    PlantillaCrear,
)
from app.services import boletines, campanas, masivos, plantillas_correo

router = APIRouter()

lector = require_permiso("boletines.ver")
gestor_listas = require_permiso("boletines.listas.gestionar")
gestor_campanas = require_permiso("boletines.campanas.gestionar")
emisor = require_permiso("boletines.campanas.enviar")
admin = require_permiso("usuario.admin")


# ---------- Listas ----------


def _lista(db: Session, lista) -> dict:
    miembros = boletines.contactos_de(db, lista)
    return {"id": lista.id, "nombre": lista.nombre, "descripcion": lista.descripcion, "tipo": lista.tipo,
            "filtros": lista.filtros, "activo": lista.activo, "contactos": [c.id for c in lista.miembros],
            "miembros": len(miembros), "creado_en": lista.creado_en.isoformat()}


@router.get("/boletines/listas", tags=["boletines"])
def listar_listas(activo: bool | None = None, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return [_lista(db, l) for l in boletines.listar_listas(db, activo)]


@router.get("/boletines/listas/{lista_id}", tags=["boletines"])
def detalle_lista(lista_id: int, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    lista = boletines.obtener_lista(db, lista_id)
    return _lista(db, lista) | {"resumen": boletines.resumen_miembros(db, boletines.contactos_de(db, lista))}


@router.post("/boletines/listas", status_code=status.HTTP_201_CREATED, tags=["boletines"])
def crear_lista(datos: ListaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_listas)):
    return _lista(db, boletines.crear_lista(db, actor, datos.model_dump()))


@router.patch("/boletines/listas/{lista_id}", tags=["boletines"])
def actualizar_lista(lista_id: int, datos: ListaActualizar, db: Session = Depends(get_db),
                     actor: Usuario = Depends(gestor_listas)):
    return _lista(db, boletines.actualizar_lista(db, actor, lista_id, datos.model_dump(exclude_unset=True)))


@router.post("/boletines/listas/{lista_id}/importar", tags=["boletines"])
def importar(lista_id: int, datos: ImportarEmails, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_listas)):
    return boletines.importar_emails(db, actor, lista_id, datos.emails)


@router.post("/boletines/listas/vista-previa", tags=["boletines"])
def vista_previa_lista(datos: ListaVistaPrevia, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return boletines.vista_previa(db, datos.tipo, datos.filtros, datos.contactos)


@router.get("/boletines/contactos", tags=["boletines"])
def buscar_contactos(q: str = "", db: Session = Depends(get_db), _: Usuario = Depends(gestor_listas)):
    return boletines.buscar_contactos(db, q)


@router.get("/boletines/filtros", tags=["boletines"])
def opciones_filtro(db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return boletines.ciudades_y_paises(db)


# ---------- Bajas ----------


def _baja(baja) -> dict:
    return {"id": baja.id, "email": baja.email, "motivo": baja.motivo, "fecha": baja.fecha.isoformat(),
            "revertida": baja.revertida, "revertida_en": baja.revertida_en.isoformat() if baja.revertida_en else None,
            "campana_id": baja.campana_id}


@router.get("/boletines/bajas", tags=["boletines"])
def listar_bajas(q: str | None = None, revertida: bool | None = None, db: Session = Depends(get_db),
                 _: Usuario = Depends(lector)):
    return [_baja(b) for b in boletines.listar_bajas(db, q, revertida)]


@router.post("/boletines/bajas", status_code=status.HTTP_201_CREATED, tags=["boletines"])
def crear_baja(datos: BajaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_listas)):
    baja = boletines.registrar_baja(db, datos.email, "MANUAL", actor)
    db.commit()
    return _baja(baja)


@router.post("/boletines/bajas/{baja_id}/revertir", tags=["boletines"])
def revertir_baja(baja_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_listas)):
    return _baja(boletines.revertir_baja(db, actor, baja_id))


# ---------- Campañas ----------


@router.get("/boletines/campanas", tags=["boletines"])
def listar_campanas(estado: str | None = None, servicio: str | None = None, desde: date | None = None,
                    hasta: date | None = None, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return campanas.listar(db, estado, servicio, desde, hasta)


@router.get("/boletines/tarifas", tags=["boletines"])
def tarifas_disponibles(fecha: date | None = None, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return campanas.tarifas_disponibles(db, fecha)


@router.post("/boletines/campanas", status_code=status.HTTP_201_CREATED, tags=["boletines"])
def crear_campana(datos: CampanaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_campanas)):
    return campanas.presentar(campanas.crear(db, actor, datos.model_dump(exclude_none=True)), db)


@router.get("/boletines/campanas/{campana_id}", tags=["boletines"])
def detalle_campana(campana_id: int, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return campanas.presentar(campanas.obtener(db, campana_id), db)


@router.patch("/boletines/campanas/{campana_id}", tags=["boletines"])
def actualizar_campana(campana_id: int, datos: CampanaActualizar, db: Session = Depends(get_db),
                       actor: Usuario = Depends(gestor_campanas)):
    return campanas.presentar(campanas.actualizar(db, actor, campana_id, datos.model_dump(exclude_unset=True)), db)


@router.delete("/boletines/campanas/{campana_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["boletines"])
def descartar_campana(campana_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(gestor_campanas)):
    campanas.descartar(db, actor, campana_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/boletines/campanas/{campana_id}/conteo", tags=["boletines"])
def conteo(campana_id: int, db: Session = Depends(get_db), _: Usuario = Depends(lector)):
    return campanas.conteo(db, campana_id)


@router.get("/boletines/campanas/{campana_id}/vista-previa", tags=["boletines"])
def vista_previa(campana_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(lector)):
    return campanas.vista_previa(db, actor, campana_id)


@router.post("/boletines/campanas/{campana_id}/prueba", tags=["boletines"])
def enviar_prueba(campana_id: int, datos: CampanaPrueba, db: Session = Depends(get_db),
                  actor: Usuario = Depends(gestor_campanas)):
    return campanas.enviar_prueba(db, actor, campana_id, datos.email)


@router.post("/boletines/campanas/{campana_id}/enviar", tags=["boletines"])
def enviar_campana(campana_id: int, datos: CampanaEnviar, db: Session = Depends(get_db), actor: Usuario = Depends(emisor)):
    return campanas.enviar_o_programar(db, actor, campana_id, datos.model_dump())


@router.post("/boletines/campanas/{campana_id}/{accion}", tags=["boletines"])
def accion_campana(campana_id: int, accion: str, db: Session = Depends(get_db), actor: Usuario = Depends(emisor)):
    if accion not in ("pausar", "reanudar", "cancelar"):
        from app.core.errors import ErrorNegocio

        raise ErrorNegocio(404, "ACCION_INVALIDA", "Acción no encontrada")
    return campanas.presentar(campanas.cambiar_estado(db, actor, campana_id, accion), db)


@router.get("/boletines/campanas/{campana_id}/destinatarios", tags=["boletines"])
def destinatarios(campana_id: int, estado: str | None = None, q: str | None = None, db: Session = Depends(get_db),
                  _: Usuario = Depends(lector)):
    return campanas.destinatarios(db, campana_id, estado, q)


# ---------- Plantillas de correo (solo admin) ----------


def _plantilla(p, avisos: list[str] | None = None) -> dict:
    datos = {campo: getattr(p, campo) for campo in (
        "id", "nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido", "html", "texto", "variables_esperadas",
        "tencent_id", "estado_tencent", "motivo_tencent", "notas", "activo")}
    datos["sincronizada_en"] = p.sincronizada_en.isoformat() if p.sincronizada_en else None
    return datos | ({"avisos": avisos} if avisos is not None else {})


@router.get("/plantillas-correo", tags=["correo"])
def listar_plantillas(uso: str | None = None, activo: bool | None = None, db: Session = Depends(get_db),
                      _: Usuario = Depends(lector)):
    return [_plantilla(p) for p in plantillas_correo.listar(db, uso, activo)]


@router.post("/plantillas-correo", status_code=status.HTTP_201_CREATED, tags=["correo"])
def crear_plantilla(datos: PlantillaCrear, db: Session = Depends(get_db), actor: Usuario = Depends(admin)):
    plantilla, avisos = plantillas_correo.crear(db, actor, datos.model_dump())
    return _plantilla(plantilla, avisos)


@router.patch("/plantillas-correo/{plantilla_id}", tags=["correo"])
def actualizar_plantilla(plantilla_id: int, datos: PlantillaActualizar, db: Session = Depends(get_db),
                         actor: Usuario = Depends(admin)):
    plantilla, avisos = plantillas_correo.actualizar(db, actor, plantilla_id, datos.model_dump(exclude_unset=True))
    return _plantilla(plantilla, avisos)


@router.post("/plantillas-correo/sincronizar", tags=["correo"])
def sincronizar(db: Session = Depends(get_db), actor: Usuario = Depends(admin)):
    return plantillas_correo.sincronizar(db, actor)


# ---------- Envíos masivos (solo admin) ----------


@router.get("/correo/masivos", tags=["correo"])
def leer_masivos(db: Session = Depends(get_db), _: Usuario = Depends(admin)):
    return masivos.presentar(db)


@router.put("/correo/masivos", tags=["correo"])
def guardar_masivos(datos: MasivosActualizar, db: Session = Depends(get_db), actor: Usuario = Depends(admin)):
    return masivos.actualizar(db, actor, datos.model_dump(exclude_unset=True))

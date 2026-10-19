"""E1 Catálogo de plantillas de correo, sincronizado con Tencent SES (usos COTIZACION, BOLETIN y AVISO).

- Solo el administrador lo edita, con auditoría.
- Al crear o editar con HTML, la plantilla se crea o actualiza en Tencent por API (CreateEmailTemplate o
  UpdateEmailTemplate) y se guarda su ID. Editar en Tencent la devuelve a revisión. Si la llave no tiene permiso
  (AuthFailure / UnauthorizedOperation), se guarda igual y el ID se registra a mano después (aviso en la respuesta).
- En Tencent el nombre lleva el prefijo "XPS-". La plantilla de cotizaciones de F4 (config_correo) nunca se edita desde
  aquí: solo se importa y se sincroniza su estado.
- Sincronizar: trae el estado y el motivo de cada plantilla con ID, e importa las de la cuenta que no estén en el
  catálogo (inactivas, salvo la de cotizaciones de F4).
- Una campaña o un aviso solo usa una plantilla activa, APROBADA y con todas sus variables con valor.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import PlantillaCorreo, Usuario
from app.models.boletines import DISENOS_PLANTILLA, USOS_PLANTILLA
from app.services import auditoria, correo, plantillas_diseno
from app.services.proveedor_correo import ErrorProveedor, traducir

PREFIJO = "XPS-"
ESTADO_POR_CODIGO = {0: "APROBADA", 1: "EN_REVISION", 2: "RECHAZADA"}
CAMPOS = (
    "nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido", "html", "texto", "variables_esperadas",
    "tencent_id", "estado_tencent", "motivo_tencent", "notas", "activo",
)
AVISO_REVISION = "Editar el contenido en Tencent devuelve la plantilla a revisión: no se podrá usar hasta que Tencent la apruebe de nuevo."


def _foto(plantilla: PlantillaCorreo) -> dict[str, Any]:
    foto = {campo: getattr(plantilla, campo) for campo in CAMPOS}
    foto["html"] = f"({len(plantilla.html)} caracteres)" if plantilla.html else None  # el HTML completo no va a la auditoría
    foto["texto"] = f"({len(plantilla.texto)} caracteres)" if plantilla.texto else None
    return foto


def listar(db: Session, uso: str | None = None, activo: bool | None = None) -> list[PlantillaCorreo]:
    consulta = select(PlantillaCorreo)
    if uso is not None:
        consulta = consulta.where(PlantillaCorreo.uso == uso)
    if activo is not None:
        consulta = consulta.where(PlantillaCorreo.activo.is_(activo))
    return list(db.scalars(consulta.order_by(PlantillaCorreo.uso, PlantillaCorreo.nombre)))


def obtener(db: Session, plantilla_id: int) -> PlantillaCorreo:
    plantilla = db.get(PlantillaCorreo, plantilla_id)
    if plantilla is None:
        raise ErrorNegocio(404, "PLANTILLA_NO_ENCONTRADA", "Plantilla no encontrada")
    return plantilla


def _es_cotizacion_f4(db: Session, plantilla: PlantillaCorreo) -> bool:
    return plantilla.tencent_id is not None and plantilla.tencent_id == correo.config_vigente(db).plantilla_cotizacion_id


def _proveedor(db: Session):
    vigente = correo.config_vigente(db)
    if not vigente.configurado:
        return None
    return correo.fabrica_proveedor(vigente.proveedor())


def _sin_permiso(error: ErrorProveedor) -> bool:
    return error.codigo.startswith(("AuthFailure", "UnauthorizedOperation"))


def _validar(datos: dict[str, Any]) -> dict[str, Any]:
    datos["nombre"] = " ".join((datos.get("nombre") or "").split())
    if not datos["nombre"]:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
    if datos["uso"] not in USOS_PLANTILLA:
        raise ErrorNegocio(422, "PLANTILLA_INVALIDA", "El uso debe ser COTIZACION, BOLETIN o AVISO")
    if datos["diseno"] not in DISENOS_PLANTILLA:
        raise ErrorNegocio(422, "PLANTILLA_INVALIDA", f"Diseño desconocido: {datos['diseno']}")
    html = datos.get("html") or None
    datos["html"] = html
    if html:
        datos["variables_esperadas"] = plantillas_diseno.variables_de(html)
        datos["texto"] = (datos.get("texto") or "").strip() or plantillas_diseno.texto_plano(html)
    else:
        datos["variables_esperadas"] = [v.strip() for v in datos.get("variables_esperadas") or [] if v.strip()]
    if len(datos["variables_esperadas"]) > plantillas_diseno.MAXIMO_VARIABLES:
        raise ErrorNegocio(
            422, "PLANTILLA_INVALIDA",
            f"La plantilla tiene {len(datos['variables_esperadas'])} variables; el máximo es {plantillas_diseno.MAXIMO_VARIABLES}",
        )
    for campo in ("evento_o_servicio", "asunto_sugerido", "notas"):
        datos[campo] = (datos.get(campo) or "").strip() or None
    return datos


def _nombre_tencent(nombre: str) -> str:
    return nombre if nombre.startswith(PREFIJO) else PREFIJO + nombre


def _publicar(db: Session, plantilla: PlantillaCorreo, avisos: list[str]) -> None:
    """Crea o actualiza la plantilla en Tencent con su HTML. Sin permiso o sin llaves: queda como estaba y avisa."""
    if not plantilla.html:
        return
    proveedor = _proveedor(db)
    if proveedor is None:
        avisos.append("El correo no está configurado: la plantilla no se cargó en Tencent.")
        return
    nombre = _nombre_tencent(plantilla.nombre)
    try:
        if plantilla.tencent_id is None:
            plantilla.tencent_id = proveedor.crear_plantilla(nombre, plantilla.html, plantilla.texto or "")
        else:
            proveedor.actualizar_plantilla(plantilla.tencent_id, nombre, plantilla.html, plantilla.texto or "")
        plantilla.estado_tencent = "EN_REVISION"
        plantilla.motivo_tencent = None
        avisos.append("Plantilla enviada a Tencent: queda en revisión hasta que Tencent la apruebe.")
    except ErrorProveedor as error:
        if _sin_permiso(error):
            avisos.append(
                "La llave de Tencent no tiene permiso para crear o editar plantillas por API. Créela en la consola de "
                "Tencent con este HTML (guía en docs/extensiones/plantillas/) y registre aquí su ID."
            )
            return
        traduccion = traducir(error.codigo)
        raise ErrorNegocio(422, traduccion.codigo, f"Tencent rechazó la plantilla: {traduccion.mensaje}") from None


def crear(db: Session, actor: Usuario, datos: dict[str, Any]) -> tuple[PlantillaCorreo, list[str]]:
    datos = _validar(dict(datos))
    if db.scalar(select(PlantillaCorreo.id).where(func.lower(PlantillaCorreo.nombre) == datos["nombre"].lower())):
        raise ErrorNegocio(409, "PLANTILLA_DUPLICADA", "Ya existe una plantilla con ese nombre")
    tencent_id = datos.get("tencent_id")
    plantilla = PlantillaCorreo(
        **{campo: datos.get(campo) for campo in ("nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido",
                                                  "html", "texto", "variables_esperadas", "notas")},
        tencent_id=tencent_id, estado_tencent="EN_REVISION" if tencent_id else "SIN_REGISTRAR",
        creado_por=auditoria.id_de(actor),
    )
    db.add(plantilla)
    avisos: list[str] = []
    if tencent_id is None:
        _publicar(db, plantilla, avisos)
    enviar(db)
    auditoria.registrar(db, actor, "plantilla_correo", plantilla.id, "CREAR", despues=_foto(plantilla))
    confirmar(db)
    if plantilla.tencent_id:
        sincronizar(db, actor, silenciosa=True)
    return obtener(db, plantilla.id), avisos


def actualizar(db: Session, actor: Usuario, plantilla_id: int, cambios: dict[str, Any]) -> tuple[PlantillaCorreo, list[str]]:
    plantilla = obtener(db, plantilla_id)
    antes = _foto(plantilla)
    contenido_cambia = any(campo in cambios and cambios[campo] != getattr(plantilla, campo) for campo in ("html", "texto"))
    if contenido_cambia and _es_cotizacion_f4(db, plantilla):
        raise ErrorNegocio(409, "PLANTILLA_PROTEGIDA", "La plantilla de cotizaciones de F4 no se edita desde el sistema")
    final = _validar({campo: getattr(plantilla, campo) for campo in CAMPOS} | cambios)
    if final["nombre"].lower() != plantilla.nombre.lower() and db.scalar(
        select(PlantillaCorreo.id).where(func.lower(PlantillaCorreo.nombre) == final["nombre"].lower())
    ):
        raise ErrorNegocio(409, "PLANTILLA_DUPLICADA", "Ya existe una plantilla con ese nombre")
    avisos: list[str] = []
    with db.no_autoflush:
        for campo in ("nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido", "html", "texto",
                      "variables_esperadas", "notas"):
            setattr(plantilla, campo, final[campo])
        if "activo" in cambios:
            plantilla.activo = bool(cambios["activo"])
        if "tencent_id" in cambios and cambios["tencent_id"] != plantilla.tencent_id:
            plantilla.tencent_id = cambios["tencent_id"]
            plantilla.estado_tencent = "EN_REVISION" if plantilla.tencent_id else "SIN_REGISTRAR"
            plantilla.motivo_tencent = None
        elif contenido_cambia:
            _publicar(db, plantilla, avisos)
        despues = _foto(plantilla)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "plantilla_correo", plantilla.id, accion, antes=antes, despues=despues)
    confirmar(db)
    if "tencent_id" in cambios and plantilla.tencent_id:
        sincronizar(db, actor, silenciosa=True)
    return obtener(db, plantilla.id), avisos


def _uso_importada(nombre: str, tencent_id: int, cotizacion_id: int) -> tuple[str, str, bool]:
    if tencent_id == cotizacion_id:
        return "COTIZACION", "LIBRE", True
    minusculas = nombre.lower()
    if "boletin" in minusculas:
        return "BOLETIN", "GENERAL", False
    if "aviso" in minusculas or "resumen" in minusculas:
        return "AVISO", "AVISO", False
    return "COTIZACION", "LIBRE", False


def _traer_contenido(proveedor, plantilla: PlantillaCorreo) -> None:
    """El HTML y el texto reales de Tencent (GetEmailTemplate): sus variables mandan sobre las registradas."""
    try:
        html, texto, _ = proveedor.contenido_plantilla(plantilla.tencent_id)
    except (ErrorProveedor, AttributeError):
        return
    if html:
        plantilla.html, plantilla.texto = html, texto or plantillas_diseno.texto_plano(html)
        plantilla.variables_esperadas = plantillas_diseno.variables_de(html)


def sincronizar(db: Session, actor: Usuario | None, *, silenciosa: bool = False) -> dict[str, Any]:
    """Trae de Tencent el estado y el motivo de cada plantilla, e importa las que falten en el catálogo."""
    proveedor = _proveedor(db)
    if proveedor is None:
        if silenciosa:
            return {"sincronizadas": 0, "importadas": 0, "error": "CORREO_NO_CONFIGURADO"}
        raise ErrorNegocio(503, "CORREO_NO_CONFIGURADO", "El correo no está configurado: cargue las llaves en Configuración.")
    try:
        remotas = {p.id: p for p in proveedor.plantillas()}
    except ErrorProveedor as error:
        if silenciosa:
            return {"sincronizadas": 0, "importadas": 0, "error": error.codigo}
        traduccion = traducir(error.codigo)
        raise ErrorNegocio(422, traduccion.codigo, traduccion.mensaje) from None
    ahora = datetime.now(timezone.utc)
    cotizacion_id = correo.config_vigente(db).plantilla_cotizacion_id
    sincronizadas = importadas = 0
    por_id = {p.tencent_id: p for p in db.scalars(select(PlantillaCorreo).where(PlantillaCorreo.tencent_id.is_not(None)))}
    por_nombre = {p.nombre.lower(): p for p in db.scalars(select(PlantillaCorreo).where(PlantillaCorreo.tencent_id.is_(None)))}
    for tencent_id, remota in remotas.items():
        local = por_id.get(tencent_id) or por_nombre.get((remota.nombre or "").lower())
        estado = ESTADO_POR_CODIGO.get(remota.estado, "RECHAZADA")
        if local is None:
            uso, diseno, activa = _uso_importada(remota.nombre or "", tencent_id, cotizacion_id)
            nombre = remota.nombre or f"Plantilla {tencent_id}"
            if db.scalar(select(PlantillaCorreo.id).where(func.lower(PlantillaCorreo.nombre) == nombre.lower())):
                nombre = f"{nombre} ({tencent_id})"
            nueva = PlantillaCorreo(nombre=nombre, uso=uso, diseno=diseno, tencent_id=tencent_id, estado_tencent=estado,
                                    motivo_tencent=remota.motivo or None, sincronizada_en=ahora, activo=activa,
                                    notas="Importada desde la cuenta de Tencent")
            _traer_contenido(proveedor, nueva)
            db.add(nueva)
            importadas += 1
            continue
        local.tencent_id = tencent_id
        local.estado_tencent = estado
        local.motivo_tencent = remota.motivo or None
        local.sincronizada_en = ahora
        _traer_contenido(proveedor, local)
        sincronizadas += 1
    for local in por_id.values():
        if local.tencent_id not in remotas:
            local.estado_tencent = "NO_ENCONTRADA"
            local.sincronizada_en = ahora
    from app.services import masivos

    masivos.config(db).ultima_sincronizacion = ahora
    if actor is not None and (importadas or sincronizadas):
        auditoria.registrar(db, actor, "plantilla_correo", "sincronizacion", "EDITAR",
                            despues={"sincronizadas": sincronizadas, "importadas": importadas}, nota="SINCRONIZAR CON TENCENT")
    confirmar(db)
    return {"sincronizadas": sincronizadas, "importadas": importadas, "error": None}


def plantilla_utilizable(db: Session, plantilla_id: int | None, uso: str) -> PlantillaCorreo:
    """Activa, del uso indicado, aprobada en Tencent y con ID."""
    if plantilla_id is None:
        raise ErrorNegocio(422, "PLANTILLA_REQUERIDA", "Elija una plantilla")
    plantilla = obtener(db, plantilla_id)
    if plantilla.uso != uso:
        raise ErrorNegocio(422, "PLANTILLA_NO_DISPONIBLE", f"La plantilla «{plantilla.nombre}» no es de uso {uso}")
    if not plantilla.activo:
        raise ErrorNegocio(422, "PLANTILLA_NO_DISPONIBLE", f"La plantilla «{plantilla.nombre}» está inactiva")
    if plantilla.estado_tencent != "APROBADA" or plantilla.tencent_id is None:
        raise ErrorNegocio(
            422, "PLANTILLA_NO_DISPONIBLE",
            f"La plantilla «{plantilla.nombre}» no está aprobada en Tencent (estado: {plantilla.estado_tencent})",
        )
    return plantilla


def exigir_variables(plantilla: PlantillaCorreo, datos: dict[str, str], opcionales: set[str] = frozenset()) -> None:
    """Todas las variables esperadas deben tener valor (las opcionales pueden ir vacías, como las filas sin usar)."""
    faltan = [v for v in plantilla.variables_esperadas if v not in datos or (not str(datos[v]).strip() and v not in opcionales)]
    if faltan:
        raise ErrorNegocio(
            422, "VARIABLES_SIN_VALOR",
            f"La plantilla «{plantilla.nombre}» espera variables sin valor: {', '.join(faltan)}",
            extra={"variables": faltan},
        )

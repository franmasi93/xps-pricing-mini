"""E0 Servicios editables: la fuente única de servicios, sus tramos de peso y los tipos de ubicación.

- `servicios_activos(db)` es la ÚNICA fuente de servicios para tarifas, recargos, cotizador, boletines (E1) y
  avisos (E3): activos y ordenados.
- Un servicio usado (tarifas, recargos, cotizaciones o tipos de equipo) no cambia de código, forma de cobro ni
  tipos de ubicación, y no se borra: se desactiva. Lo histórico queda intacto.
- Un tramo usado por una tarifa no se borra ni cambia su "desde": se desactiva.
- Auditoría en la misma transacción (services/auditoria). El borrado de algo nunca usado se audita como
  DESACTIVAR con la nota "BORRADO".
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.db import engine
from app.models import (
    Cotizacion,
    Incoterm,
    Puerto,
    Recargo,
    Servicio,
    ServicioTramo,
    Tarifa,
    TipoEquipo,
    TipoUbicacion,
    TramoAereo,
    Usuario,
)
from app.services import auditoria, formas_cobro

PATRON_CODIGO = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
PATRON_CODIGO_LIBRE = re.compile(r"^[A-Z0-9]{2,10}$")  # código de un puerto cuyo tipo no tiene regex
UNIDADES_PESO = ("KG", "LB")
CAMPOS_SERVICIO = (
    "codigo",
    "nombre",
    "forma_cobro",
    "tipo_ubicacion_origen",
    "tipo_ubicacion_destino",
    "usa_tipo_equipo",
    "permite_libras",
    "orden",
    "descripcion_pdf",
    "etiqueta_transportista",
    "aviso_incoterm",
    "activo",
)
CAMPOS_TRAMO = ("servicio_id", "unidad_peso", "desde", "orden", "activo")
CAMPOS_UBICACION = ("codigo", "nombre", "regex_codigo", "ayuda_codigo", "prefijo_pais", "activo")


def _texto(valor: str | None, campo: str, maximo: int, *, obligatorio: bool = True) -> str | None:
    valor = " ".join((valor or "").split())
    if not valor:
        if obligatorio:
            raise ErrorNegocio(422, "NOMBRE_INVALIDO", f"{campo} no puede estar vacío")
        return None
    if len(valor) > maximo:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", f"{campo} admite como máximo {maximo} caracteres")
    return valor


def _codigo(codigo: str, que: str) -> str:
    codigo = "".join((codigo or "").split()).upper()
    if not PATRON_CODIGO.match(codigo):
        raise ErrorNegocio(
            422, "CODIGO_INVALIDO", f"El código {que} es de 2 a 10 letras, números o _, y empieza con una letra"
        )
    return codigo


def _foto(objeto, campos) -> dict[str, Any]:
    return {campo: getattr(objeto, campo) for campo in campos}


# ---------- Fuente única ----------


def servicios_activos(db: Session) -> list[Servicio]:
    """Los servicios que se ofrecen para tarifas, recargos y cotizaciones nuevas, en el orden de la pantalla."""
    return list(
        db.scalars(
            select(Servicio).where(Servicio.activo.is_(True)).order_by(Servicio.orden, Servicio.nombre, Servicio.id)
        )
    )


def listar_servicios(db: Session, activo: bool | None = None) -> list[Servicio]:
    consulta = select(Servicio).options(selectinload(Servicio.tramos))
    if activo is not None:
        consulta = consulta.where(Servicio.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Servicio.orden, Servicio.nombre, Servicio.id)))


def obtener_servicio(db: Session, servicio_id: int) -> Servicio:
    servicio = db.get(Servicio, servicio_id)
    if servicio is None:
        raise ErrorNegocio(404, "SERVICIO_NO_ENCONTRADO", "Servicio no encontrado")
    return servicio


def servicio_por_codigo(db: Session, codigo: str | None) -> Servicio | None:
    if codigo is None:
        return None
    return db.scalars(select(Servicio).where(Servicio.codigo == codigo)).one_or_none()


def servicio_utilizable(db: Session, codigo: str | None, exigir_activo: bool) -> Servicio:
    """El servicio de una tarifa, recargo o cotización: debe existir y, para algo nuevo o activo, estar activo."""
    servicio = servicio_por_codigo(db, codigo)
    if servicio is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "No existe el servicio indicado")
    if exigir_activo and not servicio.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", f"No se puede usar el servicio {servicio.codigo} inactivo; actívelo primero")
    return servicio


def forma_de(servicio: Servicio) -> formas_cobro.FormaCobro:
    return formas_cobro.forma(servicio.forma_cobro)


def _sesion_propia():
    """Las funciones puras del motor (sin sesión) consultan el catálogo con una conexión propia, de solo lectura."""
    return Session(engine)


def forma_de_codigo(codigo: str) -> formas_cobro.FormaCobro:
    """Forma de cobro de un servicio por su código, para el motor puro (pruebas y scripts que no pasan la forma)."""
    with _sesion_propia() as db:
        servicio = servicio_por_codigo(db, codigo)
        if servicio is None:
            raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"No existe el servicio {codigo}")
        return forma_de(servicio)


def textos_pdf(codigo: str) -> dict[str, str]:
    """Textos del servicio para el PDF de una cotización emitida antes de E0 (su snapshot no los trae)."""
    with _sesion_propia() as db:
        servicio = servicio_por_codigo(db, codigo)
        if servicio is None:
            return {"codigo": codigo, "descripcion_pdf": codigo, "etiqueta_transportista": "Transportista"}
        return snapshot_servicio(servicio)


def snapshot_servicio(servicio: Servicio) -> dict[str, str]:
    return {
        "codigo": servicio.codigo,
        "nombre": servicio.nombre,
        "forma_cobro": servicio.forma_cobro,
        "descripcion_pdf": servicio.descripcion_pdf,
        "etiqueta_transportista": servicio.etiqueta_transportista,
    }


def unidades_recargo_sin_servicio(db: Session, tipo_ubicacion: str) -> set[str]:
    """Recargo sin servicio: las unidades de recargo de los servicios activos que tocan ese tipo de ubicación,
    sin las que exigen tipo de equipo. Reproduce A1/D-F2-10 (aeropuerto: KG, ENVIO; marítimo: WM, CBM, ENVIO)."""
    servicios = db.scalars(
        select(Servicio).where(
            Servicio.activo.is_(True),
            or_(Servicio.tipo_ubicacion_origen == tipo_ubicacion, Servicio.tipo_ubicacion_destino == tipo_ubicacion),
        )
    )
    unidades = {unidad for s in servicios for unidad in forma_de(s).unidades_recargo}
    return (unidades - formas_cobro.UNIDADES_DE_EQUIPO) or {"ENVIO"}


def desdes_permitidos(db: Session, servicio_codigo: str, unidad_peso: str) -> list[Decimal]:
    """Los "desde" activos del servicio en esa unidad, ordenados (reemplaza a DESDE_KG/LB_PERMITIDOS)."""
    return list(
        db.scalars(
            select(ServicioTramo.desde)
            .join(Servicio, Servicio.id == ServicioTramo.servicio_id)
            .where(
                Servicio.codigo == servicio_codigo,
                ServicioTramo.unidad_peso == unidad_peso,
                ServicioTramo.activo.is_(True),
            )
            .order_by(ServicioTramo.desde)
        )
    )


def numero(valor: Decimal) -> int | float:
    """Un "desde" para el JSON: entero si no tiene decimales (0, 45…), si no con decimales (0.5)."""
    valor = Decimal(valor)
    return int(valor) if valor == valor.to_integral_value() else float(valor.normalize())


def texto_desde(valor: Decimal) -> str:
    return str(numero(valor))


# ---------- Servicios: uso y CRUD ----------


def en_uso(db: Session, servicio: Servicio) -> bool:
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(Tarifa.modo == servicio.codigo),
                    exists().where(Recargo.modo == servicio.codigo),
                    exists().where(Cotizacion.modo == servicio.codigo),
                    exists().where(TipoEquipo.servicio_id == servicio.id),
                )
            )
        )
    )


def _tipo_ubicacion(db: Session, codigo: str, exigir_activo: bool) -> TipoUbicacion:
    tipo = db.scalars(select(TipoUbicacion).where(TipoUbicacion.codigo == codigo)).one_or_none()
    if tipo is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "No existe el tipo de ubicación indicado")
    if exigir_activo and not tipo.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", f"No se puede usar el tipo de ubicación {tipo.codigo} inactivo")
    return tipo


def _validar_servicio(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    datos["codigo"] = _codigo(datos["codigo"], "del servicio")
    datos["nombre"] = _texto(datos["nombre"], "El nombre", 60)
    forma = formas_cobro.forma(datos["forma_cobro"])
    activo = datos.get("activo", True)
    for campo in ("tipo_ubicacion_origen", "tipo_ubicacion_destino"):
        datos[campo] = "".join((datos.get(campo) or "").split()).upper()
        _tipo_ubicacion(db, datos[campo], activo)
    datos["usa_tipo_equipo"] = forma.usa_tipo_equipo if datos.get("usa_tipo_equipo") is None else datos["usa_tipo_equipo"]
    if datos["usa_tipo_equipo"] != forma.usa_tipo_equipo:
        regla = "requiere" if forma.usa_tipo_equipo else "no lleva"
        raise ErrorNegocio(422, "SERVICIO_INCOHERENTE", f"La forma de cobro {forma.codigo} {regla} tipo de equipo")
    datos["permite_libras"] = bool(datos.get("permite_libras"))
    if datos["permite_libras"] and not forma.admite_libras:
        raise ErrorNegocio(422, "SERVICIO_INCOHERENTE", f"La forma de cobro {forma.codigo} no admite tarifas por libra")
    orden = datos.get("orden") or 0
    if not 0 <= int(orden) <= 999:
        raise ErrorNegocio(422, "ORDEN_INVALIDO", "El orden va de 0 a 999")
    datos["orden"] = int(orden)
    datos["descripcion_pdf"] = _texto(datos.get("descripcion_pdf") or datos["nombre"].lower(), "La descripción para el PDF", 120)
    datos["etiqueta_transportista"] = _texto(
        datos.get("etiqueta_transportista") or "Transportista", "La etiqueta del transportista", 40
    )
    datos["aviso_incoterm"] = _texto(datos.get("aviso_incoterm"), "El aviso de Incoterm", 200, obligatorio=False)
    return datos


def _incoterms_por_defecto(db: Session, servicio: Servicio) -> list[Incoterm]:
    """Los Incoterms del primer servicio existente con los mismos tipos de ubicación; si no hay, todos."""
    gemelo = db.scalars(
        select(Servicio)
        .where(
            Servicio.id != servicio.id,
            Servicio.tipo_ubicacion_origen == servicio.tipo_ubicacion_origen,
            Servicio.tipo_ubicacion_destino == servicio.tipo_ubicacion_destino,
        )
        .order_by(Servicio.orden, Servicio.id)
        .limit(1)
    ).one_or_none()
    incoterms = list(db.scalars(select(Incoterm).order_by(Incoterm.id)))
    if gemelo is None:
        return incoterms
    return [incoterm for incoterm in incoterms if gemelo in incoterm.servicios]


def crear_servicio(db: Session, actor: Usuario, datos: dict[str, Any]) -> Servicio:
    actor_id = auditoria.id_de(actor)
    datos = _validar_servicio(db, dict(datos) | {"activo": True})
    incoterms = datos.pop("incoterms", None)
    if servicio_por_codigo(db, datos["codigo"]) is not None:
        raise ErrorNegocio(409, "SERVICIO_DUPLICADO", "Ya existe un servicio con ese código")
    servicio = Servicio(**{campo: datos[campo] for campo in CAMPOS_SERVICIO}, creado_por=actor_id)
    db.add(servicio)
    enviar(db)
    elegidos = _incoterms_por_defecto(db, servicio) if incoterms is None else _incoterms(db, incoterms)
    for incoterm in elegidos:
        incoterm.servicios.append(servicio)
    enviar(db)
    despues = _foto(servicio, CAMPOS_SERVICIO) | {"incoterms": [i.codigo for i in elegidos]}
    auditoria.registrar(db, actor, "servicio", servicio.codigo, "CREAR", despues=despues)
    confirmar(db)
    return servicio


def _incoterms(db: Session, codigos: list[str]) -> list[Incoterm]:
    codigos = sorted({c.strip().upper() for c in codigos})
    encontrados = list(db.scalars(select(Incoterm).where(Incoterm.codigo.in_(codigos)).order_by(Incoterm.id)))
    if len(encontrados) != len(codigos):
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "Algún Incoterm indicado no existe")
    return encontrados


def actualizar_servicio(db: Session, actor: Usuario, servicio_id: int, cambios: dict[str, Any]) -> Servicio:
    servicio = obtener_servicio(db, servicio_id)
    antes = _foto(servicio, CAMPOS_SERVICIO)
    final = _validar_servicio(db, antes | cambios)
    usado = en_uso(db, servicio)
    for campo in ("codigo", "forma_cobro", "tipo_ubicacion_origen", "tipo_ubicacion_destino", "usa_tipo_equipo"):
        if final[campo] != antes[campo] and usado:
            raise ErrorNegocio(
                409,
                "SERVICIO_EN_USO",
                "El servicio ya tiene tarifas, recargos, cotizaciones o tipos de equipo: no cambia su código, su forma "
                "de cobro ni sus tipos de ubicación (cree un servicio nuevo)",
            )
    if final["codigo"] != antes["codigo"] and servicio_por_codigo(db, final["codigo"]) is not None:
        raise ErrorNegocio(409, "SERVICIO_DUPLICADO", "Ya existe un servicio con ese código")
    with db.no_autoflush:
        for campo in CAMPOS_SERVICIO:
            setattr(servicio, campo, final[campo])
        despues = _foto(servicio, CAMPOS_SERVICIO)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "servicio", servicio.codigo, accion, antes=antes, despues=despues)
    confirmar(db)
    return servicio


def borrar_servicio(db: Session, actor: Usuario, servicio_id: int) -> None:
    """Solo si nunca se usó; sus tramos y su relación con los Incoterms se van con él."""
    servicio = obtener_servicio(db, servicio_id)
    if en_uso(db, servicio):
        raise ErrorNegocio(
            409, "SERVICIO_EN_USO", "El servicio ya se usó: no se borra, desactívelo para que no se ofrezca más"
        )
    antes = _foto(servicio, CAMPOS_SERVICIO) | {"tramos": [_foto(t, CAMPOS_TRAMO) for t in servicio.tramos]}
    with db.no_autoflush:
        for incoterm in db.scalars(select(Incoterm)):
            if servicio in incoterm.servicios:
                incoterm.servicios.remove(servicio)
        for tramo in list(servicio.tramos):
            db.delete(tramo)
        db.delete(servicio)
        auditoria.registrar(db, actor, "servicio", antes["codigo"], "DESACTIVAR", antes=antes, nota="BORRADO: nunca se usó")
    confirmar(db)


# ---------- Tramos del servicio ----------


def _desde(valor: Any) -> Decimal:
    try:
        desde = Decimal(str(valor))
    except InvalidOperation:
        raise ErrorNegocio(422, "TRAMOS_INVALIDOS", "El desde debe ser un número") from None
    if not desde.is_finite() or desde < 0 or desde >= Decimal("10000000"):
        raise ErrorNegocio(422, "TRAMOS_INVALIDOS", "El desde va de 0 a 9 999 999,999")
    if desde.normalize().as_tuple().exponent < -3:
        raise ErrorNegocio(422, "TRAMOS_INVALIDOS", "El desde admite como máximo 3 decimales")
    return desde


def tramo_en_uso(db: Session, tramo: ServicioTramo) -> bool:
    return bool(
        db.scalar(
            select(
                exists()
                .where(TramoAereo.tarifa_id == Tarifa.id)
                .where(
                    Tarifa.modo == tramo.servicio.codigo,
                    Tarifa.unidad_peso == tramo.unidad_peso,
                    TramoAereo.desde_kg == tramo.desde,
                )
            )
        )
    )


def obtener_tramo(db: Session, tramo_id: int) -> ServicioTramo:
    tramo = db.get(ServicioTramo, tramo_id)
    if tramo is None:
        raise ErrorNegocio(404, "TRAMO_NO_ENCONTRADO", "Tramo no encontrado")
    return tramo


def _validar_tramo(db: Session, servicio: Servicio, datos: dict[str, Any], excluir_id: int | None) -> dict[str, Any]:
    if not forma_de(servicio).usa_tramos:
        raise ErrorNegocio(422, "TRAMOS_NO_PERMITIDOS", f"El servicio {servicio.codigo} no cobra por peso con tramos")
    datos["unidad_peso"] = (datos.get("unidad_peso") or "KG").upper()
    if datos["unidad_peso"] not in UNIDADES_PESO:
        raise ErrorNegocio(422, "CARGA_INVALIDA", "La unidad de peso debe ser KG o LB")
    if datos["unidad_peso"] == "LB" and not servicio.permite_libras:
        raise ErrorNegocio(422, "UNIDAD_PESO_INCOMPATIBLE", f"El servicio {servicio.codigo} no tiene tarifas por libra")
    datos["desde"] = _desde(datos["desde"])
    datos["orden"] = int(datos.get("orden") or 0)
    repetido = db.scalar(
        select(ServicioTramo.id).where(
            ServicioTramo.servicio_id == servicio.id,
            ServicioTramo.unidad_peso == datos["unidad_peso"],
            ServicioTramo.desde == datos["desde"],
            ServicioTramo.id != (excluir_id or 0),
        )
    )
    if repetido is not None:
        raise ErrorNegocio(409, "TRAMO_DUPLICADO", "El servicio ya tiene ese tramo en esa unidad")
    return datos


def crear_tramo(db: Session, actor: Usuario, servicio_id: int, datos: dict[str, Any]) -> ServicioTramo:
    servicio = obtener_servicio(db, servicio_id)
    datos = _validar_tramo(db, servicio, dict(datos), None)
    tramo = ServicioTramo(
        servicio_id=servicio.id, unidad_peso=datos["unidad_peso"], desde=datos["desde"], orden=datos["orden"],
        creado_por=auditoria.id_de(actor),
    )
    db.add(tramo)
    enviar(db)
    auditoria.registrar(db, actor, "servicio_tramo", tramo.id, "CREAR", despues=_foto(tramo, CAMPOS_TRAMO))
    confirmar(db)
    return tramo


def actualizar_tramo(db: Session, actor: Usuario, tramo_id: int, cambios: dict[str, Any]) -> ServicioTramo:
    tramo = obtener_tramo(db, tramo_id)
    antes = _foto(tramo, CAMPOS_TRAMO)
    final = _validar_tramo(db, tramo.servicio, antes | cambios, tramo.id)
    cambia_clave = final["desde"] != antes["desde"] or final["unidad_peso"] != antes["unidad_peso"]
    if cambia_clave and tramo_en_uso(db, tramo):
        raise ErrorNegocio(409, "TRAMO_EN_USO", "Hay tarifas con este tramo: no cambia su desde ni su unidad; desactívelo")
    with db.no_autoflush:
        for campo in ("unidad_peso", "desde", "orden"):
            setattr(tramo, campo, final[campo])
        if "activo" in cambios:
            tramo.activo = bool(cambios["activo"])
        despues = _foto(tramo, CAMPOS_TRAMO)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "servicio_tramo", tramo.id, accion, antes=antes, despues=despues)
    confirmar(db)
    return tramo


def borrar_tramo(db: Session, actor: Usuario, tramo_id: int) -> None:
    tramo = obtener_tramo(db, tramo_id)
    if tramo_en_uso(db, tramo):
        raise ErrorNegocio(409, "TRAMO_EN_USO", "Hay tarifas con este tramo: no se borra, desactívelo")
    antes = _foto(tramo, CAMPOS_TRAMO)
    db.delete(tramo)
    auditoria.registrar(db, actor, "servicio_tramo", tramo_id, "DESACTIVAR", antes=antes, nota="BORRADO: nunca se usó")
    confirmar(db)


# ---------- Tipos de ubicación ----------


def listar_tipos_ubicacion(db: Session, activo: bool | None = None) -> list[TipoUbicacion]:
    consulta = select(TipoUbicacion)
    if activo is not None:
        consulta = consulta.where(TipoUbicacion.activo.is_(activo))
    return list(db.scalars(consulta.order_by(TipoUbicacion.nombre)))


def obtener_tipo_ubicacion(db: Session, tipo_id: int) -> TipoUbicacion:
    tipo = db.get(TipoUbicacion, tipo_id)
    if tipo is None:
        raise ErrorNegocio(404, "TIPO_UBICACION_NO_ENCONTRADO", "Tipo de ubicación no encontrado")
    return tipo


def tipo_de_puerto(db: Session, codigo: str) -> TipoUbicacion | None:
    return db.scalars(select(TipoUbicacion).where(TipoUbicacion.codigo == codigo)).one_or_none()


def compilar_regex(regex: str | None) -> re.Pattern | None:
    if not regex:
        return None
    try:
        return re.compile(regex)
    except re.error as error:
        raise ErrorNegocio(422, "REGEX_INVALIDA", f"La expresión regular no es válida: {error}") from None


def error_codigo_puerto(tipo: TipoUbicacion, codigo: str, iso2_pais: str) -> ErrorNegocio | None:
    """La regla del código de un puerto según su tipo (antes: UN/LOCODE con prefijo de país o IATA)."""
    patron = compilar_regex(tipo.regex_codigo)
    if patron is not None and not patron.fullmatch(codigo):
        return ErrorNegocio(422, "CODIGO_INVALIDO", tipo.ayuda_codigo or f"El código no cumple el formato de {tipo.nombre}")
    if patron is None and not PATRON_CODIGO_LIBRE.match(codigo):
        return ErrorNegocio(422, "CODIGO_INVALIDO", tipo.ayuda_codigo or "El código es de 2 a 10 letras o números")
    if tipo.prefijo_pais and codigo[:2] != iso2_pais:
        return ErrorNegocio(
            422, "PUERTO_PAIS_INCONSISTENTE", f"El código {codigo} empieza con {codigo[:2]}, pero el país es {iso2_pais}"
        )
    return None


def _validar_ubicacion(datos: dict[str, Any]) -> dict[str, Any]:
    datos["codigo"] = _codigo(datos["codigo"], "del tipo de ubicación")
    datos["nombre"] = _texto(datos["nombre"], "El nombre", 60)
    datos["regex_codigo"] = (datos.get("regex_codigo") or "").strip() or None
    compilar_regex(datos["regex_codigo"])
    datos["ayuda_codigo"] = _texto(datos.get("ayuda_codigo"), "La ayuda del código", 200, obligatorio=False)
    datos["prefijo_pais"] = bool(datos.get("prefijo_pais"))
    return datos


def _ubicacion_en_uso(db: Session, codigo: str, solo_activos: bool = False) -> bool:
    puertos = exists().where(Puerto.tipo == codigo)
    servicios = exists().where(or_(Servicio.tipo_ubicacion_origen == codigo, Servicio.tipo_ubicacion_destino == codigo))
    if solo_activos:
        puertos = puertos.where(Puerto.activo.is_(True))
        servicios = servicios.where(Servicio.activo.is_(True))
    return bool(db.scalar(select(or_(puertos, servicios))))


def crear_tipo_ubicacion(db: Session, actor: Usuario, datos: dict[str, Any]) -> TipoUbicacion:
    datos = _validar_ubicacion(dict(datos))
    if tipo_de_puerto(db, datos["codigo"]) is not None:
        raise ErrorNegocio(409, "TIPO_UBICACION_DUPLICADO", "Ya existe un tipo de ubicación con ese código")
    tipo = TipoUbicacion(**{campo: datos[campo] for campo in CAMPOS_UBICACION if campo != "activo"},
                         creado_por=auditoria.id_de(actor))
    db.add(tipo)
    enviar(db)
    auditoria.registrar(db, actor, "tipo_ubicacion", tipo.codigo, "CREAR", despues=_foto(tipo, CAMPOS_UBICACION))
    confirmar(db)
    return tipo


def actualizar_tipo_ubicacion(db: Session, actor: Usuario, tipo_id: int, cambios: dict[str, Any]) -> TipoUbicacion:
    tipo = obtener_tipo_ubicacion(db, tipo_id)
    antes = _foto(tipo, CAMPOS_UBICACION)
    final = _validar_ubicacion(antes | cambios)
    if final["codigo"] != antes["codigo"]:
        if _ubicacion_en_uso(db, antes["codigo"]):
            raise ErrorNegocio(409, "TIENE_DEPENDIENTES", "Hay puertos o servicios con este tipo: su código no cambia")
        if tipo_de_puerto(db, final["codigo"]) is not None:
            raise ErrorNegocio(409, "TIPO_UBICACION_DUPLICADO", "Ya existe un tipo de ubicación con ese código")
    if cambios.get("activo") is False and tipo.activo and _ubicacion_en_uso(db, tipo.codigo, solo_activos=True):
        raise ErrorNegocio(409, "TIENE_DEPENDIENTES", "Hay puertos o servicios activos con este tipo; desactívelos primero")
    if final["regex_codigo"] != antes["regex_codigo"] or final["prefijo_pais"] != antes["prefijo_pais"]:
        _exigir_puertos_validos(db, tipo, final)
    with db.no_autoflush:
        for campo in CAMPOS_UBICACION:
            if campo != "activo":
                setattr(tipo, campo, final[campo])
        if "activo" in cambios:
            tipo.activo = bool(cambios["activo"])
        despues = _foto(tipo, CAMPOS_UBICACION)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "tipo_ubicacion", tipo.codigo, accion, antes=antes, despues=despues)
    confirmar(db)
    return tipo


def _exigir_puertos_validos(db: Session, tipo: TipoUbicacion, final: dict[str, Any]) -> None:
    """Una regla nueva no puede dejar inválidos los puertos que ya existen con ese tipo."""
    prueba = TipoUbicacion(
        codigo=tipo.codigo, nombre=final["nombre"], regex_codigo=final["regex_codigo"],
        ayuda_codigo=final["ayuda_codigo"], prefijo_pais=final["prefijo_pais"],
    )
    malos = [
        puerto.codigo
        for puerto in db.scalars(select(Puerto).options(selectinload(Puerto.pais)).where(Puerto.tipo == tipo.codigo))
        if error_codigo_puerto(prueba, puerto.codigo, puerto.pais.iso2) is not None
    ]
    if malos:
        muestra = ", ".join(malos[:5]) + ("…" if len(malos) > 5 else "")
        raise ErrorNegocio(
            409, "TIENE_DEPENDIENTES", f"Con la regla nueva quedarían {len(malos)} puertos con código inválido: {muestra}"
        )


def contar_puertos(db: Session, codigo: str) -> int:
    return db.scalar(select(func.count()).select_from(Puerto).where(Puerto.tipo == codigo))

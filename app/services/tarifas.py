"""M5 Tarifas y tramos aéreos.

- Gating de costos en el SERVICE (D-F2-5): `nivel_de(usuario)` elige el esquema de salida.
- No superposición de vigencias (D-F2-1): verificación previa (devuelve el id en conflicto) y, como
  respaldo ante carreras, la exclusión `ex_tarifa_vigencia_sin_superposicion` de la base.
- Venta calculada siempre con `precio_venta` (§15.3: nunca es un input editable).
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.core.rbac import permisos_de
from app.models import Moneda, Proveedor, Puerto, Tarifa, TipoEquipo, TramoAereo, Usuario
from app.models.tarifas import DESDE_KG_PERMITIDOS
from app.schemas.tarifas import (
    PuertoRef,
    Referencia,
    TarifaCosto,
    TarifaCostoMargen,
    TarifaVenta,
    TipoEquipoRef,
    TramoCosto,
    TramoCostoMargen,
    TramoVenta,
)
from app.services import auditoria, precio_venta
from app.services.configuracion import leer_config

NIVEL_VENTA, NIVEL_COSTO, NIVEL_MARGEN = "venta", "costo", "margen"
UNIDADES_TARIFA = {"AEREO": {"KG", "ENVIO"}, "LCL": {"WM", "CBM", "ENVIO"}, "FCL": {"CONTENEDOR"}}
CAMPOS_VENTA = (
    "costo",
    "moneda_id",
    "minimo",
    "metodo_venta",
    "parametro_venta",
    "precio_venta_manual",
    "minimo_venta_manual",
    "valido_desde",
    "valido_hasta",
)
CAMPOS_TARIFA = (
    "proveedor_id",
    "modo",
    "origen_puerto_id",
    "destino_puerto_id",
    "tipo_equipo_id",
    "rate_unit",
    *CAMPOS_VENTA,
    "transit_time_dias",
    "dias_libres",
    "notas",
    "activo",
)
MONTOS = ("costo", "minimo", "parametro_venta", "precio_venta_manual", "minimo_venta_manual")


# ---------- Piezas comunes a tarifas y recargos ----------


def nivel_de(usuario: Usuario) -> str:
    """D-F2-5: el margen solo con costo.ver Y margen.ver (el margen permite deducir el costo)."""
    permisos = permisos_de(usuario)
    if "costo.ver" not in permisos:
        return NIVEL_VENTA
    return NIVEL_MARGEN if "margen.ver" in permisos else NIVEL_COSTO


def dias_alerta(db: Session) -> int:
    return int(leer_config(db, "dias_alerta_vencimiento"))


def estado_vigencia(desde: date, hasta: date, hoy: date, dias: int) -> str:
    if hoy < desde:
        return "FUTURA"
    if hoy > hasta:
        return "VENCIDA"
    return "POR_VENCER" if hasta <= hoy + timedelta(days=dias) else "VIGENTE"


def filtros_vigencia(modelo, vigente_en: date | None, por_vencer: bool | None, hoy: date, dias: int) -> list:
    filtros = []
    if vigente_en is not None:
        filtros += [modelo.valido_desde <= vigente_en, modelo.valido_hasta >= vigente_en]
    if por_vencer is not None:
        condicion = (
            (modelo.valido_desde <= hoy) & (modelo.valido_hasta >= hoy) & (modelo.valido_hasta <= hoy + timedelta(days=dias))
        )
        filtros.append(condicion if por_vencer else ~condicion)
    return filtros


def referencia_activa(db: Session, modelo, ident: int | None, que: str, exigir_activo: bool):
    objeto = db.get(modelo, ident) if ident is not None else None
    if objeto is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"No existe {que} indicado")
    if exigir_activo and not objeto.activo:
        codigo = "MONEDA_INACTIVA" if modelo is Moneda else "PADRE_INACTIVO"
        raise ErrorNegocio(422, codigo, f"No se puede usar {que} inactivo; actívelo primero")
    return objeto


def validar_venta(datos: dict[str, Any]) -> dict[str, Any]:
    """Montos (4 decimales, sin redondeo silencioso), esquema de venta (D-F2-3) y vigencia."""
    datos["costo"] = precio_venta.validar_monto(datos["costo"], "El costo", positivo=True)
    datos["minimo"] = precio_venta.validar_monto(datos["minimo"], "El mínimo", positivo=False)
    if datos.get("parametro_venta") is not None:
        datos["parametro_venta"] = precio_venta.validar_monto(
            datos["parametro_venta"], "El parámetro de venta", positivo=False, enteros_maximos=6
        )
    if datos.get("precio_venta_manual") is not None:
        datos["precio_venta_manual"] = precio_venta.validar_monto(
            datos["precio_venta_manual"], "El precio de venta manual", positivo=True
        )
    if datos.get("minimo_venta_manual") is not None:
        datos["minimo_venta_manual"] = precio_venta.validar_monto(
            datos["minimo_venta_manual"], "El mínimo de venta manual", positivo=False
        )
    precio_venta.validar_esquema(
        datos["metodo_venta"],
        datos.get("parametro_venta"),
        datos.get("precio_venta_manual"),
        datos["minimo"],
        datos.get("minimo_venta_manual"),
    )
    if datos["valido_hasta"] < datos["valido_desde"]:
        raise ErrorNegocio(422, "VIGENCIA_INVALIDA", "La fecha de fin de vigencia es anterior a la de inicio")
    return datos


def precios_de(objeto) -> tuple[Decimal, Decimal]:
    venta = precio_venta.precio_venta(
        objeto.metodo_venta, objeto.costo, objeto.parametro_venta, objeto.precio_venta_manual
    )
    minimo = precio_venta.precio_venta_minimo(
        objeto.metodo_venta, objeto.minimo, objeto.parametro_venta, objeto.minimo_venta_manual
    )
    return venta, minimo


def campos_de_costo(objeto) -> dict[str, Any]:
    return {
        "costo": objeto.costo,
        "minimo": objeto.minimo,
        "metodo_venta": objeto.metodo_venta,
        "parametro_venta": objeto.parametro_venta,
        "precio_venta_manual": objeto.precio_venta_manual,
        "minimo_venta_manual": objeto.minimo_venta_manual,
    }


def foto(objeto, campos) -> dict[str, Any]:
    """Valores para la auditoría tal como quedan guardados (montos a 4 decimales)."""
    valores = {campo: getattr(objeto, campo) for campo in campos}
    for campo in MONTOS:
        if campo in valores and valores[campo] is not None:
            valores[campo] = precio_venta.redondear(Decimal(valores[campo]))
    return valores


def error_superposicion(conflicto: int, que: str) -> ErrorNegocio:
    return ErrorNegocio(
        409,
        "VIGENCIA_SUPERPUESTA",
        f"La vigencia se superpone con {que} activa #{conflicto} con la misma clave",
        extra={"id_en_conflicto": conflicto},
    )


def superpuesta(db: Session, modelo, clave: list, desde: date, hasta: date, excluir_id: int | None) -> int | None:
    consulta = select(modelo.id).where(
        *clave, modelo.activo.is_(True), modelo.valido_desde <= hasta, modelo.valido_hasta >= desde
    )
    if excluir_id is not None:
        consulta = consulta.where(modelo.id != excluir_id)
    return db.scalar(consulta.order_by(modelo.id).limit(1))


# ---------- Tarifas ----------


def _clave_tarifa(datos: dict[str, Any]) -> list:
    return [
        Tarifa.proveedor_id == datos["proveedor_id"],
        Tarifa.modo == datos["modo"],
        Tarifa.origen_puerto_id == datos["origen_puerto_id"],
        Tarifa.destino_puerto_id == datos["destino_puerto_id"],
        Tarifa.tipo_equipo_id.is_not_distinct_from(datos["tipo_equipo_id"]),
    ]


def _validar_tarifa(db: Session, datos: dict[str, Any], excluir_id: int | None = None) -> dict[str, Any]:
    """Valida el estado FINAL de la tarifa. Las referencias se exigen activas solo si la tarifa queda activa."""
    activa = datos.get("activo", True)
    referencia_activa(db, Proveedor, datos["proveedor_id"], "el proveedor", activa)
    referencia_activa(db, Moneda, datos["moneda_id"], "la moneda", activa)
    origen = referencia_activa(db, Puerto, datos["origen_puerto_id"], "el puerto de origen", activa)
    destino = referencia_activa(db, Puerto, datos["destino_puerto_id"], "el puerto de destino", activa)
    modo = datos["modo"]
    if origen.id == destino.id:
        raise ErrorNegocio(422, "ORIGEN_IGUAL_DESTINO", "El origen y el destino deben ser distintos")
    tipo_puerto = "AEREO" if modo == "AEREO" else "MARITIMO"
    if origen.tipo != tipo_puerto or destino.tipo != tipo_puerto:
        raise ErrorNegocio(
            422,
            "PUERTO_MODO_INCONSISTENTE",
            "El modo AEREO usa aeropuertos; LCL y FCL usan puertos marítimos",
        )
    if modo == "FCL":
        if datos.get("tipo_equipo_id") is None:
            raise ErrorNegocio(422, "TIPO_EQUIPO_REQUERIDO", "Una tarifa FCL requiere el tipo de equipo")
        referencia_activa(db, TipoEquipo, datos["tipo_equipo_id"], "el tipo de equipo", activa)
    elif datos.get("tipo_equipo_id") is not None:
        raise ErrorNegocio(422, "TIPO_EQUIPO_NO_PERMITIDO", "Solo las tarifas FCL llevan tipo de equipo")
    if datos["rate_unit"] not in UNIDADES_TARIFA[modo]:
        permitidas = ", ".join(sorted(UNIDADES_TARIFA[modo]))
        raise ErrorNegocio(422, "RATE_UNIT_INCOMPATIBLE", f"Con {modo} la unidad debe ser una de: {permitidas}")
    validar_venta(datos)
    if activa:
        conflicto = superpuesta(
            db, Tarifa, _clave_tarifa(datos), datos["valido_desde"], datos["valido_hasta"], excluir_id
        )
        if conflicto is not None:
            raise error_superposicion(conflicto, "la tarifa")
    return datos


def _consulta_tarifas():
    return select(Tarifa).options(
        selectinload(Tarifa.proveedor),
        selectinload(Tarifa.moneda),
        selectinload(Tarifa.origen),
        selectinload(Tarifa.destino),
        selectinload(Tarifa.tipo_equipo),
        selectinload(Tarifa.tramos),
    )


def presentar_tarifa(tarifa: Tarifa, nivel: str, hoy: date, dias: int):
    venta, venta_minima = precios_de(tarifa)
    datos = {
        "id": tarifa.id,
        "proveedor": Referencia.model_validate(tarifa.proveedor),
        "modo": tarifa.modo,
        "origen": PuertoRef.model_validate(tarifa.origen),
        "destino": PuertoRef.model_validate(tarifa.destino),
        "tipo_equipo": TipoEquipoRef.model_validate(tarifa.tipo_equipo) if tarifa.tipo_equipo else None,
        "rate_unit": tarifa.rate_unit,
        "moneda": tarifa.moneda.codigo,
        "precio_venta": venta,
        "precio_venta_minimo": venta_minima,
        "transit_time_dias": tarifa.transit_time_dias,
        "dias_libres": tarifa.dias_libres,
        "valido_desde": tarifa.valido_desde,
        "valido_hasta": tarifa.valido_hasta,
        "estado_vigencia": estado_vigencia(tarifa.valido_desde, tarifa.valido_hasta, hoy, dias),
        "tiene_tramos": bool(tarifa.tramos),
        "activo": tarifa.activo,
        "creado_en": tarifa.creado_en,
        "actualizado_en": tarifa.actualizado_en,
    }
    if nivel == NIVEL_VENTA:
        return TarifaVenta(**datos)
    datos |= campos_de_costo(tarifa) | {"notas": tarifa.notas}
    if nivel == NIVEL_COSTO:
        return TarifaCosto(**datos)
    unitario, pct = precio_venta.margen(venta, tarifa.costo)
    return TarifaCostoMargen(**datos, margen_unitario=unitario, margen_pct=pct)


def _presentar(db: Session, usuario: Usuario, tarifa: Tarifa):
    db.refresh(tarifa)
    return presentar_tarifa(tarifa, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db))


def obtener_tarifa(db: Session, tarifa_id: int) -> Tarifa:
    tarifa = db.scalars(_consulta_tarifas().where(Tarifa.id == tarifa_id)).one_or_none()
    if tarifa is None:
        raise ErrorNegocio(404, "TARIFA_NO_ENCONTRADA", "Tarifa no encontrada")
    return tarifa


def detalle_tarifa(db: Session, usuario: Usuario, tarifa_id: int):
    tarifa = obtener_tarifa(db, tarifa_id)
    return presentar_tarifa(tarifa, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db))


def listar_tarifas(
    db: Session,
    usuario: Usuario,
    modo: str | None = None,
    origen: int | None = None,
    destino: int | None = None,
    proveedor: int | None = None,
    tipo_equipo: int | None = None,
    vigente_en: date | None = None,
    por_vencer: bool | None = None,
    activo: bool | None = None,
):
    hoy, dias = fechas.hoy_ecuador(), dias_alerta(db)
    filtros = filtros_vigencia(Tarifa, vigente_en, por_vencer, hoy, dias)
    for columna, valor in (
        (Tarifa.modo, modo),
        (Tarifa.origen_puerto_id, origen),
        (Tarifa.destino_puerto_id, destino),
        (Tarifa.proveedor_id, proveedor),
        (Tarifa.tipo_equipo_id, tipo_equipo),
    ):
        if valor is not None:
            filtros.append(columna == valor)
    if activo is not None:
        filtros.append(Tarifa.activo.is_(activo))
    tarifas = db.scalars(_consulta_tarifas().where(*filtros).order_by(Tarifa.valido_hasta, Tarifa.id))
    nivel = nivel_de(usuario)
    return [presentar_tarifa(t, nivel, hoy, dias) for t in tarifas]


def crear_tarifa(db: Session, actor: Usuario, datos: dict[str, Any]):
    actor_id = auditoria.id_de(actor)
    datos = _validar_tarifa(db, dict(datos) | {"activo": True})
    tarifa = Tarifa(**{campo: datos.get(campo) for campo in CAMPOS_TARIFA}, creado_por=actor_id)
    db.add(tarifa)
    enviar(db)
    auditoria.registrar(db, actor, "tarifa", tarifa.id, "CREAR", despues=foto(tarifa, CAMPOS_TARIFA))
    confirmar(db)
    return _presentar(db, actor, tarifa)


def actualizar_tarifa(db: Session, actor: Usuario, tarifa_id: int, cambios: dict[str, Any]):
    tarifa = obtener_tarifa(db, tarifa_id)
    if tarifa.tramos:
        if "costo" in cambios:
            raise ErrorNegocio(422, "COSTO_DESDE_TRAMOS", "Con tramos, el costo se edita desde los tramos")
        if "precio_venta_manual" in cambios and tarifa.metodo_venta == "MANUAL":
            raise ErrorNegocio(
                422, "PRECIO_DESDE_TRAMOS", "Con tramos, el precio de venta se edita desde los tramos"
            )
        for campo in ("modo", "rate_unit", "metodo_venta"):
            if campo in cambios and cambios[campo] != getattr(tarifa, campo):
                raise ErrorNegocio(
                    409, "TIENE_DEPENDIENTES", "La tarifa tiene tramos: reemplace o quite los tramos antes de ese cambio"
                )
    final = _validar_tarifa(
        db, {campo: getattr(tarifa, campo) for campo in CAMPOS_TARIFA} | cambios, excluir_id=tarifa.id
    )
    antes = foto(tarifa, CAMPOS_TARIFA)
    with db.no_autoflush:
        for campo in cambios:
            setattr(tarifa, campo, final[campo])
        despues = foto(tarifa, CAMPOS_TARIFA)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "tarifa", tarifa_id, accion, antes=antes, despues=despues)
    confirmar(db)
    return _presentar(db, actor, tarifa)


def _foto_tramos(tarifa: Tarifa) -> list[dict[str, Any]]:
    return [
        {
            "desde_kg": tramo.desde_kg,
            "costo_kg": precio_venta.redondear(Decimal(tramo.costo_kg)),
            "precio_venta_kg": None
            if tramo.precio_venta_kg is None
            else precio_venta.redondear(Decimal(tramo.precio_venta_kg)),
        }
        for tramo in tarifa.tramos
    ]


def duplicar_tarifa(db: Session, actor: Usuario, tarifa_id: int, valido_desde: date, valido_hasta: date):
    actor_id = auditoria.id_de(actor)
    original = obtener_tarifa(db, tarifa_id)
    datos = {campo: getattr(original, campo) for campo in CAMPOS_TARIFA}
    datos |= {"valido_desde": valido_desde, "valido_hasta": valido_hasta, "activo": True}
    datos = _validar_tarifa(db, datos)
    nueva = Tarifa(**{campo: datos[campo] for campo in CAMPOS_TARIFA}, creado_por=actor_id)
    for tramo in original.tramos:
        nueva.tramos.append(
            TramoAereo(desde_kg=tramo.desde_kg, costo_kg=tramo.costo_kg, precio_venta_kg=tramo.precio_venta_kg)
        )
    db.add(nueva)
    enviar(db)
    despues = foto(nueva, CAMPOS_TARIFA) | {"tramos": _foto_tramos(nueva)}
    auditoria.registrar(db, actor, "tarifa", nueva.id, "CREAR", despues=despues, nota=f"duplicada de #{original.id}")
    confirmar(db)
    return _presentar(db, actor, nueva)


# ---------- Tramos aéreos (D-F2-2) ----------


def precio_venta_kg(tarifa: Tarifa, tramo: TramoAereo) -> Decimal:
    """Venta por kg del tramo en la moneda de la tarifa (hueco 11 de F2: el método se aplica por kg)."""
    if tarifa.metodo_venta == "MANUAL":
        return precio_venta.redondear(tramo.precio_venta_kg)
    return precio_venta.aplicar_metodo(tarifa.metodo_venta, tramo.costo_kg, tarifa.parametro_venta)


def presentar_tramos(tarifa: Tarifa, nivel: str):
    salida = []
    for tramo in tarifa.tramos:
        venta = precio_venta_kg(tarifa, tramo)
        datos = {"desde_kg": tramo.desde_kg, "precio_venta_kg": venta}
        if nivel == NIVEL_VENTA:
            salida.append(TramoVenta(**datos))
            continue
        datos["costo_kg"] = tramo.costo_kg
        if nivel == NIVEL_COSTO:
            salida.append(TramoCosto(**datos))
            continue
        unitario, pct = precio_venta.margen(venta, tramo.costo_kg)
        salida.append(TramoCostoMargen(**datos, margen_unitario=unitario, margen_pct=pct))
    return salida


def obtener_tramos(db: Session, usuario: Usuario, tarifa_id: int):
    return presentar_tramos(obtener_tarifa(db, tarifa_id), nivel_de(usuario))


def _validar_tramos(tarifa: Tarifa, tramos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if tarifa.modo != "AEREO" or tarifa.rate_unit != "KG":
        raise ErrorNegocio(422, "TRAMOS_NO_PERMITIDOS", "Solo las tarifas AEREO por KG llevan tramos")
    desdes = [tramo["desde_kg"] for tramo in tramos]
    if any(desde not in DESDE_KG_PERMITIDOS for desde in desdes):
        permitidos = ", ".join(str(d) for d in DESDE_KG_PERMITIDOS)
        raise ErrorNegocio(422, "TRAMOS_INVALIDOS", f"Los tramos permitidos desde kg son: {permitidos}")
    if len(set(desdes)) != len(desdes):
        raise ErrorNegocio(422, "TRAMOS_INVALIDOS", "Hay tramos repetidos")
    if tramos and 0 not in desdes:
        raise ErrorNegocio(422, "TRAMO_CERO_REQUERIDO", "El tramo desde 0 kg (-45) es obligatorio")
    validados = []
    for tramo in sorted(tramos, key=lambda t: t["desde_kg"]):
        costo_kg = precio_venta.validar_monto(tramo["costo_kg"], "El costo por kg", positivo=True)
        venta_kg = tramo.get("precio_venta_kg")
        if tarifa.metodo_venta == "MANUAL":
            if venta_kg is None:
                raise ErrorNegocio(422, "TRAMOS_INVALIDOS", "Con MANUAL cada tramo requiere su precio de venta por kg")
            venta_kg = precio_venta.validar_monto(venta_kg, "El precio de venta por kg", positivo=True)
        elif venta_kg is not None:
            raise ErrorNegocio(
                422, "TRAMOS_INVALIDOS", f"Con {tarifa.metodo_venta} el precio por kg se calcula; envíelo vacío"
            )
        validados.append({"desde_kg": tramo["desde_kg"], "costo_kg": costo_kg, "precio_venta_kg": venta_kg})
    return validados


def reemplazar_tramos(db: Session, actor: Usuario, tarifa_id: int, tramos: list[dict[str, Any]]):
    """PUT: reemplaza el conjunto completo en una transacción. tarifa.costo (y el precio manual) = tramo 0."""
    tarifa = db.scalars(
        select(Tarifa).options(selectinload(Tarifa.tramos)).where(Tarifa.id == tarifa_id).with_for_update()
    ).one_or_none()
    if tarifa is None:
        raise ErrorNegocio(404, "TARIFA_NO_ENCONTRADA", "Tarifa no encontrada")
    validados = _validar_tramos(tarifa, tramos)
    campos_auditados = ("costo", "precio_venta_manual")
    antes = foto(tarifa, campos_auditados) | {"tramos": _foto_tramos(tarifa)}

    for tramo in list(tarifa.tramos):
        db.delete(tramo)
    enviar(db)
    db.expire(tarifa, ["tramos"])
    for tramo in validados:
        tarifa.tramos.append(TramoAereo(**tramo))
    if validados:
        tarifa.costo = validados[0]["costo_kg"]
        if tarifa.metodo_venta == "MANUAL":
            tarifa.precio_venta_manual = validados[0]["precio_venta_kg"]
    enviar(db)

    despues = foto(tarifa, campos_auditados) | {"tramos": _foto_tramos(tarifa)}
    auditoria.registrar(db, actor, "tarifa", tarifa_id, "EDITAR", antes=antes, despues=despues, nota="tramos reemplazados")
    confirmar(db)
    db.refresh(tarifa)
    return presentar_tramos(tarifa, nivel_de(actor))

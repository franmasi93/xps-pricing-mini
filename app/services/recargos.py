"""M5 Recargos locales (THC, BL, handling, seguro…) por puerto y lado.

- Mismo esquema de venta, mínimos, decimales, vigencias y gating que la tarifa (services/tarifas).
- No superposición (D-F2-1) por (proveedor o null, puerto, lado, bloque, concepto, modo o null,
  tipo_equipo o null); el concepto se compara sin distinguir mayúsculas.
- Unidad según el servicio (A1, D-F2-10; E0: la forma de cobro del servicio); sin servicio, según el tipo de
  ubicación del puerto (las unidades de los servicios que la usan, sin las que exigen tipo de equipo).
- Seguro por envío o como % del valor de la mercancía (PCT_VALOR, solo en USD; D-F3-3).
- % sobre el Recibo de Caja (PCT_RECIBO, D3 de F4): costo = porcentaje, mínimo en USD; solo USD y en cualquier
  bloque menos el seguro (el flete principal no es un recargo).
- D-R2 (0015): un recargo se puede VINCULAR a tarifas y a servicios. Vinculado a tarifas no necesita puerto: toma el
  de la tarifa según su lado. Sin vínculos sigue siendo "general". Vincular y desvincular quedan auditados.
- D-R3 (0015): el recargo dice si va en Recibo de Caja o en Factura (el seguro, siempre en Recibo de Caja). Si no se
  indica y tiene puerto, se usa la regla de antes (Ecuador → Factura; exterior → Recibo de Caja).
- Advertencias de coherencia (no bloquean): un gasto de destino en un puerto del exterior, o uno de origen en Ecuador.
"""
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import Moneda, Proveedor, Puerto, Recargo, RecargoServicio, RecargoTarifa, Servicio, Tarifa, Usuario
from app.schemas.tarifas import PuertoRef, RecargoCosto, RecargoCostoMargen, RecargoVenta, Referencia, TipoEquipoRef
from app.services import auditoria, precio_venta, servicios
from app.services.tarifas import (
    CAMPOS_VENTA,
    NIVEL_COSTO,
    NIVEL_VENTA,
    campos_de_costo,
    dias_alerta,
    error_superposicion,
    estado_vigencia,
    filtros_vigencia,
    foto,
    nivel_de,
    precios_de,
    referencia_activa,
    superpuesta,
    validar_tipo_equipo,
    validar_venta,
)

LADO_BLOQUES = {
    "ORIGEN": {"RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN", "SEGURO"},
    "DESTINO": {"GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL", "SEGURO"},
}
UNIDADES_SEGURO = {"ENVIO", "PCT_VALOR"}
CAMPOS_RECARGO = (
    "proveedor_id",
    "puerto_id",
    "lado",
    "bloque_incoterm",
    "concepto",
    "modo",
    "tipo_equipo_id",
    "rate_unit",
    *CAMPOS_VENTA,
    "aplica_iva",
    "rol_ingreso",
    "bloque_fiscal",
    "activo",
)
BLOQUES_FISCALES = ("RECIBO_CAJA", "FACTURA")


def normalizar_concepto(concepto: str) -> str:
    """Se guarda como lo escribió Pricing, con btrim y espacios internos colapsados (A4)."""
    return " ".join(concepto.split())


def _clave_recargo(datos: dict[str, Any]) -> list:
    return [
        Recargo.proveedor_id.is_not_distinct_from(datos.get("proveedor_id")),
        Recargo.puerto_id.is_not_distinct_from(datos.get("puerto_id")),
        Recargo.lado == datos["lado"],
        Recargo.bloque_incoterm == datos["bloque_incoterm"],
        func.lower(Recargo.concepto) == datos["concepto"].lower(),
        Recargo.modo.is_not_distinct_from(datos.get("modo")),
        Recargo.tipo_equipo_id.is_not_distinct_from(datos.get("tipo_equipo_id")),
    ]


def bloque_fiscal_por_regla(puerto: Puerto | None, bloque_incoterm: str) -> str | None:
    """La regla de antes (D-F3-4): seguro → Recibo de Caja; Ecuador → Factura; exterior → Recibo de Caja."""
    if bloque_incoterm == "SEGURO":
        return "RECIBO_CAJA"
    if puerto is None:
        return None
    return "FACTURA" if puerto.pais.iso2 == "EC" else "RECIBO_CAJA"


def _tarifas_de(db: Session, ids: list[int]) -> list[Tarifa]:
    salida = []
    for tarifa_id in dict.fromkeys(ids):
        tarifa = db.get(Tarifa, tarifa_id)
        if tarifa is None:
            raise ErrorNegocio(422, "TARIFA_INEXISTENTE", f"La tarifa {tarifa_id} no existe")
        salida.append(tarifa)
    return salida


def _servicios_de(db: Session, codigos: list[str]) -> list[Servicio]:
    salida = []
    for codigo in dict.fromkeys(codigos):
        servicio = db.scalars(select(Servicio).where(Servicio.codigo == codigo)).one_or_none()
        if servicio is None:
            raise ErrorNegocio(422, "SERVICIO_INEXISTENTE", f"El servicio {codigo} no existe")
        salida.append(servicio)
    return salida


def _validar_recargo(db: Session, datos: dict[str, Any], excluir_id: int | None = None) -> dict[str, Any]:
    activo = datos.get("activo", True)
    modo = datos.get("modo")
    servicio = servicios.servicio_utilizable(db, modo, activo) if modo is not None else None
    tarifas = _tarifas_de(db, datos.get("tarifas_ids") or [])
    vinculados_servicio = _servicios_de(db, datos.get("servicios") or [])
    datos["_tarifas"], datos["_servicios"] = tarifas, vinculados_servicio
    puerto = None
    if datos.get("puerto_id") is not None:
        puerto = referencia_activa(db, Puerto, datos["puerto_id"], "el puerto", activo)
    elif not tarifas:
        raise ErrorNegocio(422, "PUERTO_REQUERIDO",
                           "Elija el puerto o vincule el recargo a una tarifa (toma el puerto de la tarifa)")
    for tarifa in tarifas:
        if datos.get("proveedor_id") is not None and tarifa.proveedor_id != datos["proveedor_id"]:
            raise ErrorNegocio(422, "VINCULO_OTRO_PROVEEDOR",
                               f"La tarifa {tarifa.id} es de otro proveedor; el recargo debe ser del mismo o propio de XPRESS")
        if modo is not None and tarifa.modo != modo:
            raise ErrorNegocio(422, "VINCULO_OTRO_SERVICIO", f"La tarifa {tarifa.id} es de {tarifa.modo}, no de {modo}")
    if vinculados_servicio and modo is not None and any(s.codigo != modo for s in vinculados_servicio):
        raise ErrorNegocio(422, "VINCULO_OTRO_SERVICIO", "Con servicios vinculados, deje el servicio del recargo en «todos»")
    # D-R3: el bloque fiscal lo elige Pricing; el seguro va siempre en Recibo de Caja.
    if datos["bloque_incoterm"] == "SEGURO":
        datos["bloque_fiscal"] = "RECIBO_CAJA"
    elif datos.get("bloque_fiscal") is None:
        datos["bloque_fiscal"] = bloque_fiscal_por_regla(puerto, datos["bloque_incoterm"])
        if datos["bloque_fiscal"] is None:
            raise ErrorNegocio(422, "BLOQUE_FISCAL_REQUERIDO", "Elija si el recargo va en Recibo de Caja o en Factura")
    if datos["bloque_fiscal"] not in BLOQUES_FISCALES:
        raise ErrorNegocio(422, "BLOQUE_FISCAL_INVALIDO", "El bloque fiscal es Recibo de Caja o Factura")
    if datos["bloque_fiscal"] == "RECIBO_CAJA":
        datos["aplica_iva"] = False  # el Recibo de Caja va con IVA 0%
    # Sin puerto, las unidades y el tipo de ubicación salen del servicio de la primera tarifa vinculada.
    referencia_servicio = servicio or (servicios.servicio_utilizable(db, tarifas[0].modo, False) if puerto is None else None)
    if datos.get("proveedor_id") is not None:
        referencia_activa(db, Proveedor, datos["proveedor_id"], "el proveedor", activo)
    moneda = referencia_activa(db, Moneda, datos["moneda_id"], "la moneda", activo)

    datos["concepto"] = normalizar_concepto(datos["concepto"])
    if not datos["concepto"]:
        raise ErrorNegocio(422, "CONCEPTO_INVALIDO", "El concepto no puede estar vacío")
    if len(datos["concepto"]) > 120:
        raise ErrorNegocio(422, "CONCEPTO_INVALIDO", "El concepto admite como máximo 120 caracteres")
    if datos["bloque_incoterm"] not in LADO_BLOQUES[datos["lado"]]:
        raise ErrorNegocio(
            422, "LADO_BLOQUE_INCOHERENTE", f"El bloque {datos['bloque_incoterm']} no corresponde al lado {datos['lado']}"
        )

    if servicio is not None and puerto is not None:
        esperado = servicio.tipo_ubicacion_origen if datos["lado"] == "ORIGEN" else servicio.tipo_ubicacion_destino
        if puerto.tipo != esperado:
            raise ErrorNegocio(
                422,
                "PUERTO_MODO_INCONSISTENTE",
                f"El servicio {servicio.nombre} va de {servicio.origen.nombre.lower()} a "
                f"{servicio.destino.nombre.lower()}; este puerto es {puerto.tipo_ubicacion.nombre.lower()}",
            )
    if datos.get("tipo_equipo_id") is not None:
        if servicio is None:
            raise ErrorNegocio(
                422, "TIPO_EQUIPO_NO_PERMITIDO", "Solo los recargos de un servicio con tipo de equipo llevan tipo de equipo"
            )
        validar_tipo_equipo(db, servicio, datos["tipo_equipo_id"], "Los recargos", activo)

    # D-F3-3: el seguro va por envío o como % del valor (PCT_VALOR, solo en USD; el costo es el porcentaje).
    if datos["rate_unit"] == "PCT_VALOR" and datos["bloque_incoterm"] != "SEGURO":
        raise ErrorNegocio(422, "PCT_VALOR_SOLO_SEGURO", "El % del valor de la mercancía solo se usa en el seguro")
    if datos["bloque_incoterm"] == "SEGURO" and datos["rate_unit"] not in UNIDADES_SEGURO:
        raise ErrorNegocio(
            422, "SEGURO_UNIDAD_INVALIDA", "El seguro se registra por envío o como % del valor de la mercancía"
        )
    if datos["rate_unit"] == "PCT_VALOR":
        if moneda.codigo != "USD":
            raise ErrorNegocio(422, "PCT_VALOR_SOLO_USD", "El seguro como % del valor se registra en USD")
        permitidas = UNIDADES_SEGURO
    elif datos["rate_unit"] == "PCT_RECIBO":
        if moneda.codigo != "USD":
            raise ErrorNegocio(422, "PCT_RECIBO_SOLO_USD", "El % sobre el Recibo de Caja se registra en USD")
        permitidas = {"PCT_RECIBO"}
    else:
        permitidas = (
            set(servicios.forma_de(referencia_servicio).unidades_recargo)
            if referencia_servicio is not None
            else servicios.unidades_recargo_sin_servicio(db, puerto.tipo)
        )
    if datos["rate_unit"] not in permitidas:
        referencia = (f"el servicio {referencia_servicio.codigo}" if referencia_servicio is not None
                      else f"un {puerto.tipo_ubicacion.nombre.lower()}")
        raise ErrorNegocio(
            422,
            "RATE_UNIT_INCOMPATIBLE",
            f"Con {referencia} la unidad debe ser una de: {', '.join(sorted(permitidas))}",
        )

    validar_venta(datos)
    if activo and puerto is not None:  # sin puerto (vinculado a tarifas) no hay superposición por puerto
        conflicto = superpuesta(
            db, Recargo, _clave_recargo(datos), datos["valido_desde"], datos["valido_hasta"], excluir_id
        )
        if conflicto is not None:
            raise error_superposicion(conflicto, "el recargo")
    return datos


def _consulta_recargos():
    return select(Recargo).options(
        selectinload(Recargo.proveedor),
        selectinload(Recargo.moneda),
        selectinload(Recargo.puerto),
        selectinload(Recargo.tipo_equipo),
        selectinload(Recargo.vinculos_tarifa).selectinload(RecargoTarifa.tarifa),
        selectinload(Recargo.vinculos_servicio).selectinload(RecargoServicio.servicio),
    )


def etiqueta_tarifa(tarifa: Tarifa) -> str:
    tipo = f" {tarifa.tipo_equipo.codigo}" if tarifa.tipo_equipo else ""
    return (f"#{tarifa.id} {tarifa.modo}{tipo} {tarifa.origen.codigo} → {tarifa.destino.codigo} · "
            f"hasta {tarifa.valido_hasta.strftime('%d/%m/%Y')}")


def advertencias(db: Session, datos: dict[str, Any]) -> list[str]:
    """Coherencia del puerto con el lado (no bloquea): el error de producción fue un gasto de destino en Shanghái."""
    if datos.get("puerto_id") is None or datos.get("lado") is None:
        return []
    puerto = db.get(Puerto, datos["puerto_id"])
    if puerto is None:
        return []
    pais = f"{puerto.pais.nombre} ({puerto.codigo})"
    if datos["lado"] == "DESTINO" and puerto.pais.iso2 != "EC":
        return [f"¿Seguro? Este gasto de destino está en un puerto de {pais}. En importaciones a Ecuador, el destino "
                "es un puerto ecuatoriano. Si es para una tarifa, vincúlelo a ella y el puerto se toma solo."]
    if datos["lado"] == "ORIGEN" and puerto.pais.iso2 == "EC":
        return [f"¿Seguro? Este gasto de origen está en un puerto de {pais}. En importaciones, el origen es el puerto "
                "del exterior."]
    return []


def presentar_recargo(recargo: Recargo, nivel: str, hoy: date, dias: int):
    venta, venta_minima = precios_de(recargo)
    datos = {
        "id": recargo.id,
        "proveedor": Referencia.model_validate(recargo.proveedor) if recargo.proveedor else None,
        "puerto": PuertoRef.model_validate(recargo.puerto) if recargo.puerto else None,
        "lado": recargo.lado,
        "bloque_incoterm": recargo.bloque_incoterm,
        "concepto": recargo.concepto,
        "modo": recargo.modo,
        "tipo_equipo": TipoEquipoRef.model_validate(recargo.tipo_equipo) if recargo.tipo_equipo else None,
        "rate_unit": recargo.rate_unit,
        "moneda": recargo.moneda.codigo,
        "precio_venta": venta,
        "precio_venta_minimo": venta_minima,
        "aplica_iva": recargo.aplica_iva,
        "rol_ingreso": recargo.rol_ingreso,
        "bloque_fiscal": recargo.bloque_fiscal,
        "tarifas_vinculadas": [{"id": v.tarifa_id, "etiqueta": etiqueta_tarifa(v.tarifa)} for v in recargo.vinculos_tarifa],
        "servicios_vinculados": [v.servicio.codigo for v in recargo.vinculos_servicio],
        "valido_desde": recargo.valido_desde,
        "valido_hasta": recargo.valido_hasta,
        "estado_vigencia": estado_vigencia(recargo.valido_desde, recargo.valido_hasta, hoy, dias),
        "activo": recargo.activo,
        "creado_en": recargo.creado_en,
        "actualizado_en": recargo.actualizado_en,
    }
    if nivel == NIVEL_VENTA:
        return RecargoVenta(**datos)
    datos |= campos_de_costo(recargo)
    if nivel == NIVEL_COSTO:
        return RecargoCosto(**datos)
    unitario, pct = precio_venta.margen(venta, recargo.costo)
    return RecargoCostoMargen(**datos, margen_unitario=unitario, margen_pct=pct)


def _presentar(db: Session, usuario: Usuario, recargo: Recargo):
    db.refresh(recargo)
    return presentar_recargo(recargo, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db))


def obtener_recargo(db: Session, recargo_id: int) -> Recargo:
    recargo = db.scalars(_consulta_recargos().where(Recargo.id == recargo_id)).one_or_none()
    if recargo is None:
        raise ErrorNegocio(404, "RECARGO_NO_ENCONTRADO", "Recargo no encontrado")
    return recargo


def detalle_recargo(db: Session, usuario: Usuario, recargo_id: int):
    recargo = obtener_recargo(db, recargo_id)
    return presentar_recargo(recargo, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db))


def listar_recargos(
    db: Session,
    usuario: Usuario,
    puerto: int | None = None,
    lado: str | None = None,
    bloque: str | None = None,
    proveedor: int | None = None,
    modo: str | None = None,
    vigente_en: date | None = None,
    por_vencer: bool | None = None,
    activo: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
    total: list[int] | None = None,
):
    """F5-A2: con limit/offset pagina en SQL (mismos filtros); `total`, si se pasa, recibe el conteo sin paginar."""
    hoy, dias = fechas.hoy_ecuador(), dias_alerta(db)
    filtros = filtros_vigencia(Recargo, vigente_en, por_vencer, hoy, dias)
    for columna, valor in (
        (Recargo.puerto_id, puerto),
        (Recargo.lado, lado),
        (Recargo.bloque_incoterm, bloque),
        (Recargo.proveedor_id, proveedor),
        (Recargo.modo, modo),
    ):
        if valor is not None:
            filtros.append(columna == valor)
    if activo is not None:
        filtros.append(Recargo.activo.is_(activo))
    if total is not None:
        total.append(db.scalar(select(func.count()).select_from(Recargo).where(*filtros)))
    consulta = _consulta_recargos().where(*filtros).order_by(Recargo.puerto_id, Recargo.lado, Recargo.id)
    if limit is not None:
        consulta = consulta.limit(limit).offset(offset)
    recargos = db.scalars(consulta)
    nivel = nivel_de(usuario)
    return [presentar_recargo(r, nivel, hoy, dias) for r in recargos]


def _vinculos(recargo: Recargo) -> dict[str, list]:
    return {"tarifas": sorted(v.tarifa_id for v in recargo.vinculos_tarifa),
            "servicios": sorted(v.servicio.codigo for v in recargo.vinculos_servicio)}


def _aplicar_vinculos(db: Session, actor: Usuario, recargo: Recargo, tarifas: list[Tarifa] | None,
                      servicios_: list[Servicio] | None) -> None:
    """Deja exactamente los vínculos pedidos (None = no tocar) y audita cada alta y cada baja."""
    actor_id = auditoria.id_de(actor)
    if tarifas is not None:
        pedidos = {t.id for t in tarifas}
        for vinculo in list(recargo.vinculos_tarifa):
            if vinculo.tarifa_id not in pedidos:
                recargo.vinculos_tarifa.remove(vinculo)
                auditoria.registrar(db, actor, "recargo", recargo.id, "EDITAR", antes={"tarifa_id": vinculo.tarifa_id},
                                    nota=f"DESVINCULAR TARIFA {vinculo.tarifa_id}")
        actuales = {v.tarifa_id for v in recargo.vinculos_tarifa}
        for tarifa in tarifas:
            if tarifa.id not in actuales:
                recargo.vinculos_tarifa.append(RecargoTarifa(tarifa_id=tarifa.id, creado_por=actor_id))
                auditoria.registrar(db, actor, "recargo", recargo.id, "EDITAR", despues={"tarifa_id": tarifa.id},
                                    nota=f"VINCULAR TARIFA {tarifa.id}")
    if servicios_ is not None:
        pedidos = {s.id for s in servicios_}
        for vinculo in list(recargo.vinculos_servicio):
            if vinculo.servicio_id not in pedidos:
                recargo.vinculos_servicio.remove(vinculo)
                auditoria.registrar(db, actor, "recargo", recargo.id, "EDITAR", antes={"servicio_id": vinculo.servicio_id},
                                    nota=f"DESVINCULAR SERVICIO {vinculo.servicio_id}")
        actuales = {v.servicio_id for v in recargo.vinculos_servicio}
        for servicio in servicios_:
            if servicio.id not in actuales:
                recargo.vinculos_servicio.append(RecargoServicio(servicio_id=servicio.id, creado_por=actor_id))
                auditoria.registrar(db, actor, "recargo", recargo.id, "EDITAR", despues={"servicio": servicio.codigo},
                                    nota=f"VINCULAR SERVICIO {servicio.codigo}")
    enviar(db)


def crear_recargo(db: Session, actor: Usuario, datos: dict[str, Any]):
    actor_id = auditoria.id_de(actor)
    datos = _validar_recargo(db, dict(datos) | {"activo": True})
    recargo = Recargo(**{campo: datos.get(campo) for campo in CAMPOS_RECARGO}, creado_por=actor_id)
    db.add(recargo)
    enviar(db)
    auditoria.registrar(db, actor, "recargo", recargo.id, "CREAR", despues=foto(recargo, CAMPOS_RECARGO))
    _aplicar_vinculos(db, actor, recargo, datos["_tarifas"], datos["_servicios"])
    confirmar(db)
    return _presentar(db, actor, recargo)


def actualizar_recargo(db: Session, actor: Usuario, recargo_id: int, cambios: dict[str, Any]):
    recargo = obtener_recargo(db, recargo_id)
    vigentes = _vinculos(recargo)
    base = {campo: getattr(recargo, campo) for campo in CAMPOS_RECARGO}
    base |= {"tarifas_ids": vigentes["tarifas"], "servicios": vigentes["servicios"]}
    final = _validar_recargo(db, base | cambios, excluir_id=recargo.id)
    antes = foto(recargo, CAMPOS_RECARGO)
    with db.no_autoflush:
        for campo in cambios:
            if campo in CAMPOS_RECARGO:
                setattr(recargo, campo, final[campo])
        for campo in ("bloque_fiscal", "aplica_iva"):  # el seguro y el Recibo de Caja los ajusta la validación
            setattr(recargo, campo, final[campo])
        _aplicar_vinculos(db, actor, recargo, final["_tarifas"] if "tarifas_ids" in cambios else None,
                          final["_servicios"] if "servicios" in cambios else None)
        despues = foto(recargo, CAMPOS_RECARGO)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "recargo", recargo_id, accion, antes=antes, despues=despues)
    confirmar(db)
    return _presentar(db, actor, recargo)


# ---------- Vínculos desde la ficha de la tarifa (D-R2) ----------


def recargos_de_tarifa(db: Session, usuario: Usuario, tarifa_id: int) -> list:
    if db.get(Tarifa, tarifa_id) is None:
        raise ErrorNegocio(404, "TARIFA_NO_ENCONTRADA", "Tarifa no encontrada")
    consulta = _consulta_recargos().join(RecargoTarifa, RecargoTarifa.recargo_id == Recargo.id).where(
        RecargoTarifa.tarifa_id == tarifa_id).order_by(Recargo.bloque_incoterm, Recargo.id)
    hoy, dias, nivel = fechas.hoy_ecuador(), dias_alerta(db), nivel_de(usuario)
    return [presentar_recargo(r, nivel, hoy, dias) for r in db.scalars(consulta)]


def vincular(db: Session, actor: Usuario, tarifa_id: int, recargo_id: int, vincular_: bool):
    """Vincula o desvincula un recargo de una tarifa (con las mismas validaciones del formulario y auditoría)."""
    recargo = obtener_recargo(db, recargo_id)
    if db.get(Tarifa, tarifa_id) is None:
        raise ErrorNegocio(404, "TARIFA_NO_ENCONTRADA", "Tarifa no encontrada")
    actuales = [v.tarifa_id for v in recargo.vinculos_tarifa]
    pedidos = sorted(set(actuales) | {tarifa_id}) if vincular_ else [i for i in actuales if i != tarifa_id]
    if pedidos == sorted(actuales):
        return _presentar(db, actor, recargo)
    if not pedidos and recargo.puerto_id is None:
        raise ErrorNegocio(422, "PUERTO_REQUERIDO",
                           "Este recargo no tiene puerto: no se puede quitar su única tarifa. Edítelo y elija un puerto")
    return actualizar_recargo(db, actor, recargo_id, {"tarifas_ids": pedidos})

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
- D-A1 (0016): alcance en cadena (services/alcance.py): servicio, modo, tipo de contenedor, región, país, puerto, ruta,
  proveedor, tipo de carga y clase IMO, cada uno multiselección ("Todos" = sin valores). Las columnas de antes
  (puerto_id, modo, tipo_equipo_id) quedan como copia del valor cuando el nivel tiene uno solo; el dueño del cargo
  (proveedor_id) fija el nivel PROVEEDOR.
"""
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import (
    Moneda,
    Pais,
    Proveedor,
    Puerto,
    Recargo,
    RecargoAlcance,
    RecargoTarifa,
    Region,
    Servicio,
    Tarifa,
    TipoCarga,
    TipoEquipo,
    Usuario,
)
from app.models.geografia import TipoUbicacion
from app.services import alcance as alcance_svc
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
    "alcance_firma",
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
        Recargo.alcance_firma == datos.get("alcance_firma", ""),
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


def alcance_api(alc: dict[str, set]) -> dict[str, list]:
    """nivel → clave del JSON, con los valores ordenados."""
    return {alcance_svc.CLAVE_API[nivel]: sorted(valores, key=str) for nivel, valores in alc.items() if valores}


def _alcance_de_entrada(entrada: dict[str, Any]) -> dict[str, set]:
    por_clave = {v: k for k, v in alcance_svc.CLAVE_API.items()}
    salida: dict[str, set] = {}
    for clave, valores in (entrada or {}).items():
        nivel = por_clave.get(clave)
        if nivel is None:
            raise ErrorNegocio(422, "ALCANCE_INVALIDO", f"Nivel de alcance desconocido: {clave}")
        if not isinstance(valores, list):
            raise ErrorNegocio(422, "ALCANCE_INVALIDO", f"El nivel {clave} es una lista")
        if valores:
            salida[nivel] = {str(v).strip().upper() for v in valores} if nivel in alcance_svc.NIVELES_TEXTO else {int(v) for v in valores}
    return salida


def _validar_alcance(db: Session, alc: dict[str, set]) -> None:
    """Cada valor existe; la ruta lleva origen y destino; la clase IMO, solo con un tipo de carga que pide datos IMO."""
    for nivel, modelo, que in (("REGION", Region, "región"), ("PAIS", Pais, "país"), ("PUERTO", Puerto, "puerto"),
                               ("PUERTO_ORIGEN", Puerto, "puerto de origen"), ("PUERTO_DESTINO", Puerto, "puerto de destino"),
                               ("PROVEEDOR", Proveedor, "proveedor"), ("TIPO_EQUIPO", TipoEquipo, "tipo de contenedor")):
        for valor in alc.get(nivel, ()):
            if db.get(modelo, valor) is None:
                raise ErrorNegocio(422, "ALCANCE_INVALIDO", f"El {que} {valor} no existe")
    for codigo in alc.get("SERVICIO", ()):
        if db.scalars(select(Servicio).where(Servicio.codigo == codigo)).one_or_none() is None:
            raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"El servicio {codigo} no existe")
    for codigo in alc.get("MODO", ()):
        if db.scalars(select(TipoUbicacion).where(TipoUbicacion.codigo == codigo)).one_or_none() is None:
            raise ErrorNegocio(422, "ALCANCE_INVALIDO", f"El modo {codigo} no existe")
    tipos_carga = {t.codigo: t for t in db.scalars(select(TipoCarga))}
    for codigo in alc.get("TIPO_CARGA", ()):
        if codigo not in tipos_carga:
            raise ErrorNegocio(422, "ALCANCE_INVALIDO", f"El tipo de carga {codigo} no existe")
    if ("PUERTO_ORIGEN" in alc) != ("PUERTO_DESTINO" in alc):
        raise ErrorNegocio(422, "RUTA_INCOMPLETA", "La ruta exacta exige puerto de origen y puerto de destino")
    if "CLASE_IMO" in alc:
        if not any(tipos_carga[c].pide_imo for c in alc.get("TIPO_CARGA", ())):
            raise ErrorNegocio(422, "CLASE_IMO_SIN_TIPO", "La clase IMO va con un tipo de carga que pide datos IMO (por ejemplo IMO)")
        if any(c not in {str(n) for n in range(1, 10)} for c in alc["CLASE_IMO"]):
            raise ErrorNegocio(422, "CLASE_IMO_INVALIDA", "La clase IMO es un número del 1 al 9")
    if "TIPO_EQUIPO" in alc:
        servicios_con_equipo = [s for s in alc.get("SERVICIO", ()) if (sv := db.scalars(select(Servicio).where(
            Servicio.codigo == s)).one_or_none()) is not None and sv.usa_tipo_equipo]
        if len(alc.get("SERVICIO", ())) != 1 or not servicios_con_equipo:
            raise ErrorNegocio(422, "TIPO_EQUIPO_NO_PERMITIDO",
                               "El tipo de contenedor va con un único servicio que use tipo de equipo (por ejemplo FCL)")


def _alcance_final(recargo: Recargo | None, datos: dict[str, Any], cambios: dict[str, Any] | None) -> dict[str, set]:
    """El alcance pedido: el explícito ("alcance"), o el de antes ajustado por los campos sueltos (puerto_id, modo,
    tipo_equipo_id, servicios). El dueño del cargo (proveedor_id) siempre fija el nivel PROVEEDOR."""
    if "alcance" in (cambios if cambios is not None else datos) and datos.get("alcance") is not None:
        alc = _alcance_de_entrada(datos["alcance"])
    else:
        alc = {k: set(v) for k, v in alcance_svc.de(recargo).items()} if recargo is not None else {}
        sueltos = cambios if cambios is not None else datos
        for campo, nivel in (("puerto_id", "PUERTO"), ("tipo_equipo_id", "TIPO_EQUIPO")):
            if campo in sueltos:
                alc.pop(nivel, None)
                if datos.get(campo) is not None:
                    alc[nivel] = {int(datos[campo])}
        if "modo" in sueltos or "servicios" in sueltos:
            alc.pop("SERVICIO", None)
            codigos = {c for c in ([datos.get("modo")] + list(datos.get("servicios") or [])) if c}
            if codigos:
                alc["SERVICIO"] = set(codigos)
    alc.pop("PROVEEDOR", None) if datos.get("proveedor_id") is not None else None
    if datos.get("proveedor_id") is not None:
        alc["PROVEEDOR"] = {datos["proveedor_id"]}
    elif recargo is not None and recargo.proveedor_id is not None and cambios is not None and "proveedor_id" in cambios:
        alc.get("PROVEEDOR", set()).discard(recargo.proveedor_id)
        if not alc.get("PROVEEDOR"):
            alc.pop("PROVEEDOR", None)
    return alc


def _validar_recargo(db: Session, datos: dict[str, Any], excluir_id: int | None = None,
                     recargo: Recargo | None = None, cambios: dict[str, Any] | None = None) -> dict[str, Any]:
    activo = datos.get("activo", True)
    tarifas = _tarifas_de(db, datos.get("tarifas_ids") or [])
    # D-A1: el alcance manda; las columnas de antes son la copia del valor único de cada nivel.
    alc = _alcance_final(recargo, datos, cambios)
    _validar_alcance(db, alc)
    datos["puerto_id"] = next(iter(alc["PUERTO"])) if len(alc.get("PUERTO", ())) == 1 else None
    datos["modo"] = next(iter(alc["SERVICIO"])) if len(alc.get("SERVICIO", ())) == 1 else None
    datos["tipo_equipo_id"] = next(iter(alc["TIPO_EQUIPO"])) if len(alc.get("TIPO_EQUIPO", ())) == 1 else None
    datos["_tarifas"], datos["_alcance"] = tarifas, alc
    datos["alcance_firma"] = alcance_svc.firma(alc, datos["puerto_id"], datos["modo"], datos["tipo_equipo_id"],
                                               datos.get("proveedor_id"))
    modo = datos.get("modo")
    servicio = servicios.servicio_utilizable(db, modo, activo) if modo is not None else None
    puerto = None
    if datos.get("puerto_id") is not None:
        puerto = referencia_activa(db, Puerto, datos["puerto_id"], "el puerto", activo)
    for tarifa in tarifas:
        if datos.get("proveedor_id") is not None and tarifa.proveedor_id != datos["proveedor_id"]:
            raise ErrorNegocio(422, "VINCULO_OTRO_PROVEEDOR",
                               f"La tarifa {tarifa.id} es de otro proveedor; el recargo debe ser del mismo o propio de XPRESS")
        if modo is not None and tarifa.modo != modo:
            raise ErrorNegocio(422, "VINCULO_OTRO_SERVICIO", f"La tarifa {tarifa.id} es de {tarifa.modo}, no de {modo}")
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
    # Unidades: las del servicio (único); con varios, las comunes; sin servicio, las del modo, del puerto o de la
    # primera tarifa vinculada; sin nada de eso, las de cualquier servicio que no exija tipo de equipo.
    referencia_servicio = servicio
    if referencia_servicio is None and puerto is None and tarifas:
        referencia_servicio = servicios.servicio_utilizable(db, tarifas[0].modo, False)
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
        if referencia_servicio is not None:
            permitidas = set(servicios.forma_de(referencia_servicio).unidades_recargo)
            referencia = f"el servicio {referencia_servicio.codigo}"
        elif len(alc.get("SERVICIO", ())) > 1:
            conjuntos = [set(servicios.forma_de(servicios.servicio_utilizable(db, c, False)).unidades_recargo)
                         for c in alc["SERVICIO"]]
            permitidas = set.intersection(*conjuntos)
            referencia = "los servicios elegidos"
        elif len(alc.get("MODO", ())) == 1:
            permitidas = servicios.unidades_recargo_sin_servicio(db, next(iter(alc["MODO"])))
            referencia = "ese modo"
        elif puerto is not None:
            permitidas = servicios.unidades_recargo_sin_servicio(db, puerto.tipo)
            referencia = f"un {puerto.tipo_ubicacion.nombre.lower()}"
        else:
            permitidas = set().union(*(servicios.unidades_recargo_sin_servicio(db, t.codigo)
                                       for t in db.scalars(select(TipoUbicacion))))
            referencia = "cualquier servicio"
    if datos["rate_unit"] not in permitidas:
        raise ErrorNegocio(
            422,
            "RATE_UNIT_INCOMPATIBLE",
            f"Con {referencia} la unidad debe ser una de: {', '.join(sorted(permitidas))}",
        )

    validar_venta(datos)
    if activo:  # D-A1: con la huella del alcance, dos alcances distintos del mismo concepto no se superponen
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
        selectinload(Recargo.alcance),
    )


def nombres_alcance(db: Session) -> dict[str, dict]:
    """Nombres legibles de todos los valores posibles del alcance (para el resumen "Aplica a")."""
    return {
        "PUERTO": {p.id: p.codigo for p in db.scalars(select(Puerto))},
        "PAIS": {p.id: p.nombre for p in db.scalars(select(Pais))},
        "REGION": {r.id: r.nombre for r in db.scalars(select(Region))},
        "PROVEEDOR": {p.id: p.nombre for p in db.scalars(select(Proveedor))},
        "TIPO_EQUIPO": {t.id: t.codigo for t in db.scalars(select(TipoEquipo))},
        "MODO": {t.codigo: t.nombre for t in db.scalars(select(TipoUbicacion))},
        "TIPO_CARGA": {t.codigo: t.nombre for t in db.scalars(select(TipoCarga))},
    }


def etiqueta_tarifa(tarifa: Tarifa) -> str:
    tipo = f" {tarifa.tipo_equipo.codigo}" if tarifa.tipo_equipo else ""
    return (f"#{tarifa.id} {tarifa.modo}{tipo} {tarifa.origen.codigo} → {tarifa.destino.codigo} · "
            f"hasta {tarifa.valido_hasta.strftime('%d/%m/%Y')}")


def advertencias(db: Session, datos: dict[str, Any]) -> list[str]:
    """Coherencia de la ubicación con el lado (no bloquea): el error de producción fue un gasto de destino en Shanghái.
    D-A1: se revisan el puerto, los países y las regiones del alcance."""
    lado = datos.get("lado")
    if lado is None:
        return []
    try:
        alc = _alcance_de_entrada(datos.get("alcance") or {})
    except (ErrorNegocio, ValueError):
        alc = {}
    puertos = set(alc.get("PUERTO", set())) | ({int(datos["puerto_id"])} if datos.get("puerto_id") else set())
    lugares: list[tuple[str, bool]] = []  # (descripción, es Ecuador)
    for puerto_id in puertos:
        puerto = db.get(Puerto, puerto_id)
        if puerto is not None:
            lugares.append((f"un puerto de {puerto.pais.nombre} ({puerto.codigo})", puerto.pais.iso2 == "EC"))
    for pais_id in alc.get("PAIS", ()):
        pais = db.get(Pais, pais_id)
        if pais is not None:
            lugares.append((f"el país {pais.nombre}", pais.iso2 == "EC"))
    ecuador = db.scalars(select(Pais).where(Pais.iso2 == "EC")).one_or_none()
    for region_id in alc.get("REGION", ()):
        region = db.get(Region, region_id)
        if region is not None:
            lugares.append((f"la región {region.nombre}", ecuador is not None and ecuador.region_id == region.id))
    salida = []
    for descripcion, es_ecuador in lugares:
        if lado == "DESTINO" and not es_ecuador:
            salida.append(f"¿Seguro? Este gasto de destino está en {descripcion}. En importaciones a Ecuador, el destino "
                          "es un puerto ecuatoriano. Si es para una tarifa, vincúlelo a ella y el puerto se toma solo.")
        if lado == "ORIGEN" and es_ecuador:
            salida.append(f"¿Seguro? Este gasto de origen está en {descripcion}. En importaciones, el origen es el puerto "
                          "del exterior.")
    return salida


def presentar_recargo(recargo: Recargo, nivel: str, hoy: date, dias: int, nombres: dict[str, dict] | None = None):
    venta, venta_minima = precios_de(recargo)
    alc = alcance_svc.de(recargo)
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
        "servicios_vinculados": sorted(alc.get("SERVICIO", set())),
        "alcance": alcance_api(alc),
        "aplica_a": alcance_svc.resumen(alc, recargo.lado, nombres, len(recargo.vinculos_tarifa)),
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
    return presentar_recargo(recargo, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db), nombres_alcance(db))


def obtener_recargo(db: Session, recargo_id: int) -> Recargo:
    recargo = db.scalars(_consulta_recargos().where(Recargo.id == recargo_id)).one_or_none()
    if recargo is None:
        raise ErrorNegocio(404, "RECARGO_NO_ENCONTRADO", "Recargo no encontrado")
    return recargo


def detalle_recargo(db: Session, usuario: Usuario, recargo_id: int):
    recargo = obtener_recargo(db, recargo_id)
    return presentar_recargo(recargo, nivel_de(usuario), fechas.hoy_ecuador(), dias_alerta(db), nombres_alcance(db))


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
    aplica_en: int | None = None,
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
    if aplica_en is not None:
        # D-A1: "todo lo que aplica a ECGYE": su puerto, su país, su región, una ruta que lo incluya, o sin ubicación.
        puerto = db.get(Puerto, aplica_en)
        if puerto is not None:
            ubicacion = select(RecargoAlcance.recargo_id).where(
                ((RecargoAlcance.nivel.in_(("PUERTO", "PUERTO_ORIGEN", "PUERTO_DESTINO"))) & (RecargoAlcance.valor_id == puerto.id))
                | ((RecargoAlcance.nivel == "PAIS") & (RecargoAlcance.valor_id == puerto.pais_id))
                | ((RecargoAlcance.nivel == "REGION") & (RecargoAlcance.valor_id == puerto.pais.region_id)))
            con_ubicacion = select(RecargoAlcance.recargo_id).where(
                RecargoAlcance.nivel.in_(("PUERTO", "PUERTO_ORIGEN", "PUERTO_DESTINO", "PAIS", "REGION")))
            filtros.append(Recargo.id.in_(ubicacion) | Recargo.id.not_in(con_ubicacion))
    if total is not None:
        total.append(db.scalar(select(func.count()).select_from(Recargo).where(*filtros)))
    consulta = _consulta_recargos().where(*filtros).order_by(Recargo.puerto_id, Recargo.lado, Recargo.id)
    if limit is not None:
        consulta = consulta.limit(limit).offset(offset)
    recargos = db.scalars(consulta)
    nivel, nombres = nivel_de(usuario), nombres_alcance(db)
    return [presentar_recargo(r, nivel, hoy, dias, nombres) for r in recargos]


def _vinculos(recargo: Recargo) -> dict[str, list]:
    return {"tarifas": sorted(v.tarifa_id for v in recargo.vinculos_tarifa)}


def _aplicar_alcance(db: Session, actor: Usuario, recargo: Recargo, alc: dict[str, set]) -> None:
    """Deja exactamente el alcance pedido y audita el cambio (antes/después por nivel)."""
    antes = alcance_api(alcance_svc.de(recargo))
    despues = alcance_api(alc)
    if antes == despues:
        return
    recargo.alcance.clear()
    enviar(db)
    for nivel, valores in alc.items():
        for valor in sorted(valores, key=str):
            texto = nivel in alcance_svc.NIVELES_TEXTO
            recargo.alcance.append(RecargoAlcance(nivel=nivel, valor_texto=valor if texto else None,
                                                  valor_id=None if texto else valor))
    auditoria.registrar(db, actor, "recargo", recargo.id, "EDITAR", antes={"alcance": antes}, despues={"alcance": despues},
                        nota="ALCANCE")


def _aplicar_vinculos(db: Session, actor: Usuario, recargo: Recargo, tarifas: list[Tarifa] | None,
                      servicios_=None) -> None:
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
    enviar(db)


def crear_recargo(db: Session, actor: Usuario, datos: dict[str, Any]):
    actor_id = auditoria.id_de(actor)
    datos = _validar_recargo(db, dict(datos) | {"activo": True})
    recargo = Recargo(**{campo: datos.get(campo) for campo in CAMPOS_RECARGO}, creado_por=actor_id)
    # D-A1: el alcance se arma antes de insertar (así el valor por defecto del modelo no se aplica).
    for nivel, valores in datos["_alcance"].items():
        for valor in sorted(valores, key=str):
            texto = nivel in alcance_svc.NIVELES_TEXTO
            recargo.alcance.append(RecargoAlcance(nivel=nivel, valor_texto=valor if texto else None,
                                                  valor_id=None if texto else valor))
    db.add(recargo)
    enviar(db)
    auditoria.registrar(db, actor, "recargo", recargo.id, "CREAR",
                        despues=foto(recargo, CAMPOS_RECARGO) | {"alcance": alcance_api(datos["_alcance"])})
    _aplicar_vinculos(db, actor, recargo, datos["_tarifas"])
    confirmar(db)
    return _presentar(db, actor, recargo)


def actualizar_recargo(db: Session, actor: Usuario, recargo_id: int, cambios: dict[str, Any]):
    recargo = obtener_recargo(db, recargo_id)
    vigentes = _vinculos(recargo)
    base = {campo: getattr(recargo, campo) for campo in CAMPOS_RECARGO}
    base |= {"tarifas_ids": vigentes["tarifas"]}
    final = _validar_recargo(db, base | cambios, excluir_id=recargo.id, recargo=recargo, cambios=cambios)
    antes = foto(recargo, CAMPOS_RECARGO)
    with db.no_autoflush:
        for campo in cambios:
            if campo in CAMPOS_RECARGO:
                setattr(recargo, campo, final[campo])
        # el seguro y el Recibo de Caja los ajusta la validación; puerto, servicio y equipo son copia del alcance
        for campo in ("bloque_fiscal", "aplica_iva", "puerto_id", "modo", "tipo_equipo_id", "alcance_firma"):
            setattr(recargo, campo, final[campo])
        _aplicar_vinculos(db, actor, recargo, final["_tarifas"] if "tarifas_ids" in cambios else None)
        _aplicar_alcance(db, actor, recargo, final["_alcance"])
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
    return actualizar_recargo(db, actor, recargo_id, {"tarifas_ids": pedidos})

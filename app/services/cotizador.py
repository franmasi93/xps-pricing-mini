"""Motor de cotización (§10): única fuente de cálculo de cantidades, conversión, precios y totales.

Funciones puras (salvo `tasa_vigente`, que lee la tasa de la base). Las usan el borrador (vista en
vivo), la emisión (congelado) y el script de prueba. Reutiliza services/precio_venta.py y
services/tarifas.precio_venta_kg; no duplica fórmulas de venta.

Redondeo (H7, H8): peso cobrable a 3 decimales; W/M y CBM derivado a 4; unitarios, mínimos y
subtotales de línea en USD a 4; totales a 2, una sola vez sobre la suma; todo ROUND_HALF_UP.
"""
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ErrorNegocio
from app.core.unidades import kg_a_lb
from app.services import precio_venta, tasas

CERO = Decimal("0")
CIEN = Decimal("100")
TRES_DECIMALES = Decimal("0.001")
CUATRO_DECIMALES = Decimal("0.0001")
DOS_DECIMALES = Decimal("0.01")
FACTOR_VOLUMETRICO = Decimal("6000")  # D-F3-5: cm³ por kg, sin redondeo IATA a 0,5 kg
CM3_POR_M3 = Decimal("1000000")
KG_POR_TONELADA = Decimal("1000")

BLOQUES_ORIGEN = ("RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN")
BLOQUES_DESTINO = ("GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL")


def a_3(valor: Decimal) -> Decimal:
    return valor.quantize(TRES_DECIMALES, rounding=ROUND_HALF_UP)


def a_4(valor: Decimal) -> Decimal:
    return valor.quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def a_2(valor: Decimal) -> Decimal:
    return valor.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


# ---------- Carga y cantidades (§10.1) ----------


@dataclass(frozen=True)
class Bulto:
    cantidad: int
    largo_cm: Decimal
    ancho_cm: Decimal
    alto_cm: Decimal

    @property
    def volumen_cm3(self) -> Decimal:
        return self.cantidad * self.largo_cm * self.ancho_cm * self.alto_cm


@dataclass(frozen=True)
class Carga:
    modo: str
    peso_kg: Decimal = CERO
    cbm: Decimal | None = None
    dimensiones: tuple[Bulto, ...] = ()
    contenedores: dict[int, int] = field(default_factory=dict)  # tipo_equipo_id → cantidad
    valor_mercancia_usd: Decimal | None = None
    peso_lb: Decimal | None = None  # lo capturado en libras (H-F4-1); None si la carga se capturó en kg


def carga_incompleta(mensaje: str) -> ErrorNegocio:
    return ErrorNegocio(422, "CARGA_INCOMPLETA", mensaje)


def peso_volumetrico(carga: Carga) -> Decimal:
    """D-F3-5: Σ(cantidad × L × A × H cm) / 6000, a 3 decimales."""
    return a_3(sum((bulto.volumen_cm3 for bulto in carga.dimensiones), CERO) / FACTOR_VOLUMETRICO)


def peso_cobrable(carga: Carga) -> Decimal:
    """max(peso real, volumétrico), a 3 decimales."""
    return max(a_3(carga.peso_kg), peso_volumetrico(carga))


def peso_cobrable_en(carga: Carga, unidad: str) -> Decimal:
    """Peso cobrable en kg o en lb (D2). En lb: si gana el peso real y se capturó en libras, se usa lo capturado
    tal cual (H-F4-1, evita 224.999 por la ida y vuelta); si no, el cobrable en kg convertido a 3 decimales.
    """
    if unidad != "LB":
        return peso_cobrable(carga)
    real = a_3(carga.peso_kg)
    volumetrico = peso_volumetrico(carga)
    if carga.peso_lb is not None and real >= volumetrico:
        return a_3(carga.peso_lb)
    return kg_a_lb(max(real, volumetrico))


def cbm_de(carga: Carga) -> Decimal:
    """El CBM declarado o, si no viene, el derivado de las dimensiones (Σ L×A×H / 1.000.000), a 4 decimales."""
    if carga.cbm is not None:
        return a_4(carga.cbm)
    if carga.dimensiones:
        return a_4(sum((bulto.volumen_cm3 for bulto in carga.dimensiones), CERO) / CM3_POR_M3)
    raise carga_incompleta("Indique el CBM o las dimensiones de los bultos")


def peso_medida(carga: Carga) -> Decimal:
    """W/M de LCL = max(CBM, peso kg / 1000), a 4 decimales (H7)."""
    return max(cbm_de(carga), a_4(carga.peso_kg / KG_POR_TONELADA))


def total_contenedores(carga: Carga) -> int:
    return sum(carga.contenedores.values())


def cantidad_cobrable(carga: Carga) -> Decimal:
    """§10.1: AEREO → peso cobrable; LCL → W/M; FCL → total de contenedores."""
    if carga.modo == "AEREO":
        return peso_cobrable(carga)
    if carga.modo == "LCL":
        return peso_medida(carga)
    return Decimal(total_contenedores(carga))


def cantidad_por_unidad(
    rate_unit: str,
    carga: Carga,
    tipo_equipo_id: int | None = None,
    tipos: Iterable[int] | None = None,
    unidad_peso: str = "KG",
) -> Decimal:
    """Cantidad que se cobra según la unidad de la tarifa o del recargo.

    KG: el peso cobrable en la unidad de peso de la tarifa (kg o lb, D2).
    CONTENEDOR: los del tipo indicado; si no hay tipo, los de `tipos` (H6: un genérico que gana en
    varios tipos) o, sin `tipos`, el total.
    PCT_RECIBO no pasa por aquí: depende de las demás líneas (cantidad_pct_recibo).
    """
    if rate_unit == "KG":
        return peso_cobrable_en(carga, unidad_peso)
    if rate_unit == "CBM":
        return cbm_de(carga)
    if rate_unit == "WM":
        return peso_medida(carga)
    if rate_unit == "CONTENEDOR":
        if tipo_equipo_id is not None:
            return Decimal(carga.contenedores.get(tipo_equipo_id, 0))
        if tipos is not None:
            return Decimal(sum(carga.contenedores.get(tipo, 0) for tipo in set(tipos)))
        return Decimal(total_contenedores(carga))
    if rate_unit == "ENVIO":
        return Decimal("1")
    if rate_unit == "PCT_VALOR":
        if carga.valor_mercancia_usd is None:
            raise ErrorNegocio(
                422, "VALOR_MERCANCIA_REQUERIDO", "Indique el valor de la mercancía para el seguro como % del valor"
            )
        return a_4(carga.valor_mercancia_usd / CIEN)
    raise ErrorNegocio(422, "RATE_UNIT_INVALIDA", f"Unidad desconocida: {rate_unit}")


def tramo_aplicable(tramos: Iterable[Any], peso: Decimal):
    """El tramo de mayor desde_kg que no supera el peso cobrable, ambos en la unidad de la tarifa (el tramo 0
    siempre existe)."""
    candidatos = [tramo for tramo in tramos if Decimal(tramo.desde_kg) <= peso]
    if not candidatos:
        raise ErrorNegocio(422, "TRAMO_CERO_REQUERIDO", "La tarifa no tiene tramo para ese peso")
    return max(candidatos, key=lambda tramo: tramo.desde_kg)


# ---------- Moneda (§10.3) ----------


def tasa_vigente(db: Session, moneda_codigo: str, fecha: date) -> Decimal:
    """La misma tasa de services/tasas (USD = 1); sin tasa → 422 SIN_TASA con moneda y fecha (H3)."""
    try:
        return tasas.obtener_tasa_vigente(db, moneda_codigo, fecha)
    except ErrorNegocio as error:
        if error.codigo != "TASA_NO_DISPONIBLE":
            raise
        raise ErrorNegocio(
            422,
            "SIN_TASA",
            f"No hay tasa de {moneda_codigo} vigente al {fecha.isoformat()}; pida a Pricing que la registre",
            extra={"moneda": moneda_codigo, "fecha": fecha.isoformat()},
        ) from None


def a_usd(valor: Decimal, tasa: Decimal) -> Decimal:
    return a_4(valor * tasa)


# ---------- Línea (§10.4) ----------


@dataclass(frozen=True)
class Precios:
    """Unitarios y mínimos en la moneda original (salen de precio_venta.py)."""

    costo_unit: Decimal
    minimo: Decimal
    venta_unit: Decimal
    venta_minimo: Decimal


def precios_de_objeto(objeto, costo_unit: Decimal | None = None, venta_unit: Decimal | None = None) -> Precios:
    """Tarifa o recargo. Con tramos se pasan el costo y la venta por kg del tramo aplicable."""
    venta = venta_unit
    if venta is None:
        venta = precio_venta.precio_venta(
            objeto.metodo_venta, objeto.costo, objeto.parametro_venta, objeto.precio_venta_manual
        )
    minimo_venta = precio_venta.precio_venta_minimo(
        objeto.metodo_venta, objeto.minimo, objeto.parametro_venta, objeto.minimo_venta_manual
    )
    return Precios(
        costo_unit=costo_unit if costo_unit is not None else objeto.costo,
        minimo=objeto.minimo,
        venta_unit=venta,
        venta_minimo=minimo_venta,
    )


@dataclass(frozen=True)
class Calculo:
    cantidad: Decimal
    tasa: Decimal
    costo_usd: Decimal
    precio_calculado_unit_usd: Decimal
    precio_venta_unit_usd: Decimal
    minimo_venta_usd: Decimal
    subtotal_venta_usd: Decimal
    bajo_minimo_venta: bool
    bajo_costo: bool


def calcular_linea(cantidad: Decimal, precios: Precios, tasa: Decimal, ajuste_unit_usd: Decimal | None = None) -> Calculo:
    """Prioridad del precio (§10.4): ajuste manual > el método de la tarifa (MANUAL o fórmula).

    Costo: max(cantidad × costo unitario USD, mínimo USD). Venta: max(cantidad × precio USD, mínimo
    de venta USD). Con ajuste manual (H9): cantidad × precio ajustado, sin mínimo de venta.
    """
    cantidad = a_4(cantidad)
    costo_unit_usd = a_usd(precios.costo_unit, tasa)
    minimo_usd = a_usd(precios.minimo, tasa)
    costo_usd = a_4(max(cantidad * costo_unit_usd, minimo_usd))
    precio_calculado = a_usd(precios.venta_unit, tasa)
    minimo_venta_usd = a_usd(precios.venta_minimo, tasa)
    if ajuste_unit_usd is not None:
        precio = a_4(ajuste_unit_usd)
        subtotal = a_4(cantidad * precio)
    else:
        precio = precio_calculado
        subtotal = a_4(max(cantidad * precio, minimo_venta_usd))
    return Calculo(
        cantidad=cantidad,
        tasa=tasa,
        costo_usd=costo_usd,
        precio_calculado_unit_usd=precio_calculado,
        precio_venta_unit_usd=precio,
        minimo_venta_usd=minimo_venta_usd,
        subtotal_venta_usd=subtotal,
        bajo_minimo_venta=ajuste_unit_usd is not None and subtotal < minimo_venta_usd,
        bajo_costo=subtotal < costo_usd,
    )


# ---------- Recargo porcentual sobre el Recibo de Caja (D3, H-F4-4) ----------


def base_pct_recibo(filas: Iterable[Any]) -> Decimal:
    """Subtotal de las líneas de Recibo de Caja incluidas, sin ningún PCT_RECIBO ni opcionales apagadas.

    Cada fila trae rate_unit, bloque_fiscal, incluida y subtotal_venta_usd (ya calculado).
    """
    return sum(
        (
            fila.subtotal_venta_usd
            for fila in filas
            if fila.incluida and fila.bloque_fiscal == "RECIBO_CAJA" and fila.rate_unit != "PCT_RECIBO"
        ),
        CERO,
    )


def calcular_pct_recibo(base: Decimal, precios: Precios, tasa: Decimal, ajuste_unit_usd: Decimal | None = None) -> Calculo:
    """Cantidad = base / 100 y precio = porcentaje, como PCT_VALOR. Con base 0 la línea vale 0 y no se cobra el
    mínimo (H-F4-4); con base mayor que 0, el mínimo como en cualquier recargo."""
    if base <= 0:
        cero = a_4(CERO)
        calculo = calcular_linea(cero, precios, tasa, ajuste_unit_usd)
        return Calculo(
            cantidad=cero,
            tasa=calculo.tasa,
            costo_usd=cero,
            precio_calculado_unit_usd=calculo.precio_calculado_unit_usd,
            precio_venta_unit_usd=calculo.precio_venta_unit_usd,
            minimo_venta_usd=calculo.minimo_venta_usd,
            subtotal_venta_usd=cero,
            bajo_minimo_venta=False,
            bajo_costo=False,
        )
    return calcular_linea(a_4(base / CIEN), precios, tasa, ajuste_unit_usd)


AVISO_SIN_BASE = "Manejo sobre recibo sin base"


# ---------- Fiscal (D-F3-4, D-F3-14) ----------


def bloque_fiscal(bloque_incoterm: str, pais_iso2_del_puerto: str | None) -> str:
    """Flete y seguro → RECIBO_CAJA. Recargos en Ecuador → FACTURA; en el exterior → RECIBO_CAJA."""
    if bloque_incoterm in ("FLETE_PRINCIPAL", "SEGURO"):
        return "RECIBO_CAJA"
    return "FACTURA" if pais_iso2_del_puerto == "EC" else "RECIBO_CAJA"


# ---------- Totales (§10.5, D-F3-4) ----------


@dataclass(frozen=True)
class Totales:
    subtotal_recibo_caja: Decimal
    subtotal_factura: Decimal
    base_iva: Decimal
    iva: Decimal
    total_general: Decimal
    costo_total: Decimal
    margen_total: Decimal
    margen_pct: Decimal
    iva_tasa: Decimal


def totales(lineas_incluidas: Iterable[Any], iva_tasa: Decimal) -> Totales:
    """Cada total se redondea a 2 una vez sobre la suma de las líneas (a 4); el IVA sobre la base ya
    redondeada, solo de las líneas FACTURA con aplica_iva. El margen siempre sin IVA; 0 si no hay venta.
    """
    lineas = list(lineas_incluidas)
    recibo = a_2(sum((linea.subtotal_venta_usd for linea in lineas if linea.bloque_fiscal == "RECIBO_CAJA"), CERO))
    factura = a_2(sum((linea.subtotal_venta_usd for linea in lineas if linea.bloque_fiscal == "FACTURA"), CERO))
    base_iva = a_2(
        sum(
            (linea.subtotal_venta_usd for linea in lineas if linea.bloque_fiscal == "FACTURA" and linea.aplica_iva),
            CERO,
        )
    )
    iva = a_2(base_iva * iva_tasa / CIEN)
    costo_total = a_2(sum((linea.costo_usd for linea in lineas), CERO))
    venta = recibo + factura
    margen_total = venta - costo_total
    margen_pct = a_2(margen_total / venta * CIEN) if venta else a_2(CERO)
    return Totales(
        subtotal_recibo_caja=recibo,
        subtotal_factura=factura,
        base_iva=base_iva,
        iva=iva,
        total_general=recibo + factura + iva,
        costo_total=costo_total,
        margen_total=margen_total,
        margen_pct=margen_pct,
        iva_tasa=iva_tasa,
    )


# ---------- Recargo más específico (D-F3-7, H6) ----------


def concepto_clave(concepto: str) -> str:
    """El concepto comparado sin mayúsculas ni espacios de más."""
    return " ".join(concepto.split()).lower()


def _rango(recargo, proveedor_flete_id: int | None) -> tuple[int, int]:
    """Menor es mejor: 1) proveedor del flete antes que NULL; 2) tipo de equipo > modo > todos."""
    proveedor = 0 if proveedor_flete_id is not None and recargo.proveedor_id == proveedor_flete_id else 1
    especificidad = 0 if recargo.tipo_equipo_id is not None else (1 if recargo.modo is not None else 2)
    return proveedor, especificidad


def recargos_aplicables(recargos: Iterable[Any], proveedor_flete_id: int | None, modo: str, tipos: Iterable[int]) -> list:
    """Filtra por proveedor (el del flete o NULL), modo y tipo de equipo de la cotización."""
    tipos = set(tipos)
    salida = []
    for recargo in recargos:
        if recargo.proveedor_id is not None and recargo.proveedor_id != proveedor_flete_id:
            continue
        if recargo.modo is not None and recargo.modo != modo:
            continue
        if recargo.tipo_equipo_id is not None and recargo.tipo_equipo_id not in tipos:
            continue
        salida.append(recargo)
    return salida


def elegir_mas_especifico(
    recargos: Iterable[Any], proveedor_flete_id: int | None, modo: str, tipos: Iterable[int] = ()
) -> list[tuple[Any, tuple[int, ...]]]:
    """Un recargo por concepto (aéreo y LCL) o por concepto y tipo de equipo (FCL, H6).

    Devuelve (recargo, tipos que cubre). En FCL, un recargo genérico que gana en varios tipos sale
    una sola vez con todos los tipos que cubre; uno específico cubre solo su tipo.
    """
    tipos = sorted(set(tipos))
    candidatos = recargos_aplicables(recargos, proveedor_flete_id, modo, tipos)
    por_concepto: dict[str, list] = {}
    for recargo in candidatos:
        por_concepto.setdefault(concepto_clave(recargo.concepto), []).append(recargo)

    elegidos: list[tuple[Any, tuple[int, ...]]] = []
    for concepto in sorted(por_concepto):
        grupo = por_concepto[concepto]
        if modo != "FCL":
            ganador = min(grupo, key=lambda r: (_rango(r, proveedor_flete_id), r.id))
            elegidos.append((ganador, ()))
            continue
        cubre: dict[int, list[int]] = {}
        orden: list = []
        for tipo in tipos:
            del_tipo = [r for r in grupo if r.tipo_equipo_id in (None, tipo)]
            if not del_tipo:
                continue
            ganador = min(del_tipo, key=lambda r: (_rango(r, proveedor_flete_id), r.id))
            if ganador.id not in cubre:
                cubre[ganador.id] = []
                orden.append(ganador)
            cubre[ganador.id].append(tipo)
        elegidos.extend((ganador, tuple(cubre[ganador.id])) for ganador in orden)
    return elegidos

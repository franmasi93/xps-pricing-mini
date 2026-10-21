"""M7 Cotizaciones: borrador, líneas por Incoterm, ajuste, emisión con número, estados y duplicado.

- Alcance (§6.3.2): sin cotizacion.ver_todas solo las propias (comercial_id); una ajena da 404.
- Gating (D-F2-5, H10): las claves de costo y margen se omiten del JSON según el nivel del usuario.
- Todo el cálculo sale de services/cotizador.py (una sola fuente).
- Solo el BORRADOR se edita; cualquier escritura sobre otro estado → 409 COTIZACION_NO_EDITABLE.
- Auditoría: emitir, estado, duplicar y ajustes como EDITAR; descartar como DESACTIVAR; la nota
  empieza con la acción real en mayúsculas.
- E0: "modo" es el código del servicio; lo que dependía del modo (ubicaciones, carga exigida, cantidad, claves de
  flete, recargos por tipo de equipo) sale del servicio y de su forma de cobro.
"""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, object_session, selectinload

from app.config import get_settings
from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar
from app.core.unidades import in_a_cm, kg_a_lb, lb_a_kg
from app.models import (
    Cliente,
    ContactoCliente,
    ContadorCotizacion,
    Cotizacion,
    CotizacionContenedor,
    Incoterm,
    LineaCotizacion,
    Proveedor,
    Puerto,
    Recargo,
    RecargoServicio,
    RecargoTarifa,
    Tarifa,
    TipoEquipo,
    Usuario,
)
from app.models.cotizaciones import BLOQUES_LINEA
from app.services import administracion, auditoria, clientes, cotizador, pdf, precio_venta, servicios
from app.services.empresa import datos_empresa
from app.services.configuracion import leer_config, leer_iva_tasa
from app.services.cotizador import Bulto, Carga
from app.services.incoterms import bloques_incluidos, validar_incoterm_modo
from app.services.tarifas import NIVEL_MARGEN, NIVEL_VENTA, error_ubicaciones, nivel_de, precio_venta_kg

EMPRESA = "XPRESS LOGISTICS XPS S.A."
ESTADOS_FINALES = ("ACEPTADA", "RECHAZADA")
CAMPOS_QUE_BORRAN_LINEAS = (
    "sentido",
    "incoterm_id",
    "modo",
    "origen_puerto_id",
    "destino_puerto_id",
    "proveedor_recargos_id",
    "peso_kg",
    "cbm",
    "bultos",
    "dimensiones",
    "contenedores",
    "unidad_peso",
    "peso_lb",
)
CAMPOS_CABECERA = (
    "cliente_id",
    "contacto_id",
    "sentido",
    "incoterm_id",
    "modo",
    "origen_puerto_id",
    "destino_puerto_id",
    "proveedor_recargos_id",
    "peso_kg",
    "cbm",
    "bultos",
    "dimensiones",
    "valor_mercancia_usd",
    "notas_cliente",
    "notas_internas",
    "unidad_peso",
    "peso_lb",
    "transportista",
    "descripcion_carga",
)
MEDIDAS = ("largo", "ancho", "alto")
# Claves de línea y cabecera que solo existen con costo.ver (y las de margen, con margen.ver).
CLAVES_COSTO_LINEA = ("costo_unit_original", "minimo_original", "costo_usd", "precio_calculado_unit_usd", "bajo_costo")
MOTIVO_MINIMO = 5
BLOQUE_RECARGO = {
    "recogida_origen": "RECOGIDA_ORIGEN",
    "despacho_export": "DESPACHO_EXPORT",
    "gastos_origen": "GASTOS_ORIGEN",
    "seguro": "SEGURO",
    "gastos_destino": "GASTOS_DESTINO",
    "despacho_import": "DESPACHO_IMPORT",
    "entrega_final": "ENTREGA_FINAL",
}
CAMPOS_RECARGO = ("recogida_origen", "despacho_export", "gastos_origen", "seguro", "gastos_destino", "despacho_import",
                  "entrega_final")
AVISO_SIN_RECARGOS = "Esta tarifa no tiene recargos cargados para este puerto y servicio"


# ---------- Errores y alcance ----------


def _no_encontrada() -> ErrorNegocio:
    return ErrorNegocio(404, "COTIZACION_NO_ENCONTRADA", "Cotización no encontrada")


def _no_editable() -> ErrorNegocio:
    return ErrorNegocio(409, "COTIZACION_NO_EDITABLE", "Solo se edita una cotización en BORRADOR")


def _consulta():
    return select(Cotizacion).options(
        selectinload(Cotizacion.cliente).selectinload(Cliente.pais),
        selectinload(Cotizacion.contacto),
        selectinload(Cotizacion.comercial),
        selectinload(Cotizacion.incoterm),
        selectinload(Cotizacion.origen).selectinload(Puerto.pais),
        selectinload(Cotizacion.destino).selectinload(Puerto.pais),
        selectinload(Cotizacion.proveedor_recargos),
        selectinload(Cotizacion.contenedores).selectinload(CotizacionContenedor.tipo_equipo),
        selectinload(Cotizacion.lineas).selectinload(LineaCotizacion.tarifa).selectinload(Tarifa.tramos),
        selectinload(Cotizacion.lineas).selectinload(LineaCotizacion.tarifa).selectinload(Tarifa.moneda),
        selectinload(Cotizacion.lineas).selectinload(LineaCotizacion.recargo).selectinload(Recargo.moneda),
        selectinload(Cotizacion.lineas).selectinload(LineaCotizacion.moneda_original),
        selectinload(Cotizacion.lineas).selectinload(LineaCotizacion.tipo_equipo),
    )


def _con_alcance(consulta, usuario: Usuario):
    if clientes.ve_todos(usuario):
        return consulta
    return consulta.where(Cotizacion.comercial_id == auditoria.id_de(usuario))


def obtener_cotizacion(db: Session, usuario: Usuario, cotizacion_id: int) -> Cotizacion:
    cotizacion = db.scalars(_con_alcance(_consulta().where(Cotizacion.id == cotizacion_id), usuario)).one_or_none()
    if cotizacion is None:
        raise _no_encontrada()
    return cotizacion


def _editable(db: Session, usuario: Usuario, cotizacion_id: int) -> Cotizacion:
    cotizacion = obtener_cotizacion(db, usuario, cotizacion_id)
    if cotizacion.estado != "BORRADOR" or not cotizacion.activo:
        raise _no_editable()
    return cotizacion


# ---------- Validación de la cabecera y de la carga ----------


def _decimal(valor: Any, campo: str, decimales: int, *, positivo: bool = False) -> Decimal | None:
    """Monto o medida con un máximo de decimales; nunca se redondea en silencio (regla 3)."""
    if valor is None:
        return None
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero < 0 or (positivo and numero == 0):
        raise ErrorNegocio(422, "CARGA_INVALIDA", f"{campo} debe ser {'mayor que' if positivo else 'mayor o igual a'} 0")
    if numero.normalize().as_tuple().exponent < -decimales:
        raise ErrorNegocio(422, "CARGA_INVALIDA", f"{campo} admite como máximo {decimales} decimales")
    return numero


def _activo(db: Session, modelo, ident: int | None, que: str):
    objeto = db.get(modelo, ident) if ident is not None else None
    if objeto is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"No existe {que} indicado")
    if not objeto.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", f"No se puede usar {que} inactivo")
    return objeto


def _validar(db: Session, actor: Usuario, datos: dict[str, Any], contenedores: list[dict[str, Any]],
             modo_anterior: str | None = None) -> dict[str, Any]:
    """Valida cabecera y carga completas (crear y PATCH) y devuelve los datos normalizados.

    El servicio debe estar activo al crear o al cambiarlo; un borrador de un servicio ya desactivado se sigue
    editando (lo histórico queda intacto)."""
    servicio = servicios.servicio_utilizable(db, datos["modo"], exigir_activo=datos["modo"] != modo_anterior)
    forma = servicios.forma_de(servicio)
    cliente = clientes.obtener_cliente(db, actor, datos["cliente_id"])  # ajeno → 404
    if not cliente.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", "El cliente está inactivo")
    if datos.get("contacto_id") is not None:
        contacto = db.get(ContactoCliente, datos["contacto_id"])
        if contacto is None or contacto.cliente_id != cliente.id or not contacto.activo:
            raise ErrorNegocio(422, "CONTACTO_INVALIDO", "El contacto debe ser un contacto activo del cliente")

    incoterm = _activo(db, Incoterm, datos["incoterm_id"], "el Incoterm")
    validar_incoterm_modo(incoterm, datos["modo"])
    bloques, advertencia = bloques_incluidos(incoterm, datos["sentido"])
    if not bloques:
        raise ErrorNegocio(422, "NADA_QUE_COTIZAR", advertencia)

    for campo, que, tipo in (
        ("origen_puerto_id", "el puerto de origen", servicio.tipo_ubicacion_origen),
        ("destino_puerto_id", "el puerto de destino", servicio.tipo_ubicacion_destino),
    ):
        puerto = _activo(db, Puerto, datos[campo], que)
        if puerto.tipo != tipo:
            raise error_ubicaciones(servicio)
    if datos["origen_puerto_id"] == datos["destino_puerto_id"]:
        raise ErrorNegocio(422, "ORIGEN_IGUAL_DESTINO", "El origen y el destino deben ser distintos")
    if datos.get("proveedor_recargos_id") is not None:
        _activo(db, Proveedor, datos["proveedor_recargos_id"], "el proveedor")

    _validar_peso_y_dimensiones(datos, forma.peso_obligatorio)
    datos["cbm"] = _decimal(datos.get("cbm"), "El CBM", 4)
    datos["valor_mercancia_usd"] = _decimal(datos.get("valor_mercancia_usd"), "El valor de la mercancía", 2)
    dimensiones = datos["dimensiones"] or []
    forma.validar_carga(datos, dimensiones, contenedores, servicio.codigo)
    if forma.usa_tipo_equipo:
        for contenedor in contenedores:
            tipo = _activo(db, TipoEquipo, contenedor["tipo_equipo_id"], "el tipo de equipo")
            if tipo.servicio_id != servicio.id:
                raise ErrorNegocio(
                    422, "TIPO_EQUIPO_NO_PERMITIDO", f"El tipo de equipo {tipo.codigo} no es del servicio {servicio.codigo}"
                )
    for campo in ("notas_cliente", "notas_internas", "transportista", "descripcion_carga"):
        if datos.get(campo) is not None:
            datos[campo] = datos[campo].strip() or None
    return datos


def _medida(bulto: dict[str, Any], clave: str) -> Decimal:
    if bulto.get(clave) is None:
        unidad = "pulgadas" if clave.endswith("_in") else "centímetros"
        raise ErrorNegocio(422, "CARGA_INVALIDA", f"Indique largo, ancho y alto de cada bulto en {unidad}")
    return _decimal(bulto[clave], "Cada medida", 2, positivo=True)


def _validar_peso_y_dimensiones(datos: dict[str, Any], positivo: bool) -> None:
    """KG: igual que en F3. LB (H-F4-1): se guarda lo capturado (lb, pulgadas) y se derivan kg y cm.
    `positivo`: la forma de cobro exige peso mayor que 0 (antes: AEREO)."""
    unidad = datos.get("unidad_peso") or "KG"
    if unidad not in ("KG", "LB"):
        raise ErrorNegocio(422, "CARGA_INVALIDA", "La unidad de peso debe ser KG o LB")
    datos["unidad_peso"] = unidad
    if unidad == "LB":
        datos["peso_lb"] = _decimal(datos.get("peso_lb") or 0, "El peso", 3, positivo=positivo)
        datos["peso_kg"] = lb_a_kg(datos["peso_lb"])
        if positivo and datos["peso_kg"] == 0:
            raise ErrorNegocio(422, "CARGA_INVALIDA", "El peso debe ser mayor que 0")
    else:
        datos["peso_lb"] = None
        datos["peso_kg"] = _decimal(datos.get("peso_kg") or 0, "El peso", 3, positivo=positivo)
    dimensiones = []
    for bulto in datos.get("dimensiones") or []:
        fila: dict[str, Any] = {"cantidad": int(bulto["cantidad"])}
        if unidad == "LB":
            for medida in MEDIDAS:
                pulgadas = _medida(bulto, f"{medida}_in")
                fila[f"{medida}_in"] = str(pulgadas)
                fila[f"{medida}_cm"] = str(in_a_cm(pulgadas))
        else:
            fila |= {f"{medida}_cm": str(_medida(bulto, f"{medida}_cm")) for medida in MEDIDAS}
        dimensiones.append(fila)
    datos["dimensiones"] = dimensiones or None


def carga_de(cotizacion: Cotizacion) -> Carga:
    return Carga(
        modo=cotizacion.modo,
        peso_kg=cotizacion.peso_kg,
        cbm=cotizacion.cbm,
        dimensiones=tuple(
            Bulto(int(b["cantidad"]), Decimal(b["largo_cm"]), Decimal(b["ancho_cm"]), Decimal(b["alto_cm"]))
            for b in cotizacion.dimensiones or []
        ),
        contenedores={c.tipo_equipo_id: c.cantidad for c in cotizacion.contenedores},
        valor_mercancia_usd=cotizacion.valor_mercancia_usd,
        peso_lb=cotizacion.peso_lb,
        forma_cobro=cotizacion.servicio.forma_cobro,
    )


# ---------- Cálculo de una línea ----------


def _precios(objeto, carga: Carga) -> cotizador.Precios:
    """Tarifa con tramos: el tramo del peso cobrable (D-F2-2). Si no, el costo de la tarifa o del recargo."""
    if isinstance(objeto, Tarifa) and objeto.tramos:
        tramo = cotizador.tramo_aplicable(objeto.tramos, cotizador.peso_cobrable_en(carga, objeto.unidad_peso))
        return cotizador.precios_de_objeto(objeto, costo_unit=tramo.costo_kg, venta_unit=precio_venta_kg(objeto, tramo))
    return cotizador.precios_de_objeto(objeto)


def _cantidad_linea(linea: LineaCotizacion, carga: Carga) -> Decimal:
    """La cantidad guardada; el seguro como % del valor se recalcula (cambiar el valor no borra líneas, H15)."""
    if linea.rate_unit == "PCT_VALOR":
        return cotizador.cantidad_por_unidad("PCT_VALOR", carga) if carga.valor_mercancia_usd is not None else Decimal(0)
    return linea.cantidad


def _guardar_calculo(linea: LineaCotizacion, precios: cotizador.Precios | None, calculo) -> None:
    if precios is not None:
        linea.costo_unit_original = precios.costo_unit
        linea.minimo_original = precios.minimo
    linea.cantidad = calculo.cantidad
    linea.tasa_aplicada = calculo.tasa
    linea.costo_usd = calculo.costo_usd
    linea.precio_calculado_unit_usd = calculo.precio_calculado_unit_usd
    linea.precio_venta_unit_usd = calculo.precio_venta_unit_usd
    linea.minimo_venta_usd = calculo.minimo_venta_usd
    linea.subtotal_venta_usd = calculo.subtotal_venta_usd


def _recalcular(db: Session, linea: LineaCotizacion, carga: Carga, hoy: date, tasas: dict):
    """Recalcula y guarda la línea con las tasas y los precios de hoy, conservando el ajuste manual."""
    objeto = linea.tarifa or linea.recargo
    precios = _precios(objeto, carga)
    codigo = objeto.moneda.codigo
    if codigo not in tasas:
        tasas[codigo] = cotizador.tasa_vigente(db, codigo, hoy)
    ajuste = linea.precio_venta_unit_usd if linea.ajuste_manual else None
    calculo = cotizador.calcular_linea(_cantidad_linea(linea, carga), precios, tasas[codigo], ajuste)
    _guardar_calculo(linea, precios, calculo)
    return calculo


def _vigente(objeto, hoy: date) -> bool:
    return objeto.activo and objeto.valido_desde <= hoy <= objeto.valido_hasta


# ---------- Presentación (con gating) ----------


def _d(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def _ref_puerto(puerto: Puerto) -> dict[str, Any]:
    return {"id": puerto.id, "codigo": puerto.codigo, "nombre": puerto.nombre}


def vencida(cotizacion: Cotizacion, hoy: date) -> bool:
    """Vencida no es un estado guardado: se calcula al leer (§11)."""
    return (
        cotizacion.estado in ("EMITIDA", "ENVIADA") and cotizacion.valida_hasta is not None and hoy > cotizacion.valida_hasta
    )


def etiqueta(cotizacion: Cotizacion) -> str:
    return cotizacion.numero or f"Borrador #{cotizacion.id}"


def _linea_dict(linea: LineaCotizacion, calculo, nivel: str) -> dict[str, Any]:
    datos = {
        "id": linea.id,
        "orden": linea.orden,
        "concepto": linea.concepto,
        "bloque_incoterm": linea.bloque_incoterm,
        "tarifa_id": linea.tarifa_id,
        "recargo_id": linea.recargo_id,
        "tipo_equipo": linea.tipo_equipo.codigo if linea.tipo_equipo else None,
        "cantidad": _d(calculo.cantidad),
        "rate_unit": linea.rate_unit,
        "unidad_peso": linea.unidad_peso,
        "moneda_original": linea.moneda_original.codigo,
        "tasa_aplicada": _d(calculo.tasa),
        "precio_venta_unit_usd": _d(calculo.precio_venta_unit_usd),
        "minimo_venta_usd": _d(calculo.minimo_venta_usd),
        "subtotal_venta_usd": _d(calculo.subtotal_venta_usd),
        "bloque_fiscal": linea.bloque_fiscal,
        "aplica_iva": linea.aplica_iva,
        "rol_ingreso": linea.rol_ingreso,
        "opcional": linea.opcional,
        "incluida": linea.incluida,
        "ajuste_manual": linea.ajuste_manual,
        "motivo_ajuste": linea.motivo_ajuste,
        "valido_hasta_origen": linea.valido_hasta_origen.isoformat(),
        "seleccion": linea.seleccion,
        "vinculado": linea.vinculado,
    }
    if linea.ajuste_manual:
        datos["bajo_minimo_venta"] = calculo.bajo_minimo_venta  # el mínimo de venta no revela el costo
    if nivel != NIVEL_VENTA:
        # D-R1: el proveedor es interno: solo con costo.ver (admin, pricing, gerencia), nunca para el comercial.
        origen = linea.tarifa or linea.recargo
        datos |= {
            "proveedor_id": linea.proveedor_id,
            "proveedor": origen.proveedor.nombre if origen is not None and origen.proveedor else "XPRESS (propio)",
            "proveedor_propio": linea.recargo_id is not None and linea.proveedor_id is None,
            "costo_unit_original": _d(linea.costo_unit_original),
            "minimo_original": _d(linea.minimo_original),
            "costo_usd": _d(calculo.costo_usd),
            "precio_calculado_unit_usd": _d(calculo.precio_calculado_unit_usd),
        }
        if linea.ajuste_manual:
            datos["bajo_costo"] = calculo.bajo_costo
    if nivel == NIVEL_MARGEN:
        datos["margen_usd"] = _d(calculo.subtotal_venta_usd - calculo.costo_usd)
    return datos


def _totales_dict(totales: cotizador.Totales | None, nivel: str) -> dict[str, Any]:
    if totales is None:
        return {}
    datos = {
        "subtotal_recibo_caja": _d(totales.subtotal_recibo_caja),
        "subtotal_factura": _d(totales.subtotal_factura),
        "iva": _d(totales.iva),
        "total_general": _d(totales.total_general),
        "iva_tasa_aplicada": _d(totales.iva_tasa),
    }
    if nivel != NIVEL_VENTA:
        datos["costo_total"] = _d(totales.costo_total)
    if nivel == NIVEL_MARGEN:
        datos |= {"margen_total": _d(totales.margen_total), "margen_pct": _d(totales.margen_pct)}
    return datos


def _carga_dict(cotizacion: Cotizacion) -> dict[str, Any]:
    carga = carga_de(cotizacion)
    datos: dict[str, Any] = {
        "unidad_peso": cotizacion.unidad_peso,
        "peso_kg": _d(cotizacion.peso_kg),
        "peso_lb": _d(cotizacion.peso_lb),
        "cbm": _d(cotizacion.cbm),
        "bultos": cotizacion.bultos,
        "dimensiones": cotizacion.dimensiones,
        "valor_mercancia_usd": _d(cotizacion.valor_mercancia_usd),
        "contenedores": [
            {"tipo_equipo_id": c.tipo_equipo_id, "codigo": c.tipo_equipo.codigo, "cantidad": c.cantidad}
            for c in cotizacion.contenedores
        ],
    }
    try:
        datos |= servicios.forma_de(cotizacion.servicio).datos_carga(carga)
    except ErrorNegocio:
        pass
    return datos


def _calcular(db: Session, cotizacion: Cotizacion, hoy: date, *, guardar: bool) -> tuple[list, list[str]]:
    """Todas las líneas con las tasas y precios de hoy; los PCT_RECIBO al final, sobre la base ya calculada (D3).

    guardar=False (vista en vivo del BORRADOR): no guarda; un error queda como aviso con el cálculo guardado.
    guardar=True (emisión): guarda cada línea y los errores se propagan.
    """
    carga = carga_de(cotizacion)
    tasas: dict[str, Decimal] = {}
    calculos: dict[int, Any] = {}
    avisos: list[str] = []

    def una(linea: LineaCotizacion, base: Decimal | None):
        objeto = linea.tarifa or linea.recargo
        if not guardar and not _vigente(objeto, hoy):
            avisos.append(f"{linea.concepto}: la tarifa o el recargo ya no está vigente; vuelva a proponer las líneas")
        try:
            precios = _precios(objeto, carga)
            codigo = objeto.moneda.codigo
            if codigo not in tasas:
                tasas[codigo] = cotizador.tasa_vigente(db, codigo, hoy)
            ajuste = linea.precio_venta_unit_usd if linea.ajuste_manual else None
            if base is None:
                calculo = cotizador.calcular_linea(_cantidad_linea(linea, carga), precios, tasas[codigo], ajuste)
            else:
                calculo = cotizador.calcular_pct_recibo(base, precios, tasas[codigo], ajuste)
        except ErrorNegocio as error:
            if guardar:
                raise
            avisos.append(f"{linea.concepto}: {error.mensaje}")
            return _calculo_guardado(linea)
        if guardar:
            _guardar_calculo(linea, precios, calculo)
        return calculo

    normales = [linea for linea in cotizacion.lineas if linea.rate_unit != "PCT_RECIBO"]
    sobre_recibo = [linea for linea in cotizacion.lineas if linea.rate_unit == "PCT_RECIBO"]
    for linea in normales:
        calculos[id(linea)] = una(linea, None)
    if sobre_recibo:
        base = cotizador.base_pct_recibo([_Fila(linea, calculos[id(linea)]) for linea in normales])
        for linea in sobre_recibo:
            calculos[id(linea)] = una(linea, base)
        if base <= 0 and any(linea.incluida for linea in sobre_recibo):
            avisos.append(cotizador.AVISO_SIN_BASE)
    return [(linea, calculos[id(linea)]) for linea in cotizacion.lineas], avisos


def _vivo(db: Session, cotizacion: Cotizacion, hoy: date) -> tuple[list, list[str]]:
    """BORRADOR: cada línea recalculada en memoria con las tasas y precios de hoy (no se guarda)."""
    return _calcular(db, cotizacion, hoy, guardar=False)


def _guardar_pct_recibo(db: Session, cotizacion: Cotizacion, hoy: date) -> None:
    """Tras ajustar o activar una línea, los PCT_RECIBO se recalculan sobre la nueva base y se guardan."""
    if not any(linea.rate_unit == "PCT_RECIBO" for linea in cotizacion.lineas):
        return
    filas, _ = _vivo(db, cotizacion, hoy)
    for linea, calculo in filas:
        if linea.rate_unit == "PCT_RECIBO":
            _guardar_calculo(linea, None, calculo)


def _calculo_guardado(linea: LineaCotizacion) -> cotizador.Calculo:
    return cotizador.Calculo(
        cantidad=linea.cantidad,
        tasa=linea.tasa_aplicada,
        costo_usd=linea.costo_usd,
        precio_calculado_unit_usd=linea.precio_calculado_unit_usd,
        precio_venta_unit_usd=linea.precio_venta_unit_usd,
        minimo_venta_usd=linea.minimo_venta_usd,
        subtotal_venta_usd=linea.subtotal_venta_usd,
        bajo_minimo_venta=linea.ajuste_manual and linea.subtotal_venta_usd < linea.minimo_venta_usd,
        bajo_costo=linea.subtotal_venta_usd < linea.costo_usd,
    )


class _Fila:
    """Línea para los totales: subtotal y costo del cálculo, datos fiscales de la línea."""

    def __init__(self, linea: LineaCotizacion, calculo) -> None:
        self.subtotal_venta_usd = calculo.subtotal_venta_usd
        self.costo_usd = calculo.costo_usd
        self.bloque_fiscal = linea.bloque_fiscal
        self.aplica_iva = linea.aplica_iva
        self.rate_unit = linea.rate_unit
        self.incluida = linea.incluida


def presentar_cotizacion(db: Session, usuario: Usuario, cotizacion: Cotizacion, avisos: list[str] | None = None) -> dict:
    nivel = nivel_de(usuario)
    hoy = fechas.hoy_ecuador()
    avisos = list(avisos or [])
    if cotizacion.estado == "BORRADOR":
        filas, avisos_vivos = _vivo(db, cotizacion, hoy)
        avisos += avisos_vivos
        incluidas = [(linea, calculo) for linea, calculo in filas if linea.incluida]
        totales = cotizador.totales([_Fila(l, c) for l, c in incluidas], leer_iva_tasa(db)) if filas else None
        valida_hasta_calculada = min((l.valido_hasta_origen for l, _ in incluidas), default=None)
    else:
        filas = [(linea, _calculo_guardado(linea)) for linea in cotizacion.lineas]
        totales = cotizador.Totales(
            subtotal_recibo_caja=cotizacion.subtotal_recibo_caja,
            subtotal_factura=cotizacion.subtotal_factura,
            base_iva=Decimal(0),
            iva=cotizacion.iva,
            total_general=cotizacion.total_general,
            costo_total=cotizacion.costo_total,
            margen_total=cotizacion.margen_total,
            margen_pct=cotizacion.margen_pct,
            iva_tasa=cotizacion.iva_tasa_aplicada,
        )
        valida_hasta_calculada = None
    datos = {
        "id": cotizacion.id,
        "numero": cotizacion.numero,
        "etiqueta": etiqueta(cotizacion),
        "estado": cotizacion.estado,
        "vencida": vencida(cotizacion, hoy),
        "activo": cotizacion.activo,
        "cliente": {"id": cotizacion.cliente.id, "razon_social": cotizacion.cliente.razon_social},
        "contacto": (
            {"id": cotizacion.contacto.id, "nombre": cotizacion.contacto.nombre, "email": cotizacion.contacto.email}
            if cotizacion.contacto
            else None
        ),
        "comercial": {"id": cotizacion.comercial.id, "nombre": cotizacion.comercial.nombre},
        "sentido": cotizacion.sentido,
        "incoterm": {
            "id": cotizacion.incoterm.id, "codigo": cotizacion.incoterm.codigo, "nombre": cotizacion.incoterm.nombre
        },
        "modo": cotizacion.modo,
        "servicio": {
            "codigo": cotizacion.servicio.codigo,
            "nombre": cotizacion.servicio.nombre,
            "forma_cobro": cotizacion.servicio.forma_cobro,
            "usa_tipo_equipo": cotizacion.servicio.usa_tipo_equipo,
            "etiqueta_transportista": cotizacion.servicio.etiqueta_transportista,
            "activo": cotizacion.servicio.activo,
        },
        "origen": _ref_puerto(cotizacion.origen),
        "destino": _ref_puerto(cotizacion.destino),
        "proveedor_recargos_id": cotizacion.proveedor_recargos_id,
        "carga": _carga_dict(cotizacion),
        "fecha_emision": cotizacion.fecha_emision.isoformat() if cotizacion.fecha_emision else None,
        "valida_hasta": cotizacion.valida_hasta.isoformat() if cotizacion.valida_hasta else None,
        "valida_hasta_calculada": valida_hasta_calculada.isoformat() if valida_hasta_calculada else None,
        "moneda_cotizacion": cotizacion.moneda_cotizacion,
        "notas_cliente": cotizacion.notas_cliente,
        "notas_internas": cotizacion.notas_internas,
        "transportista": cotizacion.transportista,
        "descripcion_carga": cotizacion.descripcion_carga,
        "motivo_rechazo": cotizacion.motivo_rechazo,
        "detalle_rechazo": cotizacion.detalle_rechazo,
        "cotizacion_origen_id": cotizacion.cotizacion_origen_id,
        "requiere_proponer": cotizacion.estado == "BORRADOR" and not cotizacion.lineas,
        "sin_recargos": bool(cotizacion.lineas) and not any(l.recargo_id is not None for l in cotizacion.lineas),
        "lineas": [_linea_dict(linea, calculo, nivel) for linea, calculo in filas],
        "totales": _totales_dict(totales, nivel),
        "avisos": avisos,
        "creado_en": cotizacion.creado_en.isoformat(),
        "actualizado_en": cotizacion.actualizado_en.isoformat(),
    }
    return datos


def _respuesta(db: Session, usuario: Usuario, cotizacion_id: int, avisos: list[str] | None = None) -> dict:
    db.expire_all()
    return presentar_cotizacion(db, usuario, obtener_cotizacion(db, usuario, cotizacion_id), avisos)


def detalle_cotizacion(db: Session, usuario: Usuario, cotizacion_id: int) -> dict:
    return presentar_cotizacion(db, usuario, obtener_cotizacion(db, usuario, cotizacion_id))


def listar_cotizaciones(
    db: Session,
    usuario: Usuario,
    *,
    estado: str | None = None,
    cliente_id: int | None = None,
    comercial_id: int | None = None,
    vencidas: bool | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    hoy = fechas.hoy_ecuador()
    consulta = _con_alcance(select(Cotizacion), usuario).where(Cotizacion.activo.is_(True))
    if estado is not None:
        consulta = consulta.where(Cotizacion.estado == estado)
    if cliente_id is not None:
        consulta = consulta.where(Cotizacion.cliente_id == cliente_id)
    if comercial_id is not None:
        consulta = consulta.where(Cotizacion.comercial_id == comercial_id)
    if vencidas is not None:
        condicion = Cotizacion.estado.in_(("EMITIDA", "ENVIADA")) & (Cotizacion.valida_hasta < hoy)
        consulta = consulta.where(condicion if vencidas else ~condicion)
    if desde is not None:
        consulta = consulta.where(func.date(Cotizacion.creado_en) >= desde)
    if hasta is not None:
        consulta = consulta.where(func.date(Cotizacion.creado_en) <= hasta)
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = db.scalars(
        consulta.options(
            selectinload(Cotizacion.cliente),
            selectinload(Cotizacion.comercial),
            selectinload(Cotizacion.origen),
            selectinload(Cotizacion.destino),
            selectinload(Cotizacion.incoterm),
        )
        .order_by(Cotizacion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        {
            "id": c.id,
            "numero": c.numero,
            "etiqueta": etiqueta(c),
            "estado": c.estado,
            "vencida": vencida(c, hoy),
            "cliente": {"id": c.cliente.id, "razon_social": c.cliente.razon_social},
            "comercial": {"id": c.comercial.id, "nombre": c.comercial.nombre},
            "sentido": c.sentido,
            "incoterm": c.incoterm.codigo,
            "modo": c.modo,
            "origen": _ref_puerto(c.origen),
            "destino": _ref_puerto(c.destino),
            "fecha_emision": c.fecha_emision.isoformat() if c.fecha_emision else None,
            "valida_hasta": c.valida_hasta.isoformat() if c.valida_hasta else None,
            "total_general": _d(c.total_general),
            "creado_en": c.creado_en.isoformat(),
        }
        for c in filas
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ---------- Crear y editar el borrador ----------


def _foto(cotizacion: Cotizacion) -> dict[str, Any]:
    datos = {campo: getattr(cotizacion, campo) for campo in CAMPOS_CABECERA}
    datos["contenedores"] = sorted((c.tipo_equipo_id, c.cantidad) for c in cotizacion.contenedores)
    return datos


def crear_cotizacion(db: Session, actor: Usuario, datos: dict[str, Any]) -> dict:
    actor_id = auditoria.id_de(actor)
    contenedores = datos.pop("contenedores", None) or []
    datos = _validar(db, actor, datos, contenedores)
    if datos.get("contacto_id") is None:
        cliente = db.get(Cliente, datos["cliente_id"])
        principal = next((c for c in cliente.contactos if c.principal and c.activo), None)
        datos["contacto_id"] = principal.id if principal else None
    with db.no_autoflush:
        cotizacion = Cotizacion(
            **{campo: datos.get(campo) for campo in CAMPOS_CABECERA},
            comercial_id=actor_id,
            creado_por=actor_id,
            estado="BORRADOR",
        )
        cotizacion.contenedores = [CotizacionContenedor(**c) for c in contenedores]
        db.add(cotizacion)
        db.flush()
        auditoria.registrar(db, actor, "cotizacion", cotizacion.id, "CREAR", despues=_foto(cotizacion))
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


def _hay_ajustes(cotizacion: Cotizacion) -> bool:
    return any(linea.ajuste_manual for linea in cotizacion.lineas)


def _exigir_confirmacion(cotizacion: Cotizacion, confirmado: bool) -> None:
    """D-F3-10: borrar líneas con ajuste manual exige confirmar=true."""
    if _hay_ajustes(cotizacion) and not confirmado:
        raise ErrorNegocio(
            409,
            "AJUSTES_SE_PIERDEN",
            "El cambio borra las líneas y sus ajustes manuales; confírmelo para continuar",
        )


def actualizar_cotizacion(db: Session, actor: Usuario, cotizacion_id: int, cambios: dict[str, Any]) -> dict:
    cotizacion = _editable(db, actor, cotizacion_id)
    confirmado = cambios.pop("confirmar", False)
    antes = _foto(cotizacion)
    datos = {campo: getattr(cotizacion, campo) for campo in CAMPOS_CABECERA}
    contenedores = [{"tipo_equipo_id": c.tipo_equipo_id, "cantidad": c.cantidad} for c in cotizacion.contenedores]
    if "contenedores" in cambios:
        contenedores = cambios.pop("contenedores") or []
    datos |= cambios
    nuevo_servicio = servicios.servicio_por_codigo(db, datos["modo"])
    if "modo" in cambios and "contenedores" not in cambios and nuevo_servicio and not nuevo_servicio.usa_tipo_equipo:
        contenedores = []
    datos = _validar(db, actor, datos, contenedores, modo_anterior=cotizacion.modo)
    nuevos_contenedores = sorted((c["tipo_equipo_id"], c["cantidad"]) for c in contenedores)
    borra = any(
        datos[campo] != antes[campo] for campo in CAMPOS_QUE_BORRAN_LINEAS if campo != "contenedores"
    ) or nuevos_contenedores != antes["contenedores"]
    nota = None
    with db.no_autoflush:
        if borra and cotizacion.lineas:
            _exigir_confirmacion(cotizacion, confirmado)
            cotizacion.lineas.clear()
            nota = "LINEAS BORRADAS POR CAMBIO DE RUTA, MODO, INCOTERM O CARGA"
        for campo in CAMPOS_CABECERA:
            setattr(cotizacion, campo, datos.get(campo))
        if nuevos_contenedores != antes["contenedores"]:
            cotizacion.contenedores.clear()
            db.flush()
            cotizacion.contenedores = [CotizacionContenedor(**c) for c in contenedores]
        despues = _foto(cotizacion)
        if despues != antes:
            auditoria.registrar(db, actor, "cotizacion", cotizacion.id, "EDITAR", antes=antes, despues=despues, nota=nota)
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


# ---------- Tarifas elegibles (§10.2) ----------


def _claves_flete(cotizacion: Cotizacion) -> list[tuple[str, int | None]]:
    """(clave, tipo_equipo_id): una por tipo de equipo si el servicio cobra por equipo; si no, una sola."""
    return servicios.forma_de(cotizacion.servicio).claves_flete(cotizacion.modo, cotizacion.contenedores)


def _tarifas_elegibles(db: Session, cotizacion: Cotizacion, tipo_equipo_id: int | None, hoy: date) -> list[Tarifa]:
    consulta = (
        select(Tarifa)
        .options(selectinload(Tarifa.tramos), selectinload(Tarifa.moneda), selectinload(Tarifa.proveedor))
        .where(
            Tarifa.activo.is_(True),
            Tarifa.modo == cotizacion.modo,
            Tarifa.origen_puerto_id == cotizacion.origen_puerto_id,
            Tarifa.destino_puerto_id == cotizacion.destino_puerto_id,
            Tarifa.valido_desde <= hoy,
            Tarifa.valido_hasta >= hoy,
        )
    )
    if tipo_equipo_id is not None:
        consulta = consulta.where(Tarifa.tipo_equipo_id == tipo_equipo_id)
    return list(db.scalars(consulta.order_by(Tarifa.id)))


def _cantidad_tarifa(tarifa: Tarifa, carga: Carga) -> Decimal:
    return cotizador.cantidad_por_unidad(
        tarifa.rate_unit, carga, tipo_equipo_id=tarifa.tipo_equipo_id, unidad_peso=tarifa.unidad_peso
    )


def _transportista(tarifas: list[Tarifa]) -> str | None:
    """H-F4-5: los transportistas distintos de las tarifas elegidas, en orden, unidos con " / "."""
    nombres: list[str] = []
    for tarifa in tarifas:
        nombre = (tarifa.transportista or "").strip()
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return " / ".join(nombres) or None


def opciones_flete(db: Session, usuario: Usuario, cotizacion_id: int) -> dict:
    """Tarifas elegibles por clave, ordenadas por el subtotal de venta USD para esta carga (H17)."""
    cotizacion = obtener_cotizacion(db, usuario, cotizacion_id)
    nivel = nivel_de(usuario)
    hoy = fechas.hoy_ecuador()
    carga = carga_de(cotizacion)
    tipos = {c.tipo_equipo_id: c.tipo_equipo for c in cotizacion.contenedores}
    grupos = []
    for clave, tipo_id in _claves_flete(cotizacion):
        opciones, sin_precio = [], []
        for tarifa in _tarifas_elegibles(db, cotizacion, tipo_id, hoy):
            opcion: dict[str, Any] = {
                "tarifa_id": tarifa.id,
                "rate_unit": tarifa.rate_unit,
                "unidad_peso": tarifa.unidad_peso,
                "transportista": tarifa.transportista,
                "moneda": tarifa.moneda.codigo,
                "transit_time_dias": tarifa.transit_time_dias,
                "dias_libres": tarifa.dias_libres,
                "valido_desde": tarifa.valido_desde.isoformat(),
                "valido_hasta": tarifa.valido_hasta.isoformat(),
                "tiene_tramos": bool(tarifa.tramos),
            }
            if nivel != NIVEL_VENTA:
                opcion["proveedor"] = {"id": tarifa.proveedor.id, "nombre": tarifa.proveedor.nombre}  # D-R1: interno
            try:
                calculo = cotizador.calcular_linea(
                    _cantidad_tarifa(tarifa, carga),
                    _precios(tarifa, carga),
                    cotizador.tasa_vigente(db, tarifa.moneda.codigo, hoy),
                )
            except ErrorNegocio as error:
                opcion |= {"precio_venta_unit_usd": None, "subtotal_venta_usd": None, "aviso": error.codigo}
                sin_precio.append(opcion)
                continue
            opcion |= {
                "precio_venta_unit_usd": _d(calculo.precio_venta_unit_usd),
                "subtotal_venta_usd": _d(calculo.subtotal_venta_usd),
            }
            if nivel != NIVEL_VENTA:
                opcion["costo_usd"] = _d(calculo.costo_usd)
            opciones.append((calculo.subtotal_venta_usd, tarifa.id, opcion))
        opciones.sort(key=lambda fila: (fila[0], fila[1]))
        tipo = tipos.get(tipo_id)
        grupos.append(
            {
                "clave": clave,
                "tipo_equipo": {"id": tipo.id, "codigo": tipo.codigo} if tipo else None,
                "opciones": [fila[2] for fila in opciones] + sin_precio,
            }
        )
    return {"cotizacion_id": cotizacion.id, "grupos": grupos}


# ---------- Proponer líneas (§9, §10) ----------


def _elegir_tarifas(db: Session, cotizacion: Cotizacion, elegidas: dict[str, int], hoy: date) -> list[Tarifa]:
    tarifas = []
    for clave, tipo_id in _claves_flete(cotizacion):
        elegibles = _tarifas_elegibles(db, cotizacion, tipo_id, hoy)
        nombre = clave if tipo_id is None else next(c.tipo_equipo.codigo for c in cotizacion.contenedores if c.tipo_equipo_id == tipo_id)
        if clave in elegidas:
            tarifa = next((t for t in elegibles if t.id == elegidas[clave]), None)
            if tarifa is None:
                raise ErrorNegocio(422, "TARIFA_NO_ELEGIBLE", f"La tarifa indicada para {nombre} no es elegible hoy")
        elif len(elegibles) == 1:
            tarifa = elegibles[0]
        elif not elegibles:
            raise ErrorNegocio(422, "SIN_TARIFA", f"No hay tarifa vigente para {nombre} en esta ruta")
        else:
            raise ErrorNegocio(
                422, "ELEGIR_TARIFA", f"Hay {len(elegibles)} tarifas para {nombre}; elija una", extra={"clave": clave}
            )
        tarifas.append(tarifa)
    if len({t.proveedor_id for t in tarifas}) > 1:
        raise ErrorNegocio(
            422, "PROVEEDORES_DISTINTOS", f"En {cotizacion.modo} todas las tarifas deben ser del mismo proveedor"
        )
    return tarifas


def _puerto_de_bloque(cotizacion: Cotizacion, bloque: str) -> tuple[Puerto, str | None]:
    """Origen → puerto de origen; destino → de destino; SEGURO → destino en importación, origen en exportación."""
    if bloque in cotizador.BLOQUES_ORIGEN:
        return cotizacion.origen, "ORIGEN"
    if bloque in cotizador.BLOQUES_DESTINO:
        return cotizacion.destino, "DESTINO"
    return (cotizacion.destino if cotizacion.sentido == "IMPORTACION" else cotizacion.origen), None


def _vinculos_cotizacion(db: Session, cotizacion: Cotizacion, tarifas: list[Tarifa], hoy: date) -> dict[str, Any]:
    """D-R2: recargos vinculados a las tarifas elegidas (vigentes y activos), los que están vinculados a OTRAS
    tarifas (no aplican como generales) y los vinculados por servicio."""
    ids = [t.id for t in tarifas]
    por_tarifa = []
    if ids:
        por_tarifa = list(db.scalars(
            select(Recargo).options(selectinload(Recargo.moneda)).join(RecargoTarifa, RecargoTarifa.recargo_id == Recargo.id)
            .where(RecargoTarifa.tarifa_id.in_(ids), Recargo.activo.is_(True), Recargo.valido_desde <= hoy,
                   Recargo.valido_hasta >= hoy).distinct().order_by(Recargo.id)))
    con_tarifa = set(db.scalars(select(RecargoTarifa.recargo_id).distinct()))
    servicio_id = cotizacion.servicio.id
    por_servicio: dict[int, set[int]] = {}
    for recargo_id, sid in db.execute(select(RecargoServicio.recargo_id, RecargoServicio.servicio_id)):
        por_servicio.setdefault(recargo_id, set()).add(sid)
    return {"por_tarifa": por_tarifa, "ids_tarifa": {r.id for r in por_tarifa}, "con_tarifa": con_tarifa,
            "por_servicio": por_servicio, "servicio_id": servicio_id}


def _recargos_vigentes(db: Session, puerto: Puerto, bloque: str, lado: str | None, hoy: date) -> list[Recargo]:
    consulta = (
        select(Recargo)
        .options(selectinload(Recargo.moneda))
        .where(
            Recargo.activo.is_(True),
            Recargo.puerto_id == puerto.id,
            Recargo.bloque_incoterm == bloque,
            Recargo.valido_desde <= hoy,
            Recargo.valido_hasta >= hoy,
        )
    )
    if lado is not None:
        consulta = consulta.where(Recargo.lado == lado)
    return list(db.scalars(consulta.order_by(Recargo.id)))


def _nueva_linea(objeto, concepto: str, bloque: str, precios, calculo,
                 *, fiscal: str, aplica_iva: bool, rol: str, opcional: bool, incluida: bool,
                 tipo_equipo_id: int | None, seleccion: str | None = None, vinculado: bool = False) -> LineaCotizacion:
    unidad_peso = None
    if objeto.rate_unit == "KG":
        unidad_peso = objeto.unidad_peso if isinstance(objeto, Tarifa) else "KG"
    return LineaCotizacion(
        unidad_peso=unidad_peso,
        concepto=concepto,
        bloque_incoterm=bloque,
        tarifa_id=objeto.id if isinstance(objeto, Tarifa) else None,
        recargo_id=objeto.id if isinstance(objeto, Recargo) else None,
        proveedor_id=objeto.proveedor_id,
        tipo_equipo_id=tipo_equipo_id,
        cantidad=calculo.cantidad,
        rate_unit=objeto.rate_unit,
        costo_unit_original=precios.costo_unit,
        minimo_original=precios.minimo,
        moneda_original_id=objeto.moneda_id,
        tasa_aplicada=calculo.tasa,
        costo_usd=calculo.costo_usd,
        precio_venta_unit_usd=calculo.precio_venta_unit_usd,
        minimo_venta_usd=calculo.minimo_venta_usd,
        subtotal_venta_usd=calculo.subtotal_venta_usd,
        precio_calculado_unit_usd=calculo.precio_calculado_unit_usd,
        bloque_fiscal=fiscal,
        aplica_iva=aplica_iva,
        rol_ingreso=rol,
        opcional=opcional,
        incluida=incluida,
        ajuste_manual=False,
        valido_hasta_origen=objeto.valido_hasta,
        seleccion=seleccion,
        vinculado=vinculado,
    )


def _fiscal_recargo(recargo: Recargo, bloque: str) -> str:
    """D-R3: el bloque fiscal lo dice el recargo; el seguro sigue siempre en Recibo de Caja."""
    return "RECIBO_CAJA" if bloque == "SEGURO" else recargo.bloque_fiscal


def _proponer(db: Session, cotizacion: Cotizacion, elegidas: dict[str, int], proveedor_id: int | None,
              hoy: date) -> tuple[list[LineaCotizacion], list[str], str | None]:
    """Calcula las líneas sin tocar la cotización: si algo falla, no queda nada a medias."""
    validar_incoterm_modo(cotizacion.incoterm, cotizacion.modo)
    bloques, advertencia = bloques_incluidos(cotizacion.incoterm, cotizacion.sentido)
    if not bloques:
        raise ErrorNegocio(422, "NADA_QUE_COTIZAR", advertencia)
    carga = carga_de(cotizacion)
    tasas: dict[str, Decimal] = {}

    def tasa(objeto) -> Decimal:
        codigo = objeto.moneda.codigo
        if codigo not in tasas:
            tasas[codigo] = cotizador.tasa_vigente(db, codigo, hoy)
        return tasas[codigo]

    lineas: list[LineaCotizacion] = []
    avisos: list[str] = []
    tipos = [c.tipo_equipo_id for c in cotizacion.contenedores]
    codigos_tipo = {c.tipo_equipo_id: c.tipo_equipo.codigo for c in cotizacion.contenedores}

    transportista = None
    tarifas_elegidas: list[Tarifa] = []
    sobre_recibo: list[tuple] = []
    if "flete_principal" in bloques:
        tarifas = _elegir_tarifas(db, cotizacion, elegidas, hoy)
        tarifas_elegidas = tarifas
        transportista = _transportista(tarifas)
        proveedor_flete = tarifas[0].proveedor_id
        for tarifa in tarifas:
            precios = _precios(tarifa, carga)
            calculo = cotizador.calcular_linea(_cantidad_tarifa(tarifa, carga), precios, tasa(tarifa))
            concepto = f"Flete {cotizacion.modo} {cotizacion.origen.codigo} → {cotizacion.destino.codigo}"
            if tarifa.tipo_equipo_id is not None:
                concepto += f" {codigos_tipo[tarifa.tipo_equipo_id]}"
            lineas.append(
                _nueva_linea(
                    tarifa, concepto, "FLETE_PRINCIPAL", precios, calculo,
                    fiscal="RECIBO_CAJA", aplica_iva=False, rol="PRINCIPAL", opcional=False, incluida=True,
                    tipo_equipo_id=tarifa.tipo_equipo_id,
                )
            )
    else:
        # D-F3-9: sin flete, el proveedor opcional; sin él, solo los recargos propios (proveedor NULL).
        proveedor_flete = proveedor_id

    # FIX cotizador: además de los recargos que el Incoterm asigna a XPRESS (marcados, como siempre), se proponen
    # desmarcados los de los bloques fuera del Incoterm y las alternativas que perdieron por D-F3-7. Las líneas
    # desmarcadas no se cobran: los totales no cambian hasta que el usuario las marque.
    por_tipo = cotizacion.servicio.usa_tipo_equipo
    vinculos = _vinculos_cotizacion(db, cotizacion, tarifas_elegidas, hoy)
    for campo in CAMPOS_RECARGO:
        bloque = BLOQUE_RECARGO[campo]
        dentro = campo in bloques
        puerto, lado = _puerto_de_bloque(cotizacion, bloque)
        # D-R2: primero los vinculados a la tarifa elegida (toman el puerto de la tarifa por su lado); luego los
        # generales del puerto, sin los vinculados a otras tarifas y sin los vinculados a otros servicios.
        vigentes = [r for r in vinculos["por_tarifa"] if r.bloque_incoterm == bloque and (lado is None or r.lado == lado)]
        vinculados = set(vinculos["ids_tarifa"])
        for recargo in _recargos_vigentes(db, puerto, bloque, lado, hoy):
            if recargo.id in vinculados:
                continue
            if recargo.id in vinculos["con_tarifa"]:
                continue  # vinculado a otra tarifa
            servicios_del_recargo = vinculos["por_servicio"].get(recargo.id)
            if servicios_del_recargo is not None:
                if vinculos["servicio_id"] not in servicios_del_recargo:
                    continue
                vinculados.add(recargo.id)
            vigentes.append(recargo)
        elegidos = cotizador.elegir_mas_especifico(vigentes, proveedor_flete, cotizacion.modo, tipos, por_tipo_equipo=por_tipo,
                                                   vinculados=vinculados)
        if not elegidos:
            if dentro:
                avisos.append(f"Sin recargo cargado para {bloque} en {puerto.codigo}")
            continue
        ganadores = {recargo.id for recargo, _ in elegidos}
        candidatos = [(recargo, cubre, "INCOTERM" if dentro else "FUERA_INCOTERM") for recargo, cubre in elegidos]
        for recargo in cotizador.recargos_aplicables(vigentes, proveedor_flete, cotizacion.modo, tipos, vinculados):
            if recargo.id not in ganadores:
                cubre = ((recargo.tipo_equipo_id,) if recargo.tipo_equipo_id else tuple(sorted(set(tipos)))) if por_tipo else ()
                candidatos.append((recargo, cubre, "ALTERNATIVA"))
        es_seguro = bloque == "SEGURO"
        for recargo, cubre, seleccion in candidatos:
            marcada = seleccion == "INCOTERM" and not es_seguro  # D-F3-6: el seguro se propone apagado
            opcional = es_seguro or not marcada
            if recargo.rate_unit == "PCT_RECIBO":
                # D3: se calcula al final, sobre la base
                sobre_recibo.append((recargo, bloque, puerto, seleccion, marcada, opcional, recargo.id in vinculados))
                continue
            try:
                if recargo.rate_unit == "PCT_VALOR" and carga.valor_mercancia_usd is None:
                    cantidad = Decimal(0)
                else:
                    cantidad = cotizador.cantidad_por_unidad(
                        recargo.rate_unit, carga, tipo_equipo_id=recargo.tipo_equipo_id, tipos=cubre or None
                    )
            except ErrorNegocio as error:
                avisos.append(f"{recargo.concepto}: {error.mensaje}")
                continue
            if cantidad == 0 and recargo.rate_unit == "CONTENEDOR":
                continue
            precios = _precios(recargo, carga)
            try:
                calculo = cotizador.calcular_linea(cantidad, precios, tasa(recargo))
            except ErrorNegocio as error:
                if seleccion == "INCOTERM":
                    raise
                avisos.append(f"{recargo.concepto}: {error.mensaje}")  # una línea desmarcada sin tasa no frena la propuesta
                continue
            tipo_linea = recargo.tipo_equipo_id or (cubre[0] if len(cubre) == 1 else None)
            lineas.append(
                _nueva_linea(
                    recargo, recargo.concepto, bloque, precios, calculo,
                    fiscal=_fiscal_recargo(recargo, bloque),
                    aplica_iva=recargo.aplica_iva, rol=recargo.rol_ingreso,
                    opcional=opcional, incluida=marcada, tipo_equipo_id=tipo_linea, seleccion=seleccion,
                    vinculado=recargo.id in vinculados,
                )
            )
    if sobre_recibo:
        base = cotizador.base_pct_recibo(lineas)
        for recargo, bloque, puerto, seleccion, marcada, opcional, es_vinculado in sobre_recibo:
            precios = _precios(recargo, carga)
            try:
                calculo = cotizador.calcular_pct_recibo(base, precios, tasa(recargo))
            except ErrorNegocio as error:
                if seleccion == "INCOTERM":
                    raise
                avisos.append(f"{recargo.concepto}: {error.mensaje}")
                continue
            lineas.append(
                _nueva_linea(
                    recargo, recargo.concepto, bloque, precios, calculo,
                    fiscal=_fiscal_recargo(recargo, bloque),
                    aplica_iva=recargo.aplica_iva, rol=recargo.rol_ingreso, opcional=opcional, incluida=marcada,
                    tipo_equipo_id=recargo.tipo_equipo_id, seleccion=seleccion, vinculado=es_vinculado,
                )
            )
        if base <= 0 and any(item[4] for item in sobre_recibo):
            avisos.append(cotizador.AVISO_SIN_BASE)
    if not any(linea.recargo_id is not None for linea in lineas):
        avisos.append(AVISO_SIN_RECARGOS)
    orden_bloque = {bloque: posicion for posicion, bloque in enumerate(BLOQUES_LINEA)}
    lineas.sort(key=lambda l: (orden_bloque[l.bloque_incoterm], cotizador.concepto_clave(l.concepto)))
    for posicion, linea in enumerate(lineas, start=1):
        linea.orden = posicion
    return lineas, avisos, transportista


def _reemplazar_lineas(db: Session, cotizacion: Cotizacion, lineas: list[LineaCotizacion]) -> None:
    cotizacion.lineas.clear()
    db.flush()
    cotizacion.lineas.extend(lineas)


def proponer_lineas(db: Session, actor: Usuario, cotizacion_id: int, datos: dict[str, Any]) -> dict:
    cotizacion = _editable(db, actor, cotizacion_id)
    _exigir_confirmacion(cotizacion, datos.get("confirmar", False))
    proveedor_id = datos.get("proveedor_id")
    if proveedor_id is not None:
        _activo(db, Proveedor, proveedor_id, "el proveedor")
    else:
        proveedor_id = cotizacion.proveedor_recargos_id
    hoy = fechas.hoy_ecuador()
    with db.no_autoflush:
        lineas, avisos, transportista = _proponer(db, cotizacion, datos.get("tarifas") or {}, proveedor_id, hoy)
        antes = {"lineas": len(cotizacion.lineas), "proveedor_recargos_id": cotizacion.proveedor_recargos_id}
        cotizacion.proveedor_recargos_id = proveedor_id
        if transportista is not None:
            cotizacion.transportista = transportista  # H-F4-5: proponer vuelve a copiar el de la tarifa
        _reemplazar_lineas(db, cotizacion, lineas)
        auditoria.registrar(
            db, actor, "cotizacion", cotizacion.id, "EDITAR", antes=antes,
            despues={"lineas": len(lineas), "proveedor_recargos_id": proveedor_id},
            nota=f"PROPONER LINEAS: {len(lineas)}",
        )
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id, avisos)


# ---------- ¿Por qué no aparece? (FIX cotizador) ----------

NOMBRES_BLOQUE = {
    "RECOGIDA_ORIGEN": "recogida en origen", "DESPACHO_EXPORT": "despacho de exportación",
    "GASTOS_ORIGEN": "gastos en origen", "SEGURO": "seguro", "GASTOS_DESTINO": "gastos en destino",
    "DESPACHO_IMPORT": "despacho de importación", "ENTREGA_FINAL": "entrega final",
}


def _fecha(valor: date) -> str:
    return valor.strftime("%d/%m/%Y")


def motivos_recargo(db: Session, cotizacion: Cotizacion, recargo: Recargo, proveedor_flete: int | None, hoy: date,
                    tasas: dict[str, bool], tarifas_elegidas: set[int] | None = None) -> list[str]:
    """Por qué un recargo no entra en la propuesta de esta cotización, en palabras simples. Vacío = sí aplica."""
    motivos: list[str] = []
    if not recargo.activo:
        motivos.append("está inactivo")
    vinculos = {v.tarifa_id for v in recargo.vinculos_tarifa}
    vinculado_aqui = bool(vinculos & (tarifas_elegidas or set()))
    if vinculos and not vinculado_aqui:
        motivos.append("está vinculado a otra tarifa (" + ", ".join(f"#{i}" for i in sorted(vinculos)) + ")")
    servicios_v = {v.servicio_id for v in recargo.vinculos_servicio}
    if servicios_v and cotizacion.servicio.id not in servicios_v:
        motivos.append("está vinculado a otros servicios (" + ", ".join(v.servicio.codigo for v in recargo.vinculos_servicio) + ")")
    if not vinculado_aqui and recargo.proveedor_id is not None and recargo.proveedor_id != proveedor_flete:
        motivos.append(f"es de otro proveedor ({recargo.proveedor.nombre})")
    if recargo.modo is not None and recargo.modo != cotizacion.modo:
        motivos.append(f"es de otro servicio ({recargo.modo}; esta cotización es {cotizacion.modo})")
    tipos = {c.tipo_equipo_id for c in cotizacion.contenedores}
    if recargo.tipo_equipo_id is not None and recargo.tipo_equipo_id not in tipos:
        motivos.append(f"es de otro tipo de contenedor ({recargo.tipo_equipo.codigo})")
    puerto, lado = _puerto_de_bloque(cotizacion, recargo.bloque_incoterm)
    bloque = NOMBRES_BLOQUE.get(recargo.bloque_incoterm, recargo.bloque_incoterm)
    if vinculado_aqui or recargo.puerto_id is None:
        pass  # vinculado a la tarifa: el puerto sale de la tarifa por su lado
    elif recargo.puerto_id != puerto.id:
        papel = ("el ORIGEN" if recargo.puerto_id == cotizacion.origen_puerto_id
                 else "el DESTINO" if recargo.puerto_id == cotizacion.destino_puerto_id else None)
        if papel:
            motivos.append(f"otro puerto: es de {bloque} (lado {recargo.lado}) pero está cargado en {recargo.puerto.codigo}, "
                           f"que es {papel} de esta cotización; debería estar en {puerto.codigo}")
        else:
            motivos.append(f"otro puerto: está en {recargo.puerto.codigo}; esta cotización usa {puerto.codigo} para {bloque}")
    elif lado is not None and recargo.lado != lado:
        motivos.append(f"otro lado: está como {recargo.lado}; en {puerto.codigo} esta cotización usa el lado {lado}")
    if recargo.valido_hasta < hoy:
        motivos.append(f"vencido el {_fecha(recargo.valido_hasta)}")
    elif recargo.valido_desde > hoy:
        motivos.append(f"vigente recién desde el {_fecha(recargo.valido_desde)}")
    codigo = recargo.moneda.codigo
    if codigo not in tasas:
        try:
            cotizador.tasa_vigente(db, codigo, hoy)
            tasas[codigo] = True
        except ErrorNegocio:
            tasas[codigo] = False
    if not tasas[codigo]:
        motivos.append(f"sin tasa de cambio vigente para {codigo}")
    return motivos


def recargos_descartados(db: Session, usuario: Usuario, cotizacion_id: int) -> dict:
    """Los recargos del proveedor del flete, los propios de XPRESS y los de los puertos de la cotización que NO están
    en el borrador, cada uno con su motivo. Solo para quien edita tarifas y recargos (admin y pricing)."""
    cotizacion = obtener_cotizacion(db, usuario, cotizacion_id)
    hoy = fechas.hoy_ecuador()
    flete = next((l for l in cotizacion.lineas if l.tarifa_id is not None), None)
    proveedor_flete = flete.proveedor_id if flete else cotizacion.proveedor_recargos_id
    tarifas_elegidas = {l.tarifa_id for l in cotizacion.lineas if l.tarifa_id is not None}
    en_borrador = {l.recargo_id for l in cotizacion.lineas if l.recargo_id is not None}
    puertos = (cotizacion.origen_puerto_id, cotizacion.destino_puerto_id)
    filtro = Recargo.puerto_id.in_(puertos)
    if proveedor_flete is not None:
        filtro = filtro | (Recargo.proveedor_id == proveedor_flete)
    # D-R2: también los vinculados a cualquier tarifa de esta ruta (los de otra tarifa explican por qué no salen).
    filtro = filtro | Recargo.id.in_(select(RecargoTarifa.recargo_id).join(Tarifa, Tarifa.id == RecargoTarifa.tarifa_id).where(
        Tarifa.origen_puerto_id == cotizacion.origen_puerto_id, Tarifa.destino_puerto_id == cotizacion.destino_puerto_id))
    consulta = (select(Recargo).options(selectinload(Recargo.moneda), selectinload(Recargo.puerto),
                                        selectinload(Recargo.proveedor), selectinload(Recargo.tipo_equipo),
                                        selectinload(Recargo.vinculos_tarifa),
                                        selectinload(Recargo.vinculos_servicio).selectinload(RecargoServicio.servicio))
                .where(filtro).order_by(Recargo.puerto_id, Recargo.bloque_incoterm, Recargo.id))
    tasas: dict[str, bool] = {}
    salida = []
    for recargo in db.scalars(consulta):
        if recargo.id in en_borrador:
            continue
        motivos = motivos_recargo(db, cotizacion, recargo, proveedor_flete, hoy, tasas, tarifas_elegidas)
        if not motivos:
            motivos = ["aplica, pero no está en el borrador: vuelva a elegir la tarifa para proponer las líneas"]
        salida.append({
            "recargo_id": recargo.id, "concepto": recargo.concepto,
            "proveedor": recargo.proveedor.nombre if recargo.proveedor else "XPRESS (propio)",
            "puerto": recargo.puerto.codigo if recargo.puerto else "(de la tarifa)", "lado": recargo.lado,
            "bloque_incoterm": recargo.bloque_incoterm,
            "modo": recargo.modo, "tipo_equipo": recargo.tipo_equipo.codigo if recargo.tipo_equipo else None,
            "valido_desde": recargo.valido_desde.isoformat(), "valido_hasta": recargo.valido_hasta.isoformat(),
            "activo": recargo.activo, "motivos": motivos,
        })
    return {"cotizacion_id": cotizacion.id, "proveedor_flete_id": proveedor_flete, "recargos": salida}


# ---------- Ajuste de una línea (§10.4, H9) ----------


def _foto_linea(linea: LineaCotizacion) -> dict[str, Any]:
    return {
        "orden": linea.orden,
        "concepto": linea.concepto,
        "precio_venta_unit_usd": linea.precio_venta_unit_usd,
        "subtotal_venta_usd": linea.subtotal_venta_usd,
        "ajuste_manual": linea.ajuste_manual,
        "motivo_ajuste": linea.motivo_ajuste,
        "incluida": linea.incluida,
        "seleccion": linea.seleccion,
    }


def actualizar_linea(db: Session, actor: Usuario, cotizacion_id: int, linea_id: int, cambios: dict[str, Any]) -> dict:
    cotizacion = _editable(db, actor, cotizacion_id)
    linea = next((l for l in cotizacion.lineas if l.id == linea_id), None)
    if linea is None:
        raise ErrorNegocio(404, "LINEA_NO_ENCONTRADA", "Línea no encontrada")
    antes = _foto_linea(linea)
    notas = []
    with db.no_autoflush:
        if cambios.get("quitar_ajuste"):
            linea.ajuste_manual = False
            linea.motivo_ajuste = None
            notas.append(f"QUITAR AJUSTE LINEA {linea.orden}")
        if cambios.get("precio_venta_unit_usd") is not None:
            motivo = " ".join((cambios.get("motivo") or "").split())
            if len(motivo) < MOTIVO_MINIMO:
                raise ErrorNegocio(
                    422, "MOTIVO_REQUERIDO", f"El ajuste exige un motivo de al menos {MOTIVO_MINIMO} caracteres"
                )
            linea.precio_venta_unit_usd = precio_venta.validar_monto(
                cambios["precio_venta_unit_usd"], "El precio ajustado", positivo=True
            )
            linea.ajuste_manual = True
            linea.motivo_ajuste = motivo
            notas.append(f"AJUSTE LINEA {linea.orden}: {motivo}")
        if cambios.get("incluida") is not None:
            # FIX cotizador: cualquier recargo se marca o desmarca; el flete principal no.
            if not linea.opcional and linea.recargo_id is None:
                raise ErrorNegocio(422, "LINEA_NO_OPCIONAL", "El flete principal no se puede quitar de la cotización")
            if cambios["incluida"] and linea.rate_unit == "PCT_VALOR" and cotizacion.valor_mercancia_usd is None:
                raise ErrorNegocio(
                    422, "VALOR_MERCANCIA_REQUERIDO", "Indique el valor de la mercancía para el seguro como % del valor"
                )
            if linea.recargo_id is not None:
                linea.opcional = True  # un recargo desmarcado queda como opcional apagado (regla opcional OR incluida)
            linea.incluida = cambios["incluida"]
            notas.append(f"LINEA {linea.orden} {'INCLUIDA' if linea.incluida else 'EXCLUIDA'}")
            if linea.incluida and linea.recargo_id is not None:
                # D-F3-7: uno por concepto. Elegir una alternativa desmarca la otra del mismo concepto y bloque.
                for otra in cotizacion.lineas:
                    if (otra is not linea and otra.incluida and otra.recargo_id is not None
                            and otra.bloque_incoterm == linea.bloque_incoterm
                            and cotizador.concepto_clave(otra.concepto) == cotizador.concepto_clave(linea.concepto)
                            and (otra.tipo_equipo_id is None or linea.tipo_equipo_id is None
                                 or otra.tipo_equipo_id == linea.tipo_equipo_id)):
                        otra.opcional = True
                        otra.incluida = False
                        notas.append(f"LINEA {otra.orden} EXCLUIDA (un recargo por concepto)")
        if not notas:
            raise ErrorNegocio(422, "SIN_CAMBIOS", "Indique un precio con motivo, quitar_ajuste o incluida")
        hoy = fechas.hoy_ecuador()
        if linea.rate_unit != "PCT_RECIBO":
            _recalcular(db, linea, carga_de(cotizacion), hoy, {})
        _guardar_pct_recibo(db, cotizacion, hoy)
        auditoria.registrar(
            db, actor, "cotizacion", cotizacion.id, "EDITAR", antes=antes, despues=_foto_linea(linea),
            nota="; ".join(notas)[:300],
        )
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


# ---------- Emitir (D-F3-1, D-F3-12, §10.6) ----------


def siguiente_numero(db: Session, anio: int) -> str:
    """Contador anual con SELECT … FOR UPDATE dentro de la transacción de la emisión (D-F3-1)."""
    db.execute(insert(ContadorCotizacion).values(anio=anio, ultimo=0).on_conflict_do_nothing(index_elements=["anio"]))
    contador = db.scalars(
        select(ContadorCotizacion).where(ContadorCotizacion.anio == anio).with_for_update().execution_options(
            populate_existing=True
        )
    ).one()
    contador.ultimo += 1
    return f"{get_settings().COT_PREFIJO}-{anio}-{contador.ultimo:05d}"


def _texto_dias(valores: list[int | None]) -> str:
    dias = sorted({v for v in valores if v is not None})
    if not dias:
        return "—"
    if len(dias) == 1:
        return f"{dias[0]} días"
    return f"{dias[0]}–{dias[-1]} días"


def _cobro_minimo(linea: LineaCotizacion, calculo) -> bool:
    """Se cobró el mínimo de venta: sin ajuste manual y cantidad × precio quedó por debajo del mínimo."""
    if linea.ajuste_manual or calculo.minimo_venta_usd <= 0:
        return False
    bruto = cotizador.a_4(calculo.cantidad * calculo.precio_venta_unit_usd)
    return bruto < calculo.minimo_venta_usd and calculo.subtotal_venta_usd == calculo.minimo_venta_usd


def _snapshot(cotizacion: Cotizacion, condiciones: str, totales: cotizador.Totales, filas: list,
              empresa: dict[str, str]) -> dict[str, Any]:
    """Textos y montos de venta congelados (D-F3-13). Nunca lleva costo, margen, proveedor ni tasa.

    F4: también los datos de la empresa (A4), el transportista, la descripción de la carga y, por línea, el
    mínimo de venta, la unidad de peso aplicada y si se cobró el mínimo.
    """
    cliente = cotizacion.cliente
    contacto = cotizacion.contacto
    fletes = [l.tarifa for l, _ in filas if l.tarifa is not None]
    lineas = [
        {
            "orden": l.orden,
            "concepto": l.concepto,
            "bloque_incoterm": l.bloque_incoterm,
            "bloque_fiscal": l.bloque_fiscal,
            "cantidad": str(c.cantidad),
            "rate_unit": l.rate_unit,
            "precio_venta_unit_usd": str(c.precio_venta_unit_usd),
            "subtotal_venta_usd": str(c.subtotal_venta_usd),
            "aplica_iva": l.aplica_iva,
            "minimo_venta_usd": str(c.minimo_venta_usd),
            "cobro_minimo": _cobro_minimo(l, c),
            "unidad_peso": l.unidad_peso,
            "tipo_equipo": l.tipo_equipo.codigo if l.tipo_equipo else None,
        }
        for l, c in filas
    ]

    def puerto(p: Puerto) -> dict[str, str]:
        return {"codigo": p.codigo, "nombre": p.nombre, "pais": p.pais.nombre}

    return {
        "empresa": EMPRESA,
        "numero": cotizacion.numero,
        "fecha_emision": cotizacion.fecha_emision.isoformat() if cotizacion.fecha_emision else None,
        "valida_hasta": cotizacion.valida_hasta.isoformat() if cotizacion.valida_hasta else None,
        "cliente": {
            "razon_social": cliente.razon_social,
            "tipo_id": cliente.tipo_id,
            "ruc_o_id": cliente.ruc_o_id,
            "direccion": cliente.direccion,
            "ciudad": cliente.ciudad,
            "pais": cliente.pais.nombre,
        },
        "contacto": (
            {"nombre": contacto.nombre, "cargo": contacto.cargo, "email": contacto.email, "telefono": contacto.telefono}
            if contacto
            else None
        ),
        "comercial": {"nombre": cotizacion.comercial.nombre, "email": cotizacion.comercial.email},
        "origen": puerto(cotizacion.origen),
        "destino": puerto(cotizacion.destino),
        "incoterm": {"codigo": cotizacion.incoterm.codigo, "nombre": cotizacion.incoterm.nombre},
        "sentido": cotizacion.sentido,
        "modo": cotizacion.modo,
        "servicio": servicios.snapshot_servicio(cotizacion.servicio),  # E0: textos del PDF congelados
        "carga": _carga_dict(cotizacion),
        "transit_time": _texto_dias([t.transit_time_dias for t in fletes]),
        "dias_libres": _texto_dias([t.dias_libres for t in fletes]),
        "condiciones": condiciones,
        "notas_cliente": cotizacion.notas_cliente,
        "transportista": cotizacion.transportista,
        "descripcion_carga": cotizacion.descripcion_carga,
        "datos_empresa": empresa,
        "textos_pdf": administracion.textos_pdf(object_session(cotizacion)),  # E2: congelados al emitir
        "lineas": lineas,
        "totales": {
            "subtotal_recibo_caja": str(totales.subtotal_recibo_caja),
            "subtotal_factura": str(totales.subtotal_factura),
            "iva": str(totales.iva),
            "total_general": str(totales.total_general),
            "iva_tasa": str(totales.iva_tasa),
        },
    }


def emitir_cotizacion(db: Session, actor: Usuario, cotizacion_id: int, valida_hasta: date | None) -> dict:
    cotizacion = _editable(db, actor, cotizacion_id)
    incluidas = [linea for linea in cotizacion.lineas if linea.incluida]
    if not incluidas:
        raise ErrorNegocio(422, "SIN_LINEAS", "La cotización no tiene líneas incluidas; proponga las líneas primero")
    if not cotizacion.cliente.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", "El cliente está inactivo")
    contacto = cotizacion.contacto
    if contacto is None or not contacto.activo or contacto.cliente_id != cotizacion.cliente_id:
        raise ErrorNegocio(422, "CONTACTO_REQUERIDO", "Indique un contacto activo del cliente antes de emitir")
    condiciones = leer_config(db, "condiciones_generales_pdf").strip()
    if not condiciones:
        raise ErrorNegocio(
            422, "CONDICIONES_PDF_VACIAS", "Cargue las condiciones generales en Configuración antes de emitir"
        )
    hoy = fechas.hoy_ecuador()
    no_vigentes = [
        {"orden": l.orden, "concepto": l.concepto} for l in incluidas if not _vigente(l.tarifa or l.recargo, hoy)
    ]
    if no_vigentes:
        raise ErrorNegocio(
            409, "RE_PROPONER", "Hay tarifas o recargos que ya no están vigentes; vuelva a proponer las líneas",
            extra={"lineas": no_vigentes},
        )
    for linea in incluidas:
        if linea.rate_unit == "PCT_VALOR" and cotizacion.valor_mercancia_usd is None:
            raise ErrorNegocio(
                422, "VALOR_MERCANCIA_REQUERIDO", "Indique el valor de la mercancía para el seguro como % del valor"
            )
    calculada = min(linea.valido_hasta_origen for linea in incluidas)
    if valida_hasta is not None:
        if valida_hasta > calculada:
            raise ErrorNegocio(
                422, "NO_SE_PUEDE_EXTENDER", f"La validez no puede pasar del {calculada.isoformat()} (vigencias usadas)"
            )
        if valida_hasta < hoy:
            raise ErrorNegocio(422, "VALIDEZ_INVALIDA", "La validez no puede ser anterior a la fecha de emisión")
    with db.no_autoflush:
        filas, _ = _calcular(db, cotizacion, hoy, guardar=True)
        calculos = {linea.id: calculo for linea, calculo in filas}
        iva_tasa = leer_iva_tasa(db)
        totales = cotizador.totales([_Fila(l, calculos[l.id]) for l in incluidas], iva_tasa)
        cotizacion.numero = siguiente_numero(db, hoy.year)
        cotizacion.estado = "EMITIDA"
        cotizacion.fecha_emision = hoy
        cotizacion.valida_hasta = valida_hasta or calculada
        cotizacion.subtotal_recibo_caja = totales.subtotal_recibo_caja
        cotizacion.subtotal_factura = totales.subtotal_factura
        cotizacion.iva = totales.iva
        cotizacion.total_general = totales.total_general
        cotizacion.costo_total = totales.costo_total
        cotizacion.margen_total = totales.margen_total
        cotizacion.margen_pct = totales.margen_pct
        cotizacion.iva_tasa_aplicada = iva_tasa
        cotizacion.snapshot_emision = _snapshot(
            cotizacion, condiciones, totales, [(l, calculos[l.id]) for l in incluidas], datos_empresa(db)
        )
        auditoria.registrar(
            db, actor, "cotizacion", cotizacion.id, "EDITAR",
            antes={"estado": "BORRADOR"},
            despues={"estado": "EMITIDA", "numero": cotizacion.numero, "total_general": totales.total_general,
                     "valida_hasta": cotizacion.valida_hasta.isoformat()},
            nota=f"EMITIR {cotizacion.numero}",
        )
    from app.services import notificaciones  # E3: margen bajo y reemplazo (outbox, en esta misma transacción)

    notificaciones.al_emitir(db, cotizacion, sum(1 for l in incluidas if calculos[l.id].bajo_costo))
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


# ---------- Estados, descartar y duplicar (D-F3-2, D-F3-11, §11) ----------


def cambiar_estado(db: Session, actor: Usuario, cotizacion_id: int, datos: dict[str, Any]) -> dict:
    cotizacion = obtener_cotizacion(db, actor, cotizacion_id)
    nuevo = datos["estado"]
    if nuevo == "ENVIADA":
        raise ErrorNegocio(422, "ESTADO_NO_PERMITIDO", "ENVIADA la marca solo el envío por correo (F4)")
    if nuevo not in ESTADOS_FINALES:
        raise ErrorNegocio(422, "ESTADO_NO_PERMITIDO", "Solo se marca ACEPTADA o RECHAZADA")
    if cotizacion.estado not in ("EMITIDA", "ENVIADA") or not cotizacion.activo:
        raise ErrorNegocio(
            409, "TRANSICION_INVALIDA", f"Una cotización {cotizacion.estado} no puede pasar a {nuevo}"
        )
    motivo = datos.get("motivo_rechazo")
    detalle = " ".join((datos.get("detalle_rechazo") or "").split()) or None
    if nuevo == "RECHAZADA":
        if motivo is None:
            raise ErrorNegocio(422, "MOTIVO_RECHAZO_REQUERIDO", "Indique el motivo del rechazo")
        # E2: los motivos salen del catálogo motivo_rechazo; cada uno dice si exige detalle (OTRO siempre).
        if administracion.motivo_utilizable(db, motivo).exige_detalle and detalle is None:
            raise ErrorNegocio(422, "DETALLE_RECHAZO_REQUERIDO", f"Con motivo {motivo}, el detalle es obligatorio")
    else:
        motivo, detalle = None, None
    antes = {"estado": cotizacion.estado}
    with db.no_autoflush:
        cotizacion.estado = nuevo
        cotizacion.motivo_rechazo = motivo
        cotizacion.detalle_rechazo = detalle
        nota = f"ESTADO {antes['estado']}→{nuevo}" + (f" ({motivo})" if motivo else "")
        auditoria.registrar(
            db, actor, "cotizacion", cotizacion.id, "EDITAR", antes=antes,
            despues={"estado": nuevo, "motivo_rechazo": motivo, "detalle_rechazo": detalle}, nota=nota,
        )
    from app.services import notificaciones  # E3: avisos (outbox, en esta misma transacción)

    notificaciones.al_cerrar_cotizacion(db, cotizacion, nuevo)
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


def descartar_cotizacion(db: Session, actor: Usuario, cotizacion_id: int) -> dict:
    cotizacion = _editable(db, actor, cotizacion_id)
    with db.no_autoflush:
        cotizacion.activo = False
        auditoria.registrar(
            db, actor, "cotizacion", cotizacion.id, "DESACTIVAR", antes={"activo": True}, despues={"activo": False},
            nota="DESCARTAR BORRADOR",
        )
    confirmar(db)
    return _respuesta(db, actor, cotizacion.id)


def duplicar_cotizacion(db: Session, actor: Usuario, cotizacion_id: int) -> dict:
    """BORRADOR nuevo desde cualquier estado; copia cabecera, carga y contenedores, no los ajustes.

    Intenta proponer con las mismas tarifas si siguen elegibles; si no, queda sin líneas
    (requiere_proponer=true) y la respuesta lo explica en avisos.
    """
    origen = obtener_cotizacion(db, actor, cotizacion_id)
    clientes.obtener_cliente(db, actor, origen.cliente_id)  # el cliente debe seguir en el alcance (H19)
    actor_id = auditoria.id_de(actor)
    contacto_id = origen.contacto_id if origen.contacto and origen.contacto.activo else None
    elegidas = {}
    for linea in origen.lineas:
        if linea.tarifa_id is not None:
            clave = str(linea.tipo_equipo_id) if origen.servicio.usa_tipo_equipo else origen.modo
            elegidas[clave] = linea.tarifa_id
    avisos: list[str] = []
    with db.no_autoflush:
        nueva = Cotizacion(
            **{campo: getattr(origen, campo) for campo in CAMPOS_CABECERA if campo != "contacto_id"},
            contacto_id=contacto_id,
            comercial_id=actor_id,
            creado_por=actor_id,
            estado="BORRADOR",
            cotizacion_origen_id=origen.id,
        )
        nueva.contenedores = [
            CotizacionContenedor(tipo_equipo_id=c.tipo_equipo_id, cantidad=c.cantidad) for c in origen.contenedores
        ]
        db.add(nueva)
        db.flush()
        db.refresh(nueva)
        try:
            lineas, avisos, transportista = _proponer(
                db, nueva, elegidas, nueva.proveedor_recargos_id, fechas.hoy_ecuador()
            )
            nueva.lineas.extend(lineas)
            if transportista is not None:
                nueva.transportista = transportista
        except ErrorNegocio as error:
            avisos = [f"No se pudieron proponer las líneas: {error.mensaje}"]
        auditoria.registrar(
            db, actor, "cotizacion", nueva.id, "EDITAR", despues=_foto(nueva), nota=f"DUPLICAR desde #{origen.id}"
        )
    confirmar(db)
    return _respuesta(db, actor, nueva.id, avisos)


# ---------- PDF (§12, D-F3-13) ----------


def pdf_cotizacion(db: Session, usuario: Usuario, cotizacion_id: int) -> tuple[bytes, str]:
    """Emitida: desde el snapshot congelado. Borrador: vista previa en vivo, sin número y con marca de agua."""
    cotizacion = obtener_cotizacion(db, usuario, cotizacion_id)
    if cotizacion.estado == "BORRADOR":
        hoy = fechas.hoy_ecuador()
        filas, _ = _vivo(db, cotizacion, hoy)
        incluidas = [(linea, calculo) for linea, calculo in filas if linea.incluida]
        totales = cotizador.totales([_Fila(l, c) for l, c in incluidas], leer_iva_tasa(db))
        datos = _snapshot(
            cotizacion, leer_config(db, "condiciones_generales_pdf").strip(), totales, incluidas, datos_empresa(db)
        )
        datos["valida_hasta"] = min((l.valido_hasta_origen for l, _ in incluidas), default=None)
        datos["valida_hasta"] = datos["valida_hasta"].isoformat() if datos["valida_hasta"] else None
        borrador = True
    else:
        datos = cotizacion.snapshot_emision
        borrador = False
    return pdf.generar_pdf_de(datos, borrador), pdf.nombre_archivo(
        cotizacion.numero, cotizacion.id, cotizacion.cliente.razon_social
    )

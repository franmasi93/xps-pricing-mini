"""M5 Recargos locales (THC, BL, handling, seguro…) por puerto y lado.

- Mismo esquema de venta, mínimos, decimales, vigencias y gating que la tarifa (services/tarifas).
- No superposición (D-F2-1) por (proveedor o null, puerto, lado, bloque, concepto, modo o null,
  tipo_equipo o null); el concepto se compara sin distinguir mayúsculas.
- Unidad según el modo (A1, D-F2-10); sin modo, según el tipo de puerto.
- Seguro por envío o como % del valor de la mercancía (PCT_VALOR, solo en USD; D-F3-3).
- % sobre el Recibo de Caja (PCT_RECIBO, D3 de F4): costo = porcentaje, mínimo en USD; solo USD y en cualquier
  bloque menos el seguro (el flete principal no es un recargo).
"""
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import Moneda, Proveedor, Puerto, Recargo, TipoEquipo, Usuario
from app.schemas.tarifas import PuertoRef, RecargoCosto, RecargoCostoMargen, RecargoVenta, Referencia, TipoEquipoRef
from app.services import auditoria, precio_venta
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
    validar_venta,
)

LADO_BLOQUES = {
    "ORIGEN": {"RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN", "SEGURO"},
    "DESTINO": {"GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL", "SEGURO"},
}
# A1 + D-F2-10: con modo, manda el modo; sin modo, el tipo de puerto. CONTENEDOR solo con FCL.
UNIDADES_POR_MODO = {"AEREO": {"KG", "ENVIO"}, "LCL": {"WM", "CBM", "ENVIO"}, "FCL": {"CONTENEDOR", "ENVIO"}}
UNIDADES_POR_PUERTO = {"AEREO": {"KG", "ENVIO"}, "MARITIMO": {"WM", "CBM", "ENVIO"}}
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
    "activo",
)


def normalizar_concepto(concepto: str) -> str:
    """Se guarda como lo escribió Pricing, con btrim y espacios internos colapsados (A4)."""
    return " ".join(concepto.split())


def _clave_recargo(datos: dict[str, Any]) -> list:
    return [
        Recargo.proveedor_id.is_not_distinct_from(datos.get("proveedor_id")),
        Recargo.puerto_id == datos["puerto_id"],
        Recargo.lado == datos["lado"],
        Recargo.bloque_incoterm == datos["bloque_incoterm"],
        func.lower(Recargo.concepto) == datos["concepto"].lower(),
        Recargo.modo.is_not_distinct_from(datos.get("modo")),
        Recargo.tipo_equipo_id.is_not_distinct_from(datos.get("tipo_equipo_id")),
    ]


def _validar_recargo(db: Session, datos: dict[str, Any], excluir_id: int | None = None) -> dict[str, Any]:
    activo = datos.get("activo", True)
    puerto = referencia_activa(db, Puerto, datos["puerto_id"], "el puerto", activo)
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

    modo = datos.get("modo")
    if modo is not None:
        tipo_puerto = "AEREO" if modo == "AEREO" else "MARITIMO"
        if puerto.tipo != tipo_puerto:
            raise ErrorNegocio(
                422, "PUERTO_MODO_INCONSISTENTE", "El modo AEREO usa aeropuertos; LCL y FCL usan puertos marítimos"
            )
    if datos.get("tipo_equipo_id") is not None:
        if modo != "FCL":
            raise ErrorNegocio(422, "TIPO_EQUIPO_NO_PERMITIDO", "Solo los recargos FCL llevan tipo de equipo")
        referencia_activa(db, TipoEquipo, datos["tipo_equipo_id"], "el tipo de equipo", activo)

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
        permitidas = UNIDADES_POR_MODO[modo] if modo is not None else UNIDADES_POR_PUERTO[puerto.tipo]
    if datos["rate_unit"] not in permitidas:
        referencia = f"el modo {modo}" if modo is not None else f"un puerto {puerto.tipo.lower()}"
        raise ErrorNegocio(
            422,
            "RATE_UNIT_INCOMPATIBLE",
            f"Con {referencia} la unidad debe ser una de: {', '.join(sorted(permitidas))}",
        )

    validar_venta(datos)
    if activo:
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
    )


def presentar_recargo(recargo: Recargo, nivel: str, hoy: date, dias: int):
    venta, venta_minima = precios_de(recargo)
    datos = {
        "id": recargo.id,
        "proveedor": Referencia.model_validate(recargo.proveedor) if recargo.proveedor else None,
        "puerto": PuertoRef.model_validate(recargo.puerto),
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


def crear_recargo(db: Session, actor: Usuario, datos: dict[str, Any]):
    actor_id = auditoria.id_de(actor)
    datos = _validar_recargo(db, dict(datos) | {"activo": True})
    recargo = Recargo(**{campo: datos.get(campo) for campo in CAMPOS_RECARGO}, creado_por=actor_id)
    db.add(recargo)
    enviar(db)
    auditoria.registrar(db, actor, "recargo", recargo.id, "CREAR", despues=foto(recargo, CAMPOS_RECARGO))
    confirmar(db)
    return _presentar(db, actor, recargo)


def actualizar_recargo(db: Session, actor: Usuario, recargo_id: int, cambios: dict[str, Any]):
    recargo = obtener_recargo(db, recargo_id)
    final = _validar_recargo(
        db, {campo: getattr(recargo, campo) for campo in CAMPOS_RECARGO} | cambios, excluir_id=recargo.id
    )
    antes = foto(recargo, CAMPOS_RECARGO)
    with db.no_autoflush:
        for campo in cambios:
            setattr(recargo, campo, final[campo])
        despues = foto(recargo, CAMPOS_RECARGO)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "recargo", recargo_id, accion, antes=antes, despues=despues)
    confirmar(db)
    return _presentar(db, actor, recargo)

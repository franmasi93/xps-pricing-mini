"""Migración 0004 (T208–T214): tablas de cotización, constraints en la base y seguro como % del valor."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import ContadorCotizacion, CotizacionContenedor, LineaCotizacion, Recargo
from fabricas import crear_contacto, crear_cotizacion, crear_moneda, crear_tarifa, payload_recargo, tipo_equipo, usd
from test_seed_f2 import _head_de_alembic

CHECKS_NUEVOS = {
    "ck_recargo_seguro_unidad",
    "ck_recargo_pct_valor_solo_seguro",
    "ck_cotizacion_numero_si_emitida",
    "ck_cotizacion_rechazo_con_motivo",
    "ck_linea_cotizacion_tarifa_xor_recargo",
}


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _rechaza(db_session, objeto) -> None:
    """La base rechaza el INSERT o el UPDATE pendiente; se vuelve al savepoint del test."""
    db_session.add(objeto)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_head_tablas_y_condiciones(db_session):  # T208
    def contar(tabla: str) -> int:
        return db_session.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar_one()

    assert db_session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _head_de_alembic()
    for tabla in ("contador_cotizacion", "cotizacion", "cotizacion_contenedor", "linea_cotizacion"):
        contar(tabla)
    assert (contar("rol"), contar("permiso"), contar("rol_permiso"), contar("tipo_equipo")) == (4, 15, 38, 5)
    condiciones = db_session.execute(
        text("SELECT valor FROM configuracion WHERE clave = 'condiciones_generales_pdf'")
    ).scalar_one()
    assert condiciones == ""
    checks = set(db_session.execute(text("SELECT conname FROM pg_constraint WHERE contype = 'c'")).scalars())
    assert checks.issuperset(CHECKS_NUEVOS)
    assert "ck_recargo_seguro_por_envio" not in checks


@pytest.mark.parametrize(
    ("cambios", "moneda_usd", "estado", "codigo"),
    [
        ({"lado": "DESTINO", "bloque_incoterm": "SEGURO", "rate_unit": "PCT_VALOR", "costo": "0.35"}, True, 201, None),
        ({"lado": "ORIGEN", "bloque_incoterm": "SEGURO", "rate_unit": "PCT_VALOR", "costo": "0.35"}, False, 422,
         "PCT_VALOR_SOLO_USD"),
        ({"rate_unit": "PCT_VALOR", "costo": "0.35"}, True, 422, "PCT_VALOR_SOLO_SEGURO"),
        ({"lado": "ORIGEN", "bloque_incoterm": "SEGURO", "rate_unit": "ENVIO"}, True, 201, None),
    ],
    ids=["pct_valor_usd", "pct_valor_en_otra_moneda", "pct_valor_fuera_de_seguro", "seguro_por_envio_sigue"],
)
def test_recargo_seguro_pct_valor(client, crear_usuario, headers_de, db_session, cambios, moneda_usd, estado, codigo):  # T209
    datos = payload_recargo(db_session, **cambios)
    if not moneda_usd:
        datos["moneda_id"] = crear_moneda(db_session).id
    respuesta = client.post("/v1/recargos", json=datos, headers=headers_de(crear_usuario("pricing")))
    assert respuesta.status_code == estado, respuesta.text
    if codigo:
        assert _codigo(respuesta) == codigo
    else:
        assert respuesta.json()["rate_unit"] == cambios["rate_unit"]


@pytest.mark.parametrize(
    ("bloque", "lado", "unidad"),
    [("GASTOS_DESTINO", "DESTINO", "PCT_VALOR"), ("SEGURO", "DESTINO", "KG")],
    ids=["pct_valor_fuera_de_seguro", "seguro_por_kg"],
)
def test_recargo_checks_en_la_base(db_session, bloque, lado, unidad):  # T210
    datos = payload_recargo(db_session, bloque_incoterm=bloque, lado=lado, rate_unit=unidad)
    for campo in ("costo", "minimo", "parametro_venta"):
        datos[campo] = Decimal(datos[campo])
    for campo in ("valido_desde", "valido_hasta"):
        datos[campo] = date.fromisoformat(datos[campo])
    _rechaza(db_session, Recargo(**datos))


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado": "EMITIDA"},
        {"estado": "RECHAZADA", "_congelada": True},
        {"motivo_rechazo": "OTRO"},
        {"motivo_rechazo": "CARO"},
        {"peso_kg": Decimal("-1")},
        {"cbm": Decimal("-0.5")},
        {"bultos": -1},
        {"valor_mercancia_usd": Decimal("-10")},
        {"numero": "COT-26-1"},
        {"moneda_cotizacion": "EUR"},
        {"activo": False, "estado": "EMITIDA", "_congelada": True},
        {"sentido": "TRANSITO"},
    ],
    ids=[
        "emitida_sin_numero_ni_congelar",
        "rechazada_sin_motivo",
        "otro_sin_detalle",
        "motivo_invalido",
        "peso_negativo",
        "cbm_negativo",
        "bultos_negativos",
        "valor_negativo",
        "numero_mal_formado",
        "moneda_no_usd",
        "descartar_no_borrador",
        "sentido_invalido",
    ],
)
def test_cotizacion_checks_en_la_base(crear_usuario, db_session, cambios):  # T211
    comercial = crear_usuario("comercial")
    cotizacion = crear_cotizacion(db_session, comercial)
    cambios = dict(cambios)
    if cambios.pop("_congelada", False):
        # Todo lo de una emitida, para que la fila falle solo por el CHECK que se prueba.
        cotizacion.numero = f"COT-2026-{cotizacion.id:05d}"
        cotizacion.contacto_id = crear_contacto(db_session, cotizacion.cliente).id
        cotizacion.fecha_emision = date(2026, 10, 7)
        cotizacion.valida_hasta = date(2026, 10, 31)
        cotizacion.total_general = Decimal("100.00")
        cotizacion.iva_tasa_aplicada = Decimal("15.00")
        cotizacion.snapshot_emision = {"cliente": "x"}
    for campo, valor in cambios.items():
        setattr(cotizacion, campo, valor)
    _rechaza(db_session, cotizacion)


def test_cotizacion_congelada_valida_se_guarda(crear_usuario, db_session):  # T211 (control positivo)
    cotizacion = crear_cotizacion(db_session, crear_usuario("comercial"))
    cotizacion.numero = f"COT-2026-{cotizacion.id:05d}"
    cotizacion.contacto_id = crear_contacto(db_session, cotizacion.cliente).id
    cotizacion.estado = "RECHAZADA"
    cotizacion.motivo_rechazo = "OTRO"
    cotizacion.detalle_rechazo = "Eligió otro agente"
    cotizacion.fecha_emision = date(2026, 10, 7)
    cotizacion.valida_hasta = date(2026, 10, 31)
    cotizacion.total_general = Decimal("100.00")
    cotizacion.iva_tasa_aplicada = Decimal("15.00")
    cotizacion.snapshot_emision = {"cliente": "x"}
    db_session.commit()
    assert cotizacion.estado == "RECHAZADA"


def test_cotizacion_origen_igual_destino_en_la_base(crear_usuario, db_session):  # T211 (origen = destino)
    cotizacion = crear_cotizacion(db_session, crear_usuario("comercial"))
    cotizacion.destino_puerto_id = cotizacion.origen_puerto_id
    _rechaza(db_session, cotizacion)


@pytest.mark.parametrize("caso", ["cantidad_cero", "tipo_repetido"])
def test_contenedor_checks_en_la_base(crear_usuario, db_session, caso):  # T212
    cotizacion = crear_cotizacion(db_session, crear_usuario("comercial"), modo="FCL")
    equipo = tipo_equipo(db_session)
    if caso == "cantidad_cero":
        _rechaza(db_session, CotizacionContenedor(cotizacion_id=cotizacion.id, tipo_equipo_id=equipo.id, cantidad=0))
    else:
        db_session.add(CotizacionContenedor(cotizacion_id=cotizacion.id, tipo_equipo_id=equipo.id, cantidad=1))
        db_session.commit()
        _rechaza(db_session, CotizacionContenedor(cotizacion_id=cotizacion.id, tipo_equipo_id=equipo.id, cantidad=2))


def _linea(db_session, cotizacion, **cambios) -> LineaCotizacion:
    datos = {
        "cotizacion_id": cotizacion.id,
        "orden": 1,
        "concepto": "Flete LCL",
        "bloque_incoterm": "FLETE_PRINCIPAL",
        "tarifa_id": crear_tarifa(db_session, "LCL").id,
        "cantidad": Decimal("1"),
        "rate_unit": "WM",
        "costo_unit_original": Decimal("100"),
        "minimo_original": Decimal("0"),
        "moneda_original_id": usd(db_session).id,
        "tasa_aplicada": Decimal("1"),
        "costo_usd": Decimal("100"),
        "precio_venta_unit_usd": Decimal("120"),
        "minimo_venta_usd": Decimal("0"),
        "subtotal_venta_usd": Decimal("120"),
        "precio_calculado_unit_usd": Decimal("120"),
        "bloque_fiscal": "RECIBO_CAJA",
        "aplica_iva": False,
        "rol_ingreso": "PRINCIPAL",
        "valido_hasta_origen": date(2026, 12, 31),
    }
    return LineaCotizacion(**(datos | cambios))


def test_linea_valida_se_guarda(crear_usuario, db_session):  # T213 (control positivo)
    cotizacion = crear_cotizacion(db_session, crear_usuario("comercial"))
    db_session.add(_linea(db_session, cotizacion))
    db_session.commit()
    assert len(cotizacion.lineas) == 1


@pytest.mark.parametrize(
    "caso",
    ["tarifa_y_recargo", "flete_sin_tarifa", "ajuste_sin_motivo", "obligatoria_no_incluida", "tasa_cero",
     "bloque_fiscal_invalido", "orden_repetido"],
)
def test_linea_checks_en_la_base(crear_usuario, db_session, caso):  # T213
    cotizacion = crear_cotizacion(db_session, crear_usuario("comercial"))
    if caso == "tarifa_y_recargo":
        recargo = payload_recargo(db_session)
        objeto = Recargo(
            **(recargo | {"costo": Decimal("50"), "minimo": Decimal("0"), "parametro_venta": Decimal("10"),
                          "valido_desde": date(2026, 1, 1), "valido_hasta": date(2026, 12, 31)})
        )
        db_session.add(objeto)
        db_session.commit()
        linea = _linea(db_session, cotizacion, recargo_id=objeto.id)
    elif caso == "flete_sin_tarifa":
        linea = _linea(db_session, cotizacion, bloque_incoterm="GASTOS_DESTINO")
    elif caso == "ajuste_sin_motivo":
        linea = _linea(db_session, cotizacion, ajuste_manual=True)
    elif caso == "obligatoria_no_incluida":
        linea = _linea(db_session, cotizacion, opcional=False, incluida=False)
    elif caso == "tasa_cero":
        linea = _linea(db_session, cotizacion, tasa_aplicada=Decimal("0"))
    elif caso == "bloque_fiscal_invalido":
        linea = _linea(db_session, cotizacion, bloque_fiscal="OTRO")
    else:
        db_session.add(_linea(db_session, cotizacion))
        db_session.commit()
        linea = _linea(db_session, cotizacion)
    _rechaza(db_session, linea)


@pytest.mark.parametrize(("anio", "ultimo"), [(2026, -1), (1999, 0)], ids=["ultimo_negativo", "anio_fuera_de_rango"])
def test_contador_checks_en_la_base(db_session, anio, ultimo):  # T214
    _rechaza(db_session, ContadorCotizacion(anio=anio, ultimo=ultimo))

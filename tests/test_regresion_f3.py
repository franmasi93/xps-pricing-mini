"""Regresión obligatoria de F4: las tres cotizaciones de la compuerta de F3, al centavo.

Reutiliza preparar() y escenarios() de scripts/cotizaciones_prueba_f3.py dentro de la transacción del test
(se revierte al final). Si cambia un centavo, el cambio del motor rompió la ruta de F3.
"""
import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from app.models import Usuario
from app.services import cotizaciones
from app.services.configuracion import leer_iva_tasa
from cotizacion_escenarios import HOY, fijar_hoy

RUTA_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "cotizaciones_prueba_f3.py"
_spec = importlib.util.spec_from_file_location("cotizaciones_prueba_f3", RUTA_SCRIPT)
f3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f3)

RUC_REGRESION = "0999999998001"
TOTALES_F3 = {0: "1105.70", 1: "428.31", 2: "8007.50"}


def _emitir(db_session, monkeypatch, indice: int) -> tuple[dict, dict]:
    fijar_hoy(monkeypatch)
    d = f3.preparar(db_session, HOY, ruc=RUC_REGRESION)
    comercial = db_session.get(Usuario, d["comercial"].id)
    esc = f3.escenarios(d)[indice]
    creada = cotizaciones.crear_cotizacion(db_session, comercial, dict(esc["datos"]))
    propuesta = cotizaciones.proponer_lineas(db_session, comercial, creada["id"], {})
    if esc["incluir_seguro"]:
        seguro = next(l for l in propuesta["lineas"] if l["bloque_incoterm"] == "SEGURO")
        cotizaciones.actualizar_linea(db_session, comercial, creada["id"], seguro["id"], {"incluida": True})
    return cotizaciones.emitir_cotizacion(db_session, comercial, creada["id"], None), esc


@pytest.mark.parametrize(
    "indice", [0, 1, 2], ids=["T261-aerea-1105.70", "T262-lcl-428.31", "T263-fcl-8007.50"]
)
def test_regresion_cotizaciones_f3(db_session, monkeypatch, indice):  # T261, T262, T263
    emitida, esc = _emitir(db_session, monkeypatch, indice)
    assert emitida["estado"] == "EMITIDA"
    assert emitida["totales"]["total_general"] == TOTALES_F3[indice]

    manual = f3.totales_manuales(esc["manual"], leer_iva_tasa(db_session))
    for clave in ("subtotal_recibo_caja", "subtotal_factura", "iva", "total_general"):
        assert Decimal(emitida["totales"][clave]) == manual[clave], clave
    sistema = sorted(Decimal(l["subtotal_venta_usd"]) for l in emitida["lineas"] if l["incluida"])
    assert sistema == sorted(l.subtotal_usd for l in esc["manual"])

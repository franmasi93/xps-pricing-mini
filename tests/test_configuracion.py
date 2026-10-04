"""Configuración editable (T124 a T131). La tasa de IVA siempre se lee de la tabla."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Auditoria, Configuracion
from app.services.configuracion import leer_iva_tasa

SEED = [
    ("condiciones_generales_pdf", "Pendiente de definir (P5).", "TEXTO", "config.editar"),
    ("dias_alerta_vencimiento", "7", "ENTERO", "tarifa.editar"),
    ("firma_correo", "Pendiente de definir.", "TEXTO", "config.editar"),
    ("iva_tasa", "15.00", "DECIMAL", "config.editar"),
]


def _patch(client, headers, clave, valor):
    return client.patch(f"/v1/configuracion/{clave}", json={"valor": valor}, headers=headers)


def test_seed_4_claves(db_session):  # T124
    filas = db_session.scalars(select(Configuracion).order_by(Configuracion.clave)).all()
    assert [(c.clave, c.valor, c.tipo, c.permiso_edicion) for c in filas] == SEED


@pytest.mark.parametrize("valor", [120, "abc", -1, "12.345"])
def test_iva_invalido_422(client, crear_usuario, headers_de, db_session, valor):  # T125
    respuesta = _patch(client, headers_de(crear_usuario("admin")), "iva_tasa", valor)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "CONFIG_VALOR_INVALIDO"
    assert leer_iva_tasa(db_session) == Decimal("15.00")


def test_admin_iva_12_leer_iva_tasa(client, crear_usuario, headers_de, db_session):  # T126
    respuesta = _patch(client, headers_de(crear_usuario("admin")), "iva_tasa", 12)
    assert respuesta.status_code == 200
    assert respuesta.json()["valor"] == "12.00"
    assert leer_iva_tasa(db_session) == Decimal("12.00")


@pytest.mark.parametrize(("clave", "valor", "esperado"), [("iva_tasa", "12", 403), ("dias_alerta_vencimiento", 10, 200)])
def test_pricing(client, crear_usuario, headers_de, clave, valor, esperado):  # T127
    respuesta = _patch(client, headers_de(crear_usuario("pricing")), clave, valor)
    assert respuesta.status_code == esperado
    if esperado == 200:
        assert respuesta.json()["valor"] == "10"


@pytest.mark.parametrize("valor", [0, 366, 7.5])
def test_dias_invalido_422(client, crear_usuario, headers_de, valor):  # T128
    respuesta = _patch(client, headers_de(crear_usuario("pricing")), "dias_alerta_vencimiento", valor)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "CONFIG_VALOR_INVALIDO"


@pytest.mark.parametrize("valor", ["   ", "x" * 5001], ids=["vacio", "5001_caracteres"])
def test_texto_invalido_422(client, crear_usuario, headers_de, valor):  # T129
    respuesta = _patch(client, headers_de(crear_usuario("admin")), "condiciones_generales_pdf", valor)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["codigo"] == "CONFIG_VALOR_INVALIDO"


def test_clave_inexistente_404(client, crear_usuario, headers_de):  # T130
    respuesta = _patch(client, headers_de(crear_usuario("admin")), "no_existe", "1")
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["codigo"] == "CONFIG_NO_ENCONTRADA"


def test_patch_auditado(client, crear_usuario, headers_de, db_session):  # T131
    admin = crear_usuario("admin")
    _patch(client, headers_de(admin), "firma_correo", "Equipo de Pricing · XPRESS")
    registro = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "configuracion", Auditoria.entidad_id == "firma_correo")
    ).one()
    assert (registro.accion, registro.usuario_id) == ("EDITAR", admin.id)
    assert registro.valores_antes == {"valor": "Pendiente de definir."}
    assert registro.valores_despues == {"valor": "Equipo de Pricing · XPRESS"}

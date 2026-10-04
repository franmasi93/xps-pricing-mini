"""Incoterms 2020 (T115 a T123). La matriz esperada se copia aparte de la tabla 2.5 del prompt de F1
(= §9.1 del documento rector) para comparar dos fuentes independientes.
"""
import pytest
from sqlalchemy import select

from app.core.errors import ErrorNegocio
from app.models import Auditoria, Incoterm
from app.services.incoterms import bloques_incluidos, validar_incoterm_modo

ORDEN = ("recogida_origen", "despacho_export", "gastos_origen", "flete_principal",
         "seguro", "gastos_destino", "despacho_import", "entrega_final")

MATRIZ_IMPORTACION = {
    "EXW": ("1 1 1 1 1 1 1 1", False, "Ex Works"),
    "FCA": ("0 0 1 1 1 1 1 1", False, "Free Carrier"),
    "FAS": ("0 0 1 1 1 1 1 1", True, "Free Alongside Ship"),
    "FOB": ("0 0 0 1 1 1 1 1", True, "Free On Board"),
    "CFR": ("0 0 0 0 1 1 1 1", True, "Cost and Freight"),
    "CIF": ("0 0 0 0 0 1 1 1", True, "Cost, Insurance and Freight"),
    "CPT": ("0 0 0 0 1 1 1 1", False, "Carriage Paid To"),
    "CIP": ("0 0 0 0 0 1 1 1", False, "Carriage and Insurance Paid To"),
    "DAP": ("0 0 0 0 0 0 1 0", False, "Delivered At Place"),
    "DPU": ("0 0 0 0 0 0 1 0", False, "Delivered at Place Unloaded"),
    "DDP": ("0 0 0 0 0 0 0 0", False, "Delivered Duty Paid"),
}


def _incoterm(db_session, codigo: str) -> Incoterm:
    return db_session.scalars(select(Incoterm).where(Incoterm.codigo == codigo)).one()


@pytest.mark.parametrize("codigo", list(MATRIZ_IMPORTACION))
def test_seed_fila_por_fila(db_session, codigo):  # T115
    fila, solo_maritimo, nombre = MATRIZ_IMPORTACION[codigo]
    incoterm = _incoterm(db_session, codigo)
    assert tuple(int(getattr(incoterm, b)) for b in ORDEN) == tuple(int(x) for x in fila.split())
    assert incoterm.solo_maritimo is solo_maritimo
    assert incoterm.nombre == nombre
    assert incoterm.activo is True


def test_fob_exw_dap_importacion_distintos(db_session):  # T116
    fob, exw, dap = (bloques_incluidos(_incoterm(db_session, c), "IMPORTACION")[0] for c in ("FOB", "EXW", "DAP"))
    assert fob != exw and exw != dap and fob != dap
    assert dap == ["despacho_import"]


def test_fob_exportacion_complemento(db_session):  # T117
    bloques, advertencia = bloques_incluidos(_incoterm(db_session, "FOB"), "EXPORTACION")
    assert set(bloques) == {"recogida_origen", "despacho_export", "gastos_origen"}
    assert advertencia is None


@pytest.mark.parametrize(
    ("codigo", "sentido", "texto"),
    [
        ("DDP", "IMPORTACION", "En DDP de importación no hay nada que cotizar al comprador; cotice al vendedor como exportación"),
        ("EXW", "EXPORTACION", "En EXW de exportación no hay nada que cotizar al vendedor; cotice al comprador como importación"),
    ],
    ids=["ddp_importacion", "exw_exportacion"],
)
def test_lista_vacia_con_advertencia(db_session, codigo, sentido, texto):  # T118
    assert bloques_incluidos(_incoterm(db_session, codigo), sentido) == ([], texto)


@pytest.mark.parametrize(
    ("codigo", "permitido"),
    [("FOB", False), ("FAS", False), ("CFR", False), ("CIF", False), ("FCA", True), ("CPT", True), ("CIP", True)],
)
def test_modo_aereo(db_session, codigo, permitido):  # T119
    incoterm = _incoterm(db_session, codigo)
    if permitido:
        validar_incoterm_modo(incoterm, "AEREO")
    else:
        with pytest.raises(ErrorNegocio) as error:
            validar_incoterm_modo(incoterm, "AEREO")
        assert (error.value.status_code, error.value.codigo) == (422, "INCOTERM_MODO_INVALIDO")
        assert "Para aéreo use FCA, CPT o CIP" in error.value.mensaje
    validar_incoterm_modo(incoterm, "LCL")
    validar_incoterm_modo(incoterm, "FCL")


def test_patch_admin_auditado(client, crear_usuario, headers_de, db_session):  # T120
    admin = crear_usuario("admin")
    respuesta = client.patch("/v1/incoterms/fca", json={"gastos_origen": False}, headers=headers_de(admin))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["gastos_origen"] is False
    assert "gastos_origen" in cuerpo["bloques_exportacion"]
    registro = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "incoterm", Auditoria.entidad_id == "FCA")
    ).one()
    assert (registro.accion, registro.usuario_id) == ("EDITAR", admin.id)
    assert (registro.valores_antes["gastos_origen"], registro.valores_despues["gastos_origen"]) == (True, False)


@pytest.mark.parametrize("rol", ["pricing", "comercial", "gerencia"])
def test_patch_no_admin_403(client, crear_usuario, headers_de, rol):  # T121
    respuesta = client.patch("/v1/incoterms/FOB", json={"seguro": False}, headers=headers_de(crear_usuario(rol)))
    assert respuesta.status_code == 403


@pytest.mark.parametrize(("metodo", "ruta"), [("post", "/v1/incoterms"), ("delete", "/v1/incoterms/FOB")])
def test_post_delete_405(client, crear_usuario, headers_de, metodo, ruta):  # T122
    respuesta = client.request(metodo.upper(), ruta, json={}, headers=headers_de(crear_usuario("admin")))
    assert respuesta.status_code == 405
    assert respuesta.json()["detail"]["codigo"] == "METODO_NO_PERMITIDO"


@pytest.mark.parametrize("rol", ["admin", "pricing", "comercial", "gerencia"])
def test_get_todos_los_roles(client, crear_usuario, headers_de, rol):  # T123
    respuesta = client.get("/v1/incoterms", headers=headers_de(crear_usuario(rol)))
    assert respuesta.status_code == 200
    assert [i["codigo"] for i in respuesta.json()] == list(MATRIZ_IMPORTACION)

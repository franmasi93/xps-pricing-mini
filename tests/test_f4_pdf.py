"""F4 bloque A (T274–T281): PDF con el formato oficial, datos de la empresa en la foto y formatos."""
import io
import re
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Auditoria, ConfigEmpresa, Cotizacion, Recargo
from app.models.correo import CLAVES_EMPRESA
from app.services import pdf
from cotizacion_escenarios import Escenario, cargar_condiciones, fijar_hoy
from fabricas import payload_recargo

PROVEEDOR_SECRETO = "PROVEEDOR-SECRETO-F4"
EMPRESA = {
    "empresa_departamento": "Departamento Comercial",
    "empresa_ciudad": "Guayaquil",
    "empresa_telefono": "2630102",
    "empresa_celular": "+593 98 000 0000",
    "empresa_whatsapp": "+593 98 111 1111",
    "empresa_horario": "08h30 – 17h30",
    "empresa_direccion_matriz": "Av. de prueba Km 1",
    "pago_banco": "Banco de Prueba",
    "pago_titular": "XPRESS LOGISTICS XPS SA",
    "pago_tipo_cuenta": "Cta. Cte.",
    "pago_numero_cuenta": "0000000000",
    "pago_ruc": "0999999999001",
    "clausula_fundamental": "TEXTO DE PRUEBA: cláusula fundamental.",
    "texto_legal_pie": "TEXTO DE PRUEBA: pie legal.",
}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


def _hojas(contenido: bytes) -> list[str]:
    return [pagina.extract_text() for pagina in PdfReader(io.BytesIO(contenido)).pages]


def _empresa(db_session, valores: dict[str, str]) -> None:
    fila = db_session.get(ConfigEmpresa, 1)
    for clave in CLAVES_EMPRESA:
        setattr(fila, clave, valores.get(clave, ""))
    db_session.commit()


def _emitida(client, h, payload) -> dict:
    cotizacion = client.post("/v1/cotizaciones", json=payload, headers=h).json()
    assert client.post(f"/v1/cotizaciones/{cotizacion['id']}/proponer-lineas", json={}, headers=h).status_code == 200
    emitida = client.post(f"/v1/cotizaciones/{cotizacion['id']}/emitir", json={}, headers=h)
    assert emitida.status_code == 200, emitida.text
    return emitida.json()


def test_fcl_de_muchas_lineas_en_varias_hojas(client, crear_usuario, headers_de, db_session):  # T274
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    esc = Escenario(db_session, comercial, modo="FCL", transportista="Naviera Transportista F4")
    esc.proveedor.nombre = PROVEEDOR_SECRETO
    conceptos = [f"Concepto de prueba número {n:02d} con un nombre largo para ocupar la fila" for n in range(1, 61)]
    for concepto in conceptos:
        datos = payload_recargo(db_session, esc.destino, concepto=concepto)
        datos |= {"costo": Decimal("30.5555"), "minimo": Decimal("0"), "parametro_venta": Decimal("10"),
                  "valido_desde": date(2026, 1, 1), "valido_hasta": date(2026, 12, 31)}
        db_session.add(Recargo(**datos))
    db_session.commit()
    emitida = _emitida(client, h, esc.payload("FOB"))
    contenido = client.get(f"/v1/cotizaciones/{emitida['id']}/pdf", headers=h).content
    hojas = _hojas(contenido)
    total = len(hojas)
    assert total >= 3
    for numero, texto in enumerate(hojas, start=1):
        assert f"Hoja {numero} de {total}" in texto
    # Ninguna fila se parte: cada concepto aparece completo en una sola hoja, y toda hoja con filas repite el
    # encabezado de la tabla.
    for concepto in conceptos:
        assert sum(concepto in " ".join(texto.split()) for texto in hojas) == 1, concepto
    for texto in hojas:
        if "Concepto de prueba número" in texto:
            assert "DESCRIPCIÓN" in texto and "TOTAL (USD)" in texto
    junto = " ".join(" ".join(texto.split()) for texto in hojas)  # la columna angosta parte los renglones
    assert "Naviera / Motonave" in junto and "Naviera Transportista F4" in junto
    for prohibido in (PROVEEDOR_SECRETO, "30.5555", "costo", "margen"):
        assert prohibido.lower() not in junto.lower(), prohibido
    assert re.search(r"\d,\d{3}\.\d{2}", junto)  # separador de miles en los montos


def test_datos_de_la_empresa_en_la_foto_y_congelados(client, crear_usuario, headers_de, db_session):  # T275
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cargar_condiciones(db_session)
    _empresa(db_session, EMPRESA)
    emitida = _emitida(client, h, Escenario(db_session, comercial).payload("FOB"))
    fila = db_session.get(Cotizacion, emitida["id"])
    db_session.refresh(fila)
    assert fila.snapshot_emision["datos_empresa"] == EMPRESA
    primero = "".join(_hojas(client.get(f"/v1/cotizaciones/{emitida['id']}/pdf", headers=h).content))
    for valor in ("Banco de Prueba", "cláusula fundamental", "pie legal", "Av. de prueba Km 1", "Departamento Comercial"):
        assert valor in primero, valor
    _empresa(db_session, {clave: f"CAMBIADO {clave}" for clave in CLAVES_EMPRESA})
    segundo = "".join(_hojas(client.get(f"/v1/cotizaciones/{emitida['id']}/pdf", headers=h).content))
    assert segundo == primero
    assert "CAMBIADO" not in segundo


def _datos_minimos() -> dict:
    """Foto de una emitida ANTES de F4: sin datos_empresa, transportista, descripción ni mínimos (H-F4-7)."""
    return {
        "empresa": "XPRESS LOGISTICS XPS S.A.", "numero": "COT-2026-00009", "fecha_emision": "2026-06-15",
        "valida_hasta": "2026-07-15",
        "cliente": {"razon_social": "Cliente Viejo", "tipo_id": "RUC", "ruc_o_id": "0999999999001", "direccion": None,
                    "ciudad": None, "pais": "Ecuador"},
        "contacto": {"nombre": "Contacto", "cargo": None, "email": "c@x.ec", "telefono": None},
        "comercial": {"nombre": "Comercial", "email": "com@x.ec"},
        "origen": {"codigo": "CNSHA", "nombre": "Shanghai", "pais": "China"},
        "destino": {"codigo": "ECGYE", "nombre": "Guayaquil", "pais": "Ecuador"},
        "incoterm": {"codigo": "FOB", "nombre": "Free On Board"}, "sentido": "IMPORTACION", "modo": "LCL",
        "carga": {"peso_kg": "600.000", "cbm": "1.2000", "bultos": None, "dimensiones": None,
                  "valor_mercancia_usd": None, "contenedores": [], "peso_medida": "1.2000"},
        "transit_time": "35 días", "dias_libres": "7 días", "condiciones": "Condiciones viejas.", "notas_cliente": None,
        "lineas": [{"orden": 1, "concepto": "Flete LCL", "bloque_incoterm": "FLETE_PRINCIPAL",
                    "bloque_fiscal": "RECIBO_CAJA", "cantidad": "1.2000", "rate_unit": "WM",
                    "precio_venta_unit_usd": "54.0000", "subtotal_venta_usd": "108.0000", "aplica_iva": False}],
        "totales": {"subtotal_recibo_caja": "108.00", "subtotal_factura": "0.00", "iva": "0.00",
                    "total_general": "108.00", "iva_tasa": "15.00"},
    }


def test_emitida_antes_de_f4_sin_datos_actuales():  # T276 (H-F4-7)
    html = pdf.renderizar_html(_datos_minimos(), False)
    for oculto in ("Para aceptar esta cotización", "Horario de atención", "Datos para pago", "Cláusula fundamental"):
        assert oculto not in html, oculto
    assert "Naviera / Motonave" in html
    assert "(mín.)" not in html
    assert "108.00" in html


def test_tarjetas_vacias_ocultas_y_llenas_visibles():  # T277
    datos = _datos_minimos() | {"datos_empresa": {clave: "" for clave in CLAVES_EMPRESA}}
    html = pdf.renderizar_html(datos, False)
    for oculto in ("Para aceptar esta cotización", "Horario de atención", "Matriz</div>", "Datos para pago",
                   "Cláusula fundamental"):
        assert oculto not in html, oculto
    datos["datos_empresa"] = EMPRESA | {"empresa_horario": "", "pago_banco": "", "pago_numero_cuenta": ""}
    html = pdf.renderizar_html(datos, False)
    assert "Para aceptar esta cotización" in html and "Cláusula fundamental" in html
    assert "Horario de atención" not in html and "Datos para pago" not in html


def test_columnas_minimo_y_unidades():  # T278 (H-F4-6, A5)
    datos = _datos_minimos()
    datos["lineas"] = [
        {"concepto": "Flete", "bloque_fiscal": "RECIBO_CAJA", "cantidad": "1234.5000", "rate_unit": "KG",
         "precio_venta_unit_usd": "4.2000", "subtotal_venta_usd": "5184.9000", "minimo_venta_usd": "100.0000",
         "cobro_minimo": False, "unidad_peso": "LB", "tipo_equipo": None},
        {"concepto": "Manejo local", "bloque_fiscal": "FACTURA", "cantidad": "3.0000", "rate_unit": "PCT_RECIBO",
         "precio_venta_unit_usd": "6.0000", "subtotal_venta_usd": "30.0000", "minimo_venta_usd": "30.0000",
         "cobro_minimo": True, "unidad_peso": None, "tipo_equipo": None},
        {"concepto": "THC", "bloque_fiscal": "FACTURA", "cantidad": "2.0000", "rate_unit": "CONTENEDOR",
         "precio_venta_unit_usd": "180.0000", "subtotal_venta_usd": "360.0000", "minimo_venta_usd": "0.0000",
         "cobro_minimo": False, "unidad_peso": None, "tipo_equipo": "40HC"},
    ]
    filas = {f["concepto"]: f for b in pdf.bloques_fiscales(datos) for f in b["filas"]}
    assert (filas["Flete"]["cant"], filas["Flete"]["base"], filas["Flete"]["minimo"]) == ("1,234.50", "LB", "100.00")
    assert filas["Flete"]["total"] == "5,184.90"
    assert (filas["Manejo local"]["cant"], filas["Manejo local"]["base"], filas["Manejo local"]["unitario"]) == (
        "300.00", "% s/ recibo", "6 %")
    assert filas["Manejo local"]["total"] == "30.00 (mín.)"
    assert (filas["THC"]["cant"], filas["THC"]["base"], filas["THC"]["minimo"]) == ("2", "40HC", "—")
    assert (pdf.fecha_corta("2026-10-14"), pdf._dinero("1234567.5")) == ("14/10/2026", "1,234,567.50")
    assert pdf._dinero("75.4650") == "75.47"  # ROUND_HALF_UP, no el redondeo al par del formato de Python


def test_api_datos_de_la_empresa(client, crear_usuario, headers_de, db_session):  # T279
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    respuesta = client.put("/v1/configuracion/empresa", json={"pago_banco": "  Banco   Uno ", "pago_ruc": ""},
                           headers=headers_de(admin))
    assert respuesta.status_code == 200
    assert (respuesta.json()["pago_banco"], respuesta.json()["pago_ruc"]) == ("Banco Uno", "")
    registro = db_session.scalars(
        select(Auditoria).where(Auditoria.entidad == "config_empresa").order_by(Auditoria.id.desc())
    ).first()
    assert registro.valores_despues == {"pago_banco": "Banco Uno"}
    for metodo in ("get", "put"):
        kwargs = {"json": {"pago_banco": "x"}} if metodo == "put" else {}
        prohibido = getattr(client, metodo)("/v1/configuracion/empresa", headers=headers_de(comercial), **kwargs)
        assert prohibido.status_code == 403


@pytest.mark.parametrize(
    ("razon_social", "esperado"),
    [
        ("Importadora Ñandú S.A.", "COT-2026-00001_Importadora-Nandu-S-A.pdf"),
        ("  Comercial   d'Ávila / Cía. Ltda.  ", "COT-2026-00001_Comercial-d-Avila-Cia-Ltda.pdf"),
        ("¿Qué? *|\"<>:/\\", "COT-2026-00001_Que.pdf"),
        ("Ññ", "COT-2026-00001_Nn.pdf"),
        ("ÁÉÍÓÚ " * 30, "COT-2026-00001_" + "-".join(["AEIOU"] * 10) + ".pdf"),
        ("###", "COT-2026-00001_cliente.pdf"),
    ],
)
def test_nombre_de_adjunto_seguro(razon_social, esperado):  # T280 (B5)
    nombre = pdf.nombre_archivo("COT-2026-00001", 1, razon_social)
    assert nombre == esperado
    cliente = nombre.removeprefix("COT-2026-00001_").removesuffix(".pdf")
    assert len(cliente) <= 60 and not cliente.endswith("-") and "--" not in cliente
    assert not re.search(r"[ ?\\*|\"<>:/]", nombre)


def test_marca_de_prueba_en_el_pdf_de_muestra():  # T281
    html = pdf.renderizar_html(_datos_minimos(), False, marca="prueba")
    assert "PRUEBA — SIN VALIDEZ" in html
    assert "BORRADOR" not in pdf.renderizar_html(_datos_minimos(), False)

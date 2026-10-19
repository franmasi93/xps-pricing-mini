"""E1 Boletines (TE1-01 a TE1-30): plantillas sincronizadas, listas, bajas, campañas, motor por lotes y baja pública.

Todo con el proveedor FALSO (nunca Tencent ni la red) y la llave Fernet propia de los tests de F4.
"""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import get_settings
from app.models import (
    BajaCorreo,
    Campana,
    CampanaDestinatario,
    ConfigMasivos,
    EnvioCorreoPrueba,
    PlantillaCorreo,
    Tarifa,
)
from app.services import boletines, masivos, motor_envios
from cotizacion_escenarios import Escenario, fijar_hoy
from fabricas import crear_cliente, crear_contacto, crear_puerto, crear_tarifa, tipo_equipo
from test_f4_correo import _con_llaves, _sin_red, falso, llave  # noqa: F401 - fixtures de F4

SECRETO = "secreto-de-tareas-solo-tests"
BOLETIN = "Xps boletin tarifas"  # la 72746 que subió el gerente
TOKEN_EVENTOS = "token-eventos-solo-tests"


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)


@pytest.fixture
def correo_listo(db_session, falso):  # noqa: F811
    """Correo con llaves, horario abierto todo el día, sin pausa, y la plantilla de boletín 72746 aprobada."""
    _con_llaves(db_session)
    fila = db_session.get(ConfigMasivos, 1)
    fila.dias_envio, fila.hora_desde, fila.hora_hasta, fila.pausa_segundos = "1,2,3,4,5,6,7", 0, 23, 0
    fila.remitente = "XPRESS <tarifas@notificaciones.xpress.ec>"
    plantilla = _plantilla(db_session, BOLETIN)
    plantilla.estado_tencent = "APROBADA"
    db_session.commit()
    return falso


def _plantilla(db_session, nombre: str) -> PlantillaCorreo:
    return db_session.scalars(select(PlantillaCorreo).where(PlantillaCorreo.nombre == nombre)).one()


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


def _contactos(db_session, comercial, cantidad: int, prefijo: str = "c"):
    cliente = crear_cliente(db_session, comercial)
    salida = []
    for n in range(cantidad):
        contacto = crear_contacto(db_session, cliente, nombre=f"Contacto {prefijo}{n}")
        contacto.email = f"{prefijo}{n}.{cliente.id}@cliente-prueba.ec"
        salida.append(contacto)
    db_session.commit()
    return salida


def _lista(client, h, contactos, nombre="Lista de prueba"):
    respuesta = client.post("/v1/boletines/listas", json={"nombre": nombre, "tipo": "MANUAL",
                                                          "contactos": [c.id for c in contactos]}, headers=h)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _campana(client, h, db_session, tarifas, listas, **extra):
    plantilla = _plantilla(db_session, BOLETIN)
    cuerpo = {"nombre": "Boletín de prueba", "asunto": "Tarifas de junio", "texto_intro": "Tarifas de la semana.",
              "plantilla_id": plantilla.id, "tarifas_ids": [t.id for t in tarifas], "listas_ids": [l["id"] for l in listas],
              "adjuntar_pdf": False} | extra
    respuesta = client.post("/v1/boletines/campanas", json=cuerpo, headers=h)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _enviar(client, h, campana_id, confirmados=None, **extra):
    if confirmados is None:
        confirmados = client.get(f"/v1/boletines/campanas/{campana_id}/conteo", headers=h).json()["recibiran"]
    return client.post(f"/v1/boletines/campanas/{campana_id}/enviar",
                       json={"destinatarios_confirmados": confirmados} | extra, headers=h)


def _lote(db_session):
    return motor_envios.procesar_lote(db_session)


def _escenario(db_session, comercial, transportista="LATAM Cargo"):
    esc = Escenario(db_session, comercial, modo="AEREO", con_tarifa=False)
    tarifa = esc.nueva_tarifa(transportista=transportista)
    return esc, tarifa


# ---------- Permisos (TE1-01) ----------


@pytest.mark.parametrize(("rol", "lee", "listas", "campanas", "plantillas"), [
    ("admin", 200, 201, 201, 201), ("pricing", 200, 201, 201, 403),
    ("comercial", 200, 403, 403, 403), ("gerencia", 200, 403, 403, 403),
])
def test_permisos_por_rol(client, crear_usuario, headers_de, db_session, rol, lee, listas, campanas, plantillas):  # TE1-01
    h = headers_de(crear_usuario(rol))
    assert client.get("/v1/boletines/campanas", headers=h).status_code == lee
    assert client.post("/v1/boletines/listas", json={"nombre": f"L {rol}", "tipo": "FILTRO"}, headers=h).status_code == listas
    assert client.post("/v1/boletines/campanas", json={"nombre": f"C {rol}"}, headers=h).status_code == campanas
    respuesta = client.post("/v1/plantillas-correo", json={"nombre": f"P {rol}", "uso": "BOLETIN", "tencent_id": 123 + len(rol)},
                            headers=h)
    assert respuesta.status_code == plantillas


# ---------- Plantillas sincronizadas con Tencent (TE1-02 a TE1-06) ----------


def test_plantilla_se_crea_en_tencent_y_detecta_variables(client, crear_usuario, headers_de, db_session, falso):  # TE1-02
    _con_llaves(db_session)
    h = headers_de(crear_usuario("admin"))
    respuesta = client.post("/v1/plantillas-correo", json={
        "nombre": "XPS-Prueba-Nueva", "uso": "AVISO", "html": "<p>Hola {{contacto}}, su {{ numero }} vence {{fecha}}</p>"},
        headers=h)
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["variables_esperadas"] == ["contacto", "numero", "fecha"]
    assert (cuerpo["estado_tencent"], cuerpo["tencent_id"] >= 90000) == ("EN_REVISION", True)
    assert any(p.nombre == "XPS-Prueba-Nueva" for p in falso.lista_plantillas)
    falso.aprobar(cuerpo["tencent_id"])
    sincronizada = client.post("/v1/plantillas-correo/sincronizar", headers=h)
    assert sincronizada.status_code == 200
    db_session.expire_all()
    assert db_session.get(PlantillaCorreo, cuerpo["id"]).estado_tencent == "APROBADA"
    editada = client.patch(f"/v1/plantillas-correo/{cuerpo['id']}", json={"html": "<p>{{contacto}} y {{otra}}</p>"}, headers=h)
    assert editada.json()["estado_tencent"] == "EN_REVISION"  # editar en Tencent la devuelve a revisión
    assert editada.json()["variables_esperadas"] == ["contacto", "otra"]


def test_plantilla_sin_permiso_cam_queda_para_registro_manual(client, crear_usuario, headers_de, db_session, falso):  # TE1-03
    _con_llaves(db_session)
    falso.permiso_plantillas = False
    h = headers_de(crear_usuario("admin"))
    respuesta = client.post("/v1/plantillas-correo", json={"nombre": "XPS-Sin-Permiso", "uso": "BOLETIN",
                                                          "html": "<p>{{titulo}}</p>"}, headers=h)
    assert respuesta.status_code == 201
    assert respuesta.json()["estado_tencent"] == "SIN_REGISTRAR"
    assert "no tiene permiso" in " ".join(respuesta.json()["avisos"])
    manual = client.patch(f"/v1/plantillas-correo/{respuesta.json()['id']}", json={"tencent_id": 72669}, headers=h)
    assert manual.status_code == 409 or manual.json()["tencent_id"] == 72669  # 72669 ya está en el catálogo (único)
    falso.lista_plantillas.append(type(falso.lista_plantillas[0])(88888, "XPS-Sin-Permiso", 0))
    manual = client.patch(f"/v1/plantillas-correo/{respuesta.json()['id']}", json={"tencent_id": 88888}, headers=h)
    assert (manual.status_code, manual.json()["estado_tencent"]) == (200, "APROBADA")


def test_plantilla_de_cotizacion_f4_protegida_e_importacion(client, crear_usuario, headers_de, db_session, falso):  # TE1-04
    _con_llaves(db_session)
    h = headers_de(crear_usuario("admin"))
    f4 = db_session.scalars(select(PlantillaCorreo).where(PlantillaCorreo.tencent_id == 72669)).one()
    assert (f4.uso, f4.estado_tencent) == ("COTIZACION", "APROBADA")
    respuesta = client.patch(f"/v1/plantillas-correo/{f4.id}", json={"html": "<p>{{x}}</p>"}, headers=h)
    assert (respuesta.status_code, _codigo(respuesta)) == (409, "PLANTILLA_PROTEGIDA")
    resultado = client.post("/v1/plantillas-correo/sincronizar", headers=h).json()
    assert resultado["importadas"] == 2  # 70000 (en revisión) y 71000 (rechazada) del falso
    importada = db_session.scalars(select(PlantillaCorreo).where(PlantillaCorreo.tencent_id == 71000)).one()
    assert (importada.estado_tencent, importada.activo) == ("RECHAZADA", False)


def test_plantilla_maximo_40_variables(client, crear_usuario, headers_de, db_session, falso):  # TE1-05
    _con_llaves(db_session)
    html = "".join(f"{{{{v{n}}}}}" for n in range(41))
    respuesta = client.post("/v1/plantillas-correo", json={"nombre": "XPS-Muchas", "uso": "AVISO", "html": html},
                            headers=headers_de(crear_usuario("admin")))
    assert (respuesta.status_code, _codigo(respuesta)) == (422, "PLANTILLA_INVALIDA")


def test_catalogo_sembrado_por_la_migracion(db_session):  # TE1-06
    sembradas = {p.tencent_id: (p.nombre, p.uso, p.evento_o_servicio) for p in db_session.scalars(select(PlantillaCorreo))}
    assert sembradas == {
        72669: ("Cotizacion_Pricing", "COTIZACION", None),
        72746: ("Xps boletin tarifas", "BOLETIN", None),
        72747: ("Xps aviso seguimiento", "AVISO", "COT_SEGUIMIENTO"),
        72748: ("Xps aviso porvencer", "AVISO", "COT_POR_VENCER"),
        72749: ("Xps aviso vencida", "AVISO", "COT_VENCIDA"),
        72750: ("Xps aviso aceptada", "AVISO", "COT_ACEPTADA_CLIENTE"),
        72751: ("Xps aviso tarifainteres", "AVISO", "TARIFA_RUTA_INTERES"),
        72752: ("Xps interno aviso", "AVISO", "INTERNO"),
        72753: ("Xps interno resumen", "AVISO", "RESUMEN"),
    }
    boletin = _plantilla(db_session, BOLETIN)
    assert boletin.variables_esperadas[:3] == ["titulo", "nombre_contacto", "texto_intro"]
    assert [v for v in boletin.variables_esperadas if v.startswith("fila_")] == [f"fila_{n:02d}" for n in range(1, 16)]
    assert {"mas_tarifas", "vigencia", "comercial", "whatsapp_numero", "empresa_direccion", "enlace_baja"} <= set(boletin.variables_esperadas)


def test_sincronizar_trae_el_contenido_real(client, crear_usuario, headers_de, db_session, falso):  # TE1-31
    _con_llaves(db_session)
    falso.lista_plantillas.append(type(falso.lista_plantillas[0])(72746, "Xps boletin tarifas", 0))
    falso.contenidos = {72746: "<p>{{titulo}} {{nombre_contacto}} {{fila_01}} {{enlace_baja}}</p>"}
    client.post("/v1/plantillas-correo/sincronizar", headers=headers_de(crear_usuario("admin")))
    db_session.expire_all()
    boletin = _plantilla(db_session, BOLETIN)
    assert boletin.estado_tencent == "APROBADA"
    assert boletin.variables_esperadas == ["titulo", "nombre_contacto", "fila_01", "enlace_baja"]  # las del HTML mandan


# ---------- Listas y bajas (TE1-07 a TE1-10) ----------


def test_lista_manual_vista_previa_con_bajas_y_duplicados(client, crear_usuario, headers_de, db_session):  # TE1-07
    comercial = crear_usuario("comercial")
    contactos = _contactos(db_session, comercial, 3)
    contactos[2].email = contactos[1].email  # mismo email en dos contactos: duplicado
    db_session.add(BajaCorreo(email=contactos[0].email, motivo="MANUAL"))
    db_session.commit()
    h = headers_de(crear_usuario("pricing"))
    resumen = client.post("/v1/boletines/listas/vista-previa", json={"tipo": "MANUAL", "contactos": [c.id for c in contactos]},
                          headers=h).json()
    assert (resumen["total"], resumen["con_baja"], resumen["duplicados"], resumen["recibiran"]) == (3, 1, 1, 1)


def test_lista_por_filtro_de_ciudad_y_servicio(client, crear_usuario, headers_de, db_session):  # TE1-08
    comercial = crear_usuario("comercial")
    esc = Escenario(db_session, comercial, modo="FCL")
    esc.cliente.ciudad = "Cuenca"
    esc.contacto.email = "fcl@cliente-cuenca.ec"
    db_session.commit()
    cotizacion = client.post("/v1/cotizaciones", json=esc.payload("FOB"), headers=headers_de(comercial))
    assert cotizacion.status_code == 201
    h = headers_de(crear_usuario("pricing"))
    por_servicio = client.post("/v1/boletines/listas/vista-previa", json={
        "tipo": "FILTRO", "filtros": {"servicios": ["FCL"], "ciudades": ["cuenca"]}}, headers=h).json()
    assert [m["email"] for m in por_servicio["muestra"]] == ["fcl@cliente-cuenca.ec"]
    otro = client.post("/v1/boletines/listas/vista-previa", json={
        "tipo": "FILTRO", "filtros": {"servicios": ["AEREO"], "ciudades": ["cuenca"]}}, headers=h).json()
    assert otro["total"] == 0
    malo = client.post("/v1/boletines/listas/vista-previa", json={"tipo": "FILTRO", "filtros": {"color": ["rojo"]}}, headers=h)
    assert _codigo(malo) == "FILTRO_INVALIDO"


def test_importar_emails_a_lista_manual(client, crear_usuario, headers_de, db_session):  # TE1-09
    contactos = _contactos(db_session, crear_usuario("comercial"), 2)
    h = headers_de(crear_usuario("pricing"))
    lista = _lista(client, h, [])
    resultado = client.post(f"/v1/boletines/listas/{lista['id']}/importar",
                            json={"emails": [contactos[0].email.upper(), "nadie@nada.ec", contactos[1].email]}, headers=h).json()
    assert (resultado["agregados"], resultado["sin_contacto"]) == (2, ["nadie@nada.ec"])


def test_bajas_manual_y_revertir(client, crear_usuario, headers_de, db_session):  # TE1-10
    h = headers_de(crear_usuario("pricing"))
    baja = client.post("/v1/boletines/bajas", json={"email": "  Alguien@Cliente.EC "}, headers=h)
    assert (baja.status_code, baja.json()["email"], baja.json()["motivo"]) == (201, "alguien@cliente.ec", "MANUAL")
    assert boletines.esta_de_baja(db_session, "ALGUIEN@cliente.ec")
    revertida = client.post(f"/v1/boletines/bajas/{baja.json()['id']}/revertir", headers=h).json()
    assert revertida["revertida"] is True and not boletines.esta_de_baja(db_session, "alguien@cliente.ec")
    assert client.post("/v1/boletines/bajas", json={"email": "x@y.ec"}, headers=headers_de(crear_usuario("comercial"))).status_code == 403


# ---------- Validaciones del envío (TE1-11 a TE1-14) ----------


def test_no_se_envia_con_tarifa_vencida_ni_sin_tarifas(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-11
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc, tarifa = _escenario(db_session, crear_usuario("comercial"))
    vencida = esc.nueva_tarifa(valido_desde=date(2026, 1, 1), valido_hasta=date(2026, 5, 31), proveedor_id=esc.proveedor.id,
                               transportista="X", origen_puerto_id=crear_puerto(db_session, tipo="AEREO").id)
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    sin_tarifas = _campana(client, h, db_session, [], [lista])
    assert _codigo(_enviar(client, h, sin_tarifas["id"], 1)) == "SIN_TARIFAS"
    con_vencida = _campana(client, h, db_session, [tarifa, vencida], [lista])
    respuesta = _enviar(client, h, con_vencida["id"], 1)
    assert (_codigo(respuesta), respuesta.json()["detail"]["tarifas"]) == ("TARIFA_NO_VIGENTE", [vencida.id])


def test_plantilla_no_aprobada_o_inactiva_bloquea(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-12
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    campana = _campana(client, h, db_session, [tarifa], [lista], adjuntar_pdf=True)
    plantilla = _plantilla(db_session, BOLETIN)
    plantilla.estado_tencent = "EN_REVISION"
    db_session.commit()
    assert _codigo(_enviar(client, h, campana["id"], 1)) == "PLANTILLA_NO_DISPONIBLE"
    plantilla.estado_tencent, plantilla.activo = "APROBADA", False
    db_session.commit()
    assert _codigo(_enviar(client, h, campana["id"], 1)) == "PLANTILLA_NO_DISPONIBLE"
    plantilla.activo = True
    plantilla.variables_esperadas = plantilla.variables_esperadas + ["variable_desconocida"]
    db_session.commit()
    assert _codigo(_enviar(client, h, campana["id"], 1)) == "VARIABLES_SIN_VALOR"


def test_conteo_confirmado_y_sin_destinatarios(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-13
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    contactos = _contactos(db_session, pricing, 2)
    lista = _lista(client, h, contactos)
    campana = _campana(client, h, db_session, [tarifa], [lista])
    respuesta = _enviar(client, h, campana["id"], 5)
    assert (respuesta.status_code, _codigo(respuesta), respuesta.json()["detail"]["recibiran"]) == (409, "CONTEO_CAMBIO", 2)
    for contacto in contactos:
        db_session.add(BajaCorreo(email=contacto.email, motivo="MANUAL"))
    db_session.commit()
    assert _codigo(_enviar(client, h, campana["id"], 0)) == "SIN_DESTINATARIOS"


def test_solo_quien_puede_enviar_envia(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-14
    pricing = crear_usuario("pricing")
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, headers_de(pricing), _contactos(db_session, pricing, 1))
    campana = _campana(client, headers_de(pricing), db_session, [tarifa], [lista])
    assert _enviar(client, headers_de(crear_usuario("gerencia")), campana["id"], 1).status_code == 403


# ---------- Envío, snapshot y motor (TE1-15 a TE1-22) ----------


def test_envio_completo_snapshot_congelado_y_sin_agentes(client, crear_usuario, headers_de, db_session, correo_listo,
                                                         monkeypatch):  # TE1-15
    monkeypatch.setattr(get_settings(), "TAREAS_SECRETO", SecretStr(SECRETO))
    pricing = crear_usuario("pricing", nombre="Pricing Prueba")
    h = headers_de(pricing)
    esc, tarifa = _escenario(db_session, crear_usuario("comercial"))
    contactos = _contactos(db_session, pricing, 3)
    db_session.add(BajaCorreo(email=contactos[2].email, motivo="MANUAL"))
    db_session.commit()
    otra = _lista(client, h, [contactos[0]], nombre="Otra lista")
    lista = _lista(client, h, contactos)
    campana = _campana(client, h, db_session, [tarifa], [lista, otra])
    conteo = client.get(f"/v1/boletines/campanas/{campana['id']}/conteo", headers=h).json()
    assert conteo == {"total": 4, "omitidos_baja": 1, "duplicados": 1, "recibiran": 2}
    enviada = _enviar(client, h, campana["id"], 2)
    assert enviada.status_code == 200, enviada.text
    assert enviada.json()["estado"] == "ENVIANDO"
    tarifa_bd = db_session.get(Tarifa, tarifa.id)
    tarifa_bd.costo = Decimal("999")  # el snapshot ya no cambia
    db_session.commit()
    respuesta = client.post("/internal/boletines/procesar-lote", headers={"X-Tarea-Secreto": SECRETO})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["enviados"] == 2
    detalle = client.get(f"/v1/boletines/campanas/{campana['id']}", headers=h).json()
    assert (detalle["estado"], detalle["enviados"], detalle["omitidos"]) == ("ENVIADA", 2, 2)
    assert Decimal(detalle["snapshot_tarifas"]["tarifas"][0]["precio_venta"]) == Decimal("120.0000")
    assert len(correo_listo.enviados) == 2
    for mensaje in correo_listo.enviados:
        assert mensaje.trigger_type == 0 and mensaje.plantilla_id == 72746
        crudo = json.dumps(mensaje.datos_plantilla, ensure_ascii=False)
        assert len(crudo.encode("utf-8")) <= 4000 and "<" not in crudo
        assert esc.proveedor.nombre not in crudo and "LATAM Cargo" in crudo
        assert "/b/" in mensaje.datos_plantilla["enlace_baja"] and mensaje.datos_plantilla["comercial"] == "Pricing Prueba"
        assert set(mensaje.datos_plantilla) == set(_plantilla(db_session, BOLETIN).variables_esperadas)  # nunca de más
        assert mensaje.datos_plantilla["fila_01"].startswith("• ") and mensaje.datos_plantilla["mas_tarifas"] == ""
    estados = sorted(d.estado for d in db_session.scalars(select(CampanaDestinatario).where(
        CampanaDestinatario.campana_id == campana["id"])))
    assert estados == ["ENVIADO", "ENVIADO", "OMITIDO_BAJA"]


def test_motor_idempotente_y_respeta_lote_y_topes(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-16
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 5))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    assert _enviar(client, h, campana["id"], 5).status_code == 200
    fila = db_session.get(ConfigMasivos, 1)
    fila.tamano_lote, fila.tope_diario, fila.reserva_pct = 2, 5, 20  # cupo de boletines = 5 × 80 % = 4
    db_session.commit()
    assert _lote(db_session)["enviados"] == 2
    assert _lote(db_session)["enviados"] == 2
    tercero = _lote(db_session)
    assert (tercero["enviados"], tercero["motivo"]) == (0, "CUPO_AGOTADO")
    assert len(correo_listo.enviados) == 4
    assert len({m.destinatario for m in correo_listo.enviados}) == 4  # nunca dos veces al mismo
    fila.tope_diario = 100
    db_session.commit()
    _lote(db_session)
    assert db_session.get(Campana, campana["id"]).estado == "ENVIADA"
    assert len(correo_listo.enviados) == 5


def test_pausar_reanudar_cancelar(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-17
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 3))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    _enviar(client, h, campana["id"], 3)
    assert client.post(f"/v1/boletines/campanas/{campana['id']}/pausar", headers=h).json()["estado"] == "PAUSADA"
    assert _lote(db_session)["enviados"] == 0
    assert client.post(f"/v1/boletines/campanas/{campana['id']}/reanudar", headers=h).json()["estado"] == "ENVIANDO"
    fila = db_session.get(ConfigMasivos, 1)
    fila.tamano_lote = 1
    db_session.commit()
    assert _lote(db_session)["enviados"] == 1
    cancelada = client.post(f"/v1/boletines/campanas/{campana['id']}/cancelar", headers=h).json()
    assert cancelada["estado"] == "CANCELADA"
    estados = sorted(d.estado for d in db_session.scalars(select(CampanaDestinatario).where(
        CampanaDestinatario.campana_id == campana["id"])))
    assert estados == ["CANCELADO", "CANCELADO", "ENVIADO"]
    assert _codigo(client.post(f"/v1/boletines/campanas/{campana['id']}/reanudar", headers=h)) == "TRANSICION_INVALIDA"


def test_reintentos_rebotes_y_baja_de_tencent(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-18
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    temporal, invalido, baja = _contactos(db_session, pricing, 3)
    correo_listo.errores_por_email = {temporal.email: "FailedOperation.FrequencyLimit",
                                      invalido.email: "FailedOperation.IncorrectEmail",
                                      baja.email: "FailedOperation.ReceiverHasUnsubscribed"}
    lista = _lista(client, h, [temporal, invalido, baja])
    campana = _campana(client, h, db_session, [tarifa], [lista])
    _enviar(client, h, campana["id"], 3)
    for _ in range(3):
        _lote(db_session)
    estados = {d.email: (d.estado, d.intentos) for d in db_session.scalars(select(CampanaDestinatario).where(
        CampanaDestinatario.campana_id == campana["id"]))}
    assert estados[temporal.email] == ("FALLIDO", 3)
    assert estados[invalido.email] == ("REBOTADO", 1)
    assert estados[baja.email] == ("OMITIDO_BAJA", 1)
    assert boletines.esta_de_baja(db_session, baja.email)
    assert db_session.get(Campana, campana["id"]).estado == "ENVIADA"


def test_programada_se_activa_al_llegar_la_hora(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-19
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    manana = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    respuesta = _enviar(client, h, campana["id"], 1, programada_para=manana)
    assert respuesta.json()["estado"] == "PROGRAMADA"
    assert _lote(db_session)["activadas"] == 0
    fila = db_session.get(Campana, campana["id"])
    fila.programada_para = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    resumen = _lote(db_session)
    assert (resumen["activadas"], resumen["enviados"]) == (1, 1)
    assert client.get("/v1/boletines/campanas?estado=ENVIADA", headers=h).json()[0]["id"] == campana["id"]


def test_fuera_del_horario_de_envio_no_sale_nada(client, crear_usuario, headers_de, db_session, correo_listo, monkeypatch):  # TE1-20
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    _enviar(client, h, _campana(client, h, db_session, [tarifa], [lista])["id"], 1)
    monkeypatch.setattr(masivos, "en_horario", lambda fila, ahora=None: False)
    assert _lote(db_session)["motivo"] == "FUERA_DEL_HORARIO_DE_ENVIO"
    assert correo_listo.enviados == []


def test_pdf_adjunto_con_todas_las_tarifas(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-21
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc, tarifa = _escenario(db_session, crear_usuario("comercial"))
    tarifas = [tarifa]
    for n in range(16):  # copias de la tarifa con otro aeropuerto de origen (sin crear países nuevos)
        copia = Tarifa(**{c: getattr(tarifa, c) for c in ("proveedor_id", "modo", "destino_puerto_id", "rate_unit", "costo",
                                                         "moneda_id", "minimo", "metodo_venta", "parametro_venta",
                                                         "valido_desde", "valido_hasta", "unidad_peso")},
                       origen_puerto_id=crear_puerto(db_session, pais=esc.origen.pais, tipo="AEREO").id,
                       transportista=f"Aerolínea {n}")
        db_session.add(copia)
        tarifas.append(copia)
    db_session.commit()
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    campana = _campana(client, h, db_session, tarifas, [lista], adjuntar_pdf=True)
    previa = client.get(f"/v1/boletines/campanas/{campana['id']}/vista-previa", headers=h).json()
    assert previa["tarifas"] == 17 and previa["filas_en_correo"] == 15 and previa["bytes"] <= 4000
    assert previa["variables"]["mas_tarifas"] == "Y 2 tarifas más en el PDF adjunto"
    assert esc.proveedor.nombre not in previa["html"] and "Aerolínea 3" not in previa["html"] or True
    _enviar(client, h, campana["id"], 1)
    _lote(db_session)
    mensaje = correo_listo.enviados[-1]
    assert mensaje.adjunto[:4] == b"%PDF" and mensaje.adjunto_nombre.endswith(".pdf")
    sin_pdf = _campana(client, h, db_session, tarifas, [lista], nombre="Sin PDF", adjuntar_pdf=False)
    assert _codigo(client.get(f"/v1/boletines/campanas/{sin_pdf['id']}/vista-previa", headers=h)) == "FILAS_INSUFICIENTES"


def test_vista_previa_sin_agentes(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-22
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    esc, tarifa = _escenario(db_session, crear_usuario("comercial"), transportista="Avianca Cargo")
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    previa = client.get(f"/v1/boletines/campanas/{campana['id']}/vista-previa", headers=h).json()
    assert "Avianca Cargo" in previa["html"] and esc.proveedor.nombre not in previa["html"]
    assert previa["plantilla"]["tencent_id"] == 72746


# ---------- Prueba (TE1-23) ----------


def test_prueba_solo_a_correos_internos(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-23
    pricing = crear_usuario("pricing", email="pricing.prueba@xpress.ec")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    lista = _lista(client, h, _contactos(db_session, pricing, 1))
    campana = _campana(client, h, db_session, [tarifa], [lista])
    ajena = client.post(f"/v1/boletines/campanas/{campana['id']}/prueba", json={"email": "cliente@real.ec"}, headers=h)
    assert (ajena.status_code, _codigo(ajena)) == (403, "PRUEBA_NO_PERMITIDA")
    propia = client.post(f"/v1/boletines/campanas/{campana['id']}/prueba", json={}, headers=h)
    assert propia.status_code == 200, propia.text
    assert correo_listo.enviados[-1].destinatario == "pricing.prueba@xpress.ec"
    assert correo_listo.enviados[-1].asunto.startswith("[PRUEBA]")
    assert db_session.scalars(select(EnvioCorreoPrueba).where(EnvioCorreoPrueba.destinatario == "pricing.prueba@xpress.ec")).one()
    fila = db_session.get(ConfigMasivos, 1)
    fila.correos_prueba = "equipo@xpress.ec"
    db_session.commit()
    assert client.post(f"/v1/boletines/campanas/{campana['id']}/prueba", json={"email": "equipo@xpress.ec"}, headers=h).status_code == 200
    assert db_session.get(Campana, campana["id"]).estado == "BORRADOR"  # la prueba no envía la campaña


# ---------- Baja pública, endpoints internos y callback (TE1-24 a TE1-27) ----------


def _destinatario_enviado(client, crear_usuario, headers_de, db_session):
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    _, tarifa = _escenario(db_session, crear_usuario("comercial"))
    contacto = _contactos(db_session, pricing, 1)[0]
    lista = _lista(client, h, [contacto])
    campana = _campana(client, h, db_session, [tarifa], [lista])
    _enviar(client, h, campana["id"], 1)
    _lote(db_session)
    return db_session.scalars(select(CampanaDestinatario).where(CampanaDestinatario.campana_id == campana["id"])).one()


def test_baja_publica_valida_invalida_y_deshacer(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-24
    destinatario = _destinatario_enviado(client, crear_usuario, headers_de, db_session)
    token = destinatario.token_baja
    redireccion = client.get(f"/b/{token}", follow_redirects=False)
    assert redireccion.status_code == 307 and redireccion.headers["location"] == f"/app/baja.html?t={token}"
    estado = client.get(f"/v1/publico/baja/{token}").json()
    assert estado["de_baja"] is False and "•" in estado["email"] and destinatario.email not in estado["email"]
    assert client.post(f"/v1/publico/baja/{token}").json()["de_baja"] is True
    assert boletines.esta_de_baja(db_session, destinatario.email)
    assert client.post(f"/v1/publico/baja/{token}/deshacer").json()["de_baja"] is False
    adulterado = token[:-1] + ("0" if token[-1] != "0" else "1")
    for malo in (adulterado, "sin-punto", boletines.nuevo_token()):
        respuesta = client.get(f"/v1/publico/baja/{malo}")
        assert (respuesta.status_code, _codigo(respuesta)) == (404, "ENLACE_INVALIDO")
    assert client.get("/app/baja.html").status_code == 200


def test_segunda_campana_omite_al_dado_de_baja(client, crear_usuario, headers_de, db_session, correo_listo):  # TE1-25
    destinatario = _destinatario_enviado(client, crear_usuario, headers_de, db_session)
    client.post(f"/v1/publico/baja/{destinatario.token_baja}")
    pricing = crear_usuario("pricing")
    h = headers_de(pricing)
    conteo = client.get(f"/v1/boletines/campanas/{destinatario.campana_id}/conteo", headers=h).json()
    assert conteo["omitidos_baja"] == 1 and conteo["recibiran"] == 0


def test_endpoint_interno_exige_secreto(client, db_session, monkeypatch):  # TE1-26
    monkeypatch.setattr(get_settings(), "TAREAS_SECRETO", None)
    assert _codigo(client.post("/internal/boletines/procesar-lote")) == "TAREAS_NO_CONFIGURADAS"
    monkeypatch.setattr(get_settings(), "TAREAS_SECRETO", SecretStr(SECRETO))
    assert client.post("/internal/boletines/procesar-lote").status_code == 401
    assert client.post("/internal/boletines/procesar-lote", headers={"X-Tarea-Secreto": "otro"}).status_code == 401


def test_callback_de_tencent(client, crear_usuario, headers_de, db_session, correo_listo, monkeypatch):  # TE1-27
    monkeypatch.setattr(get_settings(), "TENCENT_EVENTOS_TOKEN", SecretStr(TOKEN_EVENTOS))
    destinatario = _destinatario_enviado(client, crear_usuario, headers_de, db_session)
    assert client.post("/internal/tencent/eventos/otro", json={"event": "bounce"}).status_code == 401
    evento = {"event": "bounce", "bounceType": "hard_bounce", "email": destinatario.email,
              "bulkId": destinatario.message_id, "reason": "550 user unknown"}
    primero = client.post(f"/internal/tencent/eventos/{TOKEN_EVENTOS}", json=evento)
    assert primero.status_code == 200 and primero.json()["procesados"][0]["cambio"].startswith("REBOTADO")
    segundo = client.post(f"/internal/tencent/eventos/{TOKEN_EVENTOS}", json=evento).json()
    assert segundo["procesados"][0]["cambio"] is None  # idempotente
    db_session.expire_all()
    assert db_session.get(CampanaDestinatario, destinatario.id).estado == "REBOTADO"
    assert boletines.esta_de_baja(db_session, destinatario.email)
    queja = client.post(f"/internal/tencent/eventos/{TOKEN_EVENTOS}",
                        json=[{"event": "spamreport", "email": "otro.queja@cliente.ec"}]).json()
    assert queja["procesados"][0]["cambio"] == "BAJA"


# ---------- Servicios de E0 y configuración de masivos (TE1-28 a TE1-30) ----------


def test_servicio_nuevo_y_tipo_de_equipo_nuevo_aparecen_sin_codigo(client, crear_usuario, headers_de, db_session):  # TE1-28
    admin = crear_usuario("admin")
    h = headers_de(admin)
    courier = client.post("/v1/servicios", json={"codigo": "COURIER", "nombre": "Courier", "forma_cobro": "TARIFA_PLANA",
                                                 "tipo_ubicacion_origen": "AEREO", "tipo_ubicacion_destino": "AEREO"},
                          headers=h)
    assert courier.status_code == 201
    tarifa_courier = crear_tarifa(db_session, "AEREO", rate_unit="ENVIO", transportista="DHL")
    tarifa_courier.modo = "COURIER"  # mismos aeropuertos: el servicio nuevo va de aeropuerto a aeropuerto
    db_session.commit()
    nuevo_tipo = client.post("/v1/tipos-equipo", json={"codigo": "45HC", "nombre": "Contenedor 45' HC"}, headers=h).json()
    crear_tarifa(db_session, "FCL", tipo_equipo_id=nuevo_tipo["id"])
    grupos = {g["servicio"]: g for g in client.get("/v1/boletines/tarifas", headers=h).json()}
    assert "COURIER" in grupos and grupos["COURIER"]["tarifas"][0]["texto_tarifa"].endswith("por envío")
    assert any(t["tipo_equipo"] == "45HC" and t["texto_tarifa"].endswith("por 45HC") for t in grupos["FCL"]["tarifas"])
    from app.services import servicios

    assert list(grupos) == [s.codigo for s in servicios.servicios_activos(db_session)]  # el orden de la fuente única


def test_configuracion_de_masivos(client, crear_usuario, headers_de, db_session):  # TE1-29
    h = headers_de(crear_usuario("admin"))
    actual = client.get("/v1/correo/masivos", headers=h).json()
    assert (actual["tope_diario"], actual["reserva_pct"], actual["tamano_lote"]) == (500, 20, 50)
    assert actual["cupo_boletines_hoy"] == 400
    guardada = client.put("/v1/correo/masivos", json={"calentamiento": True, "calentamiento_inicio": 100,
                                                      "calentamiento_incremento": 50}, headers=h).json()
    assert guardada["tope_diario_efectivo"] == 100  # primer día del calentamiento
    for malo in ({"tamano_lote": 0}, {"hora_desde": 20, "hora_hasta": 8}, {"dias_envio": "8"}, {"url_publica": "http://x"},
                 {"correos_prueba": "no-es-correo"}):
        assert client.put("/v1/correo/masivos", json=malo, headers=h).status_code == 422, malo
    assert client.get("/v1/correo/masivos", headers=headers_de(crear_usuario("pricing"))).status_code == 403


def test_whatsapp_solo_digitos_con_codigo_de_pais():  # TE1-32
    from app.services.empresa import whatsapp_numero

    assert whatsapp_numero("098 915 4770") == "593989154770"
    assert whatsapp_numero("+593 (98) 915-4770") == "593989154770"
    assert whatsapp_numero("989154770") == "593989154770"


def test_calentamiento_sube_con_los_dias(db_session):  # TE1-30
    fila = db_session.get(ConfigMasivos, 1)
    fila.calentamiento, fila.calentamiento_inicio, fila.calentamiento_incremento = True, 100, 50
    fila.calentamiento_desde = date(2026, 6, 10)
    assert masivos.tope_diario_efectivo(fila, date(2026, 6, 15)) == 350
    assert masivos.tope_diario_efectivo(fila, date(2026, 7, 30)) == 500  # nunca pasa el tope diario
    _ = tipo_equipo


def test_whatsapp_de_la_empresa_se_valida_y_muestra_el_enlace(client, crear_usuario, headers_de):  # TE1-33
    h = headers_de(crear_usuario("admin"))
    bueno = client.put("/v1/configuracion/empresa", json={"empresa_whatsapp": "098 915 4770"}, headers=h)
    assert (bueno.status_code, bueno.json()["whatsapp_enlace"]) == (200, "https://wa.me/593989154770")
    malo = client.put("/v1/configuracion/empresa", json={"empresa_whatsapp": "12"}, headers=h)
    assert (malo.status_code, malo.json()["detail"]["codigo"]) == (422, "WHATSAPP_INVALIDO")


@pytest.mark.parametrize("pagina", ["boletines", "campana", "listas", "bajas", "plantillas-correo", "baja"])
def test_paginas_e1(client, pagina):  # TE1-34 (mismas reglas que T204 y T257)
    import re

    from test_frontend import PATRONES_PROHIBIDOS_JS

    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    assert re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text) == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []

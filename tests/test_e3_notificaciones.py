"""E3 Notificaciones y avisos (TE3-01 a TE3-26), con reloj simulado y el proveedor de correo FALSO (nunca la red).

Las cotizaciones "enviadas" se arman emitiendo por la API y registrando el envío en la bitácora de F4 (sin generar el
PDF), para controlar la fecha de envío.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import get_settings
from app.core import fechas
from app.models import (
    Auditoria,
    Campana,
    ConfigAvisos,
    ConfigMasivos,
    Cotizacion,
    EnvioCorreo,
    Notificacion,
    PlantillaCorreo,
    ReglaNotificacion,
    Usuario,
)
from app.services import eventos, masivos, notificaciones
from cotizacion_escenarios import HOY, Escenario, cargar_condiciones, fijar_hoy
from fabricas import crear_moneda, crear_proveedor, crear_tarifa
from test_f4_correo import _con_llaves, _emitida, _sin_red, falso, llave  # noqa: F401 - fixtures de F4

SECRETO = "secreto-de-tareas-solo-tests"
ZONA = fechas.ZONA_ECUADOR
EMAIL = "compras@cliente-prueba.ec"


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    fijar_hoy(monkeypatch)
    _reloj(monkeypatch, HOY)


def _reloj(monkeypatch, dia: date, hora: int = 10) -> None:
    monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: dia)
    monkeypatch.setattr("app.core.fechas.ahora_ecuador", lambda: datetime.combine(dia, time(hora), tzinfo=ZONA))


@pytest.fixture
def avisos(db_session):
    """"Aplicar desde" antes de HOY, horario abierto todo el día y tope semanal amplio (los tests lo ajustan)."""
    fila = db_session.get(ConfigAvisos, 1)
    fila.aplicar_desde, fila.dias_habiles, fila.hora_desde, fila.hora_hasta = HOY - timedelta(days=60), "1,2,3,4,5,6,7", 0, 23
    fila.tope_semanal_cliente = 10
    db_session.commit()
    return fila


@pytest.fixture
def correo_listo(db_session, falso, avisos):  # noqa: F811
    """Correo habilitado (proveedor falso), cupo amplio y las plantillas de avisos del gerente aprobadas."""
    _con_llaves(db_session)
    masivo = db_session.get(ConfigMasivos, 1)
    masivo.dias_envio, masivo.hora_desde, masivo.hora_hasta, masivo.pausa_segundos = "1,2,3,4,5,6,7", 0, 23, 0
    for plantilla in db_session.scalars(select(PlantillaCorreo).where(PlantillaCorreo.uso == "AVISO")):
        plantilla.estado_tencent = "APROBADA"
    db_session.commit()
    return falso


def _modo(db_session, modo: str) -> None:
    db_session.get(ConfigAvisos, 1).modo_externo = modo
    db_session.commit()


def _regla(db_session, evento: str) -> ReglaNotificacion:
    return db_session.scalars(select(ReglaNotificacion).where(ReglaNotificacion.evento == evento)).one()


def _enviada(client, h, db_session, comercial, dias_atras: int = 0, email: str = EMAIL, vence_en: int = 30):
    emitida, esc = _emitida(client, h, db_session, comercial, email)
    cotizacion = db_session.get(Cotizacion, emitida["id"])
    db_session.add(EnvioCorreo(
        cotizacion_id=cotizacion.id, destinatario=email, cc=[], asunto=f"Cotización {cotizacion.numero}",
        adjunto_nombre="x.pdf", adjunto_bytes=1, estado="ENVIADO", message_id=f"msg-e3-{cotizacion.id}", enviado_por=comercial.id,
        fecha=datetime.combine(HOY - timedelta(days=dias_atras), time(9), tzinfo=ZONA)))
    cotizacion.estado = "ENVIADA"
    cotizacion.valida_hasta = HOY + timedelta(days=vence_en)
    db_session.commit()
    return cotizacion, esc


def _de(db_session, evento: str, **filtros) -> list[Notificacion]:
    consulta = select(Notificacion).where(Notificacion.evento == evento)
    for campo, valor in filtros.items():
        consulta = consulta.where(getattr(Notificacion, campo) == valor)
    return list(db_session.scalars(consulta.order_by(Notificacion.id)))


def _evaluar(db_session):
    resultado = notificaciones.evaluar(db_session)
    db_session.expire_all()
    return resultado


def _codigo(respuesta) -> str:
    return respuesta.json()["detail"]["codigo"]


# ---------- Siembra y permisos ----------


def test_siembra(db_session):  # TE3-01
    fila = db_session.get(ConfigAvisos, 1)
    assert fila.modo_externo == "SIMULACION" and fila.aplicar_desde is not None
    reglas = {r.evento: r for r in db_session.scalars(select(ReglaNotificacion))}
    assert set(reglas) == {codigo for codigo in eventos.EVENTOS}  # una regla sembrada por evento
    externas = [e for e in eventos.EVENTOS.values() if e.audiencia == eventos.EXTERNA]
    assert {e.codigo for e in externas if not reglas[e.codigo].activo} == {"TARIFA_RUTA_INTERES"}
    tencent = {r.evento: r.plantilla.tencent_id for r in reglas.values() if r.plantilla}
    assert (tencent["COT_SEGUIMIENTO"], tencent["COT_ACEPTADA_CLIENTE"], tencent["COT_ACEPTADA"], tencent["RESUMEN_DIARIO"]) == (
        72747, 72750, 72752, 72753)
    assert all(not r.canal_interno for e in externas for r in [reglas[e.codigo]])


@pytest.mark.parametrize(("rol", "reglas", "bitacora"), [
    ("admin", 200, 200), ("pricing", 403, 200), ("comercial", 403, 403), ("gerencia", 403, 403)])
def test_permisos(client, crear_usuario, headers_de, rol, reglas, bitacora):  # TE3-02
    h = headers_de(crear_usuario(rol))
    assert client.get("/v1/notificaciones/eventos", headers=h).status_code == reglas
    assert client.get("/v1/notificaciones/config", headers=h).status_code == reglas
    assert client.get("/v1/notificaciones/bitacora", headers=h).status_code == bitacora
    assert client.get("/v1/notificaciones/mias", headers=h).status_code == 200
    assert client.get("/v1/notificaciones/preferencias", headers=h).status_code == 200


def test_endpoint_interno_exige_el_secreto(client, monkeypatch, avisos):  # TE3-03
    monkeypatch.setattr(get_settings(), "TAREAS_SECRETO", SecretStr(SECRETO))
    assert client.post("/internal/notificaciones/evaluar").status_code == 401
    assert client.post("/internal/notificaciones/evaluar", headers={"X-Tarea-Secreto": "otro"}).status_code == 401
    respuesta = client.post("/internal/notificaciones/evaluar", headers={"X-Tarea-Secreto": SECRETO})
    assert respuesta.status_code == 200 and "creadas" in respuesta.json()


# ---------- Avisos al cliente por fecha ----------


def test_seguimiento_en_su_momento_y_sin_duplicar(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-04
    comercial = crear_usuario("comercial")
    cotizacion, _ = _enviada(client, headers_de(comercial), db_session, comercial)
    _reloj(monkeypatch, HOY + timedelta(days=2))
    _evaluar(db_session)
    assert _de(db_session, "COT_SEGUIMIENTO") == []
    _reloj(monkeypatch, HOY + timedelta(days=3))
    _evaluar(db_session)
    _evaluar(db_session)  # evaluar dos veces no duplica
    primero = _de(db_session, "COT_SEGUIMIENTO")
    assert [(n.estado, n.email, n.canal, n.entidad_id) for n in primero] == [("SIMULADO", EMAIL, "CORREO", str(cotizacion.id))]
    assert primero[0].variables["numero"] == cotizacion.numero and primero[0].variables["total"].startswith("USD ")
    _reloj(monkeypatch, HOY + timedelta(days=7))
    _evaluar(db_session)
    _reloj(monkeypatch, HOY + timedelta(days=20))
    _evaluar(db_session)
    assert len(_de(db_session, "COT_SEGUIMIENTO")) == 2  # hasta N = 2 recordatorios
    # Agotados los recordatorios (3 + 2 × 4 = 11 días), aviso interno al comercial.
    sin_respuesta = _de(db_session, "COT_SIN_RESPUESTA", canal="INTERNO")
    assert [(n.usuario_id, n.estado) for n in sin_respuesta] == [(comercial.id, "ENVIADO")]


def test_por_vencer_y_vencida(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-05
    comercial = crear_usuario("comercial")
    cotizacion, _ = _enviada(client, headers_de(comercial), db_session, comercial, vence_en=10)
    _reloj(monkeypatch, HOY + timedelta(days=6))
    _evaluar(db_session)
    assert _de(db_session, "COT_POR_VENCER") == []
    _reloj(monkeypatch, HOY + timedelta(days=7))  # 3 días antes
    _evaluar(db_session)
    assert len(_de(db_session, "COT_POR_VENCER")) == 1
    _reloj(monkeypatch, HOY + timedelta(days=10))
    _evaluar(db_session)
    assert _de(db_session, "COT_VENCIDA") == []
    _reloj(monkeypatch, HOY + timedelta(days=11))  # al día siguiente del vencimiento
    _evaluar(db_session)
    assert [n.entidad_id for n in _de(db_session, "COT_VENCIDA")] == [str(cotizacion.id)]


def test_simulacion_no_envia(client, crear_usuario, headers_de, db_session, monkeypatch, correo_listo):  # TE3-06
    comercial = crear_usuario("comercial")
    _enviada(client, headers_de(comercial), db_session, comercial, dias_atras=3)
    _evaluar(db_session)
    assert correo_listo.enviados == []
    aviso = _de(db_session, "COT_SEGUIMIENTO")[0]
    assert aviso.estado == "SIMULADO" and "Modo SIMULACIÓN" in aviso.motivo_omision
    h_admin = headers_de(crear_usuario("admin"))
    detalle = client.get(f"/v1/notificaciones/bitacora/{aviso.id}", headers=h_admin).json()
    assert aviso.variables["numero"] in detalle["contenido"]


def test_activo_envia_con_el_cupo_compartido(client, crear_usuario, headers_de, db_session, monkeypatch, correo_listo):  # TE3-07
    comercial = crear_usuario("comercial")
    cotizacion, esc = _enviada(client, headers_de(comercial), db_session, comercial, dias_atras=3)
    _modo(db_session, "ACTIVO")
    _evaluar(db_session)
    aviso = _de(db_session, "COT_SEGUIMIENTO")[0]
    assert (aviso.estado, aviso.message_id is not None) == ("ENVIADO", True)
    mensaje = correo_listo.enviados[-1]
    plantilla = db_session.get(PlantillaCorreo, aviso.plantilla_id)
    assert (mensaje.destinatario, mensaje.plantilla_id, mensaje.trigger_type) == (EMAIL, 72747, 1)
    assert set(mensaje.datos_plantilla) == set(plantilla.variables_esperadas)  # nunca una variable que la plantilla no tenga
    assert esc.proveedor.nombre not in " ".join(mensaje.datos_plantilla.values())  # nunca el agente
    assert masivos.enviados_hoy(db_session)["avisos"] == 1


def test_aplicar_desde_excluye_el_historico(client, crear_usuario, headers_de, db_session, avisos):  # TE3-08
    comercial = crear_usuario("comercial")
    _enviada(client, headers_de(comercial), db_session, comercial, dias_atras=5)
    avisos.aplicar_desde = HOY - timedelta(days=4)
    db_session.commit()
    _evaluar(db_session)
    assert _de(db_session, "COT_SEGUIMIENTO") == []


def test_apagado_no_genera(client, crear_usuario, headers_de, db_session, avisos):  # TE3-09
    comercial = crear_usuario("comercial")
    _enviada(client, headers_de(comercial), db_session, comercial, dias_atras=3)
    _modo(db_session, "APAGADO")
    _evaluar(db_session)
    assert db_session.scalars(select(Notificacion).where(Notificacion.audiencia == "EXTERNA")).all() == []


# ---------- Cierre, reemplazo e interruptores ----------


def test_aceptar_cancela_pendientes_y_avisa(client, crear_usuario, headers_de, db_session, monkeypatch, correo_listo):  # TE3-10
    comercial, pricing = crear_usuario("comercial"), crear_usuario("pricing")
    h = headers_de(comercial)
    cotizacion, _ = _enviada(client, h, db_session, comercial, dias_atras=3)
    _modo(db_session, "ACTIVO")
    avisos = db_session.get(ConfigAvisos, 1)
    avisos.hora_desde, avisos.hora_hasta = 22, 23  # el seguimiento queda programado (pendiente) para la noche
    db_session.commit()
    notificaciones.generar(db_session, "COT_SEGUIMIENTO", eventos.detector_de("COT_SEGUIMIENTO")(
        db_session, _regla(db_session, "COT_SEGUIMIENTO"), notificaciones.contexto(db_session)),
        _regla(db_session, "COT_SEGUIMIENTO"), notificaciones.contexto(db_session))
    db_session.commit()
    assert _de(db_session, "COT_SEGUIMIENTO")[0].estado == "PENDIENTE"
    respuesta = client.patch(f"/v1/cotizaciones/{cotizacion.id}/estado", json={"estado": "ACEPTADA"}, headers=h)
    assert respuesta.status_code == 200, respuesta.text
    db_session.expire_all()
    assert _de(db_session, "COT_SEGUIMIENTO")[0].estado == "CANCELADO"
    internos = {(n.usuario_id, n.canal) for n in _de(db_session, "COT_ACEPTADA")}
    assert {(comercial.id, "INTERNO"), (pricing.id, "INTERNO"), (comercial.id, "CORREO")} <= internos
    cliente = _de(db_session, "COT_ACEPTADA_CLIENTE")
    assert [(n.email, n.estado) for n in cliente] == [(EMAIL, "PENDIENTE")]  # en horario de la noche
    assert cliente[0].variables["paso_1"].startswith("Le enviaremos")


def test_rechazar_avisa_con_el_motivo(client, crear_usuario, headers_de, db_session, avisos):  # TE3-11
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cotizacion, _ = _enviada(client, h, db_session, comercial)
    client.patch(f"/v1/cotizaciones/{cotizacion.id}/estado", json={"estado": "RECHAZADA", "motivo_rechazo": "PRECIO"}, headers=h)
    aviso = _de(db_session, "COT_RECHAZADA", canal="INTERNO", usuario_id=comercial.id)[0]
    assert "Precio" in aviso.mensaje and aviso.enlace == f"/app/cotizacion.html?id={cotizacion.id}"


def test_reemplazo_cancela_y_excluye(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-12
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cotizacion, _ = _enviada(client, h, db_session, comercial, dias_atras=3)
    copia = client.post(f"/v1/cotizaciones/{cotizacion.id}/duplicar", headers=h)
    assert copia.status_code in (200, 201), copia.text
    copia_id = copia.json()["id"]
    if copia.json().get("requiere_proponer"):
        client.post(f"/v1/cotizaciones/{copia_id}/proponer-lineas", json={}, headers=h)
    assert client.post(f"/v1/cotizaciones/{copia_id}/emitir", json={}, headers=h).status_code == 200
    _evaluar(db_session)
    assert _de(db_session, "COT_SEGUIMIENTO") == []  # la original fue reemplazada


def test_interruptores_y_preferencia_del_contacto(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-13
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    una, _ = _enviada(client, h, db_session, comercial, dias_atras=3, email="una@cliente-prueba.ec")
    otra, _ = _enviada(client, h, db_session, comercial, dias_atras=3, email="otra@cliente-prueba.ec")
    tercera, esc3 = _enviada(client, h, db_session, comercial, dias_atras=3, email="tercera@cliente-prueba.ec")
    assert client.patch(f"/v1/cotizaciones/{una.id}/avisos", json={"activos": False}, headers=h).json()["activos"] is False
    assert client.patch(f"/v1/clientes/{otra.cliente_id}/avisos", json={"activos": False}, headers=h).json()["activos"] is False
    respuesta = client.patch(f"/v1/clientes/{tercera.cliente_id}/contactos/{tercera.contacto_id}/avisos",
                             json={"recibir": False}, headers=h)
    assert respuesta.status_code == 200 and respuesta.json()["contactos"][0]["recibir_avisos"] is False
    _evaluar(db_session)
    avisos_por_cotizacion = {n.entidad_id: n for n in _de(db_session, "COT_SEGUIMIENTO")}
    assert str(una.id) not in avisos_por_cotizacion and str(otra.id) not in avisos_por_cotizacion
    assert avisos_por_cotizacion[str(tercera.id)].estado == "OMITIDO"
    linea = client.get(f"/v1/cotizaciones/{tercera.id}/avisos", headers=h).json()
    assert [a["estado"] for a in linea["avisos"]] == ["OMITIDO"]
    auditadas = db_session.scalars(select(Auditoria.nota).where(Auditoria.entidad == "cotizacion",
                                                                Auditoria.entidad_id == str(una.id))).all()
    assert "AVISOS DESACTIVADOS" in auditadas


def test_horario_habil_y_tope_semanal(client, crear_usuario, headers_de, db_session, monkeypatch, correo_listo):  # TE3-14
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    avisos = db_session.get(ConfigAvisos, 1)
    avisos.hora_desde, avisos.hora_hasta, avisos.tope_semanal_cliente = 8, 18, 1
    db_session.commit()
    _modo(db_session, "ACTIVO")
    cotizacion, esc = _enviada(client, h, db_session, comercial, dias_atras=3, vence_en=2)
    _reloj(monkeypatch, HOY, hora=20)
    _evaluar(db_session)
    seguimiento = _de(db_session, "COT_SEGUIMIENTO")[0]
    assert seguimiento.estado == "PENDIENTE"
    assert seguimiento.programada_para.astimezone(ZONA) == datetime.combine(HOY + timedelta(days=1), time(8), tzinfo=ZONA)
    assert correo_listo.enviados == []  # fuera de horario no sale
    por_vencer = _de(db_session, "COT_POR_VENCER")[0]  # mismo cliente, misma semana: el tope de 1 ya se usó
    assert (por_vencer.estado, por_vencer.motivo_omision) == ("OMITIDO", "Tope semanal de 1 avisos por cliente")
    _reloj(monkeypatch, HOY + timedelta(days=1), hora=8)
    notificaciones.entregar(db_session)
    db_session.expire_all()
    assert _de(db_session, "COT_SEGUIMIENTO")[0].estado == "ENVIADO"


# ---------- Comerciales y bajas ----------


def test_tarifa_ruta_interes_respeta_bajas(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-15
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    cotizacion, esc = _enviada(client, h, db_session, comercial, email="interesado@cliente-prueba.ec")
    regla = _regla(db_session, "TARIFA_RUTA_INTERES")
    regla.activo = True
    db_session.commit()
    nueva = esc.nueva_tarifa(transportista="LATAM Cargo", valido_desde=HOY.isoformat(), proveedor_id=crear_proveedor(db_session).id)
    _evaluar(db_session)
    avisos_ruta = _de(db_session, "TARIFA_RUTA_INTERES", entidad_id=str(nueva.id))
    assert [(n.email, n.estado) for n in avisos_ruta] == [("interesado@cliente-prueba.ec", "SIMULADO")]
    assert {n.email for n in _de(db_session, "TARIFA_RUTA_INTERES")} == {"interesado@cliente-prueba.ec"}
    aviso = avisos_ruta[0]
    assert aviso.variables["enlace_baja"].endswith(f"/b/{aviso.variables['token_baja']}")
    assert "LATAM Cargo" in aviso.variables["fila_01"] and esc.proveedor.nombre not in aviso.variables["fila_01"]
    # La baja pública también funciona con el enlace del aviso.
    token = aviso.variables["token_baja"]
    assert client.post(f"/v1/publico/baja/{token}").json()["de_baja"] is True
    assert cotizacion.cliente_id == aviso.cliente_id
    # Dado de baja: la siguiente tarifa nueva de la ruta ya no le llega (comercial).
    otra = esc.nueva_tarifa(transportista="Avianca Cargo", valido_desde=HOY.isoformat(), proveedor_id=crear_proveedor(db_session).id)
    _evaluar(db_session)
    omitido = _de(db_session, "TARIFA_RUTA_INTERES", entidad_id=str(otra.id))
    assert [(n.estado, n.motivo_omision) for n in omitido] == [("OMITIDO", "Dado de baja de correos comerciales")]


# ---------- Internos ----------


def test_preferencias_y_obligatorias(client, crear_usuario, headers_de, db_session, avisos):  # TE3-16
    comercial = crear_usuario("comercial")
    h = headers_de(comercial)
    preferencias = {p["evento"]: p for p in client.get("/v1/notificaciones/preferencias", headers=h).json()}
    assert preferencias["ENVIO_FALLIDO"]["obligatoria"] is True and preferencias["COT_ACEPTADA"]["correo"] is True
    prohibido = client.put("/v1/notificaciones/preferencias", json={"correo": {"ENVIO_FALLIDO": False}}, headers=h)
    assert (prohibido.status_code, _codigo(prohibido)) == (409, "PREFERENCIA_OBLIGATORIA")
    assert client.put("/v1/notificaciones/preferencias", json={"correo": {"COT_ACEPTADA": False}}, headers=h).status_code == 200
    cotizacion, _ = _enviada(client, h, db_session, comercial)
    client.patch(f"/v1/cotizaciones/{cotizacion.id}/estado", json={"estado": "ACEPTADA"}, headers=h)
    mias = {(n.canal, n.estado) for n in _de(db_session, "COT_ACEPTADA", usuario_id=comercial.id)}
    assert mias == {("INTERNO", "ENVIADO"), ("CORREO", "OMITIDO")}


def test_tarifas_por_vencer_agrupadas_por_dia(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-17
    pricing = crear_usuario("pricing")
    esc = Escenario(db_session, crear_usuario("comercial"), con_tarifa=False)
    for dias in (1, 2, 3):
        esc.nueva_tarifa(valido_hasta=(HOY + timedelta(days=dias)).isoformat(), proveedor_id=crear_proveedor(db_session).id)
    _evaluar(db_session)
    _evaluar(db_session)
    grupo = _de(db_session, "TARIFA_POR_VENCER", usuario_id=pricing.id, canal="INTERNO")
    assert len(grupo) == 1 and grupo[0].entidad_tipo == "grupo" and grupo[0].titulo.startswith("Tarifas por vencer: ")
    assert int(grupo[0].titulo.split(": ")[1]) >= 3
    _reloj(monkeypatch, HOY + timedelta(days=1))
    _evaluar(db_session)
    assert len(_de(db_session, "TARIFA_POR_VENCER", usuario_id=pricing.id, canal="INTERNO")) == 2  # un correo por día


def test_resumen_diario_con_cifras_de_la_base(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-18
    gerente, comercial = crear_usuario("gerencia"), crear_usuario("comercial")
    h = headers_de(comercial)
    aceptada, _ = _enviada(client, h, db_session, comercial)
    rechazada, _ = _enviada(client, h, db_session, comercial)
    client.patch(f"/v1/cotizaciones/{aceptada.id}/estado", json={"estado": "ACEPTADA"}, headers=h)
    client.patch(f"/v1/cotizaciones/{rechazada.id}/estado", json={"estado": "RECHAZADA", "motivo_rechazo": "TIEMPO"}, headers=h)
    for fila in db_session.scalars(select(Auditoria).where(Auditoria.entidad == "cotizacion", Auditoria.entidad_id.in_(
            [str(aceptada.id), str(rechazada.id)]))):
        fila.fecha = datetime.combine(HOY, time(11), tzinfo=ZONA)  # la auditoría usa la hora real; el reloj es simulado
    db_session.commit()
    manana = HOY + timedelta(days=1)
    _reloj(monkeypatch, manana, hora=6)
    _evaluar(db_session)
    assert _de(db_session, "RESUMEN_DIARIO") == []  # antes de la hora configurada (7)
    _reloj(monkeypatch, manana, hora=7)
    _evaluar(db_session)
    _evaluar(db_session)
    resumen = _de(db_session, "RESUMEN_DIARIO", usuario_id=gerente.id, canal="CORREO")
    assert len(resumen) == 1
    cifras = eventos.cifras(db_session, HOY, HOY)
    variables = resumen[0].variables
    assert cifras["emitidas"] >= 2 and cifras["aceptadas"] >= 1 and cifras["rechazadas"] >= 1
    assert (variables["kpi_emitidas"], variables["kpi_aceptadas"], variables["kpi_rechazadas"]) == (
        str(cifras["emitidas"]), str(cifras["aceptadas"]), str(cifras["rechazadas"]))
    assert variables["kpi_monto"] == eventos.dinero(cifras["monto"])
    assert variables["periodo"] == HOY.strftime("%d/%m/%Y") and "TIEMPO (1)" in variables["linea_01"]
    assert variables["enlace"].endswith("/app/cotizaciones.html")


def test_margen_bajo_al_emitir(client, crear_usuario, headers_de, db_session, avisos):  # TE3-19
    gerente, pricing, comercial = crear_usuario("gerencia"), crear_usuario("pricing"), crear_usuario("comercial")
    regla = _regla(db_session, "COT_MARGEN_BAJO")
    regla.parametros = {"umbral_pct": 1000}
    db_session.commit()
    emitida, _ = _emitida(client, headers_de(comercial), db_session, comercial)
    destinatarios = {n.usuario_id for n in _de(db_session, "COT_MARGEN_BAJO", canal="INTERNO")}
    assert {gerente.id, pricing.id} <= destinatarios and comercial.id not in destinatarios
    assert _de(db_session, "COT_MARGEN_BAJO")[0].entidad_id == str(emitida["id"])


def test_envio_fallido_de_cotizacion(client, crear_usuario, headers_de, db_session, correo_listo):  # TE3-20
    admin, comercial = crear_usuario("admin"), crear_usuario("comercial")
    h = headers_de(comercial)
    emitida, _ = _emitida(client, h, db_session, comercial)
    correo_listo.error_envio = "FailedOperation.EmailAddrInBlacklist"
    respuesta = client.post(f"/v1/cotizaciones/{emitida['id']}/enviar", json={"cc_contacto_ids": []}, headers=h)
    assert respuesta.status_code == 502
    db_session.expire_all()
    destinatarios = {n.usuario_id for n in _de(db_session, "ENVIO_FALLIDO", canal="INTERNO")}
    admins = set(db_session.scalars(select(Usuario.id).join(Usuario.rol).where(Usuario.activo.is_(True))
                                    .where(Usuario.rol.has(codigo="admin"))))
    assert admin.id in admins and destinatarios == admins | {comercial.id}  # cada administrador activo y quien envió


def test_usuario_bloqueado(client, crear_usuario, headers_de, db_session):  # TE3-21
    admin, victima = crear_usuario("admin"), crear_usuario("comercial")
    for _ in range(5):
        client.post("/v1/auth/login", json={"email": victima.email, "password": "ClaveIncorrecta2026"})
    db_session.expire_all()
    avisos = _de(db_session, "USUARIO_BLOQUEADO", canal="INTERNO", usuario_id=admin.id)
    assert len(avisos) == 1 and victima.email in avisos[0].titulo


def test_otros_detectores_internos(client, crear_usuario, headers_de, db_session, monkeypatch, avisos):  # TE3-22
    pricing, admin = crear_usuario("pricing"), crear_usuario("admin")
    esc = Escenario(db_session, crear_usuario("comercial"), con_tarifa=False)
    vencida = esc.nueva_tarifa(valido_desde=(HOY - timedelta(days=30)).isoformat(), valido_hasta=(HOY - timedelta(days=2)).isoformat())
    crear_moneda(db_session)
    campana = Campana(nombre="Campaña E3", estado="ENVIADA", total_destinatarios=10, enviados=8, rebotados=2,
                      snapshot_tarifas={"tarifas": [], "vigencia": HOY.isoformat()},
                      creado_por=admin.id, terminada_en=datetime.combine(HOY, time(9), tzinfo=ZONA))
    db_session.add(campana)
    db_session.commit()
    _evaluar(db_session)
    assert [n.entidad_id for n in _de(db_session, "TARIFA_SIN_REEMPLAZO", usuario_id=pricing.id, canal="INTERNO")] == [str(vencida.id)]
    assert _de(db_session, "TASA_DESACTUALIZADA", usuario_id=pricing.id, canal="INTERNO")
    assert _de(db_session, "CAMPANA_TERMINADA", entidad_id=str(campana.id), usuario_id=admin.id)
    assert _de(db_session, "CAMPANA_REBOTE_ALTO", entidad_id=str(campana.id), usuario_id=admin.id)  # 20 % > 5 %


# ---------- Campana, bitácora, reglas y configuración ----------


def test_campana_interna(client, crear_usuario, headers_de, db_session, avisos):  # TE3-23
    comercial, otro = crear_usuario("comercial"), crear_usuario("comercial")
    h = headers_de(comercial)
    for _ in range(2):
        cotizacion, _ = _enviada(client, h, db_session, comercial)
        client.patch(f"/v1/cotizaciones/{cotizacion.id}/estado", json={"estado": "ACEPTADA"}, headers=h)
    assert client.get("/v1/notificaciones/mias/conteo", headers=h).json()["no_leidas"] == 2
    lista = client.get("/v1/notificaciones/mias", headers=h).json()
    ajena = client.post(f"/v1/notificaciones/mias/{lista[0]['id']}/leida", headers=headers_de(otro))
    assert ajena.status_code == 404
    assert client.post(f"/v1/notificaciones/mias/{lista[0]['id']}/leida", headers=h).json()["leida_en"] is not None
    assert client.get("/v1/notificaciones/mias/conteo", headers=h).json()["no_leidas"] == 1
    assert client.post("/v1/notificaciones/mias/leer-todas", headers=h).json()["marcadas"] == 1
    assert client.get("/v1/notificaciones/mias?solo_no_leidas=true", headers=h).json() == []


def test_bitacora_y_reenvio(client, crear_usuario, headers_de, db_session, monkeypatch, correo_listo):  # TE3-24
    comercial, pricing = crear_usuario("comercial"), crear_usuario("pricing")
    _enviada(client, headers_de(comercial), db_session, comercial, dias_atras=3)
    _modo(db_session, "ACTIVO")
    correo_listo.error_envio = "FailedOperation.EmailAddrInBlacklist"
    _evaluar(db_session)
    fallido = _de(db_session, "COT_SEGUIMIENTO")[0]
    assert fallido.estado == "FALLIDO"
    h = headers_de(pricing)
    filtrada = client.get("/v1/notificaciones/bitacora?estado=FALLIDO&evento=COT_SEGUIMIENTO", headers=h).json()
    assert [n["id"] for n in filtrada] == [fallido.id]
    correo_listo.error_envio = None
    assert client.post(f"/v1/notificaciones/bitacora/{fallido.id}/reenviar", headers=h).json()["estado"] == "PENDIENTE"
    assert _codigo(client.post(f"/v1/notificaciones/bitacora/{fallido.id}/reenviar", headers=h)) == "NO_REENVIABLE"
    notificaciones.entregar(db_session)
    db_session.expire_all()
    assert db_session.get(Notificacion, fallido.id).estado == "ENVIADO"


def test_reglas_crud_y_validaciones(client, crear_usuario, headers_de, db_session):  # TE3-25
    h = headers_de(crear_usuario("admin"))
    malo = client.post("/v1/notificaciones/reglas", json={
        "evento": "COT_SEGUIMIENTO", "nombre": "Mal", "canal_interno": True, "destinatarios": {"tipos": ["CONTACTO_COTIZACION"]}},
        headers=h)
    assert _codigo(malo) == "CANAL_INVALIDO"
    sin_rol = client.post("/v1/notificaciones/reglas", json={
        "evento": "COT_ACEPTADA", "nombre": "Jefe", "destinatarios": {"roles": ["no_existe"]}}, headers=h)
    assert _codigo(sin_rol) == "DESTINATARIOS_INVALIDOS"
    creada = client.post("/v1/notificaciones/reglas", json={
        "evento": "COT_ACEPTADA", "nombre": "Aviso a gerencia", "canal_interno": True, "canal_correo": False,
        "destinatarios": {"roles": ["gerencia"], "correos": ["Operaciones@Xpress.ec"]}}, headers=h)
    assert creada.status_code == 201, creada.text
    assert creada.json()["destinatarios"]["correos"] == ["operaciones@xpress.ec"]
    regla = creada.json()["id"]
    assert client.patch(f"/v1/notificaciones/reglas/{regla}", json={"activo": False}, headers=h).json()["activo"] is False
    assert _codigo(client.patch(f"/v1/notificaciones/reglas/{regla}", json={"evento": "COT_RECHAZADA"}, headers=h)) == "EVENTO_NO_EDITABLE"
    acciones = db_session.scalars(select(Auditoria.accion).where(Auditoria.entidad == "regla_notificacion",
                                                                 Auditoria.entidad_id == str(regla))).all()
    assert acciones == ["CREAR", "DESACTIVAR"]
    eventos_api = client.get("/v1/notificaciones/eventos", headers=h).json()
    assert {e["codigo"] for e in eventos_api} == set(eventos.EVENTOS)


def test_configuracion(client, crear_usuario, headers_de, db_session):  # TE3-26
    h = headers_de(crear_usuario("admin"))
    fila = db_session.get(ConfigAvisos, 1)
    fila.aplicar_desde = None
    db_session.commit()
    activa = client.put("/v1/notificaciones/config", json={"modo_externo": "ACTIVO"}, headers=h)
    assert (activa.status_code, activa.json()["aplicar_desde"]) == (200, HOY.isoformat())  # al activar: desde hoy
    assert _codigo(client.put("/v1/notificaciones/config", json={"hora_desde": 19, "hora_hasta": 8}, headers=h)) == "AVISOS_INVALIDO"
    assert client.put("/v1/notificaciones/config", json={"modo_externo": "SIMULACION"}, headers=h).json()["modo_externo"] == "SIMULACION"


@pytest.mark.parametrize("pagina", ["notificaciones-config", "notificaciones-bitacora", "mis-notificaciones"])
def test_paginas_e3(client, pagina):  # TE3-27 (mismas reglas que T204 y T257)
    import re

    from test_frontend import PATRONES_PROHIBIDOS_JS

    respuesta = client.get(f"/app/{pagina}.html")
    assert respuesta.status_code == 200
    assert re.findall(r'<link rel="stylesheet" href="(?!https://)([^"]+)"', respuesta.text) == ["css/xps-pricing.css"]
    assert "<style" not in respuesta.text and "style=" not in respuesta.text
    script = client.get(f"/app/js/{pagina}.js")
    assert script.status_code == 200
    assert [patron for patron in PATRONES_PROHIBIDOS_JS if patron in script.text] == []


_ = (Decimal, Usuario, crear_tarifa, cargar_condiciones)

"""Envíos simultáneos de la misma cotización (T300, B6): SELECT … FOR UPDATE → un solo correo a la vez.

Fuera del SAVEPOINT, como T252: conexiones reales y commits reales sobre xps_pricing_test, en el año 2098, con el
proveedor FALSO (demora de 1,5 s por envío) y una llave Fernet propia del test. El finally borra todo lo que el
test creó y devuelve config_correo y las condiciones a como estaban, aunque falle. La bitácora es de solo
inserción: para limpiar se desactiva su trigger dentro de la misma transacción del borrado.
"""
import threading
from datetime import date
from uuid import uuid4

from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import cifrado
from app.core.security import hashear_password
from app.db import engine
from app.models import (
    Auditoria,
    Cliente,
    ConfigCorreo,
    Configuracion,
    ContactoCliente,
    ContadorCotizacion,
    Cotizacion,
    EnvioCorreo,
    Pais,
    Proveedor,
    Puerto,
    Region,
    Rol,
    Tarifa,
    Usuario,
)
from app.services import correo, cotizaciones
from correo_falso import CorreoFalso
from fabricas import crear_cliente, crear_contacto, crear_proveedor, crear_puerto, crear_tarifa, incoterm

ANIO = 2098
HILOS = 2
CAMPOS_CORREO = ("habilitado", "secret_id_cifrado", "secret_key_cifrado")


def test_envios_simultaneos_uno_a_la_vez(monkeypatch):  # T300
    assert engine.url.database.endswith("_test"), "Este test solo corre sobre la base de pruebas"
    monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: date(ANIO, 6, 15))
    monkeypatch.setattr(get_settings(), "CONFIG_CIFRADO_KEY", SecretStr(Fernet.generate_key().decode()))
    falso = CorreoFalso(demora_s=1.5)
    monkeypatch.setattr(correo, "fabrica_proveedor", falso.fabrica)
    correo.invalidar_cache()
    creados: dict[str, list[int]] = {"tarifa": [], "puerto": [], "pais": [], "region": [], "proveedor": [],
                                     "cliente": [], "contacto": []}
    cotizacion_id = usuario_id = None
    condiciones_antes = correo_antes = None
    try:
        with Session(engine) as db:
            config = db.scalars(select(Configuracion).where(Configuracion.clave == "condiciones_generales_pdf")).one()
            condiciones_antes = config.valor
            config.valor = "TEXTO DE PRUEBA: condiciones de la prueba de envíos simultáneos."
            fila = db.get(ConfigCorreo, 1)
            correo_antes = {campo: getattr(fila, campo) for campo in CAMPOS_CORREO}
            fila.habilitado = True
            fila.secret_id_cifrado = cifrado.cifrar("id-falso-de-la-prueba")
            fila.secret_key_cifrado = cifrado.cifrar("llave-falsa-de-la-prueba")
            rol = db.scalars(select(Rol).where(Rol.codigo == "comercial")).one()
            usuario = Usuario(email=f"c{uuid4().hex[:12]}@prueba.xps", nombre="Comercial envíos simultáneos",
                              hash_password=hashear_password("ClavePrueba2026"), rol=rol)
            db.add(usuario)
            db.commit()
            usuario_id = usuario.id
            origen, destino = crear_puerto(db), crear_puerto(db)
            proveedor = crear_proveedor(db)
            creados["puerto"] += [origen.id, destino.id]
            creados["pais"] += [origen.pais_id, destino.pais_id, proveedor.pais_id]
            creados["proveedor"].append(proveedor.id)
            creados["tarifa"].append(crear_tarifa(
                db, "LCL", proveedor_id=proveedor.id, origen_puerto_id=origen.id, destino_puerto_id=destino.id,
                valido_desde=date(ANIO, 1, 1), valido_hasta=date(ANIO, 12, 31),
            ).id)
            cliente = crear_cliente(db, usuario)
            creados["cliente"].append(cliente.id)
            creados["pais"].append(cliente.pais_id)
            contacto = crear_contacto(db, cliente, principal=True)
            contacto.email = "simultaneo@cliente-prueba.ec"
            db.commit()
            creados["contacto"].append(contacto.id)
            datos = {"cliente_id": cliente.id, "sentido": "IMPORTACION", "incoterm_id": incoterm(db, "FOB").id,
                     "modo": "LCL", "origen_puerto_id": origen.id, "destino_puerto_id": destino.id,
                     "peso_kg": "100", "cbm": "1"}
            cotizacion_id = cotizaciones.crear_cotizacion(db, usuario, datos)["id"]
            cotizaciones.proponer_lineas(db, usuario, cotizacion_id, {})
            cotizaciones.emitir_cotizacion(db, usuario, cotizacion_id, None)
            creados["region"] = list(
                db.scalars(select(Pais.region_id).where(Pais.id.in_(creados["pais"]), Pais.region_id.is_not(None)))
            )
        correo.invalidar_cache()

        barrera = threading.Barrier(HILOS)
        resultados: list[dict] = []
        errores: list[BaseException] = []

        def enviar() -> None:
            try:
                with Session(engine) as db:
                    actor = db.get(Usuario, usuario_id)
                    barrera.wait(timeout=60)
                    resultados.append(correo.enviar_cotizacion(db, actor, cotizacion_id, []))
            except BaseException as error:  # noqa: BLE001 — se reporta abajo
                errores.append(error)

        hilos = [threading.Thread(target=enviar) for _ in range(HILOS)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=240)
        assert errores == []
        assert (len(falso.enviados), falso.max_en_vuelo) == (HILOS, 1)  # dos correos, nunca a la vez
        with Session(engine) as db:
            assert db.get(Cotizacion, cotizacion_id).estado == "ENVIADA"
            envios = db.scalars(select(EnvioCorreo).where(EnvioCorreo.cotizacion_id == cotizacion_id)).all()
            assert sorted(e.estado for e in envios) == ["ENVIADO", "ENVIADO"]
            transiciones = db.scalars(select(Auditoria).where(
                Auditoria.entidad == "cotizacion", Auditoria.entidad_id == str(cotizacion_id),
                Auditoria.nota.like("ENVIAR%"))).all()
            assert len(transiciones) == 1  # EMITIDA → ENVIADA una sola vez; el otro es reenvío
    finally:
        correo.invalidar_cache()
        with Session(engine) as db:
            if cotizacion_id is not None:
                db.execute(text("ALTER TABLE envio_correo DISABLE TRIGGER tg_envio_correo_solo_insercion"))
                db.execute(delete(EnvioCorreo).where(EnvioCorreo.cotizacion_id == cotizacion_id))
                db.execute(text("ALTER TABLE envio_correo ENABLE TRIGGER tg_envio_correo_solo_insercion"))
                db.execute(delete(Auditoria).where(Auditoria.entidad == "cotizacion",
                                                   Auditoria.entidad_id == str(cotizacion_id)))
                db.execute(delete(Cotizacion).where(Cotizacion.id == cotizacion_id))
            if usuario_id is not None:
                db.execute(delete(Auditoria).where(Auditoria.usuario_id == usuario_id))
            db.execute(delete(ContadorCotizacion).where(ContadorCotizacion.anio == ANIO))
            db.execute(delete(Tarifa).where(Tarifa.id.in_(creados["tarifa"])))
            db.execute(delete(ContactoCliente).where(ContactoCliente.id.in_(creados["contacto"])))
            db.execute(delete(Cliente).where(Cliente.id.in_(creados["cliente"])))
            db.execute(delete(Puerto).where(Puerto.id.in_(creados["puerto"])))
            db.execute(delete(Proveedor).where(Proveedor.id.in_(creados["proveedor"])))
            db.execute(delete(Pais).where(Pais.id.in_(creados["pais"])))
            db.execute(delete(Region).where(Region.id.in_(creados["region"])))
            if usuario_id is not None:
                db.execute(delete(Usuario).where(Usuario.id == usuario_id))
            if condiciones_antes is not None:
                db.execute(update(Configuracion).where(Configuracion.clave == "condiciones_generales_pdf")
                           .values(valor=condiciones_antes))
            if correo_antes is not None:
                db.execute(update(ConfigCorreo).where(ConfigCorreo.id == 1).values(**correo_antes))
            db.commit()
            restos = db.execute(text("SELECT count(*) FROM cotizacion WHERE numero LIKE :p"), {"p": f"COT-{ANIO}-%"})
            assert restos.scalar_one() == 0

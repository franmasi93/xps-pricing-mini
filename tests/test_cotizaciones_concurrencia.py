"""Numeración concurrente (T252, H14): 4 emisiones a la vez → números distintos y consecutivos.

Fuera del SAVEPOINT: usa conexiones reales y commits reales sobre xps_pricing_test, con la misma
función de producción (SELECT … FOR UPDATE), en el año 2099 para no tocar el contador del año en
curso. El finally borra todo lo que el test creó, aunque falle.
"""
import threading
from datetime import date
from uuid import uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.core.security import hashear_password
from app.db import engine
from app.models import (
    Auditoria,
    Cliente,
    Configuracion,
    ContactoCliente,
    ContadorCotizacion,
    Cotizacion,
    Pais,
    Proveedor,
    Puerto,
    Region,
    Rol,
    Tarifa,
    Usuario,
)
from app.services import cotizaciones
from fabricas import crear_cliente, crear_contacto, crear_proveedor, crear_puerto, crear_tarifa, incoterm

ANIO = 2099
HILOS = 4


def test_emisiones_concurrentes_sin_duplicados(monkeypatch):  # T252
    assert engine.url.database.endswith("_test"), "Este test solo corre sobre la base de pruebas"
    monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: date(ANIO, 6, 15))
    creados: dict[str, list[int]] = {"cotizacion": [], "tarifa": [], "puerto": [], "pais": [], "region": [],
                                     "proveedor": [], "cliente": [], "contacto": []}
    usuario_id = None
    condiciones_antes = None
    try:
        with Session(engine) as db:
            config = db.scalars(select(Configuracion).where(Configuracion.clave == "condiciones_generales_pdf")).one()
            condiciones_antes = config.valor
            config.valor = "TEXTO DE PRUEBA: condiciones de la prueba de concurrencia."
            rol = db.scalars(select(Rol).where(Rol.codigo == "comercial")).one()
            usuario = Usuario(email=f"c{uuid4().hex[:12]}@prueba.xps", nombre="Comercial concurrencia",
                              hash_password=hashear_password("ClavePrueba2026"), rol=rol)
            db.add(usuario)
            db.commit()
            usuario_id = usuario.id
            origen, destino = crear_puerto(db), crear_puerto(db)
            proveedor = crear_proveedor(db)
            creados["puerto"] += [origen.id, destino.id]
            creados["pais"] += [origen.pais_id, destino.pais_id, proveedor.pais_id]
            creados["proveedor"].append(proveedor.id)
            tarifa = crear_tarifa(
                db, "LCL", proveedor_id=proveedor.id, origen_puerto_id=origen.id, destino_puerto_id=destino.id,
                valido_desde=date(ANIO, 1, 1), valido_hasta=date(ANIO, 12, 31),
            )
            creados["tarifa"].append(tarifa.id)
            cliente = crear_cliente(db, usuario)
            creados["cliente"].append(cliente.id)
            creados["pais"].append(cliente.pais_id)
            creados["contacto"].append(crear_contacto(db, cliente, principal=True).id)
            for _ in range(HILOS):
                datos = {
                    "cliente_id": cliente.id, "sentido": "IMPORTACION", "incoterm_id": incoterm(db, "FOB").id,
                    "modo": "LCL", "origen_puerto_id": origen.id, "destino_puerto_id": destino.id,
                    "peso_kg": "100", "cbm": "1",
                }
                creada = cotizaciones.crear_cotizacion(db, usuario, datos)
                creados["cotizacion"].append(creada["id"])
                cotizaciones.proponer_lineas(db, usuario, creada["id"], {})
            creados["region"] = list(
                db.scalars(select(Pais.region_id).where(Pais.id.in_(creados["pais"]), Pais.region_id.is_not(None)))
            )

        barrera = threading.Barrier(HILOS)
        numeros: list[str] = []
        errores: list[BaseException] = []

        def emitir(cotizacion_id: int) -> None:
            try:
                with Session(engine) as db:
                    actor = db.get(Usuario, usuario_id)
                    barrera.wait(timeout=60)
                    numeros.append(cotizaciones.emitir_cotizacion(db, actor, cotizacion_id, None)["numero"])
            except BaseException as error:  # noqa: BLE001 — se reporta abajo
                errores.append(error)

        hilos = [threading.Thread(target=emitir, args=(ident,)) for ident in creados["cotizacion"]]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=180)
        assert errores == []
        assert sorted(int(numero[-5:]) for numero in numeros) == [1, 2, 3, 4]
        assert all(numero.startswith(f"COT-{ANIO}-") for numero in numeros)
        with Session(engine) as db:
            assert db.get(ContadorCotizacion, ANIO).ultimo == HILOS
    finally:
        with Session(engine) as db:
            ids = creados["cotizacion"]
            if ids:
                db.execute(delete(Auditoria).where(Auditoria.entidad == "cotizacion",
                                                   Auditoria.entidad_id.in_([str(i) for i in ids])))
                db.execute(delete(Cotizacion).where(Cotizacion.id.in_(ids)))
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
                db.execute(
                    update(Configuracion)
                    .where(Configuracion.clave == "condiciones_generales_pdf")
                    .values(valor=condiciones_antes)
                )
            db.commit()
            restos = db.execute(text("SELECT count(*) FROM cotizacion WHERE numero LIKE :p"), {"p": f"COT-{ANIO}-%"})
            assert restos.scalar_one() == 0

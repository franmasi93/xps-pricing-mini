"""Escenarios de cotización para los tests de F3: puertos, tarifas y recargos propios de cada test.

"Hoy" se fija en HOY (dentro de la vigencia 2026 de las fábricas) sustituyendo hoy_ecuador().
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Configuracion, Pais, Recargo
from fabricas import (
    crear_cliente,
    crear_contacto,
    crear_pais,
    crear_proveedor,
    crear_puerto,
    crear_tarifa,
    incoterm,
    iso2_libre,
    payload_recargo,
    tipo_equipo,
)

HOY = date(2026, 6, 15)
CONDICIONES_PRUEBA = "TEXTO DE PRUEBA: condiciones generales (solo en la base de pruebas)."


def fijar_hoy(monkeypatch, dia: date = HOY) -> None:
    monkeypatch.setattr("app.core.fechas.hoy_ecuador", lambda: dia)


def pais_ecuador(db: Session) -> Pais:
    pais = db.scalars(select(Pais).where(Pais.iso2 == "EC")).one_or_none()
    return pais or crear_pais(db, iso2="EC")


def cargar_condiciones(db: Session, texto: str = CONDICIONES_PRUEBA) -> None:
    config = db.scalars(select(Configuracion).where(Configuracion.clave == "condiciones_generales_pdf")).one()
    config.valor = texto
    db.commit()


def crear_recargo(db: Session, puerto, bloque: str, lado: str, **cambios) -> Recargo:
    """Recargo por ORM (sin pasar por el service). Por defecto: por envío, costo 50, MARKUP 10 %."""
    datos = payload_recargo(db, puerto, bloque_incoterm=bloque, lado=lado, concepto=f"{bloque} {uuid4().hex[:4]}")
    datos |= cambios
    for campo in ("costo", "minimo", "parametro_venta", "precio_venta_manual", "minimo_venta_manual"):
        if datos.get(campo) is not None:
            datos[campo] = Decimal(str(datos[campo]))
    datos["valido_desde"] = date.fromisoformat(str(datos["valido_desde"]))
    datos["valido_hasta"] = date.fromisoformat(str(datos["valido_hasta"]))
    recargo = Recargo(**datos)
    db.add(recargo)
    db.commit()
    return recargo


class Escenario:
    """Ruta origen (exterior) → destino (Ecuador), cliente con contacto principal y una tarifa."""

    def __init__(self, db: Session, comercial, modo: str = "LCL", con_tarifa: bool = True, **tarifa):
        self.db = db
        self.modo = modo
        tipo = "AEREO" if modo == "AEREO" else "MARITIMO"
        self.origen = crear_puerto(db, pais=crear_pais(db, iso2=iso2_libre(db)), tipo=tipo)
        self.destino = crear_puerto(db, pais=pais_ecuador(db), tipo=tipo)
        self.cliente = crear_cliente(db, comercial)
        self.contacto = crear_contacto(db, self.cliente, principal=True)
        self.proveedor = crear_proveedor(db)
        self.tarifa = self.nueva_tarifa(**tarifa) if con_tarifa else None

    def nueva_tarifa(self, **cambios):
        datos = {
            "proveedor_id": self.proveedor.id,
            "origen_puerto_id": self.origen.id,
            "destino_puerto_id": self.destino.id,
        }
        return crear_tarifa(self.db, self.modo, **(datos | cambios))

    def payload(self, incoterm_codigo: str = "FOB", sentido: str = "IMPORTACION", **cambios) -> dict:
        datos = {
            "cliente_id": self.cliente.id,
            "sentido": sentido,
            "incoterm_id": incoterm(self.db, incoterm_codigo).id,
            "modo": self.modo,
            "origen_puerto_id": self.origen.id,
            "destino_puerto_id": self.destino.id,
            "peso_kg": "800",
            "cbm": "2.5",
        }
        if self.modo == "FCL":
            datos["contenedores"] = [{"tipo_equipo_id": tipo_equipo(self.db).id, "cantidad": 1}]
        return datos | cambios

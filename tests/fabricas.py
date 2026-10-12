"""Fábricas de datos de catálogos para los tests: cada test crea los suyos, con códigos únicos.

Los códigos se generan al azar dentro de rangos que los tests no usan a mano: las regiones
empiezan con "T_", y los países ISO2 usan la letra Q (asignada por ISO para uso privado).
"""
import random
import string
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Cliente,
    ContactoCliente,
    Cotizacion,
    Incoterm,
    Moneda,
    Pais,
    Proveedor,
    Puerto,
    Region,
    Tarifa,
    TasaCambio,
    TipoEquipo,
    Usuario,
)

LETRAS = string.ascii_uppercase


def codigo_region() -> str:
    return f"T_{uuid4().hex[:10].upper()}"


def iso2_libre(db: Session) -> str:
    """ISO2 de uso privado (QA a QZ, más XA a XZ) que todavía no exista en la base."""
    usados = set(db.scalars(select(Pais.iso2)))
    libres = [f"{a}{b}" for a in "QX" for b in LETRAS if f"{a}{b}" not in usados]
    return random.choice(libres)


def codigo_moneda_libre(db: Session) -> str:
    usados = set(db.scalars(select(Moneda.codigo)))
    while True:
        codigo = "".join(random.choices(LETRAS, k=3))
        if codigo not in usados and codigo != "USD":
            return codigo


def crear_region(db: Session, activo: bool = True) -> Region:
    region = Region(codigo=codigo_region(), nombre="Región de prueba", activo=activo)
    db.add(region)
    db.commit()
    return region


def crear_pais(db: Session, region: Region | None = None, activo: bool = True, iso2: str | None = None) -> Pais:
    pais = Pais(
        iso2=iso2 or iso2_libre(db),
        nombre="País de prueba",
        region=region or crear_region(db),
        activo=activo,
    )
    db.add(pais)
    db.commit()
    return pais


def crear_puerto(db: Session, pais: Pais | None = None, tipo: str = "MARITIMO", activo: bool = True) -> Puerto:
    pais = pais or crear_pais(db)
    usados = set(db.scalars(select(Puerto.codigo)))
    while True:
        sufijo = "".join(random.choices(LETRAS, k=3))
        codigo = f"{pais.iso2}{sufijo}" if tipo == "MARITIMO" else sufijo
        if codigo not in usados:
            break
    puerto = Puerto(codigo=codigo, nombre="Puerto de prueba", pais=pais, tipo=tipo, activo=activo)
    db.add(puerto)
    db.commit()
    return puerto


def crear_moneda(db: Session, activo: bool = True, codigo: str | None = None) -> Moneda:
    moneda = Moneda(codigo=codigo or codigo_moneda_libre(db), nombre="Moneda de prueba", simbolo="¤", activo=activo)
    db.add(moneda)
    db.commit()
    return moneda


def crear_tasa(db: Session, moneda: Moneda, tasa: str, fecha: date, usuario: Usuario) -> TasaCambio:
    registro = TasaCambio(moneda=moneda, tasa_a_usd=Decimal(tasa), fecha_vigencia=fecha, registrado_por=usuario.id)
    db.add(registro)
    db.commit()
    return registro


def crear_proveedor(db: Session, pais: Pais | None = None, nombre: str | None = None) -> Proveedor:
    proveedor = Proveedor(nombre=nombre or f"Proveedor {uuid4().hex[:10]}", pais=pais or crear_pais(db))
    db.add(proveedor)
    db.commit()
    return proveedor


# ---------- M5: tarifas y recargos ----------

UNIDAD_POR_MODO = {"AEREO": "KG", "LCL": "WM", "FCL": "CONTENEDOR"}


def usd(db: Session) -> Moneda:
    return db.scalars(select(Moneda).where(Moneda.codigo == "USD")).one()


def tipo_equipo(db: Session, codigo: str = "40HC") -> TipoEquipo:
    return db.scalars(select(TipoEquipo).where(TipoEquipo.codigo == codigo)).one()


def puertos_para(db: Session, modo: str) -> tuple[Puerto, Puerto]:
    """Origen y destino nuevos, del tipo que corresponde al modo."""
    tipo = "AEREO" if modo == "AEREO" else "MARITIMO"
    return crear_puerto(db, tipo=tipo), crear_puerto(db, tipo=tipo)


def payload_tarifa(db: Session, modo: str = "LCL", **cambios) -> dict:
    """Cuerpo válido para POST /v1/tarifas, con proveedor y puertos propios del test."""
    origen, destino = puertos_para(db, modo)
    datos = {
        "proveedor_id": crear_proveedor(db).id,
        "modo": modo,
        "origen_puerto_id": origen.id,
        "destino_puerto_id": destino.id,
        "tipo_equipo_id": tipo_equipo(db).id if modo == "FCL" else None,
        "rate_unit": UNIDAD_POR_MODO[modo],
        "costo": "100",
        "moneda_id": usd(db).id,
        "minimo": "0",
        "metodo_venta": "MARKUP",
        "parametro_venta": "20",
        "valido_desde": "2026-01-01",
        "valido_hasta": "2026-12-31",
    }
    return datos | cambios


def crear_tarifa(db: Session, modo: str = "LCL", **cambios) -> Tarifa:
    """Tarifa insertada por ORM (sin pasar por el service) para preparar datos de prueba."""
    datos = payload_tarifa(db, modo)
    datos |= {"valido_desde": date(2026, 1, 1), "valido_hasta": date(2026, 12, 31)} | cambios
    for campo in ("costo", "minimo", "parametro_venta", "precio_venta_manual", "minimo_venta_manual"):
        if datos.get(campo) is not None:
            datos[campo] = Decimal(str(datos[campo]))
    tarifa = Tarifa(**datos)
    db.add(tarifa)
    db.commit()
    return tarifa


def cedula_libre(db: Session) -> str:
    usadas = set(db.scalars(select(Cliente.ruc_o_id)))
    while True:
        cedula = "".join(random.choices(string.digits, k=10))
        if cedula not in usadas:
            return cedula


def crear_cliente(db: Session, comercial: Usuario, activo: bool = True, razon_social: str | None = None) -> Cliente:
    """Cliente insertado por ORM, asignado al comercial indicado."""
    cliente = Cliente(
        razon_social=razon_social or f"Cliente {uuid4().hex[:8]}",
        tipo_id="CEDULA",
        ruc_o_id=cedula_libre(db),
        pais=crear_pais(db),
        comercial_asignado_id=comercial.id,
        activo=activo,
    )
    db.add(cliente)
    db.commit()
    return cliente


def crear_contacto(db: Session, cliente: Cliente, principal: bool = False, nombre: str | None = None) -> ContactoCliente:
    contacto = ContactoCliente(cliente_id=cliente.id, nombre=nombre or f"Contacto {uuid4().hex[:6]}", principal=principal)
    db.add(contacto)
    db.commit()
    return contacto


def payload_recargo(db: Session, puerto: Puerto | None = None, **cambios) -> dict:
    """Cuerpo válido para POST /v1/recargos: THC de destino en un puerto marítimo propio del test."""
    datos = {
        "proveedor_id": None,
        "puerto_id": (puerto or crear_puerto(db, tipo="MARITIMO")).id,
        "lado": "DESTINO",
        "bloque_incoterm": "GASTOS_DESTINO",
        "concepto": f"THC {uuid4().hex[:6]}",
        "modo": None,
        "tipo_equipo_id": None,
        "rate_unit": "ENVIO",
        "costo": "50",
        "moneda_id": usd(db).id,
        "minimo": "0",
        "metodo_venta": "MARKUP",
        "parametro_venta": "10",
        "aplica_iva": True,
        "rol_ingreso": "PRINCIPAL",
        "valido_desde": "2026-01-01",
        "valido_hasta": "2026-12-31",
    }
    return datos | cambios


def incoterm(db: Session, codigo: str = "FOB") -> Incoterm:
    return db.scalars(select(Incoterm).where(Incoterm.codigo == codigo)).one()


def crear_cotizacion(db: Session, comercial: Usuario, modo: str = "LCL", **cambios) -> Cotizacion:
    """Borrador insertado por ORM (sin pasar por el service), con cliente y puertos propios del test."""
    origen, destino = puertos_para(db, modo)
    datos = {
        "cliente_id": crear_cliente(db, comercial).id,
        "comercial_id": comercial.id,
        "sentido": "IMPORTACION",
        "incoterm_id": incoterm(db).id,
        "modo": modo,
        "origen_puerto_id": origen.id,
        "destino_puerto_id": destino.id,
        "peso_kg": Decimal("100"),
        "cbm": Decimal("1"),
    }
    cotizacion = Cotizacion(**(datos | cambios))
    db.add(cotizacion)
    db.commit()
    return cotizacion

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

from app.models import Moneda, Pais, Proveedor, Puerto, Region, TasaCambio, Usuario

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

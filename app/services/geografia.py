"""M2 Geografía: regiones, países y puertos.

Reglas: códigos sin espacios y en mayúsculas; un hijo no puede quedar activo bajo un padre
inactivo (PADRE_INACTIVO); un padre no se desactiva con hijos activos (TIENE_DEPENDIENTES).
"""
import re
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar
from app.models import Pais, Puerto, Region, Usuario

PATRON_REGION = re.compile(r"^[A-Z0-9_]{2,20}$")
PATRON_ISO2 = re.compile(r"^[A-Z]{2}$")
PATRON_LOCODE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")
PATRON_IATA = re.compile(r"^[A-Z]{3}$")


def normalizar_codigo(codigo: str) -> str:
    return "".join(codigo.split()).upper()


def _nombre(nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
    return nombre


def _padre_inactivo(que: str) -> ErrorNegocio:
    return ErrorNegocio(422, "PADRE_INACTIVO", f"No se puede usar {que} inactivo; actívelo primero")


def _referencia_inexistente(que: str) -> ErrorNegocio:
    return ErrorNegocio(422, "REFERENCIA_INEXISTENTE", f"No existe {que} indicado")


def _tiene_dependientes(mensaje: str) -> ErrorNegocio:
    return ErrorNegocio(409, "TIENE_DEPENDIENTES", mensaje)


# ---------- Regiones ----------


def _validar_codigo_region(codigo: str) -> str:
    codigo = normalizar_codigo(codigo)
    if not PATRON_REGION.match(codigo):
        raise ErrorNegocio(
            422, "CODIGO_INVALIDO", "El código de región debe tener de 2 a 20 letras, números o guion bajo"
        )
    return codigo


def listar_regiones(db: Session, activo: bool | None = None) -> list[Region]:
    consulta = select(Region)
    if activo is not None:
        consulta = consulta.where(Region.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Region.codigo)))


def obtener_region(db: Session, region_id: int) -> Region:
    region = db.get(Region, region_id)
    if region is None:
        raise ErrorNegocio(404, "REGION_NO_ENCONTRADA", "Región no encontrada")
    return region


def crear_region(db: Session, actor: Usuario, codigo: str, nombre: str) -> Region:
    region = Region(codigo=_validar_codigo_region(codigo), nombre=_nombre(nombre), creado_por=actor.id)
    db.add(region)
    confirmar(db)
    return region


def actualizar_region(db: Session, region_id: int, cambios: dict[str, Any]) -> Region:
    region = obtener_region(db, region_id)
    with db.no_autoflush:  # las consultas de validación no deben escribir cambios a medias
        if "codigo" in cambios:
            region.codigo = _validar_codigo_region(cambios["codigo"])
        if "nombre" in cambios:
            region.nombre = _nombre(cambios["nombre"])
        if cambios.get("activo") is False and region.activo:
            if db.scalar(select(exists().where(Pais.region_id == region.id, Pais.activo.is_(True)))):
                raise _tiene_dependientes("La región tiene países activos; desactívelos primero")
        if "activo" in cambios:
            region.activo = cambios["activo"]
    confirmar(db)
    return region


# ---------- Países ----------


def _validar_iso2(iso2: str) -> str:
    iso2 = normalizar_codigo(iso2)
    if not PATRON_ISO2.match(iso2):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código ISO del país debe tener exactamente 2 letras")
    return iso2


def _region_utilizable(db: Session, region_id: int) -> Region:
    region = db.get(Region, region_id)
    if region is None:
        raise _referencia_inexistente("la región")
    if not region.activo:
        raise _padre_inactivo("una región")
    return region


def listar_paises(db: Session, region_id: int | None = None, activo: bool | None = None) -> list[Pais]:
    consulta = select(Pais).options(selectinload(Pais.region))
    if region_id is not None:
        consulta = consulta.where(Pais.region_id == region_id)
    if activo is not None:
        consulta = consulta.where(Pais.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Pais.nombre)))


def obtener_pais(db: Session, pais_id: int) -> Pais:
    pais = db.get(Pais, pais_id)
    if pais is None:
        raise ErrorNegocio(404, "PAIS_NO_ENCONTRADO", "País no encontrado")
    return pais


def crear_pais(db: Session, actor: Usuario, iso2: str, nombre: str, region_id: int) -> Pais:
    pais = Pais(
        iso2=_validar_iso2(iso2),
        nombre=_nombre(nombre),
        region=_region_utilizable(db, region_id),
        creado_por=actor.id,
    )
    db.add(pais)
    confirmar(db)
    return pais


def actualizar_pais(db: Session, pais_id: int, cambios: dict[str, Any]) -> Pais:
    pais = obtener_pais(db, pais_id)
    with db.no_autoflush:  # las consultas de validación no deben escribir cambios a medias
        if "iso2" in cambios:
            nuevo_iso2 = _validar_iso2(cambios["iso2"])
            if nuevo_iso2 != pais.iso2 and db.scalar(
                select(exists().where(Puerto.pais_id == pais.id, Puerto.tipo == "MARITIMO"))
            ):
                raise _tiene_dependientes(
                    "El país tiene puertos marítimos cuyo código empieza con su ISO actual; no se puede cambiar"
                )
            pais.iso2 = nuevo_iso2
        if "nombre" in cambios:
            pais.nombre = _nombre(cambios["nombre"])
        if "region_id" in cambios and cambios["region_id"] != pais.region_id:
            pais.region = _region_utilizable(db, cambios["region_id"])

        activo_final = cambios.get("activo", pais.activo)
        if activo_final and not pais.region.activo:
            raise _padre_inactivo("una región")
        if cambios.get("activo") is False and pais.activo:
            if db.scalar(select(exists().where(Puerto.pais_id == pais.id, Puerto.activo.is_(True)))):
                raise _tiene_dependientes("El país tiene puertos activos; desactívelos primero")
        if "activo" in cambios:
            pais.activo = cambios["activo"]
    confirmar(db)
    return pais


# ---------- Puertos ----------


def _validar_puerto(codigo: str, tipo: str, pais: Pais) -> None:
    if tipo == "MARITIMO":
        if not PATRON_LOCODE.match(codigo):
            raise ErrorNegocio(
                422, "CODIGO_INVALIDO", "Un puerto marítimo usa UN/LOCODE: 5 caracteres, como ECGYE"
            )
        if codigo[:2] != pais.iso2:
            raise ErrorNegocio(
                422,
                "PUERTO_PAIS_INCONSISTENTE",
                f"El código {codigo} empieza con {codigo[:2]}, pero el país es {pais.iso2}",
            )
    elif not PATRON_IATA.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "Un aeropuerto usa el código IATA: 3 letras, como GYE")


def _pais_utilizable(db: Session, pais_id: int) -> Pais:
    pais = db.get(Pais, pais_id)
    if pais is None:
        raise _referencia_inexistente("el país")
    if not pais.activo:
        raise _padre_inactivo("un país")
    return pais


def listar_puertos(
    db: Session,
    tipo: str | None = None,
    pais_id: int | None = None,
    activo: bool | None = None,
    q: str | None = None,
) -> list[Puerto]:
    consulta = select(Puerto).options(selectinload(Puerto.pais))
    if tipo is not None:
        consulta = consulta.where(Puerto.tipo == tipo)
    if pais_id is not None:
        consulta = consulta.where(Puerto.pais_id == pais_id)
    if activo is not None:
        consulta = consulta.where(Puerto.activo.is_(activo))
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Puerto.codigo.ilike(patron), Puerto.nombre.ilike(patron)))
    return list(db.scalars(consulta.order_by(Puerto.codigo)))


def obtener_puerto(db: Session, puerto_id: int) -> Puerto:
    puerto = db.get(Puerto, puerto_id)
    if puerto is None:
        raise ErrorNegocio(404, "PUERTO_NO_ENCONTRADO", "Puerto no encontrado")
    return puerto


def crear_puerto(db: Session, actor: Usuario, codigo: str, nombre: str, pais_id: int, tipo: str) -> Puerto:
    pais = _pais_utilizable(db, pais_id)
    codigo = normalizar_codigo(codigo)
    _validar_puerto(codigo, tipo, pais)
    puerto = Puerto(codigo=codigo, nombre=_nombre(nombre), pais=pais, tipo=tipo, creado_por=actor.id)
    db.add(puerto)
    confirmar(db)
    return puerto


def actualizar_puerto(db: Session, puerto_id: int, cambios: dict[str, Any]) -> Puerto:
    puerto = obtener_puerto(db, puerto_id)
    # Primero se valida el estado final completo; recién después se modifica el objeto.
    pais = puerto.pais
    if "pais_id" in cambios and cambios["pais_id"] != puerto.pais_id:
        pais = _pais_utilizable(db, cambios["pais_id"])
    codigo = normalizar_codigo(cambios["codigo"]) if "codigo" in cambios else puerto.codigo
    tipo = cambios.get("tipo", puerto.tipo)
    _validar_puerto(codigo, tipo, pais)
    nombre = _nombre(cambios["nombre"]) if "nombre" in cambios else puerto.nombre

    activo_final = cambios.get("activo", puerto.activo)
    if activo_final and not pais.activo:
        raise _padre_inactivo("un país")

    puerto.pais = pais
    puerto.codigo = codigo
    puerto.tipo = tipo
    puerto.nombre = nombre
    puerto.activo = activo_final
    confirmar(db)
    return puerto

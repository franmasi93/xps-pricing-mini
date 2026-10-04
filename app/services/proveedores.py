"""M4 Proveedores (agentes). Nombre único sin distinguir mayúsculas; país obligatorio y activo."""
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar
from app.models import Pais, Proveedor, Usuario
from app.schemas.usuarios import email_valido, normalizar_email

CAMPOS_OPCIONALES = ("contacto", "telefono", "notas")


def _nombre(nombre: str) -> str:
    nombre = " ".join(nombre.split())
    if not nombre:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre del proveedor no puede estar vacío")
    return nombre


def _email(email: str | None) -> str | None:
    if email is None or not email.strip():
        return None
    email = normalizar_email(email)
    if not email_valido(email):
        raise ErrorNegocio(422, "EMAIL_INVALIDO", "El email del proveedor no es válido")
    return email


def _opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def _pais_utilizable(db: Session, pais_id: int) -> Pais:
    pais = db.get(Pais, pais_id)
    if pais is None:
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "No existe el país indicado")
    if not pais.activo:
        raise ErrorNegocio(422, "PADRE_INACTIVO", "No se puede usar un país inactivo; actívelo primero")
    return pais


def listar_proveedores(
    db: Session, pais_id: int | None = None, activo: bool | None = None, q: str | None = None
) -> list[Proveedor]:
    consulta = select(Proveedor).options(selectinload(Proveedor.pais))
    if pais_id is not None:
        consulta = consulta.where(Proveedor.pais_id == pais_id)
    if activo is not None:
        consulta = consulta.where(Proveedor.activo.is_(activo))
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(Proveedor.nombre.ilike(patron), Proveedor.contacto.ilike(patron)))
    return list(db.scalars(consulta.order_by(Proveedor.nombre)))


def obtener_proveedor(db: Session, proveedor_id: int) -> Proveedor:
    proveedor = db.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise ErrorNegocio(404, "PROVEEDOR_NO_ENCONTRADO", "Proveedor no encontrado")
    return proveedor


def crear_proveedor(db: Session, actor: Usuario, datos: dict[str, Any]) -> Proveedor:
    proveedor = Proveedor(
        nombre=_nombre(datos["nombre"]),
        pais=_pais_utilizable(db, datos["pais_id"]),
        email=_email(datos.get("email")),
        creado_por=actor.id,
        **{campo: _opcional(datos.get(campo)) for campo in CAMPOS_OPCIONALES},
    )
    db.add(proveedor)
    confirmar(db)
    return proveedor


def actualizar_proveedor(db: Session, proveedor_id: int, cambios: dict[str, Any]) -> Proveedor:
    proveedor = obtener_proveedor(db, proveedor_id)
    with db.no_autoflush:  # las consultas de validación no deben escribir cambios a medias
        if "nombre" in cambios:
            proveedor.nombre = _nombre(cambios["nombre"])
        if "pais_id" in cambios and cambios["pais_id"] != proveedor.pais_id:
            proveedor.pais = _pais_utilizable(db, cambios["pais_id"])
        if "email" in cambios:
            proveedor.email = _email(cambios["email"])
        for campo in CAMPOS_OPCIONALES:
            if campo in cambios:
                setattr(proveedor, campo, _opcional(cambios[campo]))
        if cambios.get("activo") is True and not proveedor.pais.activo:
            raise ErrorNegocio(422, "PADRE_INACTIVO", "No se puede reactivar un proveedor de un país inactivo")
        if "activo" in cambios:
            proveedor.activo = cambios["activo"]
    confirmar(db)
    return proveedor

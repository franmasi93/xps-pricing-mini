"""M6 Clientes y contactos.

Alcance (§6.3.2): quien no tiene cotizacion.ver_todas (el comercial) solo ve sus clientes; un cliente
ajeno da 404 (no 403) para no revelar que existe, y la búsqueda nunca lo devuelve.
Asignación: el comercial queda asignado al crear; quien tiene cotizacion.ver_todas debe indicarlo.
"""
import re
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.core.rbac import permisos_de
from app.models import Cliente, ContactoCliente, Pais, Usuario
from app.schemas.clientes import ClienteSalida, ComercialRef, ContactoPrincipalRef, ContactoSalida
from app.schemas.geografia import PaisResumen
from app.schemas.usuarios import email_valido, normalizar_email
from app.services import auditoria
from app.services.tarifas import referencia_activa

PATRONES_IDENTIFICACION = {
    "RUC": re.compile(r"^[0-9]{10}001$"),
    "CEDULA": re.compile(r"^[0-9]{10}$"),
    "PASAPORTE": re.compile(r"^[A-Z0-9]{5,20}$"),
    "EXTRANJERO": re.compile(r"^[A-Z0-9]{3,30}$"),
}
FORMATOS_IDENTIFICACION = {
    "RUC": "13 dígitos terminados en 001",
    "CEDULA": "10 dígitos",
    "PASAPORTE": "de 5 a 20 letras o números",
    "EXTRANJERO": "de 3 a 30 letras o números",
}
CAMPOS_CLIENTE = (
    "razon_social",
    "tipo_id",
    "ruc_o_id",
    "pais_id",
    "direccion",
    "ciudad",
    "telefono",
    "notas",
    "comercial_asignado_id",
    "activo",
)
CAMPOS_OPCIONALES = ("direccion", "ciudad", "telefono", "notas")
CAMPOS_CONTACTO = ("nombre", "cargo", "email", "telefono", "principal", "activo")
BUSQUEDA_MINIMA = 2
BUSQUEDA_MAXIMA = 20


# ---------- Alcance y validaciones ----------


def ve_todos(usuario: Usuario) -> bool:
    return "cotizacion.ver_todas" in permisos_de(usuario)


def _con_alcance(consulta, usuario: Usuario):
    if ve_todos(usuario):
        return consulta
    return consulta.where(Cliente.comercial_asignado_id == auditoria.id_de(usuario))


def _no_encontrado() -> ErrorNegocio:
    return ErrorNegocio(404, "CLIENTE_NO_ENCONTRADO", "Cliente no encontrado")


def _texto(valor: str | None, campo: str, obligatorio: bool = False) -> str | None:
    if valor is None:
        if obligatorio:
            raise ErrorNegocio(422, "DATOS_INVALIDOS", f"{campo} es obligatorio")
        return None
    valor = " ".join(valor.split())
    if not valor:
        if obligatorio:
            raise ErrorNegocio(422, "DATOS_INVALIDOS", f"{campo} no puede estar vacío")
        return None
    return valor


def normalizar_identificacion(tipo_id: str, ruc_o_id: str) -> str:
    """D-F2-6: mayúsculas y sin espacios; formato según el tipo (sin dígito verificador en V1)."""
    valor = "".join(ruc_o_id.split()).upper()
    if not PATRONES_IDENTIFICACION[tipo_id].match(valor):
        raise ErrorNegocio(
            422, "IDENTIFICACION_INVALIDA", f"La identificación {tipo_id} debe tener {FORMATOS_IDENTIFICACION[tipo_id]}"
        )
    return valor


def _comercial_valido(db: Session, usuario_id: int) -> Usuario:
    """Destino de una asignación: usuario activo que pueda crear cotizaciones."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or "cotizacion.crear" not in permisos_de(usuario):
        raise ErrorNegocio(
            422, "COMERCIAL_INVALIDO", "El comercial asignado debe ser un usuario activo que pueda crear cotizaciones"
        )
    return usuario


def _validar_cliente(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    datos["razon_social"] = _texto(datos["razon_social"], "La razón social", obligatorio=True)
    datos["ruc_o_id"] = normalizar_identificacion(datos["tipo_id"], datos["ruc_o_id"])
    referencia_activa(db, Pais, datos["pais_id"], "el país", datos.get("activo", True))
    for campo in CAMPOS_OPCIONALES:
        datos[campo] = _texto(datos.get(campo), campo)
    return datos


# ---------- Presentación ----------


def _principal(cliente: Cliente) -> ContactoCliente | None:
    return next((c for c in cliente.contactos if c.principal and c.activo), None)


def presentar_cliente(cliente: Cliente) -> ClienteSalida:
    principal = _principal(cliente)
    return ClienteSalida(
        id=cliente.id,
        razon_social=cliente.razon_social,
        tipo_id=cliente.tipo_id,
        ruc_o_id=cliente.ruc_o_id,
        pais=PaisResumen.model_validate(cliente.pais),
        direccion=cliente.direccion,
        ciudad=cliente.ciudad,
        telefono=cliente.telefono,
        notas=cliente.notas,
        comercial_asignado=ComercialRef.model_validate(cliente.comercial_asignado),
        contacto_principal=ContactoPrincipalRef.model_validate(principal) if principal else None,
        activo=cliente.activo,
        creado_en=cliente.creado_en,
        actualizado_en=cliente.actualizado_en,
    )


def _consulta_clientes():
    return select(Cliente).options(
        selectinload(Cliente.pais), selectinload(Cliente.comercial_asignado), selectinload(Cliente.contactos)
    )


# ---------- Clientes ----------


def obtener_cliente(db: Session, usuario: Usuario, cliente_id: int) -> Cliente:
    cliente = db.scalars(_con_alcance(_consulta_clientes().where(Cliente.id == cliente_id), usuario)).one_or_none()
    if cliente is None:
        raise _no_encontrado()
    return cliente


def detalle_cliente(db: Session, usuario: Usuario, cliente_id: int) -> ClienteSalida:
    return presentar_cliente(obtener_cliente(db, usuario, cliente_id))


def listar_clientes(
    db: Session, usuario: Usuario, activo: bool | None = None, comercial: int | None = None
) -> list[ClienteSalida]:
    consulta = _con_alcance(_consulta_clientes(), usuario)
    if activo is not None:
        consulta = consulta.where(Cliente.activo.is_(activo))
    if comercial is not None:
        consulta = consulta.where(Cliente.comercial_asignado_id == comercial)
    return [presentar_cliente(c) for c in db.scalars(consulta.order_by(Cliente.razon_social, Cliente.id))]


def buscar_clientes(db: Session, usuario: Usuario, q: str) -> list[ClienteSalida]:
    texto = " ".join(q.split())
    if len(texto) < BUSQUEDA_MINIMA:
        raise ErrorNegocio(422, "BUSQUEDA_CORTA", f"Escriba al menos {BUSQUEDA_MINIMA} caracteres para buscar")
    patron = f"%{texto}%"
    identificacion = f"%{''.join(texto.split()).upper()}%"
    consulta = _con_alcance(_consulta_clientes(), usuario).where(
        or_(Cliente.razon_social.ilike(patron), Cliente.ruc_o_id.ilike(identificacion))
    )
    clientes = db.scalars(consulta.order_by(Cliente.razon_social, Cliente.id).limit(BUSQUEDA_MAXIMA))
    return [presentar_cliente(c) for c in clientes]


def crear_cliente(db: Session, actor: Usuario, datos: dict[str, Any]) -> ClienteSalida:
    """`datos` llega con exclude_unset: si trae comercial_asignado_id es porque se envió."""
    actor_id = auditoria.id_de(actor)
    if ve_todos(actor):
        if datos.get("comercial_asignado_id") is None:
            raise ErrorNegocio(
                422, "COMERCIAL_ASIGNADO_REQUERIDO", "Indique el comercial asignado al cliente"
            )
        comercial_id = _comercial_valido(db, datos["comercial_asignado_id"]).id
    else:
        if "comercial_asignado_id" in datos:
            raise ErrorNegocio(
                422, "ASIGNACION_NO_PERMITIDA", "El cliente queda asignado a usted; no puede elegir otro comercial"
            )
        comercial_id = actor_id
    datos = _validar_cliente(db, dict(datos) | {"activo": True, "comercial_asignado_id": comercial_id})
    cliente = Cliente(**{campo: datos.get(campo) for campo in CAMPOS_CLIENTE}, creado_por=actor_id)
    db.add(cliente)
    enviar(db)
    auditoria.registrar(db, actor, "cliente", cliente.id, "CREAR", despues=_foto(cliente, CAMPOS_CLIENTE))
    confirmar(db)
    return detalle_cliente(db, actor, cliente.id)


def _foto(objeto, campos) -> dict[str, Any]:
    return {campo: getattr(objeto, campo) for campo in campos}


def actualizar_cliente(db: Session, actor: Usuario, cliente_id: int, cambios: dict[str, Any]) -> ClienteSalida:
    cliente = obtener_cliente(db, actor, cliente_id)
    nota = None
    if "comercial_asignado_id" in cambios:
        if not ve_todos(actor):
            raise ErrorNegocio(
                422, "ASIGNACION_NO_PERMITIDA", "Solo el administrador puede reasignar clientes"
            )
        if cambios["comercial_asignado_id"] != cliente.comercial_asignado_id:
            _comercial_valido(db, cambios["comercial_asignado_id"])
            nota = f"reasignado del usuario #{cliente.comercial_asignado_id} al #{cambios['comercial_asignado_id']}"
    final = _validar_cliente(db, _foto(cliente, CAMPOS_CLIENTE) | cambios)
    antes = _foto(cliente, CAMPOS_CLIENTE)
    with db.no_autoflush:
        for campo in cambios:
            setattr(cliente, campo, final[campo])
        despues = _foto(cliente, CAMPOS_CLIENTE)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "cliente", cliente_id, accion, antes=antes, despues=despues, nota=nota)
    confirmar(db)
    db.expire_all()
    return detalle_cliente(db, actor, cliente_id)


# ---------- Contactos ----------


def _email(email: str | None) -> str | None:
    if email is None or not email.strip():
        return None
    email = normalizar_email(email)
    if not email_valido(email):
        raise ErrorNegocio(422, "EMAIL_INVALIDO", "El email del contacto no es válido")
    return email


def presentar_contacto(contacto: ContactoCliente, cliente: Cliente) -> ContactoSalida:
    return ContactoSalida(
        id=contacto.id,
        cliente_id=contacto.cliente_id,
        nombre=contacto.nombre,
        cargo=contacto.cargo,
        email=contacto.email,
        telefono=contacto.telefono,
        principal=contacto.principal,
        activo=contacto.activo,
        creado_en=contacto.creado_en,
        actualizado_en=contacto.actualizado_en,
        cliente_tiene_principal=_principal(cliente) is not None,
    )


def listar_contactos(db: Session, usuario: Usuario, cliente_id: int) -> list[ContactoSalida]:
    cliente = obtener_cliente(db, usuario, cliente_id)
    return [presentar_contacto(c, cliente) for c in cliente.contactos]


def _desmarcar_principal(db: Session, cliente_id: int, excepto_id: int | None) -> None:
    """Se desmarca primero (y se envía) para no chocar con el índice único parcial del principal."""
    consulta = update(ContactoCliente).where(ContactoCliente.cliente_id == cliente_id, ContactoCliente.principal.is_(True))
    if excepto_id is not None:
        consulta = consulta.where(ContactoCliente.id != excepto_id)
    db.execute(consulta.values(principal=False))


def _respuesta_contacto(db: Session, actor: Usuario, cliente_id: int, contacto_id: int) -> ContactoSalida:
    db.expire_all()
    cliente = obtener_cliente(db, actor, cliente_id)
    contacto = next(c for c in cliente.contactos if c.id == contacto_id)
    return presentar_contacto(contacto, cliente)


def crear_contacto(db: Session, actor: Usuario, cliente_id: int, datos: dict[str, Any]) -> ContactoSalida:
    actor_id = auditoria.id_de(actor)
    cliente = obtener_cliente(db, actor, cliente_id)
    nombre = _texto(datos.get("nombre"), "El nombre", obligatorio=True)
    email = _email(datos.get("email"))
    # El primer contacto activo queda como principal; marcar uno nuevo desmarca el anterior.
    principal = bool(datos.get("principal")) or _principal(cliente) is None
    if principal:
        _desmarcar_principal(db, cliente.id, None)
    contacto = ContactoCliente(
        cliente_id=cliente.id,
        nombre=nombre,
        cargo=_texto(datos.get("cargo"), "El cargo"),
        email=email,
        telefono=_texto(datos.get("telefono"), "El teléfono"),
        principal=principal,
        creado_por=actor_id,
    )
    db.add(contacto)
    enviar(db)
    auditoria.registrar(db, actor, "contacto_cliente", contacto.id, "CREAR", despues=_foto(contacto, CAMPOS_CONTACTO))
    confirmar(db)
    return _respuesta_contacto(db, actor, cliente_id, contacto.id)


def actualizar_contacto(
    db: Session, actor: Usuario, cliente_id: int, contacto_id: int, cambios: dict[str, Any]
) -> ContactoSalida:
    cliente = obtener_cliente(db, actor, cliente_id)
    contacto = next((c for c in cliente.contactos if c.id == contacto_id), None)
    if contacto is None:
        raise ErrorNegocio(404, "CONTACTO_NO_ENCONTRADO", "Contacto no encontrado")

    activo = cambios.get("activo", contacto.activo)
    principal = cambios.get("principal", contacto.principal)
    if principal and not activo:
        if cambios.get("principal") is True:
            raise ErrorNegocio(422, "CONTACTO_INACTIVO", "Un contacto inactivo no puede ser el principal")
        principal = False  # desactivar al principal deja al cliente sin principal
    if activo and not contacto.activo and _principal(cliente) is None:
        principal = True  # al reactivarse, si el cliente no tiene principal, lo vuelve a ser

    valores = {
        "nombre": _texto(cambios["nombre"], "El nombre", obligatorio=True) if "nombre" in cambios else contacto.nombre,
        "cargo": _texto(cambios["cargo"], "El cargo") if "cargo" in cambios else contacto.cargo,
        "email": _email(cambios["email"]) if "email" in cambios else contacto.email,
        "telefono": _texto(cambios["telefono"], "El teléfono") if "telefono" in cambios else contacto.telefono,
        "principal": principal,
        "activo": activo,
    }
    antes = _foto(contacto, CAMPOS_CONTACTO)
    if principal and not contacto.principal:
        _desmarcar_principal(db, cliente.id, contacto.id)
    with db.no_autoflush:
        for campo, valor in valores.items():
            setattr(contacto, campo, valor)
        despues = _foto(contacto, CAMPOS_CONTACTO)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "contacto_cliente", contacto_id, accion, antes=antes, despues=despues)
    confirmar(db)
    return _respuesta_contacto(db, actor, cliente_id, contacto_id)

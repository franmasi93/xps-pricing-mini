"""Administración de usuarios: alta, edición, restablecimiento y admin inicial."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar
from app.core.security import hashear_password, validar_politica_password
from app.models import Rol, Usuario
from app.schemas.usuarios import email_valido, normalizar_email

ROL_ADMIN = "admin"


def _rol_por_codigo(db: Session, codigo: str) -> Rol:
    rol = db.scalars(select(Rol).where(Rol.codigo == codigo)).one_or_none()
    if rol is None:
        raise ErrorNegocio(422, "ROL_INEXISTENTE", f"El rol '{codigo}' no existe")
    if not rol.activo:  # E2: un rol desactivado no se asigna
        raise ErrorNegocio(422, "ROL_INACTIVO", f"El rol '{rol.nombre}' está desactivado")
    return rol


def _admins_activos_bloqueados(db: Session) -> list[int]:
    """IDs de los admins activos, con SELECT ... FOR UPDATE sobre sus filas."""
    consulta = (
        select(Usuario.id)
        .join(Rol, Usuario.rol_id == Rol.id)
        .where(Usuario.activo.is_(True), Rol.codigo == ROL_ADMIN)
        .with_for_update(of=Usuario)
    )
    return list(db.scalars(consulta))


def listar_usuarios(db: Session, activo: bool | None = None, rol_codigo: str | None = None) -> list[Usuario]:
    consulta = select(Usuario).join(Rol, Usuario.rol_id == Rol.id).options(selectinload(Usuario.rol))
    if activo is not None:
        consulta = consulta.where(Usuario.activo.is_(activo))
    if rol_codigo is not None:
        consulta = consulta.where(Rol.codigo == rol_codigo)
    return list(db.scalars(consulta.order_by(Usuario.nombre, Usuario.id)))


def obtener_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise ErrorNegocio(404, "USUARIO_NO_ENCONTRADO", "Usuario no encontrado")
    return usuario


def crear_usuario(
    db: Session, actor: Usuario, email: str, nombre: str, rol_codigo: str, password_temporal: str
) -> Usuario:
    validar_politica_password(password_temporal)
    usuario = Usuario(
        email=normalizar_email(email),
        nombre=nombre,
        hash_password=hashear_password(password_temporal),
        rol=_rol_por_codigo(db, rol_codigo),
        forzar_cambio_password=True,
        creado_por=actor.id,
    )
    db.add(usuario)
    confirmar(db)
    return usuario


def actualizar_usuario(db: Session, actor: Usuario, usuario_id: int, cambios: dict[str, Any]) -> Usuario:
    """PATCH parcial: solo se aplican las claves presentes en `cambios`."""
    usuario = obtener_usuario(db, usuario_id)
    nuevo_rol = _rol_por_codigo(db, cambios["rol_codigo"]) if "rol_codigo" in cambios else None

    desactiva = cambios.get("activo") is False and usuario.activo
    cambia_rol = nuevo_rol is not None and nuevo_rol.id != usuario.rol_id
    deja_de_ser_admin = (
        usuario.activo
        and usuario.rol.codigo == ROL_ADMIN
        and (desactiva or (cambia_rol and nuevo_rol.codigo != ROL_ADMIN))
    )
    if deja_de_ser_admin:
        if usuario.id == actor.id:
            raise ErrorNegocio(
                409,
                "OPERACION_SOBRE_SI_MISMO",
                "No puede desactivarse ni quitarse el rol de administrador a sí mismo",
            )
        if len(_admins_activos_bloqueados(db)) <= 1:
            raise ErrorNegocio(409, "ULTIMO_ADMIN", "Debe quedar al menos un administrador activo")

    if "nombre" in cambios:
        usuario.nombre = cambios["nombre"]
    if "activo" in cambios:
        usuario.activo = cambios["activo"]
    if cambia_rol:
        usuario.rol = nuevo_rol
    if desactiva or cambia_rol:
        usuario.token_version += 1
    confirmar(db)
    return usuario


def restablecer_password(db: Session, usuario_id: int, password_temporal: str) -> Usuario:
    usuario = obtener_usuario(db, usuario_id)
    validar_politica_password(password_temporal)
    usuario.hash_password = hashear_password(password_temporal)
    usuario.forzar_cambio_password = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.token_version += 1
    confirmar(db)
    return usuario


def restablecer_password_admin(db: Session, email: str, password: str) -> Usuario:
    """Usado por scripts/restablecer_admin.py: un admin activo recupera el acceso desde la consola.

    La contraseña la elige la misma persona, así que no se fuerza el cambio. Se reinicia el
    bloqueo y se invalidan los tokens anteriores.
    """
    usuario = db.scalars(
        select(Usuario).where(Usuario.email == normalizar_email(email)).with_for_update()
    ).one_or_none()
    if usuario is None or usuario.rol.codigo != ROL_ADMIN:
        raise ErrorNegocio(404, "ADMIN_NO_ENCONTRADO", "No existe un administrador con ese email")
    if not usuario.activo:
        raise ErrorNegocio(409, "ADMIN_INACTIVO", "Ese administrador está desactivado")
    validar_politica_password(password)
    usuario.hash_password = hashear_password(password)
    usuario.forzar_cambio_password = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.token_version += 1
    confirmar(db)
    return usuario


def crear_admin_inicial(db: Session, email: str, nombre: str, password: str) -> Usuario:
    """Usado por scripts/crear_admin.py. Aborta si ya existe un admin activo."""
    if _admins_activos_bloqueados(db):
        raise ErrorNegocio(
            409,
            "ADMIN_YA_EXISTE",
            "Ya existe un administrador activo; cree los demás usuarios desde la pantalla de usuarios",
        )
    email = normalizar_email(email)
    if not email_valido(email):
        raise ErrorNegocio(422, "EMAIL_INVALIDO", "El email no es válido")
    nombre = nombre.strip()
    if not nombre or len(nombre) > 120:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre es obligatorio (máximo 120 caracteres)")
    validar_politica_password(password)
    usuario = Usuario(
        email=email,
        nombre=nombre,
        hash_password=hashear_password(password),
        rol=_rol_por_codigo(db, ROL_ADMIN),
        forzar_cambio_password=False,
    )
    db.add(usuario)
    confirmar(db)
    return usuario

"""E2 Catálogos de administración: roles y su matriz de permisos, motivos de rechazo, tipos de identificación y los
textos fijos del PDF. Todo con auditoría.

Roles (usuario.admin):
- Se crean y se editan nombre, descripción, permisos y estado. El código no cambia (lo usan los usuarios y los tokens).
- El rol protegido (admin) no se desactiva ni pierde usuario.admin: siempre queda quien administre.
- No se desactiva un rol con usuarios activos; un rol inactivo no se asigna (services/usuarios).
- Al cambiar los permisos de un rol, o al desactivarlo, se sube token_version de sus usuarios: deben volver a entrar y
  su menú se arma con los permisos nuevos. Los permisos ya se leen de la base en cada pedido (core/rbac).
- Los permisos en sí (sus códigos) no se crean por pantalla: cada uno lo exige el código del sistema.

Motivos de rechazo y tipos de identificación (config.editar): el código no cambia una vez creado (lo guardan las
cotizaciones y los clientes); se editan nombre, orden, estado y su regla. Desactivar uno lo saca de las listas nuevas sin
tocar lo ya guardado.

Textos del PDF (config.editar): una fila; al emitir se copian a la foto, así un PDF emitido nunca cambia.
"""
import re
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import ConfigTextosPdf, MotivoRechazo, Permiso, Rol, TipoIdentificacion, Usuario
from app.models.administracion import CLAVES_TEXTOS_PDF
from app.services import auditoria

PERMISO_ADMIN = "usuario.admin"
PATRON_ROL = re.compile(r"^[a-z][a-z0-9_]{1,29}$")
PATRON_MOTIVO = re.compile(r"^[A-Z][A-Z0-9_]{1,29}$")
PATRON_TIPO_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
MOTIVO_SISTEMA = "OTRO"  # el CHECK ck_cotizacion_detalle_si_otro de F3 lo usa: siempre exige detalle
CAMPOS_ROL = ("codigo", "nombre", "descripcion", "activo")
CAMPOS_MOTIVO = ("codigo", "nombre", "exige_detalle", "orden", "activo")
CAMPOS_TIPO_ID = ("codigo", "nombre", "regex", "formato", "orden", "activo")
TEXTO_PDF_MAXIMO = 1000


def _texto(valor: Any, campo: str, maximo: int, *, obligatorio: bool = True) -> str | None:
    valor = " ".join(str(valor or "").split())
    if not valor:
        if obligatorio:
            raise ErrorNegocio(422, "DATOS_INVALIDOS", f"{campo} no puede estar vacío")
        return None
    if len(valor) > maximo:
        raise ErrorNegocio(422, "DATOS_INVALIDOS", f"{campo} admite como máximo {maximo} caracteres")
    return valor


def _foto(objeto: Any, campos: tuple[str, ...]) -> dict[str, Any]:
    return {campo: getattr(objeto, campo) for campo in campos}


def _auditar_cambio(db: Session, actor: Usuario, entidad: str, entidad_id: Any, antes: dict, despues: dict) -> None:
    if antes != despues:
        accion = "DESACTIVAR" if antes.get("activo") and not despues.get("activo", True) else "EDITAR"
        auditoria.registrar(db, actor, entidad, entidad_id, accion, antes=antes, despues=despues)


# ---------- Roles y permisos ----------


def listar_permisos(db: Session) -> list[Permiso]:
    return list(db.scalars(select(Permiso).order_by(Permiso.codigo)))


def usuarios_por_rol(db: Session) -> dict[int, int]:
    filas = db.execute(select(Usuario.rol_id, func.count()).where(Usuario.activo.is_(True)).group_by(Usuario.rol_id))
    return {rol_id: total for rol_id, total in filas}


def listar_roles(db: Session, activo: bool | None = None) -> list[Rol]:
    consulta = select(Rol).options(selectinload(Rol.permisos))
    if activo is not None:
        consulta = consulta.where(Rol.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Rol.id)))


def obtener_rol(db: Session, rol_id: int) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise ErrorNegocio(404, "ROL_NO_ENCONTRADO", "Rol no encontrado")
    return rol


def _permisos(db: Session, codigos: list[str]) -> list[Permiso]:
    pedidos = sorted({codigo.strip() for codigo in codigos})
    encontrados = list(db.scalars(select(Permiso).where(Permiso.codigo.in_(pedidos))))
    faltan = set(pedidos) - {permiso.codigo for permiso in encontrados}
    if faltan:
        raise ErrorNegocio(422, "PERMISO_INEXISTENTE", f"No existen los permisos: {', '.join(sorted(faltan))}")
    return encontrados


def _foto_rol(rol: Rol) -> dict[str, Any]:
    return _foto(rol, CAMPOS_ROL) | {"permisos": sorted(permiso.codigo for permiso in rol.permisos)}


def _invalidar_sesiones(db: Session, rol: Rol, actor: Usuario) -> int:
    """Sube token_version de los usuarios del rol (menos quien hace el cambio, que recarga su menú): vuelven a entrar
    con los permisos nuevos."""
    resultado = db.execute(
        update(Usuario).where(Usuario.rol_id == rol.id, Usuario.id != actor.id)
        .values(token_version=Usuario.token_version + 1).execution_options(synchronize_session="fetch")
    )
    return resultado.rowcount or 0


def crear_rol(db: Session, actor: Usuario, datos: dict[str, Any]) -> Rol:
    codigo = "".join((datos.get("codigo") or "").split()).lower()
    if not PATRON_ROL.match(codigo):
        raise ErrorNegocio(
            422, "CODIGO_INVALIDO", "El código del rol es de 2 a 30 letras minúsculas, números o _, y empieza con una letra"
        )
    if db.scalars(select(Rol).where(Rol.codigo == codigo)).one_or_none() is not None:
        raise ErrorNegocio(409, "ROL_DUPLICADO", "Ya existe un rol con ese código")
    rol = Rol(
        codigo=codigo,
        nombre=_texto(datos.get("nombre"), "El nombre", 80),
        descripcion=_texto(datos.get("descripcion"), "La descripción", 300, obligatorio=False),
        permisos=_permisos(db, datos.get("permisos") or []),
        creado_por=auditoria.id_de(actor),
    )
    db.add(rol)
    enviar(db)
    auditoria.registrar(db, actor, "rol", rol.codigo, "CREAR", despues=_foto_rol(rol))
    confirmar(db)
    return rol


def actualizar_rol(db: Session, actor: Usuario, rol_id: int, cambios: dict[str, Any]) -> Rol:
    rol = db.scalars(select(Rol).where(Rol.id == rol_id).with_for_update()).one_or_none()
    if rol is None:
        raise ErrorNegocio(404, "ROL_NO_ENCONTRADO", "Rol no encontrado")
    antes = _foto_rol(rol)
    if "codigo" in cambios and cambios["codigo"] != rol.codigo:
        raise ErrorNegocio(422, "CODIGO_NO_EDITABLE", "El código del rol no cambia; cree otro rol si lo necesita")
    if "nombre" in cambios:
        rol.nombre = _texto(cambios["nombre"], "El nombre", 80)
    if "descripcion" in cambios:
        rol.descripcion = _texto(cambios["descripcion"], "La descripción", 300, obligatorio=False)
    if "permisos" in cambios:
        nuevos = _permisos(db, cambios["permisos"])
        if rol.protegido and PERMISO_ADMIN not in {permiso.codigo for permiso in nuevos}:
            raise ErrorNegocio(
                409, "ROL_PROTEGIDO", f"El rol {rol.nombre} no puede perder {PERMISO_ADMIN}: siempre debe quedar quien administre"
            )
        rol.permisos = nuevos
    if cambios.get("activo") is False and rol.activo:
        if rol.protegido:
            raise ErrorNegocio(409, "ROL_PROTEGIDO", f"El rol {rol.nombre} no se puede desactivar")
        activos = usuarios_por_rol(db).get(rol.id, 0)
        if activos:
            raise ErrorNegocio(
                409, "ROL_CON_USUARIOS", f"El rol tiene {activos} usuario(s) activo(s): páselos a otro rol antes de desactivarlo"
            )
    if "activo" in cambios:
        rol.activo = bool(cambios["activo"])
    despues = _foto_rol(rol)
    if despues != antes:
        if despues["permisos"] != antes["permisos"] or (antes["activo"] and not despues["activo"]):
            _invalidar_sesiones(db, rol, actor)
        _auditar_cambio(db, actor, "rol", rol.codigo, antes, despues)
    confirmar(db)
    return rol


# ---------- Motivos de rechazo ----------


def listar_motivos(db: Session, activo: bool | None = None) -> list[MotivoRechazo]:
    consulta = select(MotivoRechazo)
    if activo is not None:
        consulta = consulta.where(MotivoRechazo.activo.is_(activo))
    return list(db.scalars(consulta.order_by(MotivoRechazo.orden, MotivoRechazo.nombre)))


def motivo_por_codigo(db: Session, codigo: str) -> MotivoRechazo | None:
    return db.scalars(select(MotivoRechazo).where(MotivoRechazo.codigo == codigo)).one_or_none()


def motivo_utilizable(db: Session, codigo: str) -> MotivoRechazo:
    motivo = motivo_por_codigo(db, codigo)
    if motivo is None or not motivo.activo:
        raise ErrorNegocio(422, "MOTIVO_RECHAZO_INVALIDO", "El motivo de rechazo no existe o está desactivado")
    return motivo


def _validar_motivo(datos: dict[str, Any], codigo: str) -> dict[str, Any]:
    if "nombre" in datos:
        datos["nombre"] = _texto(datos["nombre"], "El nombre", 80)
    if "orden" in datos:
        datos["orden"] = int(datos["orden"])
    if codigo == MOTIVO_SISTEMA and datos.get("exige_detalle") is False:
        raise ErrorNegocio(422, "MOTIVO_PROTEGIDO", "El motivo OTRO siempre exige el detalle")
    return datos


def crear_motivo(db: Session, actor: Usuario, datos: dict[str, Any]) -> MotivoRechazo:
    codigo = "".join((datos.get("codigo") or "").split()).upper()
    if not PATRON_MOTIVO.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código es de 2 a 30 letras, números o _, y empieza con una letra")
    if motivo_por_codigo(db, codigo) is not None:
        raise ErrorNegocio(409, "MOTIVO_DUPLICADO", "Ya existe un motivo con ese código")
    datos = _validar_motivo(dict(datos), codigo)
    motivo = MotivoRechazo(codigo=codigo, nombre=datos["nombre"], exige_detalle=bool(datos.get("exige_detalle")),
                           orden=datos.get("orden", 0), creado_por=auditoria.id_de(actor))
    db.add(motivo)
    enviar(db)
    auditoria.registrar(db, actor, "motivo_rechazo", motivo.codigo, "CREAR", despues=_foto(motivo, CAMPOS_MOTIVO))
    confirmar(db)
    return motivo


def actualizar_motivo(db: Session, actor: Usuario, motivo_id: int, cambios: dict[str, Any]) -> MotivoRechazo:
    motivo = db.get(MotivoRechazo, motivo_id)
    if motivo is None:
        raise ErrorNegocio(404, "MOTIVO_NO_ENCONTRADO", "Motivo de rechazo no encontrado")
    if "codigo" in cambios and cambios["codigo"] != motivo.codigo:
        raise ErrorNegocio(422, "CODIGO_NO_EDITABLE", "El código no cambia: lo guardan las cotizaciones")
    if motivo.codigo == MOTIVO_SISTEMA and cambios.get("activo") is False:
        raise ErrorNegocio(409, "MOTIVO_PROTEGIDO", "El motivo OTRO no se desactiva")
    cambios = _validar_motivo(dict(cambios), motivo.codigo)
    antes = _foto(motivo, CAMPOS_MOTIVO)
    for campo in ("nombre", "exige_detalle", "orden", "activo"):
        if campo in cambios:
            setattr(motivo, campo, cambios[campo])
    _auditar_cambio(db, actor, "motivo_rechazo", motivo.codigo, antes, _foto(motivo, CAMPOS_MOTIVO))
    confirmar(db)
    return motivo


# ---------- Tipos de identificación ----------


def listar_tipos_identificacion(db: Session, activo: bool | None = None) -> list[TipoIdentificacion]:
    consulta = select(TipoIdentificacion)
    if activo is not None:
        consulta = consulta.where(TipoIdentificacion.activo.is_(activo))
    return list(db.scalars(consulta.order_by(TipoIdentificacion.orden, TipoIdentificacion.nombre)))


def tipo_identificacion(db: Session, codigo: str) -> TipoIdentificacion | None:
    return db.scalars(select(TipoIdentificacion).where(TipoIdentificacion.codigo == codigo)).one_or_none()


def _validar_tipo(datos: dict[str, Any]) -> dict[str, Any]:
    if "nombre" in datos:
        datos["nombre"] = _texto(datos["nombre"], "El nombre", 60)
    if "formato" in datos:
        datos["formato"] = _texto(datos["formato"], "El formato", 120)
    if "regex" in datos:
        datos["regex"] = (datos["regex"] or "").strip()
        if not datos["regex"] or len(datos["regex"]) > 300:
            raise ErrorNegocio(422, "REGEX_INVALIDA", "La regla es obligatoria y admite como máximo 300 caracteres")
        try:
            re.compile(datos["regex"])
        except re.error as error:
            raise ErrorNegocio(422, "REGEX_INVALIDA", f"La expresión regular no es válida: {error}") from None
    if "orden" in datos:
        datos["orden"] = int(datos["orden"])
    return datos


def crear_tipo_identificacion(db: Session, actor: Usuario, datos: dict[str, Any]) -> TipoIdentificacion:
    codigo = "".join((datos.get("codigo") or "").split()).upper()
    if not PATRON_TIPO_ID.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código es de 2 a 10 letras, números o _, y empieza con una letra")
    if tipo_identificacion(db, codigo) is not None:
        raise ErrorNegocio(409, "TIPO_IDENTIFICACION_DUPLICADO", "Ya existe un tipo de identificación con ese código")
    datos = _validar_tipo(dict(datos))
    tipo = TipoIdentificacion(codigo=codigo, nombre=datos["nombre"], regex=datos["regex"], formato=datos["formato"],
                              orden=datos.get("orden", 0), creado_por=auditoria.id_de(actor))
    db.add(tipo)
    enviar(db)
    auditoria.registrar(db, actor, "tipo_identificacion", tipo.codigo, "CREAR", despues=_foto(tipo, CAMPOS_TIPO_ID))
    confirmar(db)
    return tipo


def actualizar_tipo_identificacion(db: Session, actor: Usuario, tipo_id: int, cambios: dict[str, Any]) -> TipoIdentificacion:
    tipo = db.get(TipoIdentificacion, tipo_id)
    if tipo is None:
        raise ErrorNegocio(404, "TIPO_IDENTIFICACION_NO_ENCONTRADO", "Tipo de identificación no encontrado")
    if "codigo" in cambios and cambios["codigo"] != tipo.codigo:
        raise ErrorNegocio(422, "CODIGO_NO_EDITABLE", "El código no cambia: lo guardan los clientes")
    cambios = _validar_tipo(dict(cambios))
    antes = _foto(tipo, CAMPOS_TIPO_ID)
    for campo in ("nombre", "regex", "formato", "orden", "activo"):
        if campo in cambios:
            setattr(tipo, campo, cambios[campo])
    _auditar_cambio(db, actor, "tipo_identificacion", tipo.codigo, antes, _foto(tipo, CAMPOS_TIPO_ID))
    confirmar(db)
    return tipo


# ---------- Textos del PDF ----------


def textos_pdf(db: Session) -> dict[str, str]:
    """Los textos vigentes (se copian a la foto al emitir)."""
    fila = db.get(ConfigTextosPdf, 1)
    return {clave: getattr(fila, clave) for clave in CLAVES_TEXTOS_PDF}


def actualizar_textos_pdf(db: Session, actor: Usuario, cambios: dict[str, Any]) -> dict[str, str]:
    fila = db.scalars(select(ConfigTextosPdf).where(ConfigTextosPdf.id == 1).with_for_update()).one()
    antes = textos_pdf(db)
    for clave, valor in cambios.items():
        if clave not in CLAVES_TEXTOS_PDF:
            continue
        texto = (valor or "").strip()
        if not texto or len(texto) > TEXTO_PDF_MAXIMO:
            raise ErrorNegocio(422, "CONFIG_VALOR_INVALIDO", f"Cada texto debe tener entre 1 y {TEXTO_PDF_MAXIMO} caracteres")
        setattr(fila, clave, texto)
    despues = {clave: getattr(fila, clave) for clave in CLAVES_TEXTOS_PDF}
    if despues != antes:
        fila.actualizado_por = auditoria.id_de(actor)
        auditoria.registrar(db, actor, "config_textos_pdf", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return despues

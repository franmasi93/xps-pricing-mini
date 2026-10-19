"""E1 Boletines: listas de envío, bajas de correo y tokens de baja.

- Lista MANUAL: contactos elegidos uno a uno (o importados desde un CSV por su email).
- Lista FILTRO: contactos activos con email, de clientes activos, que cumplen TODOS los filtros dados:
  países y ciudades del cliente, y servicios, tipos de equipo, orígenes y destinos de sus cotizaciones.
  Sin filtros = todos los clientes activos (la lista "Todos los clientes activos").
- Las bajas aplican a TODAS las campañas y a los avisos comerciales de E3. Revertir no borra: marca revertida.
- Token de baja: aleatorio (secrets) + firma HMAC-SHA256 con JWT_SECRET, comparado en tiempo constante.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import (
    BajaCorreo,
    Cliente,
    ContactoCliente,
    Cotizacion,
    CotizacionContenedor,
    ListaEnvio,
    Pais,
    Usuario,
    lista_envio_miembro,
)
from app.services import auditoria

PATRON_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
CLAVES_FILTRO = ("servicios", "tipos_equipo", "origenes", "destinos", "paises", "ciudades")
MAXIMO_MUESTRA = 50


# ---------- Tokens de baja ----------


def _firma(aleatorio: str) -> str:
    clave = get_settings().JWT_SECRET.get_secret_value().encode()
    return hmac.new(clave, f"baja:{aleatorio}".encode(), hashlib.sha256).hexdigest()[:16]


def nuevo_token() -> str:
    aleatorio = secrets.token_urlsafe(12)
    return f"{aleatorio}.{_firma(aleatorio)}"


def token_valido(token: str) -> bool:
    if not token or token.count(".") != 1 or len(token) > 80:
        return False
    aleatorio, firma = token.split(".")
    return hmac.compare_digest(firma, _firma(aleatorio))


# ---------- Bajas ----------


def normalizar_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not PATRON_EMAIL.match(email):
        raise ErrorNegocio(422, "EMAIL_INVALIDO", "Dirección de correo no válida")
    return email


def bajas_activas(db: Session, emails: list[str] | None = None) -> set[str]:
    consulta = select(BajaCorreo.email).where(BajaCorreo.revertida.is_(False))
    if emails is not None:
        consulta = consulta.where(BajaCorreo.email.in_(emails))
    return set(db.scalars(consulta))


def esta_de_baja(db: Session, email: str) -> bool:
    return bool(bajas_activas(db, [email.strip().lower()]))


def registrar_baja(db: Session, email: str, motivo: str, actor: Usuario | None = None,
                   campana_id: int | None = None) -> BajaCorreo:
    """Idempotente: si ya existe, la reactiva (si estaba revertida) y conserva la primera fecha si seguía activa."""
    email = normalizar_email(email)
    baja = db.scalars(select(BajaCorreo).where(BajaCorreo.email == email).with_for_update()).one_or_none()
    if baja is None:
        baja = BajaCorreo(email=email, motivo=motivo, campana_id=campana_id,
                          registrado_por=auditoria.id_de(actor) if actor else None)
        db.add(baja)
    elif baja.revertida:
        baja.revertida, baja.revertida_en, baja.motivo = False, None, motivo
        baja.fecha = datetime.now(timezone.utc)
        baja.campana_id = campana_id or baja.campana_id
    enviar(db)
    auditoria.registrar(db, actor, "baja_correo", baja.id, "CREAR", despues={"email": email, "motivo": motivo},
                        nota=f"BAJA {motivo}")
    return baja


def revertir_baja(db: Session, actor: Usuario | None, baja_id: int) -> BajaCorreo:
    baja = db.get(BajaCorreo, baja_id)
    if baja is None:
        raise ErrorNegocio(404, "BAJA_NO_ENCONTRADA", "Baja no encontrada")
    if not baja.revertida:
        baja.revertida, baja.revertida_en = True, datetime.now(timezone.utc)
        auditoria.registrar(db, actor, "baja_correo", baja.id, "DESACTIVAR", antes={"revertida": False},
                            despues={"revertida": True}, nota="BAJA REVERTIDA")
    confirmar(db)
    return baja


def listar_bajas(db: Session, q: str | None = None, revertida: bool | None = None) -> list[BajaCorreo]:
    consulta = select(BajaCorreo)
    if q:
        consulta = consulta.where(BajaCorreo.email.ilike(f"%{q.strip().lower()}%"))
    if revertida is not None:
        consulta = consulta.where(BajaCorreo.revertida.is_(revertida))
    return list(db.scalars(consulta.order_by(BajaCorreo.fecha.desc()).limit(500)))


# ---------- Listas ----------


def _normalizar_filtros(filtros: dict[str, Any] | None) -> dict[str, list]:
    filtros = filtros or {}
    desconocidas = set(filtros) - set(CLAVES_FILTRO)
    if desconocidas:
        raise ErrorNegocio(422, "FILTRO_INVALIDO", f"Filtros desconocidos: {', '.join(sorted(desconocidas))}")
    salida: dict[str, list] = {}
    for clave in CLAVES_FILTRO:
        valores = [v for v in (filtros.get(clave) or []) if v not in (None, "")]
        if clave in ("tipos_equipo", "origenes", "destinos", "paises"):
            valores = sorted({int(v) for v in valores})
        else:
            valores = sorted({str(v).strip() for v in valores})
        if valores:
            salida[clave] = valores
    return salida


def consulta_por_filtro(filtros: dict[str, list]):
    """Contactos activos con email, de clientes activos, que cumplen todos los filtros."""
    consulta = (
        select(ContactoCliente)
        .join(Cliente, Cliente.id == ContactoCliente.cliente_id)
        .where(ContactoCliente.activo.is_(True), Cliente.activo.is_(True), ContactoCliente.email.is_not(None),
               ContactoCliente.email != "")
    )
    if filtros.get("paises"):
        consulta = consulta.where(Cliente.pais_id.in_(filtros["paises"]))
    if filtros.get("ciudades"):
        consulta = consulta.where(func.lower(Cliente.ciudad).in_([c.lower() for c in filtros["ciudades"]]))
    condiciones = []
    if filtros.get("servicios"):
        condiciones.append(Cotizacion.modo.in_(filtros["servicios"]))
    if filtros.get("origenes"):
        condiciones.append(Cotizacion.origen_puerto_id.in_(filtros["origenes"]))
    if filtros.get("destinos"):
        condiciones.append(Cotizacion.destino_puerto_id.in_(filtros["destinos"]))
    if filtros.get("tipos_equipo"):
        condiciones.append(exists().where(CotizacionContenedor.cotizacion_id == Cotizacion.id,
                                          CotizacionContenedor.tipo_equipo_id.in_(filtros["tipos_equipo"])))
    if condiciones:
        consulta = consulta.where(exists().where(Cotizacion.cliente_id == Cliente.id, Cotizacion.activo.is_(True),
                                                 *condiciones))
    return consulta


def contactos_de(db: Session, lista: ListaEnvio) -> list[ContactoCliente]:
    """Los contactos que hoy recibirían la lista (activos, con email y de clientes activos)."""
    if lista.tipo == "FILTRO":
        return list(db.scalars(consulta_por_filtro(lista.filtros or {}).order_by(ContactoCliente.id)))
    activos = set(db.scalars(select(Cliente.id).where(Cliente.activo.is_(True))))
    return [c for c in lista.miembros if c.activo and c.email and c.cliente_id in activos]


def _validar_lista(db: Session, datos: dict[str, Any], excluir_id: int | None) -> dict[str, Any]:
    datos["nombre"] = " ".join((datos.get("nombre") or "").split())
    if not datos["nombre"]:
        raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
    repetida = db.scalar(select(ListaEnvio.id).where(func.lower(ListaEnvio.nombre) == datos["nombre"].lower(),
                                                     ListaEnvio.id != (excluir_id or 0)))
    if repetida:
        raise ErrorNegocio(409, "LISTA_DUPLICADA", "Ya existe una lista con ese nombre")
    if datos.get("tipo") not in ("MANUAL", "FILTRO"):
        raise ErrorNegocio(422, "LISTA_INVALIDA", "El tipo de lista es MANUAL o FILTRO")
    datos["filtros"] = _normalizar_filtros(datos.get("filtros")) if datos["tipo"] == "FILTRO" else {}
    datos["descripcion"] = (datos.get("descripcion") or "").strip() or None
    return datos


def listar_listas(db: Session, activo: bool | None = None) -> list[ListaEnvio]:
    consulta = select(ListaEnvio)
    if activo is not None:
        consulta = consulta.where(ListaEnvio.activo.is_(activo))
    return list(db.scalars(consulta.order_by(ListaEnvio.nombre)))


def obtener_lista(db: Session, lista_id: int) -> ListaEnvio:
    lista = db.get(ListaEnvio, lista_id)
    if lista is None:
        raise ErrorNegocio(404, "LISTA_NO_ENCONTRADA", "Lista no encontrada")
    return lista


def crear_lista(db: Session, actor: Usuario, datos: dict[str, Any]) -> ListaEnvio:
    datos = _validar_lista(db, dict(datos), None)
    lista = ListaEnvio(nombre=datos["nombre"], descripcion=datos["descripcion"], tipo=datos["tipo"],
                       filtros=datos["filtros"], creado_por=auditoria.id_de(actor))
    db.add(lista)
    enviar(db)
    if datos["tipo"] == "MANUAL" and datos.get("contactos"):
        _poner_miembros(db, lista, datos["contactos"])
    auditoria.registrar(db, actor, "lista_envio", lista.id, "CREAR", despues=_foto_lista(lista))
    confirmar(db)
    return lista


def _foto_lista(lista: ListaEnvio) -> dict[str, Any]:
    return {"nombre": lista.nombre, "tipo": lista.tipo, "filtros": lista.filtros, "activo": lista.activo,
            "miembros": sorted(c.id for c in lista.miembros) if lista.tipo == "MANUAL" else None}


def _poner_miembros(db: Session, lista: ListaEnvio, ids: list[int]) -> None:
    ids = sorted({int(i) for i in ids})
    contactos = list(db.scalars(select(ContactoCliente).where(ContactoCliente.id.in_(ids)))) if ids else []
    if len(contactos) != len(ids):
        raise ErrorNegocio(422, "REFERENCIA_INEXISTENTE", "Algún contacto indicado no existe")
    lista.miembros = contactos


def actualizar_lista(db: Session, actor: Usuario, lista_id: int, cambios: dict[str, Any]) -> ListaEnvio:
    lista = obtener_lista(db, lista_id)
    antes = _foto_lista(lista)
    final = _validar_lista(db, {"nombre": lista.nombre, "descripcion": lista.descripcion, "tipo": lista.tipo,
                                "filtros": lista.filtros} | cambios, lista.id)
    with db.no_autoflush:
        lista.nombre, lista.descripcion, lista.tipo, lista.filtros = (final["nombre"], final["descripcion"],
                                                                      final["tipo"], final["filtros"])
        if "contactos" in cambios and lista.tipo == "MANUAL":
            _poner_miembros(db, lista, cambios["contactos"] or [])
        if lista.tipo == "FILTRO":
            lista.miembros = []
        if "activo" in cambios:
            lista.activo = bool(cambios["activo"])
        despues = _foto_lista(lista)
        if despues != antes:
            accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
            auditoria.registrar(db, actor, "lista_envio", lista.id, accion, antes=antes, despues=despues)
    confirmar(db)
    return lista


def importar_emails(db: Session, actor: Usuario, lista_id: int, emails: list[str]) -> dict[str, Any]:
    """Agrega a una lista MANUAL los contactos activos cuyo email coincide (CSV leído en el navegador)."""
    lista = obtener_lista(db, lista_id)
    if lista.tipo != "MANUAL":
        raise ErrorNegocio(422, "LISTA_INVALIDA", "Solo se importan contactos en una lista manual")
    limpios = sorted({(e or "").strip().lower() for e in emails if (e or "").strip()})
    encontrados = list(db.scalars(select(ContactoCliente).where(func.lower(ContactoCliente.email).in_(limpios),
                                                               ContactoCliente.activo.is_(True))))
    por_email = {c.email.lower() for c in encontrados}
    actuales = {c.id for c in lista.miembros}
    nuevos = [c.id for c in encontrados if c.id not in actuales]
    actualizar_lista(db, actor, lista.id, {"contactos": sorted(actuales | set(nuevos))})
    return {"agregados": len(nuevos), "ya_estaban": len(encontrados) - len(nuevos),
            "sin_contacto": [e for e in limpios if e not in por_email][:200]}


def vista_previa(db: Session, tipo: str, filtros: dict[str, Any] | None, contactos: list[int] | None) -> dict[str, Any]:
    if tipo == "FILTRO":
        lista = ListaEnvio(nombre="(vista previa)", tipo="FILTRO", filtros=_normalizar_filtros(filtros))
        miembros = contactos_de(db, lista)
    else:
        miembros = [c for c in db.scalars(select(ContactoCliente).where(ContactoCliente.id.in_(contactos or [])))
                    if c.activo and c.email]
    return resumen_miembros(db, miembros)


def resumen_miembros(db: Session, miembros: list[ContactoCliente]) -> dict[str, Any]:
    emails = [c.email.strip().lower() for c in miembros]
    bajas = bajas_activas(db, emails)
    unicos = set(emails)
    clientes = {c.cliente_id: db.get(Cliente, c.cliente_id) for c in miembros[:MAXIMO_MUESTRA]}
    return {
        "total": len(miembros),
        "con_baja": len(unicos & bajas),
        "duplicados": len(emails) - len(unicos),
        "recibiran": len(unicos - bajas),
        "muestra": [
            {"id": c.id, "nombre": c.nombre, "email": c.email, "cliente": clientes[c.cliente_id].razon_social,
             "de_baja": c.email.strip().lower() in bajas}
            for c in miembros[:MAXIMO_MUESTRA]
        ],
    }


def buscar_contactos(db: Session, q: str) -> list[dict[str, Any]]:
    patron = f"%{(q or '').strip()}%"
    filas = db.execute(
        select(ContactoCliente, Cliente.razon_social)
        .join(Cliente, Cliente.id == ContactoCliente.cliente_id)
        .where(ContactoCliente.activo.is_(True), Cliente.activo.is_(True), ContactoCliente.email.is_not(None),
               or_(ContactoCliente.nombre.ilike(patron), ContactoCliente.email.ilike(patron),
                   Cliente.razon_social.ilike(patron)))
        .order_by(Cliente.razon_social, ContactoCliente.nombre)
        .limit(30)
    ).all()
    return [{"id": c.id, "nombre": c.nombre, "email": c.email, "cliente": razon} for c, razon in filas]


def ciudades_y_paises(db: Session) -> dict[str, Any]:
    ciudades = sorted({c for c in db.scalars(select(Cliente.ciudad).where(Cliente.activo.is_(True))) if c})
    paises = db.execute(select(Pais.id, Pais.nombre).join(Cliente, Cliente.pais_id == Pais.id).distinct()
                        .order_by(Pais.nombre)).all()
    return {"ciudades": ciudades, "paises": [{"id": i, "nombre": n} for i, n in paises]}


_ = lista_envio_miembro  # tabla de miembros (mapeada en el modelo)

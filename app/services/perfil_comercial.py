"""E1-B Perfil comercial del cliente: catálogos (CRUD con auditoría), validación de los campos, interés calculado (lo que
el cliente cotizó y cuándo) y el motor de condiciones que usan los filtros de Clientes y de las Listas de envío.

- Los valores de los catálogos salen de catalogo_perfil (sembrados con la hoja Catalogos de la plantilla oficial). Los
  estados comerciales son fijos: no se crean ni se editan.
- Al comparar valores se ignoran mayúsculas, tildes, espacios y signos ("Persona natural" = PERSONA_NATURAL), y se acepta
  el código o el nombre (en volúmenes, el texto largo de la plantilla).
- servicios_interes usa los códigos del catálogo de servicios (E0); rutas_interes, "Origen>Destino" por país (ISO2) o
  puerto (código); tipos_carga, su catálogo; etiquetas son libres (se guardan en mayúsculas, sin repetir).
"""
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, exists, false, func, or_, select, true
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session, aliased

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar, enviar
from app.models import CatalogoPerfil, Cliente, ContactoCliente, Cotizacion, Pais, Puerto, Servicio, Usuario
from app.models.administracion import TIPOS_CATALOGO_PERFIL
from app.services import auditoria

CAMPOS_CATALOGO = {  # campo del cliente → tipo de catálogo
    "tipo_cliente": "TIPO_CLIENTE", "estado_comercial": "ESTADO_COMERCIAL", "sector": "SECTOR",
    "volumen_estimado": "VOLUMEN", "frecuencia": "FRECUENCIA", "origen_cliente": "ORIGEN_CLIENTE",
    "medio_consentimiento": "MEDIO_CONSENTIMIENTO",
}
CAMPOS_LISTA = ("servicios_interes", "rutas_interes", "tipos_carga", "etiquetas")
CAMPOS_PERFIL = ("nombre_comercial", *CAMPOS_CATALOGO, *CAMPOS_LISTA, "acepta_promociones", "fecha_consentimiento")
PATRON_CODIGO = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
MESES_POR_DEFECTO = 6
# Campos de filtro (Clientes y Listas de envío). "cotizo_*" es el interés calculado, con "meses" hacia atrás.
CAMPOS_FILTRO = (*CAMPOS_CATALOGO, *CAMPOS_LISTA, "acepta_promociones", "pais", "ciudad", "area_contacto",
                 "cotizo_servicio", "cotizo_ruta")


def clave(texto: Any) -> str:
    """Para comparar: sin tildes, mayúsculas, solo letras y números."""
    sin_tildes = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", sin_tildes.upper())


def lista_de(valor: Any) -> list[str]:
    """Varios valores separados por | (o ya como lista)."""
    if valor is None:
        return []
    partes = valor if isinstance(valor, list) else str(valor).split("|")
    return [str(p).strip() for p in partes if str(p).strip()]


# ---------- Catálogos ----------


def listar_catalogo(db: Session, tipo: str | None = None, activo: bool | None = None) -> list[CatalogoPerfil]:
    consulta = select(CatalogoPerfil)
    if tipo:
        consulta = consulta.where(CatalogoPerfil.tipo == tipo)
    if activo is not None:
        consulta = consulta.where(CatalogoPerfil.activo.is_(activo))
    return list(db.scalars(consulta.order_by(CatalogoPerfil.tipo, CatalogoPerfil.orden, CatalogoPerfil.codigo)))


def valores(db: Session, tipo: str, *, solo_activos: bool = True) -> list[CatalogoPerfil]:
    return listar_catalogo(db, tipo, True if solo_activos else None)


def resolver(db: Session, tipo: str, valor: Any, cache: dict | None = None) -> str | None:
    """El código del catálogo para un valor (código o nombre, sin importar mayúsculas ni tildes); None si no existe."""
    if valor in (None, ""):
        return None
    if cache is not None and tipo in cache:
        mapa = cache[tipo]
    else:
        mapa = {}
        for item in valores(db, tipo):
            mapa[clave(item.codigo)] = item.codigo
            mapa.setdefault(clave(item.nombre), item.codigo)
        if cache is not None:
            cache[tipo] = mapa
    return mapa.get(clave(valor))


def _tipo_valido(tipo: str) -> str:
    if tipo not in TIPOS_CATALOGO_PERFIL:
        raise ErrorNegocio(422, "CATALOGO_INVALIDO", f"No existe el catálogo {tipo}")
    return tipo


def crear_valor(db: Session, actor: Usuario, datos: dict[str, Any]) -> CatalogoPerfil:
    tipo = _tipo_valido(datos.get("tipo", ""))
    if tipo == "ESTADO_COMERCIAL":
        raise ErrorNegocio(409, "CATALOGO_FIJO", "Los estados comerciales son fijos")
    codigo = re.sub(r"[^A-Z0-9_]", "_", clave_simple(datos.get("codigo") or datos.get("nombre") or ""))
    if not PATRON_CODIGO.match(codigo):
        raise ErrorNegocio(422, "CODIGO_INVALIDO", "El código es de 1 a 40 letras, números o _, y empieza con una letra")
    if db.scalars(select(CatalogoPerfil).where(CatalogoPerfil.tipo == tipo, CatalogoPerfil.codigo == codigo)).first():
        raise ErrorNegocio(409, "CATALOGO_DUPLICADO", "Ya existe ese valor en el catálogo")
    nombre = " ".join(str(datos.get("nombre") or codigo.replace("_", " ").capitalize()).split())[:120]
    item = CatalogoPerfil(tipo=tipo, codigo=codigo, nombre=nombre, orden=int(datos.get("orden") or 0),
                          creado_por=auditoria.id_de(actor))
    db.add(item)
    enviar(db)
    auditoria.registrar(db, actor, "catalogo_perfil", item.id, "CREAR",
                        despues={"tipo": tipo, "codigo": codigo, "nombre": nombre})
    confirmar(db)
    return item


def clave_simple(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return "_".join(sin_tildes.upper().split())


def actualizar_valor(db: Session, actor: Usuario, item_id: int, cambios: dict[str, Any]) -> CatalogoPerfil:
    item = db.get(CatalogoPerfil, item_id)
    if item is None:
        raise ErrorNegocio(404, "CATALOGO_NO_ENCONTRADO", "Valor de catálogo no encontrado")
    if item.fijo:
        raise ErrorNegocio(409, "CATALOGO_FIJO", "Los estados comerciales son fijos")
    if "codigo" in cambios and cambios["codigo"] != item.codigo:
        raise ErrorNegocio(422, "CODIGO_NO_EDITABLE", "El código no cambia: lo guardan los clientes")
    antes = {"nombre": item.nombre, "orden": item.orden, "activo": item.activo}
    if "nombre" in cambios:
        nombre = " ".join(str(cambios["nombre"] or "").split())
        if not nombre:
            raise ErrorNegocio(422, "NOMBRE_INVALIDO", "El nombre no puede estar vacío")
        item.nombre = nombre[:120]
    if "orden" in cambios:
        item.orden = int(cambios["orden"])
    if "activo" in cambios:
        item.activo = bool(cambios["activo"])
    despues = {"nombre": item.nombre, "orden": item.orden, "activo": item.activo}
    if despues != antes:
        accion = "DESACTIVAR" if antes["activo"] and not despues["activo"] else "EDITAR"
        auditoria.registrar(db, actor, "catalogo_perfil", item.id, accion, antes=antes, despues=despues)
    confirmar(db)
    return item


# ---------- Validación del perfil ----------


def _servicios(db: Session) -> dict[str, str]:
    return {clave(s.codigo): s.codigo for s in db.scalars(select(Servicio).where(Servicio.activo.is_(True)))}


def lado_de_ruta(db: Session, texto: str, cache: dict) -> str | None:
    """Un lado de una ruta: país ISO2 (CN) o código de puerto (CNSHA). Devuelve el código normalizado o None."""
    codigo = clave(texto)
    if "paises" not in cache:
        cache["paises"] = {p.iso2 for p in db.scalars(select(Pais))}
        cache["puertos"] = {p.codigo for p in db.scalars(select(Puerto))}
    if codigo in cache["paises"] or codigo in cache["puertos"]:
        return codigo
    return None


def validar_perfil(db: Session, datos: dict[str, Any], cache: dict | None = None) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Normaliza los campos del perfil presentes en `datos`. Devuelve (valores, errores [(campo, mensaje)])."""
    cache = {} if cache is None else cache
    salida: dict[str, Any] = {}
    errores: list[tuple[str, str]] = []
    if "nombre_comercial" in datos:
        salida["nombre_comercial"] = (" ".join(str(datos["nombre_comercial"] or "").split()) or None)
    for campo, tipo in CAMPOS_CATALOGO.items():
        if campo not in datos:
            continue
        valor = datos[campo]
        if valor in (None, ""):
            salida[campo] = "ACTIVO" if campo == "estado_comercial" else None
            continue
        codigo = resolver(db, tipo, valor, cache)
        if codigo is None:
            errores.append((campo, f"«{valor}» no está en el catálogo"))
        else:
            salida[campo] = codigo
    if "servicios_interes" in datos:
        servicios = cache.setdefault("servicios", _servicios(db))
        codigos = []
        for valor in lista_de(datos["servicios_interes"]):
            codigo = servicios.get(clave(valor))
            if codigo is None:
                errores.append(("servicios_interes", f"«{valor}» no es un servicio del catálogo"))
            elif codigo not in codigos:
                codigos.append(codigo)
        salida["servicios_interes"] = codigos
    if "rutas_interes" in datos:
        rutas = []
        for valor in lista_de(datos["rutas_interes"]):
            partes = [p.strip() for p in valor.split(">")]
            lados = [lado_de_ruta(db, p, cache) for p in partes] if len(partes) == 2 else [None, None]
            if None in lados:
                errores.append(("rutas_interes", f"«{valor}» debe ser Origen>Destino con país (CN) o puerto (CNSHA) existentes"))
            elif f"{lados[0]}>{lados[1]}" not in rutas:
                rutas.append(f"{lados[0]}>{lados[1]}")
        salida["rutas_interes"] = rutas
    if "tipos_carga" in datos:
        codigos = []
        for valor in lista_de(datos["tipos_carga"]):
            codigo = resolver(db, "TIPO_CARGA", valor, cache)
            if codigo is None:
                errores.append(("tipos_carga", f"«{valor}» no está en el catálogo de tipos de carga"))
            elif codigo not in codigos:
                codigos.append(codigo)
        salida["tipos_carga"] = codigos
    if "etiquetas" in datos:
        etiquetas = []
        for valor in lista_de(datos["etiquetas"]):
            etiqueta = " ".join(valor.upper().split())[:40]
            if etiqueta not in etiquetas:
                etiquetas.append(etiqueta)
        salida["etiquetas"] = etiquetas
    if "acepta_promociones" in datos:
        salida["acepta_promociones"] = bool(datos["acepta_promociones"])
    if "fecha_consentimiento" in datos:
        salida["fecha_consentimiento"] = datos["fecha_consentimiento"] or None
    return salida, errores


def exigir_perfil(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    salida, errores = validar_perfil(db, datos)
    if errores:
        campo, mensaje = errores[0]
        raise ErrorNegocio(422, "PERFIL_INVALIDO", f"{campo}: {mensaje}", extra={"errores": [
            {"campo": c, "mensaje": m} for c, m in errores]})
    return salida


# ---------- Interés calculado ----------


def interes(db: Session, cliente_id: int) -> dict[str, Any]:
    """Servicios y rutas que el cliente cotizó (cotizaciones emitidas), cuántas veces y la última fecha."""
    origen, destino = aliased(Puerto), aliased(Puerto)
    po, pd = aliased(Pais), aliased(Pais)
    filas = db.execute(
        select(Cotizacion.modo, origen.codigo, destino.codigo, po.iso2, pd.iso2, Cotizacion.fecha_emision)
        .join(origen, origen.id == Cotizacion.origen_puerto_id).join(destino, destino.id == Cotizacion.destino_puerto_id)
        .join(po, po.id == origen.pais_id).join(pd, pd.id == destino.pais_id)
        .where(Cotizacion.cliente_id == cliente_id, Cotizacion.estado != "BORRADOR", Cotizacion.activo.is_(True))
    ).all()
    servicios: dict[str, dict[str, Any]] = {}
    rutas: dict[str, dict[str, Any]] = {}
    for modo, codigo_o, codigo_d, iso_o, iso_d, emitida in filas:
        for tabla, llave, extra in ((servicios, modo, {}), (rutas, f"{iso_o}>{iso_d}", {"puertos": f"{codigo_o}>{codigo_d}"})):
            item = tabla.setdefault(llave, {"codigo": llave, "veces": 0, "ultima": None} | extra)
            item["veces"] += 1
            if emitida and (item["ultima"] is None or emitida > item["ultima"]):
                item["ultima"] = emitida
    ordenar = lambda d: sorted(d.values(), key=lambda x: (x["ultima"] or date.min), reverse=True)  # noqa: E731
    return {"servicios": ordenar(servicios), "rutas": ordenar(rutas)}


# ---------- Condiciones de filtro ----------


def normalizar_condiciones(condiciones: Any) -> list[dict[str, Any]]:
    salida = []
    for condicion in condiciones or []:
        campo = (condicion or {}).get("campo")
        if campo not in CAMPOS_FILTRO:
            raise ErrorNegocio(422, "FILTRO_INVALIDO", f"Campo de filtro desconocido: {campo}")
        vals = sorted({str(v).strip() for v in lista_de(condicion.get("valores")) if str(v).strip()})
        if not vals:
            continue
        item = {"campo": campo, "valores": vals}
        if campo.startswith("cotizo_"):
            meses = int(condicion.get("meses") or MESES_POR_DEFECTO)
            if not 1 <= meses <= 60:
                raise ErrorNegocio(422, "FILTRO_INVALIDO", "Los meses del interés calculado van de 1 a 60")
            item["meses"] = meses
        salida.append(item)
    return salida


def _desde(meses: int) -> date:
    return fechas.hoy_ecuador() - timedelta(days=30 * meses)


def _lado(codigo: str, puerto, pais):
    return or_(puerto.codigo == codigo, pais.iso2 == codigo)


def condicion_sql(condicion: dict[str, Any]):
    """La condición SQL de un filtro, sobre Cliente (y ContactoCliente para el área)."""
    campo, vals = condicion["campo"], condicion["valores"]
    if campo in CAMPOS_CATALOGO:
        return getattr(Cliente, campo).in_(vals)
    if campo in CAMPOS_LISTA:
        valores_buscados = [v.upper() for v in vals] if campo == "etiquetas" else vals
        return getattr(Cliente, campo).has_any(array(valores_buscados))
    if campo == "acepta_promociones":
        quiere = {clave(v) in ("SI", "TRUE", "1") for v in vals}
        return Cliente.acepta_promociones.in_(list(quiere))
    if campo == "pais":
        return Cliente.pais_id.in_(select(Pais.id).where(Pais.iso2.in_([v.upper() for v in vals])))
    if campo == "ciudad":
        return func.lower(Cliente.ciudad).in_([v.lower() for v in vals])
    if campo == "area_contacto":
        return ContactoCliente.area.in_(vals)
    desde = _desde(condicion.get("meses", MESES_POR_DEFECTO))
    base = [Cotizacion.cliente_id == Cliente.id, Cotizacion.estado != "BORRADOR", Cotizacion.activo.is_(True),
            Cotizacion.fecha_emision >= desde]
    if campo == "cotizo_servicio":
        return exists().where(*base, Cotizacion.modo.in_(vals))
    origen, destino, po, pd = aliased(Puerto), aliased(Puerto), aliased(Pais), aliased(Pais)
    rutas = []
    for valor in vals:
        partes = valor.split(">")
        if len(partes) != 2:
            continue
        rutas.append(and_(_lado(clave(partes[0]), origen, po), _lado(clave(partes[1]), destino, pd)))
    return exists().where(*base, origen.id == Cotizacion.origen_puerto_id, destino.id == Cotizacion.destino_puerto_id,
                          po.id == origen.pais_id, pd.id == destino.pais_id, or_(*rutas) if rutas else false())


def combinar(condiciones: list[dict[str, Any]], modo: str):
    partes = [condicion_sql(c) for c in condiciones]
    if not partes:
        return true()
    return or_(*partes) if modo == "O" else and_(*partes)


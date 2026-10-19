"""E1 Envíos masivos: configuración (una fila, en el espacio de Tencent; solo admin, auditada) y cupos.

Cupos (Tencent: nivel 1 de reputación = 500 correos por día por dominio; 10 por hora a una misma dirección):
- tope diario efectivo = tope_diario o, con calentamiento, min(tope_diario, inicio + incremento × días desde el inicio);
- los boletines usan como máximo (100 − reserva_pct) % del tope diario: el resto queda para cotizaciones y avisos (E3);
- tope por hora para todo lo que sale (campañas, avisos, cotizaciones y pruebas);
- horario permitido: días (1 = lunes … 7 = domingo) y horas desde–hasta, en America/Guayaquil.
"""
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import fechas
from app.core.errors import ErrorNegocio, confirmar
from app.models import CampanaDestinatario, ConfigMasivos, EnvioCorreo, EnvioCorreoPrueba, Notificacion, Usuario
from app.services import auditoria

ZONA = ZoneInfo("America/Guayaquil")
PATRON_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
CAMPOS = (
    "remitente", "reply_to", "tamano_lote", "pausa_segundos", "tope_diario", "tope_hora", "reserva_pct", "adjuntar_pdf",
    "limite_filas", "texto_legal", "correos_prueba", "dias_envio", "hora_desde", "hora_hasta", "calentamiento",
    "calentamiento_inicio", "calentamiento_incremento", "calentamiento_desde",
)
RANGOS = {
    "tamano_lote": (1, 200), "pausa_segundos": (0, 3600), "tope_diario": (1, 1_000_000), "tope_hora": (1, 100_000),
    "reserva_pct": (0, 90), "limite_filas": (1, 40), "hora_desde": (0, 23), "hora_hasta": (0, 23),
    "calentamiento_inicio": (1, 1_000_000), "calentamiento_incremento": (0, 1_000_000),
}


def config(db: Session, *, bloquear: bool = False) -> ConfigMasivos:
    consulta = select(ConfigMasivos).where(ConfigMasivos.id == 1)
    if bloquear:
        consulta = consulta.with_for_update()
    return db.scalars(consulta.execution_options(populate_existing=True)).one()


def _email(valor: str) -> str:
    encontrado = re.search(r"<([^<>]+)>", valor or "")
    return (encontrado.group(1) if encontrado else (valor or "")).strip()


def lista_correos(texto: str | None) -> list[str]:
    return [c.strip().lower() for c in re.split(r"[,;\s]+", texto or "") if c.strip()]


def correos_prueba(fila: ConfigMasivos) -> list[str]:
    return lista_correos(fila.correos_prueba)


def presentar(db: Session) -> dict[str, Any]:
    fila = config(db)
    datos = {campo: getattr(fila, campo) for campo in CAMPOS}
    datos["calentamiento_desde"] = fila.calentamiento_desde.isoformat() if fila.calentamiento_desde else None
    hoy = fechas.hoy_ecuador()
    datos |= {
        "tope_diario_efectivo": tope_diario_efectivo(fila, hoy),
        "cupo_boletines_hoy": cupo_boletines(fila, hoy),
        "enviados_hoy": enviados_hoy(db),
        "enviados_ultima_hora": enviados_ultima_hora(db),
        "en_horario": en_horario(fila),
        "ultimo_lote_en": fila.ultimo_lote_en.isoformat() if fila.ultimo_lote_en else None,
        "ultima_sincronizacion": fila.ultima_sincronizacion.isoformat() if fila.ultima_sincronizacion else None,
    }
    return datos


def actualizar(db: Session, actor: Usuario, cambios: dict[str, Any]) -> dict[str, Any]:
    fila = config(db, bloquear=True)
    antes = {campo: getattr(fila, campo) for campo in CAMPOS}
    final = antes | cambios
    for campo, (minimo, maximo) in RANGOS.items():
        if not minimo <= int(final[campo]) <= maximo:
            raise ErrorNegocio(422, "MASIVOS_INVALIDO", f"{campo} va de {minimo} a {maximo}")
    if final["hora_desde"] > final["hora_hasta"]:
        raise ErrorNegocio(422, "MASIVOS_INVALIDO", "La hora de inicio no puede ser posterior a la de fin")
    dias = ",".join(sorted({d.strip() for d in str(final["dias_envio"]).split(",") if d.strip()}))
    if not re.fullmatch(r"[1-7](,[1-7])*", dias):
        raise ErrorNegocio(422, "MASIVOS_INVALIDO", "Los días de envío van de 1 (lunes) a 7 (domingo), separados por coma")
    final["dias_envio"] = dias
    for campo in ("remitente", "reply_to"):
        valor = (final[campo] or "").strip()
        if valor and not PATRON_EMAIL.match(_email(valor)):
            raise ErrorNegocio(422, "MASIVOS_INVALIDO", f"{campo}: dirección de correo no válida")
        final[campo] = valor
    for correo in lista_correos(final["correos_prueba"]):
        if not PATRON_EMAIL.match(correo):
            raise ErrorNegocio(422, "MASIVOS_INVALIDO", f"Correo de prueba no válido: {correo}")
    if final["calentamiento"] and final["calentamiento_desde"] is None:
        final["calentamiento_desde"] = fechas.hoy_ecuador()
    if isinstance(final["calentamiento_desde"], str):
        final["calentamiento_desde"] = date.fromisoformat(final["calentamiento_desde"])
    with db.no_autoflush:
        for campo in CAMPOS:
            setattr(fila, campo, final[campo])
        despues = {campo: getattr(fila, campo) for campo in CAMPOS}
        if despues != antes:
            fila.actualizado_por = auditoria.id_de(actor)
            fila.fecha = func.now()
            auditoria.registrar(db, actor, "config_masivos", 1, "EDITAR", antes=antes, despues=despues)
    confirmar(db)
    return presentar(db)


# ---------- Cupos y horario ----------


def tope_diario_efectivo(fila: ConfigMasivos, hoy: date) -> int:
    if not fila.calentamiento or fila.calentamiento_desde is None:
        return fila.tope_diario
    dias = max(0, (hoy - fila.calentamiento_desde).days)
    return min(fila.tope_diario, fila.calentamiento_inicio + fila.calentamiento_incremento * dias)


def cupo_boletines(fila: ConfigMasivos, hoy: date) -> int:
    """Lo que pueden usar los boletines en el día: el tope efectivo menos la reserva para cotizaciones y avisos."""
    return tope_diario_efectivo(fila, hoy) * (100 - fila.reserva_pct) // 100


def _inicio_del_dia() -> datetime:
    return datetime.combine(fechas.hoy_ecuador(), time.min, tzinfo=ZONA)


def _contar(db: Session, desde: datetime) -> dict[str, int]:
    return {
        "campanas": db.scalar(select(func.count()).select_from(CampanaDestinatario).where(
            CampanaDestinatario.estado == "ENVIADO", CampanaDestinatario.enviado_en >= desde)) or 0,
        "cotizaciones": db.scalar(select(func.count()).select_from(EnvioCorreo).where(
            EnvioCorreo.estado == "ENVIADO", EnvioCorreo.fecha >= desde)) or 0,
        "pruebas": db.scalar(select(func.count()).select_from(EnvioCorreoPrueba).where(
            EnvioCorreoPrueba.estado == "ENVIADO", EnvioCorreoPrueba.fecha >= desde)) or 0,
        "avisos": db.scalar(select(func.count()).select_from(Notificacion).where(  # E3
            Notificacion.canal == "CORREO", Notificacion.estado == "ENVIADO", Notificacion.enviado_en >= desde)) or 0,
    }


def enviados_hoy(db: Session) -> dict[str, int]:
    conteo = _contar(db, _inicio_del_dia())
    return conteo | {"total": sum(conteo.values())}


def enviados_ultima_hora(db: Session) -> int:
    return sum(_contar(db, datetime.now(ZONA) - timedelta(hours=1)).values())


def en_horario(fila: ConfigMasivos, ahora: datetime | None = None) -> bool:
    ahora = (ahora or datetime.now(ZONA)).astimezone(ZONA)
    dias = {int(d) for d in fila.dias_envio.split(",") if d}
    return ahora.isoweekday() in dias and fila.hora_desde <= ahora.hour <= fila.hora_hasta


def disponibles_para_boletines(db: Session, fila: ConfigMasivos) -> int:
    """Cuántos boletines pueden salir ahora mismo (cupo diario de boletines, tope total del día y tope por hora)."""
    hoy = enviados_hoy(db)
    por_dia_boletines = cupo_boletines(fila, fechas.hoy_ecuador()) - hoy["campanas"]
    por_dia_total = tope_diario_efectivo(fila, fechas.hoy_ecuador()) - hoy["total"]
    por_hora = fila.tope_hora - enviados_ultima_hora(db)
    return max(0, min(por_dia_boletines, por_dia_total, por_hora))


def disponibles_para_avisos(db: Session, fila: ConfigMasivos) -> int:
    """E3: los avisos usan el tope total del día (incluida la reserva que los boletines no pueden tocar) y el tope por
    hora."""
    por_dia_total = tope_diario_efectivo(fila, fechas.hoy_ecuador()) - enviados_hoy(db)["total"]
    return max(0, min(por_dia_total, fila.tope_hora - enviados_ultima_hora(db)))

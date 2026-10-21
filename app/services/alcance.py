"""Alcance en cadena de los recargos (D-A1..D-A4, D-T5). Una sola fuente para el cotizador, los descartes, el listado
y el formulario.

- Niveles (cada uno multiselección; sin valores = "Todos", no filtra): SERVICIO (código E0), MODO (tipo de
  ubicación: marítimo, aéreo…), TIPO_EQUIPO, REGION, PAIS, PUERTO (el del lado), PUERTO_ORIGEN + PUERTO_DESTINO (ruta
  exacta: exige los dos), PROVEEDOR (de la tarifa del flete), TIPO_CARGA y CLASE_IMO (clase principal 1–9).
  Un recargo aplica si cumple TODOS sus niveles. El vínculo a tarifas (recargo_tarifa) es el nivel más específico.
- D-A3: región, país y puerto se leen contra el puerto del lado del recargo (el seguro, contra el puerto que el
  motor le asigna por el sentido, como siempre). La ruta compara origen y destino de la cotización.
- D-A2 (precedencia entre recargos del mismo concepto): tarifa vinculada > ruta > puerto > país > región >
  servicio/modo > "Todos"; luego un tipo de carga específico antes que "Todos" (D-T5); luego el del proveedor del
  flete antes que el propio; luego tipo de equipo > servicio > todos (como D-F3-7).
- D-A4: nada de esto toca precios, mínimos, IVA ni totales.
"""
from dataclasses import dataclass, field
from typing import Any

NIVELES = ("SERVICIO", "MODO", "TIPO_EQUIPO", "REGION", "PAIS", "PUERTO", "PUERTO_ORIGEN", "PUERTO_DESTINO", "PROVEEDOR",
           "TIPO_CARGA", "CLASE_IMO")
NIVELES_TEXTO = {"SERVICIO", "MODO", "TIPO_CARGA", "CLASE_IMO"}
NOMBRE_NIVEL = {0: "tarifa vinculada", 1: "ruta exacta", 2: "puerto", 3: "país", 4: "región", 5: "servicio o modo",
                6: "todos"}
CLAVE_API = {  # nivel → clave del JSON del formulario
    "SERVICIO": "servicios", "MODO": "modos", "TIPO_EQUIPO": "tipos_equipo", "REGION": "regiones", "PAIS": "paises",
    "PUERTO": "puertos", "PUERTO_ORIGEN": "puertos_origen", "PUERTO_DESTINO": "puertos_destino",
    "PROVEEDOR": "proveedores", "TIPO_CARGA": "tipos_carga", "CLASE_IMO": "clases_imo",
}


def derivado(puerto_id, modo, tipo_equipo_id, proveedor_id) -> dict[str, set]:
    """El alcance equivalente a las columnas de antes (lo que hace la migración 0016)."""
    salida: dict[str, set] = {}
    for nivel, valor in (("PUERTO", puerto_id), ("SERVICIO", modo), ("TIPO_EQUIPO", tipo_equipo_id), ("PROVEEDOR", proveedor_id)):
        if valor is not None:
            salida[nivel] = {valor}
    return salida


def firma(alc: dict[str, set], puerto_id, modo, tipo_equipo_id, proveedor_id) -> str:
    """"" si el alcance es el equivalente a las columnas; si no, md5 de su forma canónica."""
    import hashlib
    import json

    limpio = {k: set(v) for k, v in alc.items() if v}
    if limpio == derivado(puerto_id, modo, tipo_equipo_id, proveedor_id):
        return ""
    canonico = json.dumps(sorted((k, sorted(str(x) for x in v)) for k, v in limpio.items()))
    return hashlib.md5(canonico.encode()).hexdigest()


def de(recargo) -> dict[str, set]:
    """El alcance de un recargo: nivel → conjunto de valores (ids o códigos). Niveles sin filas no aparecen."""
    salida: dict[str, set] = {}
    for fila in recargo.alcance:
        salida.setdefault(fila.nivel, set()).add(fila.valor_texto if fila.nivel in NIVELES_TEXTO else fila.valor_id)
    return salida


def clase_principal(clase: str | None) -> str | None:
    return clase.split(".")[0] if clase else None


@dataclass
class Contexto:
    """Lo que de la cotización mira el alcance."""

    servicio: str
    modo: str
    tipos_equipo: set[int]
    origen: Any
    destino: Any
    proveedor_flete: int | None
    tipo_carga: str = "GENERAL"
    clase_imo: str | None = None
    tarifas: set[int] = field(default_factory=set)


def contexto(cotizacion, proveedor_flete: int | None, tarifas: set[int] | None = None) -> Contexto:
    return Contexto(
        servicio=cotizacion.modo, modo=cotizacion.servicio.tipo_ubicacion_origen,
        tipos_equipo={c.tipo_equipo_id for c in cotizacion.contenedores}, origen=cotizacion.origen,
        destino=cotizacion.destino, proveedor_flete=proveedor_flete, tipo_carga=cotizacion.tipo_carga or "GENERAL",
        clase_imo=clase_principal(cotizacion.imo_clase), tarifas=set(tarifas or ()),
    )


def nivel_ubicacion(alc: dict[str, set], vinculado: bool) -> int:
    if vinculado:
        return 0
    if "PUERTO_ORIGEN" in alc or "PUERTO_DESTINO" in alc:
        return 1
    for nivel, rango in (("PUERTO", 2), ("PAIS", 3), ("REGION", 4)):
        if nivel in alc:
            return rango
    return 5 if ("SERVICIO" in alc or "MODO" in alc) else 6


def rango(recargo, alc: dict[str, set], vinculado: bool, proveedor_flete: int | None) -> tuple[int, int, int, int]:
    """D-A2 + D-T5 + D-F3-7. Menor es mejor."""
    tipo_carga = 0 if "TIPO_CARGA" in alc else 1
    proveedor = 0 if proveedor_flete is not None and recargo.proveedor_id == proveedor_flete else 1
    especificidad = 0 if "TIPO_EQUIPO" in alc else (1 if ("SERVICIO" in alc or "MODO" in alc) else 2)
    return nivel_ubicacion(alc, vinculado), tipo_carga, proveedor, especificidad


def motivo_derrota(ganador: tuple, perdedor: tuple, nombre_ganador: str) -> str:
    """Por qué una alternativa perdió, en palabras simples (el primer criterio de D-A2 que los separa)."""
    if ganador[0] != perdedor[0]:
        return f"Perdió contra «{nombre_ganador}», más específico ({NOMBRE_NIVEL[ganador[0]]})"
    if ganador[1] != perdedor[1]:
        return f"Perdió contra «{nombre_ganador}», específico para este tipo de carga"
    if ganador[2] != perdedor[2]:
        return f"Perdió contra «{nombre_ganador}», del proveedor del flete"
    if ganador[3] != perdedor[3]:
        return f"Perdió contra «{nombre_ganador}», más específico (tipo de equipo o servicio)"
    return f"Perdió contra «{nombre_ganador}» (un recargo por concepto)"


def tipos_de(alc: dict[str, set]) -> set[int] | None:
    return alc.get("TIPO_EQUIPO")


def _lista(valores, nombres: dict | None = None) -> str:
    textos = sorted(str((nombres or {}).get(v, v)) for v in valores)
    return " o ".join(textos) if len(textos) <= 3 else ", ".join(textos[:3]) + f" y {len(textos) - 3} más"


def motivos(alc: dict[str, set], ctx: Contexto, puerto, *, vinculado: bool,
            nombres: dict[str, dict] | None = None) -> list[tuple[str, str]]:
    """Por qué el alcance NO aplica a esta cotización (vacío = aplica). `puerto` es el puerto del lado del recargo.
    Un recargo vinculado a la tarifa elegida no mira la ubicación ni el proveedor (los da la tarifa)."""
    nombres = nombres or {}
    salida: list[tuple[str, str]] = []

    def no(nivel: str, texto: str) -> None:
        salida.append((nivel, f"no aplica: el alcance de {texto}"))

    if "SERVICIO" in alc and ctx.servicio not in alc["SERVICIO"]:
        no("SERVICIO", f"servicio es solo {_lista(alc['SERVICIO'])} y la cotización es {ctx.servicio}")
    if "MODO" in alc and ctx.modo not in alc["MODO"]:
        no("MODO", f"modo es solo {_lista(alc['MODO'], nombres.get('MODO'))} y la cotización es {nombres.get('MODO', {}).get(ctx.modo, ctx.modo)}")
    if "TIPO_EQUIPO" in alc and not (alc["TIPO_EQUIPO"] & ctx.tipos_equipo):
        no("TIPO_EQUIPO", f"tipo de contenedor es solo {_lista(alc['TIPO_EQUIPO'], nombres.get('TIPO_EQUIPO'))}")
    if "TIPO_CARGA" in alc and ctx.tipo_carga not in alc["TIPO_CARGA"]:
        no("TIPO_CARGA", f"tipo de carga es solo {_lista(alc['TIPO_CARGA'])} y la carga es {ctx.tipo_carga}")
    if "CLASE_IMO" in alc and ctx.clase_imo not in alc["CLASE_IMO"]:
        actual = f"clase {ctx.clase_imo}" if ctx.clase_imo else "sin clase IMO"
        no("CLASE_IMO", f"clase IMO es solo {_lista(alc['CLASE_IMO'])} y la carga es {actual}")
    if vinculado:
        return salida
    if "PROVEEDOR" in alc and ctx.proveedor_flete not in alc["PROVEEDOR"]:
        no("PROVEEDOR", f"proveedor es solo {_lista(alc['PROVEEDOR'], nombres.get('PROVEEDOR'))}")
    if "PUERTO_ORIGEN" in alc or "PUERTO_DESTINO" in alc:
        if ctx.origen.id not in alc.get("PUERTO_ORIGEN", set()) or ctx.destino.id not in alc.get("PUERTO_DESTINO", set()):
            ruta = f"{_lista(alc.get('PUERTO_ORIGEN', set()), nombres.get('PUERTO'))} → {_lista(alc.get('PUERTO_DESTINO', set()), nombres.get('PUERTO'))}"
            no("RUTA", f"ruta es solo {ruta} y la cotización va {ctx.origen.codigo} → {ctx.destino.codigo}")
    if "PUERTO" in alc and puerto.id not in alc["PUERTO"]:
        no("PUERTO", f"puerto es solo {_lista(alc['PUERTO'], nombres.get('PUERTO'))} y aquí es {puerto.codigo}")
    if "PAIS" in alc and puerto.pais_id not in alc["PAIS"]:
        no("PAIS", f"país es solo {_lista(alc['PAIS'], nombres.get('PAIS'))} y {puerto.codigo} es de {puerto.pais.nombre}")
    if "REGION" in alc and puerto.pais.region_id not in alc["REGION"]:
        region = puerto.pais.region.nombre if getattr(puerto.pais, "region", None) else "otra región"
        no("REGION", f"región es solo {_lista(alc['REGION'], nombres.get('REGION'))} y {puerto.codigo} es de {region}")
    return salida


def resumen(alc: dict[str, set], lado: str, nombres: dict[str, dict] | None = None, tarifas: int = 0) -> str:
    """Una línea: "Aplica a: LCL y FCL · destino Guayaquil · todos los proveedores"."""
    nombres = nombres or {}

    def n(nivel: str) -> str:
        return " y ".join(sorted(str(nombres.get(nivel, {}).get(v, v)) for v in alc[nivel]))

    partes = []
    if tarifas:
        partes.append(f"{tarifas} tarifa(s) vinculada(s)")
    partes.append(n("SERVICIO") if "SERVICIO" in alc else "todos los servicios")
    if "MODO" in alc:
        partes.append(n("MODO").lower())
    if "TIPO_EQUIPO" in alc:
        partes.append(n("TIPO_EQUIPO"))
    lugar = "destino" if lado == "DESTINO" else "origen"
    if "PUERTO_ORIGEN" in alc or "PUERTO_DESTINO" in alc:
        o = " o ".join(sorted(str(nombres.get("PUERTO", {}).get(v, v)) for v in alc.get("PUERTO_ORIGEN", set())))
        d = " o ".join(sorted(str(nombres.get("PUERTO", {}).get(v, v)) for v in alc.get("PUERTO_DESTINO", set())))
        partes.append(f"ruta {o} → {d}")
    for nivel in ("PUERTO", "PAIS", "REGION"):
        if nivel in alc:
            partes.append(f"{lugar} {n(nivel)}")
    if not any(k in alc for k in ("PUERTO", "PAIS", "REGION", "PUERTO_ORIGEN", "PUERTO_DESTINO")) and not tarifas:
        partes.append(f"cualquier {lugar}")
    partes.append(n("PROVEEDOR") if "PROVEEDOR" in alc else "todos los proveedores")
    if "TIPO_CARGA" in alc:
        partes.append(f"carga {n('TIPO_CARGA')}" + (f" clase {n('CLASE_IMO')}" if "CLASE_IMO" in alc else ""))
    return "Aplica a: " + " · ".join(partes)

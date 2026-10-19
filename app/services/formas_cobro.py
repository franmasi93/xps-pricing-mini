"""E0: formas de cobro, un catálogo cerrado en código (no editable). Cada servicio elige una.

Cada forma es una estrategia registrada que concentra lo que antes eran constantes e if por modo:
unidades permitidas, validación de la carga, cantidad cobrable, datos de carga para la pantalla y el PDF,
claves de flete y columnas de tabla (boletines de E1). La lógica es la de F2–F5, sin cambios de resultado:

- PESO_TRAMOS (antes AEREO): peso cobrable = máx(real, volumétrico), tramos por peso en kg o lb.
- VOLUMEN_WM (antes LCL): W/M = máx(CBM, kg / 1000); exige CBM o dimensiones.
- UNIDAD_EQUIPO (antes FCL): por contenedor o equipo; un flete por tipo, todos del mismo proveedor.
- TARIFA_PLANA: un precio por envío.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.errors import ErrorNegocio
from app.services import cotizador

UNIDAD_TEXTO = {"KG": "kg", "LB": "lb", "WM": "W/M", "CBM": "m³", "ENVIO": "envío"}


def precio(valor: Any) -> str:
    """Precio de venta para boletines: 2 decimales, separador de miles como el PDF de F4 (1,234.50)."""
    return f"{Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def numero_corto(valor: Any) -> str:
    numero = Decimal(str(valor)).normalize()
    return f"{numero:f}"


class FormaCobro:
    codigo = ""
    nombre = ""
    descripcion = ""
    unidades_tarifa: tuple[str, ...] = ()
    unidades_recargo: tuple[str, ...] = ()
    usa_tramos = False  # las tarifas por peso (KG) llevan tramos de servicio_tramo
    usa_tipo_equipo = False
    admite_libras = False  # el servicio puede habilitar tarifas por libra (H-F4-2)
    peso_obligatorio = False
    columnas_tabla: tuple[str, ...] = ()

    def cantidad_cobrable(self, carga: "cotizador.Carga") -> Decimal:
        raise NotImplementedError

    def validar_carga(self, datos: dict[str, Any], dimensiones: list, contenedores: list, codigo_servicio: str) -> None:
        """Requisitos de la carga propios de la forma. Los contenedores solo existen con tipo de equipo."""
        if contenedores and not self.usa_tipo_equipo:
            raise ErrorNegocio(
                422, "CONTENEDORES_NO_PERMITIDOS", f"Las cotizaciones {codigo_servicio} no llevan contenedores"
            )

    def datos_carga(self, carga: "cotizador.Carga") -> dict[str, Any]:
        """Datos derivados que la cotización muestra y congela (peso cobrable, W/M…)."""
        return {}

    def claves_flete(self, codigo_servicio: str, contenedores: list) -> list[tuple[str, int | None]]:
        """(clave, tipo_equipo_id): una sola clave salvo que la forma cobre por tipo de equipo."""
        return [(codigo_servicio, None)]

    # ---------- Boletines (E1): el formateador de cada forma de cobro ----------
    # `datos` es la foto de venta de una tarifa (services/campanas._foto_tarifa): moneda, precio_venta, minimo_venta,
    # rate_unit, unidad_peso, tramos [(desde, venta)], tipo_equipo. Nunca lleva costo ni proveedor.

    def texto_tarifa(self, datos: dict[str, Any]) -> str:
        """La tarifa en pocas palabras, para una fila del correo."""
        unidad = UNIDAD_TEXTO.get(datos["rate_unit"], datos["rate_unit"].lower())
        return f"{datos['moneda']} {precio(datos['precio_venta'])}/{unidad}"

    def detalle(self, datos: dict[str, Any]) -> str:
        """El detalle completo, para la tabla del PDF adjunto."""
        if Decimal(str(datos.get("minimo_venta") or 0)) > 0:
            return f"Mínimo {datos['moneda']} {precio(datos['minimo_venta'])}"
        return ""

    def describir(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "unidades_tarifa": list(self.unidades_tarifa),
            "unidades_recargo": list(self.unidades_recargo),
            "usa_tramos": self.usa_tramos,
            "usa_tipo_equipo": self.usa_tipo_equipo,
            "admite_libras": self.admite_libras,
            "peso_obligatorio": self.peso_obligatorio,
            "columnas_tabla": list(self.columnas_tabla),
        }


class PesoTramos(FormaCobro):
    codigo = "PESO_TRAMOS"
    nombre = "Por peso con tramos"
    descripcion = (
        "Precio por kg (o por libra si el servicio lo permite) con tramos por peso, o por envío. Se cobra el peso "
        "cobrable: el mayor entre el real y el volumétrico (cm³ / 6000)."
    )
    unidades_tarifa = ("KG", "ENVIO")
    unidades_recargo = ("KG", "ENVIO")
    usa_tramos = True
    admite_libras = True
    peso_obligatorio = True
    columnas_tabla = ("ruta", "tramos", "minimo", "transito", "vigencia", "transportista")

    def cantidad_cobrable(self, carga):
        return cotizador.peso_cobrable(carga)

    def texto_tarifa(self, datos):
        if datos["rate_unit"] != "KG":
            return f"{datos['moneda']} {precio(datos['precio_venta'])} por envío"
        unidad = UNIDAD_TEXTO[datos.get("unidad_peso") or "KG"]
        tramos = datos.get("tramos") or []
        if not tramos:
            return f"{datos['moneda']} {precio(datos['precio_venta'])}/{unidad}"
        desde, venta = min(tramos, key=lambda t: (Decimal(str(t[1])), -Decimal(str(t[0]))))
        if Decimal(str(desde)) == 0:
            return f"{datos['moneda']} {precio(venta)}/{unidad}"
        return f"{datos['moneda']} {precio(venta)}/{unidad} desde {numero_corto(desde)} {unidad}"

    def detalle(self, datos):
        tramos = datos.get("tramos") or []
        unidad = UNIDAD_TEXTO[datos.get("unidad_peso") or "KG"]
        partes = []
        for indice, (desde, venta) in enumerate(tramos):
            siguiente = tramos[indice + 1][0] if indice + 1 < len(tramos) else None
            etiqueta = f"−{numero_corto(siguiente)}" if Decimal(str(desde)) == 0 and siguiente is not None else f"+{numero_corto(desde)}"
            partes.append(f"{etiqueta} {unidad}: {precio(venta)}")
        base = super().detalle(datos)
        return " · ".join(partes + ([base] if base else []))

    def datos_carga(self, carga):
        volumetrico = cotizador.peso_volumetrico(carga)
        return {
            "peso_volumetrico_kg": str(volumetrico),
            "peso_cobrable_kg": str(cotizador.peso_cobrable(carga)),
            "peso_cobrable_lb": str(cotizador.peso_cobrable_en(carga, "LB")),
            "base_cobro": "VOLUMETRICO" if volumetrico > cotizador.a_3(carga.peso_kg) else "REAL",
        }


class VolumenWM(FormaCobro):
    codigo = "VOLUMEN_WM"
    nombre = "Por volumen (W/M)"
    descripcion = "Precio por W/M (el mayor entre m³ y toneladas), por m³ o por envío. Exige el CBM o las dimensiones."
    unidades_tarifa = ("WM", "CBM", "ENVIO")
    unidades_recargo = ("WM", "CBM", "ENVIO")
    columnas_tabla = ("ruta", "unidad", "tarifa", "minimo", "transito", "vigencia", "transportista")

    def cantidad_cobrable(self, carga):
        return cotizador.peso_medida(carga)

    def validar_carga(self, datos, dimensiones, contenedores, codigo_servicio):
        if datos["cbm"] is None and not dimensiones:
            raise cotizador.carga_incompleta("Indique el CBM o las dimensiones de los bultos")
        super().validar_carga(datos, dimensiones, contenedores, codigo_servicio)

    def datos_carga(self, carga):
        return {"peso_medida": str(cotizador.peso_medida(carga))}


class UnidadEquipo(FormaCobro):
    codigo = "UNIDAD_EQUIPO"
    nombre = "Por unidad de equipo"
    descripcion = (
        "Precio por contenedor o equipo, según su tipo (los tipos de equipo del servicio). Un flete por tipo, "
        "todos del mismo proveedor."
    )
    unidades_tarifa = ("CONTENEDOR",)
    unidades_recargo = ("CONTENEDOR", "ENVIO")
    usa_tipo_equipo = True
    columnas_tabla = ("ruta", "equipo", "tarifa", "transito", "dias_libres", "vigencia", "transportista")

    def cantidad_cobrable(self, carga):
        return Decimal(cotizador.total_contenedores(carga))

    def validar_carga(self, datos, dimensiones, contenedores, codigo_servicio):
        if not contenedores:
            raise cotizador.carga_incompleta("Indique los contenedores (tipo y cantidad)")
        tipos = [c["tipo_equipo_id"] for c in contenedores]
        if len(set(tipos)) != len(tipos):
            raise ErrorNegocio(422, "CONTENEDOR_DUPLICADO", "Cada tipo de contenedor va una sola vez")

    def claves_flete(self, codigo_servicio, contenedores):
        return [(str(c.tipo_equipo_id), c.tipo_equipo_id) for c in contenedores]

    def texto_tarifa(self, datos):
        return f"{datos['moneda']} {precio(datos['precio_venta'])} por {datos.get('tipo_equipo') or 'equipo'}"

    def detalle(self, datos):
        partes = [datos.get("tipo_equipo_nombre") or ""]
        if datos.get("dias_libres") is not None:
            partes.append(f"{datos['dias_libres']} días libres")
        base = super().detalle(datos)
        return " · ".join(p for p in partes + [base] if p)


class TarifaPlana(FormaCobro):
    codigo = "TARIFA_PLANA"
    nombre = "Tarifa plana"
    descripcion = "Un precio fijo por envío, sin importar el peso ni el volumen."
    unidades_tarifa = ("ENVIO",)
    unidades_recargo = ("ENVIO",)
    columnas_tabla = ("ruta", "tarifa", "transito", "vigencia", "transportista")

    def cantidad_cobrable(self, carga):
        return Decimal("1")

    def texto_tarifa(self, datos):
        return f"{datos['moneda']} {precio(datos['precio_venta'])} por envío"


FORMAS: dict[str, FormaCobro] = {forma.codigo: forma for forma in (PesoTramos(), VolumenWM(), UnidadEquipo(), TarifaPlana())}
# Unidades que solo existen con tipo de equipo: un recargo sin servicio nunca las usa (antes: CONTENEDOR solo con FCL).
UNIDADES_DE_EQUIPO = frozenset(
    unidad for forma in FORMAS.values() if forma.usa_tipo_equipo for unidad in forma.unidades_tarifa
)


def forma(codigo: str) -> FormaCobro:
    try:
        return FORMAS[codigo]
    except KeyError:
        raise ErrorNegocio(422, "FORMA_COBRO_INVALIDA", f"Forma de cobro desconocida: {codigo}") from None


def listar() -> list[dict[str, Any]]:
    return [f.describir() for f in FORMAS.values()]

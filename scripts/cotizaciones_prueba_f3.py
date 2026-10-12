"""Compuerta de F3: tres cotizaciones de prueba sobre xps_pricing_test, sus PDF y la hoja de cálculo manual.

Uso (después del ciclo 2 de la Regla 18, con la base de pruebas recién creada):
    .venv/Scripts/python.exe scripts/cotizaciones_prueba_f3.py

- Se niega a correr si la base conectada no termina en "_test".
- Crea los datos mínimos (puertos, proveedor, EUR con su tasa, tarifas, recargos, cliente) y emite:
  (a) AÉREA con tramos, volumétrico ganando y tarifa en EUR;
  (b) LCL con W/M, mínimo aplicado y seguro como % del valor;
  (c) FCL 40HC × 2 + 20GP × 1, con recargos en Ecuador (factura con IVA) y en el exterior.
- Guarda los 3 PDF en salidas/f3/ (fuera de git) y escribe docs/cierres/F3-cotizaciones-prueba.md con el
  cálculo manual paso a paso al lado de lo que dio el sistema. El cálculo manual NO usa el motor
  (services/cotizador.py): repite las reglas de §10 y H7/H8 con Decimal, para que la comparación valga.
- Si la base ya tiene datos que chocan (puertos, países EC/CN/DE, EUR, proveedores o el cliente de prueba), aborta
  sin escribir nada.
- Las condiciones generales se cargan con un texto marcado "TEXTO DE PRUEBA" y vuelven a su valor anterior (vacío
  tras la 0004) en un finally, aunque la corrida falle a mitad.
"""
import os
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import uuid4

os.environ["APP_ENV"] = "test"
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import fechas  # noqa: E402
from app.core.security import hashear_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import (  # noqa: E402
    Cliente,
    Configuracion,
    ContactoCliente,
    Cotizacion,
    Incoterm,
    Moneda,
    Pais,
    Proveedor,
    Puerto,
    Recargo,
    Region,
    Rol,
    Tarifa,
    TasaCambio,
    TipoEquipo,
    TramoAereo,
    Usuario,
)
from app.services import cotizaciones  # noqa: E402
from app.services.configuracion import leer_iva_tasa  # noqa: E402

D = Decimal
SALIDAS = RAIZ / "salidas" / "f3"
HOJA = RAIZ / "docs" / "cierres" / "F3-cotizaciones-prueba.md"
CONDICIONES = "TEXTO DE PRUEBA: condiciones generales de la compuerta de F3 (solo en la base de pruebas)."
TASA_EUR = D("1.085000")


def q(valor: Decimal, decimales: int) -> Decimal:
    return valor.quantize(D(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


# ---------- Cálculo manual (independiente del motor) ----------


@dataclass
class Manual:
    concepto: str
    pasos: list[str]
    cantidad: Decimal
    costo_usd: Decimal
    venta_unit_usd: Decimal
    subtotal_usd: Decimal
    fiscal: str
    iva: bool


def venta_metodo(metodo: str, base: Decimal, p: Decimal) -> Decimal:
    if metodo == "MARKUP":
        return q(base * (1 + p / 100), 4)
    if metodo == "MARGEN":
        return q(base / (1 - p / 100), 4)
    return q(base + p, 4)  # FIJO


def linea_manual(concepto, cantidad, costo_u, minimo, metodo, p, tasa, fiscal, iva, pasos) -> Manual:
    venta_u = venta_metodo(metodo, costo_u, p)
    venta_min = D("0.0000") if minimo == 0 else venta_metodo(metodo, minimo, p)
    costo_u_usd, minimo_usd = q(costo_u * tasa, 4), q(minimo * tasa, 4)
    venta_u_usd, venta_min_usd = q(venta_u * tasa, 4), q(venta_min * tasa, 4)
    bruto_costo, bruto_venta = q(cantidad * costo_u_usd, 4), q(cantidad * venta_u_usd, 4)
    costo_usd, subtotal = max(bruto_costo, minimo_usd), max(bruto_venta, venta_min_usd)
    pasos = pasos + [
        f"costo: {costo_u} × tasa {tasa} = {costo_u_usd} USD/u; mínimo {minimo} × {tasa} = {minimo_usd}; "
        f"max({cantidad} × {costo_u_usd} = {bruto_costo}; {minimo_usd}) = **{costo_usd}**",
        f"venta ({metodo} {p}): {costo_u} → {venta_u}; mínimo de venta {venta_min}; en USD {venta_u_usd}/u y "
        f"{venta_min_usd}; max({cantidad} × {venta_u_usd} = {bruto_venta}; {venta_min_usd}) = **{subtotal}**",
    ]
    return Manual(concepto, pasos, cantidad, costo_usd, venta_u_usd, subtotal, fiscal, iva)


def totales_manuales(lineas: list[Manual], iva_tasa: Decimal) -> dict[str, Decimal]:
    recibo = q(sum((l.subtotal_usd for l in lineas if l.fiscal == "RECIBO_CAJA"), D(0)), 2)
    factura = q(sum((l.subtotal_usd for l in lineas if l.fiscal == "FACTURA"), D(0)), 2)
    base_iva = q(sum((l.subtotal_usd for l in lineas if l.fiscal == "FACTURA" and l.iva), D(0)), 2)
    iva = q(base_iva * iva_tasa / 100, 2)
    costo = q(sum((l.costo_usd for l in lineas), D(0)), 2)
    margen = recibo + factura - costo
    return {
        "subtotal_recibo_caja": recibo, "subtotal_factura": factura, "iva": iva,
        "total_general": recibo + factura + iva, "costo_total": costo, "margen_total": margen,
        "margen_pct": q(margen / (recibo + factura) * 100, 2),
    }


# ---------- Datos de prueba ----------


@dataclass
class Datos:
    db: Session
    hoy: object
    usuario: Usuario = None
    puertos: dict = field(default_factory=dict)


def _pais(db, iso2, nombre, region) -> Pais:
    pais = Pais(iso2=iso2, nombre=nombre, region_id=region.id)
    db.add(pais)
    db.flush()
    return pais


def _puerto(db, codigo, nombre, pais, tipo) -> Puerto:
    puerto = Puerto(codigo=codigo, nombre=nombre, pais_id=pais.id, tipo=tipo)
    db.add(puerto)
    db.flush()
    return puerto


def _venta(**cambios) -> dict:
    return {"minimo": D("0"), "metodo_venta": "MARKUP", "parametro_venta": D("20")} | cambios


PUERTOS = ("FRA", "GYE", "CNSHA", "ECGYE")
PAISES = ("EC", "CN", "DE")
PROVEEDORES = ("Aerolínea de prueba F3", "Naviera de prueba F3")
RUC_CLIENTE = "0999999999001"


def conflictos(db: Session) -> list[str]:
    """Datos que chocarían con los que crea el script (solo lectura). Con alguno, el script no escribe nada."""
    encontrados = [f"puerto {c}" for c in db.scalars(select(Puerto.codigo).where(Puerto.codigo.in_(PUERTOS)))]
    encontrados += [f"país {c}" for c in db.scalars(select(Pais.iso2).where(Pais.iso2.in_(PAISES)))]
    encontrados += [f"moneda {c}" for c in db.scalars(select(Moneda.codigo).where(Moneda.codigo == "EUR"))]
    encontrados += [f"región {c}" for c in db.scalars(select(Region.codigo).where(Region.codigo == "T_F3"))]
    encontrados += [f"proveedor {n}" for n in db.scalars(select(Proveedor.nombre).where(Proveedor.nombre.in_(PROVEEDORES)))]
    encontrados += [f"cliente {r}" for r in db.scalars(select(Cliente.ruc_o_id).where(Cliente.ruc_o_id == RUC_CLIENTE))]
    return encontrados


def preparar(db: Session, hoy) -> dict:
    desde, hasta, hasta_recargos = hoy - timedelta(days=30), hoy + timedelta(days=60), hoy + timedelta(days=45)
    rol = db.scalars(select(Rol).where(Rol.codigo == "comercial")).one()
    comercial = Usuario(email=f"comercial.f3.{uuid4().hex[:6]}@prueba.xps", nombre="Comercial Prueba F3",
                        hash_password=hashear_password("ClavePrueba2026"), rol=rol)
    db.add(comercial)
    region = Region(codigo="T_F3", nombre="Región de prueba F3")
    db.add(region)
    db.flush()
    ec, cn, de = _pais(db, "EC", "Ecuador", region), _pais(db, "CN", "China", region), _pais(db, "DE", "Alemania", region)
    p = {
        "FRA": _puerto(db, "FRA", "Frankfurt", de, "AEREO"),
        "GYE": _puerto(db, "GYE", "Guayaquil (aeropuerto)", ec, "AEREO"),
        "CNSHA": _puerto(db, "CNSHA", "Shanghai", cn, "MARITIMO"),
        "ECGYE": _puerto(db, "ECGYE", "Guayaquil", ec, "MARITIMO"),
    }
    usd = db.scalars(select(Moneda).where(Moneda.codigo == "USD")).one()
    eur = Moneda(codigo="EUR", nombre="Euro", simbolo="€")
    db.add(eur)
    db.flush()
    db.add(TasaCambio(moneda_id=eur.id, tasa_a_usd=TASA_EUR, fecha_vigencia=hoy - timedelta(days=1), registrado_por=comercial.id))
    aerolinea = Proveedor(nombre=PROVEEDORES[0], pais_id=de.id)
    naviera = Proveedor(nombre=PROVEEDORES[1], pais_id=cn.id)
    db.add_all([aerolinea, naviera])
    db.flush()
    hc = db.scalars(select(TipoEquipo).where(TipoEquipo.codigo == "40HC")).one()
    gp = db.scalars(select(TipoEquipo).where(TipoEquipo.codigo == "20GP")).one()

    def tarifa(**datos) -> Tarifa:
        objeto = Tarifa(**({"valido_desde": desde, "valido_hasta": hasta, "moneda_id": usd.id} | datos))
        db.add(objeto)
        db.flush()
        return objeto

    aerea = tarifa(proveedor_id=aerolinea.id, modo="AEREO", origen_puerto_id=p["FRA"].id, destino_puerto_id=p["GYE"].id,
                   rate_unit="KG", costo=D("5.00"), moneda_id=eur.id, transit_time_dias=3,
                   **_venta(minimo=D("75"), parametro_venta=D("20")))
    for desde_kg, costo_kg in ((0, "5.00"), (45, "4.20"), (100, "3.80"), (300, "3.30"), (500, "3.00"), (1000, "2.70")):
        db.add(TramoAereo(tarifa_id=aerea.id, desde_kg=desde_kg, costo_kg=D(costo_kg)))
    tarifa(proveedor_id=naviera.id, modo="LCL", origen_puerto_id=p["CNSHA"].id, destino_puerto_id=p["ECGYE"].id,
           rate_unit="WM", costo=D("45"), transit_time_dias=35, dias_libres=7, **_venta(minimo=D("90")))
    tarifa(proveedor_id=naviera.id, modo="FCL", origen_puerto_id=p["CNSHA"].id, destino_puerto_id=p["ECGYE"].id,
           tipo_equipo_id=hc.id, rate_unit="CONTENEDOR", costo=D("2200"), transit_time_dias=32, dias_libres=21,
           **_venta(parametro_venta=D("10")))
    tarifa(proveedor_id=naviera.id, modo="FCL", origen_puerto_id=p["CNSHA"].id, destino_puerto_id=p["ECGYE"].id,
           tipo_equipo_id=gp.id, rate_unit="CONTENEDOR", costo=D("1500"), transit_time_dias=32, dias_libres=21,
           **_venta(parametro_venta=D("10")))

    def recargo(puerto, lado, bloque, concepto, unidad, costo, aplica_iva=True, **datos) -> None:
        db.add(Recargo(**({
            "proveedor_id": None, "puerto_id": p[puerto].id, "lado": lado, "bloque_incoterm": bloque,
            "concepto": concepto, "modo": None, "tipo_equipo_id": None, "rate_unit": unidad, "costo": D(costo),
            "moneda_id": usd.id, "aplica_iva": aplica_iva, "rol_ingreso": "PRINCIPAL",
            "valido_desde": desde, "valido_hasta": hasta_recargos,
        } | _venta() | datos)))

    # (a) aéreo
    recargo("FRA", "ORIGEN", "GASTOS_ORIGEN", "Security fee", "KG", "0.10", aplica_iva=False, modo="AEREO",
            moneda_id=eur.id, minimo=D("15"))
    recargo("GYE", "DESTINO", "GASTOS_DESTINO", "Handling aeroportuario", "KG", "0.15", modo="AEREO", minimo=D("25"))
    recargo("GYE", "DESTINO", "DESPACHO_IMPORT", "Agenciamiento de aduana", "ENVIO", "120", metodo_venta="FIJO",
            parametro_venta=D("30"))
    recargo("GYE", "DESTINO", "ENTREGA_FINAL", "Entrega en Guayaquil", "ENVIO", "60", parametro_venta=D("25"))
    # (b) LCL y (c) FCL comparten el puerto ECGYE
    recargo("ECGYE", "DESTINO", "GASTOS_DESTINO", "THC LCL", "WM", "12", modo="LCL", minimo=D("25"))
    recargo("ECGYE", "DESTINO", "GASTOS_DESTINO", "Desconsolidación", "ENVIO", "35", modo="LCL", metodo_venta="MARGEN")
    recargo("ECGYE", "DESTINO", "DESPACHO_IMPORT", "Agenciamiento de aduana", "ENVIO", "120", metodo_venta="FIJO",
            parametro_venta=D("30"))
    recargo("ECGYE", "DESTINO", "SEGURO", "Seguro de carga", "PCT_VALOR", "0.35", aplica_iva=False, minimo=D("25"))
    recargo("ECGYE", "DESTINO", "GASTOS_DESTINO", "THC destino", "CONTENEDOR", "180", modo="FCL", tipo_equipo_id=hc.id)
    recargo("ECGYE", "DESTINO", "GASTOS_DESTINO", "THC destino", "CONTENEDOR", "140", modo="FCL")
    recargo("ECGYE", "DESTINO", "GASTOS_DESTINO", "Emisión de BL", "ENVIO", "80", modo="FCL", metodo_venta="FIJO",
            parametro_venta=D("20"))
    recargo("CNSHA", "ORIGEN", "GASTOS_ORIGEN", "THC origen", "CONTENEDOR", "150", aplica_iva=False, modo="FCL")

    cliente = Cliente(razon_social="Importadora de Prueba F3 S.A.", tipo_id="RUC", ruc_o_id=RUC_CLIENTE,
                      pais_id=ec.id, ciudad="Guayaquil", comercial_asignado_id=comercial.id)
    db.add(cliente)
    db.flush()
    db.add(ContactoCliente(cliente_id=cliente.id, nombre="Contacto de Prueba", email="compras@prueba-f3.ec", principal=True))
    _condiciones(db).valor = CONDICIONES
    db.commit()
    incoterm = {c: db.scalars(select(Incoterm).where(Incoterm.codigo == c)).one().id for c in ("FCA", "FOB")}
    return {"comercial": comercial, "cliente": cliente, "p": p, "incoterm": incoterm, "hc": hc, "gp": gp}


# ---------- Escenarios ----------


def escenarios(d: dict) -> list[dict]:
    p, hc, gp = d["p"], d["hc"], d["gp"]
    base = {"cliente_id": d["cliente"].id, "sentido": "IMPORTACION"}
    uno = D(1)
    # (a) 4 bultos de 80 × 60 × 50 cm = 960 000 cm³ / 6000 = 160,000 kg > 120 kg reales → cobrable 160 → tramo +100.
    # El sistema ordena las líneas por bloque del Incoterm y, dentro del bloque, por concepto: aquí, el mismo orden.
    aerea = [
        linea_manual("Security fee (FRA, EUR)", D("160.0000"), D("0.10"), D("15"), "MARKUP", D("20"), TASA_EUR,
                     "RECIBO_CAJA", False, ["cantidad: 160,000 kg (KG = peso cobrable); puerto en Alemania → recibo de caja"]),
        linea_manual("Flete AEREO FRA → GYE", D("160.0000"), D("3.80"), D("75"), "MARKUP", D("20"), TASA_EUR,
                     "RECIBO_CAJA", False,
                     ["volumétrico 4 × 80 × 60 × 50 = 960 000 cm³ / 6000 = 160,000 kg; real 120 → cobrable 160,000 kg",
                      "tramo: el mayor desde_kg ≤ 160 → +100 (3,80 EUR/kg)"]),
        linea_manual("Handling aeroportuario (GYE)", D("160.0000"), D("0.15"), D("25"), "MARKUP", D("20"), uno,
                     "FACTURA", True, ["cantidad 160 kg; puerto en Ecuador → factura con IVA; aquí gana el mínimo de venta"]),
        linea_manual("Agenciamiento de aduana", uno, D("120"), D("0"), "FIJO", D("30"), uno, "FACTURA", True,
                     ["ENVIO = 1"]),
        linea_manual("Entrega en Guayaquil", uno, D("60"), D("0"), "MARKUP", D("25"), uno, "FACTURA", True, ["ENVIO = 1"]),
    ]
    # (b) W/M = max(1,2 m³; 600 kg / 1000 = 0,6) = 1,2000; el mínimo de 90 gana al flete.
    lcl = [
        linea_manual("Flete LCL CNSHA → ECGYE", D("1.2000"), D("45"), D("90"), "MARKUP", D("20"), uno, "RECIBO_CAJA", False,
                     ["W/M = max(1,2000; 600 / 1000 = 0,6000) = 1,2000"]),
        linea_manual("Seguro de carga (0,35 % del valor)", D("150.0000"), D("0.35"), D("25"), "MARKUP", D("20"), uno,
                     "RECIBO_CAJA", False, ["PCT_VALOR: 15 000 USD / 100 = 150,0000; activado a mano (se propone apagado)"]),
        linea_manual("Desconsolidación", uno, D("35"), D("0"), "MARGEN", D("20"), uno, "FACTURA", True,
                     ["MARGEN 20 %: 35 / 0,80"]),
        linea_manual("THC LCL", D("1.2000"), D("12"), D("25"), "MARKUP", D("20"), uno, "FACTURA", True,
                     ["WM 1,2000; gana el mínimo"]),
        linea_manual("Agenciamiento de aduana", uno, D("120"), D("0"), "FIJO", D("30"), uno, "FACTURA", True, ["ENVIO = 1"]),
    ]
    # (c) 40HC × 2 y 20GP × 1; THC 40HC específico y THC genérico solo para el 20GP (H6).
    fcl = [
        linea_manual("THC origen (Shanghai)", D("3.0000"), D("150"), D("0"), "MARKUP", D("20"), uno, "RECIBO_CAJA", False,
                     ["genérico FCL: cubre 40HC y 20GP = 3 contenedores; puerto en China → recibo de caja"]),
        linea_manual("Flete FCL 20GP", D("1.0000"), D("1500"), D("0"), "MARKUP", D("10"), uno, "RECIBO_CAJA", False,
                     ["1 contenedor 20GP"]),
        linea_manual("Flete FCL 40HC", D("2.0000"), D("2200"), D("0"), "MARKUP", D("10"), uno, "RECIBO_CAJA", False,
                     ["2 contenedores 40HC"]),
        linea_manual("Emisión de BL", uno, D("80"), D("0"), "FIJO", D("20"), uno, "FACTURA", True, ["ENVIO = 1"]),
        linea_manual("THC destino genérico (20GP)", D("1.0000"), D("140"), D("0"), "MARKUP", D("20"), uno, "FACTURA", True,
                     ["el genérico FCL queda solo para el 20GP"]),
        linea_manual("THC destino 40HC", D("2.0000"), D("180"), D("0"), "MARKUP", D("20"), uno, "FACTURA", True,
                     ["el específico 40HC gana para los 2 de 40HC"]),
        linea_manual("Agenciamiento de aduana", uno, D("120"), D("0"), "FIJO", D("30"), uno, "FACTURA", True, ["ENVIO = 1"]),
    ]
    return [
        {"nombre": "(a) Aérea con tramos, volumétrico y EUR", "manual": aerea, "incluir_seguro": False,
         "datos": base | {"incoterm_id": d["incoterm"]["FCA"], "modo": "AEREO", "origen_puerto_id": p["FRA"].id,
                          "destino_puerto_id": p["GYE"].id, "peso_kg": "120", "bultos": 4,
                          "dimensiones": [{"cantidad": 4, "largo_cm": "80", "ancho_cm": "60", "alto_cm": "50"}]}},
        {"nombre": "(b) LCL con W/M, mínimo y seguro", "manual": lcl, "incluir_seguro": True,
         "datos": base | {"incoterm_id": d["incoterm"]["FOB"], "modo": "LCL", "origen_puerto_id": p["CNSHA"].id,
                          "destino_puerto_id": p["ECGYE"].id, "peso_kg": "600", "cbm": "1.2",
                          "valor_mercancia_usd": "15000"}},
        {"nombre": "(c) FCL 40HC × 2 + 20GP × 1", "manual": fcl, "incluir_seguro": False,
         "datos": base | {"incoterm_id": d["incoterm"]["FCA"], "modo": "FCL", "origen_puerto_id": p["CNSHA"].id,
                          "destino_puerto_id": p["ECGYE"].id, "peso_kg": "18000",
                          "contenedores": [{"tipo_equipo_id": hc.id, "cantidad": 2}, {"tipo_equipo_id": gp.id, "cantidad": 1}]}},
    ]


# ---------- Corrida ----------


def _condiciones(db: Session) -> Configuracion:
    return db.scalars(select(Configuracion).where(Configuracion.clave == "condiciones_generales_pdf")).one()


def main() -> None:
    # Antes de abrir cualquier sesión o escribir nada.
    if not engine.url.database.endswith("_test"):
        raise SystemExit("Este script solo corre sobre la base de pruebas (_test); no se escribió nada.")
    hoy = fechas.hoy_ecuador()
    with Session(engine) as db:
        choques = conflictos(db)
        condiciones_antes = _condiciones(db).valor
    if choques:
        raise SystemExit(
            "La base ya tiene datos que chocan con los de la compuerta (" + ", ".join(choques) + "). "
            "No se escribió nada: recree xps_pricing_test (Regla 18) y vuelva a correr."
        )
    SALIDAS.mkdir(parents=True, exist_ok=True)
    secciones, diferencias = [], []
    try:
        _corrida(hoy, secciones, diferencias)
    finally:
        # Las condiciones vuelven a como estaban (vacías tras la 0004), aunque la corrida falle a mitad.
        with Session(engine) as db:
            _condiciones(db).valor = condiciones_antes
            db.commit()
    with Session(engine) as db:
        iva_tasa = leer_iva_tasa(db)
    total_dif = sum(diferencias, D(0))
    HOJA.write_text(_documento(secciones, hoy, iva_tasa, total_dif), encoding="utf-8")
    print(f"PDF en {SALIDAS}")
    print(f"Hoja en {HOJA}")
    print(f"Suma de diferencias absolutas: {total_dif}")


def _corrida(hoy, secciones: list[str], diferencias: list[Decimal]) -> None:
    with Session(engine) as db:
        d = preparar(db, hoy)
        comercial = db.get(Usuario, d["comercial"].id)
        iva_tasa = leer_iva_tasa(db)
        for esc in escenarios(d):
            creada = cotizaciones.crear_cotizacion(db, comercial, dict(esc["datos"]))
            propuesta = cotizaciones.proponer_lineas(db, comercial, creada["id"], {})
            if esc["incluir_seguro"]:
                seguro = next(l for l in propuesta["lineas"] if l["bloque_incoterm"] == "SEGURO")
                cotizaciones.actualizar_linea(db, comercial, creada["id"], seguro["id"], {"incluida": True})
            emitida = cotizaciones.emitir_cotizacion(db, comercial, creada["id"], None)
            # Costo y margen congelados (el comercial no los recibe en el JSON): se leen de la fila.
            fila = db.get(Cotizacion, creada["id"])
            internos = {"costo_total": fila.costo_total, "margen_total": fila.margen_total, "margen_pct": fila.margen_pct}
            contenido, nombre = cotizaciones.pdf_cotizacion(db, comercial, creada["id"])
            (SALIDAS / nombre).write_bytes(contenido)
            sistema = [l for l in emitida["lineas"] if l["incluida"]]
            manual_totales = totales_manuales(esc["manual"], iva_tasa)
            secciones.append(
                _seccion(esc, emitida, sistema, manual_totales, nombre, internos, propuesta["avisos"], diferencias)
            )


def _seccion(esc, emitida, sistema, manual_totales, nombre_pdf, internos, avisos_propuesta, diferencias) -> str:
    filas = []
    if len(sistema) != len(esc["manual"]):
        diferencias.append(D(999999))
        filas.append(f"> **ERROR:** el sistema dio {len(sistema)} líneas y el cálculo manual tiene {len(esc['manual'])}.")
    pasos = []
    for manual, linea in zip(esc["manual"], sistema):
        dif = abs(D(linea["subtotal_venta_usd"]) - manual.subtotal_usd)
        diferencias.append(dif)
        filas.append(
            f"| {linea['concepto']} | {linea['cantidad']} {linea['rate_unit']} | {manual.subtotal_usd} | "
            f"{linea['subtotal_venta_usd']} | {linea['bloque_fiscal']} | {q(dif, 2)} |"
        )
        pasos.append(f"- **{manual.concepto}**\n" + "\n".join(f"  - {paso}" for paso in manual.pasos))
    totales = []
    for clave, etiqueta in (("subtotal_recibo_caja", "Recibo de caja (IVA 0 %)"), ("subtotal_factura", "Factura"),
                            ("iva", "IVA"), ("total_general", "Total USD")):
        sistema_valor = D(emitida["totales"][clave])
        dif = abs(sistema_valor - manual_totales[clave])
        diferencias.append(dif)
        totales.append(f"| {etiqueta} | {manual_totales[clave]} | {sistema_valor} | {q(dif, 2)} |")
    for clave, etiqueta in (("costo_total", "Costo total"), ("margen_total", "Margen"), ("margen_pct", "Margen %")):
        sistema_valor = internos[clave]
        dif = abs(sistema_valor - manual_totales[clave])
        diferencias.append(dif)
        totales.append(f"| {etiqueta} (interno, no sale en el PDF) | {manual_totales[clave]} | {sistema_valor} | {q(dif, 2)} |")
    avisos = "\n".join(f"- {aviso}" for aviso in avisos_propuesta) or "- (ninguno)"
    return (
        f"## {esc['nombre']}\n\n"
        f"Número **{emitida['numero']}** · emitida {emitida['fecha_emision']} · válida hasta {emitida['valida_hasta']} · "
        f"PDF `salidas/f3/{nombre_pdf}`\n\n"
        "### Cálculo manual paso a paso\n\n" + "\n".join(pasos) + "\n\n"
        "### Líneas: manual frente al sistema (USD)\n\n"
        "| Concepto | Cantidad | Subtotal manual | Subtotal sistema | Fiscal | Diferencia |\n|---|---|--:|--:|---|--:|\n"
        + "\n".join(filas) + "\n\n"
        "### Totales\n\n| Total | Manual | Sistema | Diferencia |\n|---|--:|--:|--:|\n" + "\n".join(totales) + "\n\n"
        f"Avisos del sistema al proponer:\n\n{avisos}\n"
    )


def _documento(secciones: list[str], hoy, iva_tasa: Decimal, total_dif: Decimal) -> str:
    return (
        "# F3 — Cotizaciones de prueba (compuerta)\n\n"
        f"Generado por `scripts/cotizaciones_prueba_f3.py` sobre `xps_pricing_test`, con fecha {hoy.isoformat()}. "
        f"IVA leído de la configuración: {iva_tasa} %. Tasa EUR: {TASA_EUR} USD por EUR (vigente desde el día anterior).\n\n"
        "Reglas del cálculo manual (§10, H7, H8, D-F3-4): unitarios y mínimos a USD con 4 decimales; subtotal de línea = "
        "max(cantidad × unitario, mínimo) a 4 decimales; totales a 2 decimales, redondeando una vez la suma; IVA solo sobre "
        "las líneas de factura con IVA, sobre la base ya redondeada; margen sin IVA. ROUND_HALF_UP en todo.\n\n"
        f"**Suma de las diferencias absolutas (líneas y totales): {q(total_dif, 2)}** (debe ser 0,00).\n\n"
        + "\n".join(secciones)
        + "\n## Revisión de François\n\nPENDIENTE: revisar los 3 PDF y esta hoja.\n"
    )


if __name__ == "__main__":
    main()

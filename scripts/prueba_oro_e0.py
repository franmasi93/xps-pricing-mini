"""Prueba de oro de E0: el motor con servicios editables debe dar exactamente lo mismo que el de F5.

Uso:
    .venv/Scripts/python.exe scripts/prueba_oro_e0.py sembrar                 (solo sobre la base _test)
    .venv/Scripts/python.exe scripts/prueba_oro_e0.py capturar ARCHIVO.json [--fecha AAAA-MM-DD] [--base NOMBRE]
    .venv/Scripts/python.exe scripts/prueba_oro_e0.py comparar ANTES.json DESPUES.json

- sembrar: banco de cotizaciones en xps_pricing_test (aéreo kg y lb con tramos, LCL W/M y CBM, FCL con varios
  tipos, seguro % del valor, % sobre el recibo, EUR, ajustes manuales; mitad emitidas y mitad en borrador).
  Reutiliza los datos de la compuerta de F3. Se niega a correr fuera de una base "_test".
- capturar: SOLO LECTURA (la sesión termina en rollback). Por cada cotización guarda la presentación completa
  (nivel margen), las opciones de flete, la propuesta de líneas recalculada con el motor, la carga y el HTML del
  PDF (borrador en vivo o emitida desde su snapshot). La fecha "hoy" queda fija (la de la primera captura) para
  que la vista en vivo no dependa del día en que se corre.
- comparar: cada valor de ANTES debe estar igual en DESPUES (DESPUES puede traer claves nuevas). Diferencia
  cero o el script termina con código 1 y lista las diferencias.

APP_ENV: "test" para sembrar/capturar la base de pruebas; "dev" para capturar producción (solo lectura).
--base: otra base del mismo servidor y usuario (p. ej. xps_pricing_oro, la copia del banco sembrado); la
cadena de conexión se arma en memoria y nunca se imprime.
"""
import hashlib
import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))
os.environ.setdefault("APP_ENV", "test")
if "--base" in sys.argv:
    from sqlalchemy.engine import make_url

    from app.config import get_settings

    _url = make_url(get_settings().url_bd()).set(database=sys.argv[sys.argv.index("--base") + 1])
    os.environ["DATABASE_URL_TEST" if os.environ["APP_ENV"] == "test" else "DATABASE_URL"] = _url.render_as_string(
        hide_password=False
    )
    get_settings.cache_clear()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import fechas  # noqa: E402
from app.db import engine  # noqa: E402
from app.models import Cotizacion, Incoterm, Moneda, Recargo, Rol, Tarifa, TramoAereo, Usuario  # noqa: E402
from app.services import cotizaciones, pdf  # noqa: E402

D = Decimal


# ---------- Sembrar ----------


def _sembrar() -> None:
    if not engine.url.database.endswith("_test"):
        raise SystemExit("sembrar solo corre sobre la base de pruebas (_test); no se escribió nada.")
    import cotizaciones_prueba_f3 as f3

    hoy = fechas.hoy_ecuador()
    with Session(engine) as db:
        choques = f3.conflictos(db)
    if choques:
        raise SystemExit("La base ya tiene datos de la compuerta (" + ", ".join(choques) + "); recréela primero.")
    with Session(engine) as db:
        d = f3.preparar(db, hoy)
        p, hc, gp = d["p"], d["hc"], d["gp"]
        usd = db.scalars(select(Moneda).where(Moneda.codigo == "USD")).one()
        desde, hasta = hoy - timedelta(days=30), hoy + timedelta(days=60)
        naviera = db.scalars(select(Tarifa).where(Tarifa.modo == "LCL")).first().proveedor_id
        aerolinea = db.scalars(select(Tarifa).where(Tarifa.modo == "AEREO")).first().proveedor_id

        def tarifa(**datos) -> Tarifa:
            base = {"valido_desde": desde, "valido_hasta": hasta, "moneda_id": usd.id, "minimo": D("0"),
                    "metodo_venta": "MARKUP", "parametro_venta": D("20")}
            objeto = Tarifa(**(base | datos))
            db.add(objeto)
            db.flush()
            return objeto

        # Exportación: aéreo en libras con tramos, LCL por CBM con margen, FCL 20GP solo.
        lb = tarifa(proveedor_id=aerolinea, modo="AEREO", origen_puerto_id=p["GYE"].id, destino_puerto_id=p["FRA"].id,
                    rate_unit="KG", unidad_peso="LB", costo=D("2.10"), minimo=D("60"), transportista="Lufthansa Cargo",
                    transit_time_dias=2)
        for desde_lb, costo in ((0, "2.10"), (100, "1.95"), (220, "1.80"), (660, "1.60"), (1100, "1.45"), (2200, "1.30")):
            db.add(TramoAereo(tarifa_id=lb.id, desde_kg=desde_lb, costo_kg=D(costo)))
        tarifa(proveedor_id=naviera, modo="LCL", origen_puerto_id=p["ECGYE"].id, destino_puerto_id=p["CNSHA"].id,
               rate_unit="CBM", costo=D("38"), minimo=D("70"), metodo_venta="MARGEN", parametro_venta=D("25"),
               transportista="MSC Lorena", dias_libres=5)
        tarifa(proveedor_id=naviera, modo="FCL", origen_puerto_id=p["ECGYE"].id, destino_puerto_id=p["CNSHA"].id,
               tipo_equipo_id=gp.id, rate_unit="CONTENEDOR", costo=D("900"), metodo_venta="FIJO",
               parametro_venta=D("150"))

        def recargo(puerto, lado, bloque, concepto, unidad, costo, **datos) -> None:
            db.add(Recargo(**({
                "proveedor_id": None, "puerto_id": p[puerto].id, "lado": lado, "bloque_incoterm": bloque,
                "concepto": concepto, "modo": None, "tipo_equipo_id": None, "rate_unit": unidad, "costo": D(costo),
                "moneda_id": usd.id, "aplica_iva": True, "rol_ingreso": "PRINCIPAL", "valido_desde": desde,
                "valido_hasta": hasta, "minimo": D("0"), "metodo_venta": "MARKUP", "parametro_venta": D("20"),
            } | datos)))

        recargo("GYE", "DESTINO", "GASTOS_DESTINO", "Manejo sobre recibo", "PCT_RECIBO", "2", minimo=D("10"))
        recargo("GYE", "ORIGEN", "GASTOS_ORIGEN", "Handling exportación", "KG", "0.08", minimo=D("20"))
        recargo("GYE", "ORIGEN", "DESPACHO_EXPORT", "Aduana exportación", "ENVIO", "95")
        recargo("FRA", "DESTINO", "GASTOS_DESTINO", "Terminal FRA", "KG", "0.12", aplica_iva=False, modo="AEREO")
        recargo("ECGYE", "ORIGEN", "GASTOS_ORIGEN", "THC origen GYE", "WM", "10", modo="LCL", minimo=D("30"))
        recargo("ECGYE", "ORIGEN", "GASTOS_ORIGEN", "THC origen GYE", "CONTENEDOR", "160", modo="FCL")
        recargo("ECGYE", "ORIGEN", "DESPACHO_EXPORT", "Aduana exportación", "ENVIO", "110", metodo_venta="FIJO",
                parametro_venta=D("25"))
        recargo("ECGYE", "ORIGEN", "SEGURO", "Seguro exportación", "ENVIO", "45", aplica_iva=False)
        recargo("CNSHA", "DESTINO", "GASTOS_DESTINO", "THC destino Shanghai", "CBM", "9", aplica_iva=False)
        recargo("CNSHA", "DESTINO", "GASTOS_DESTINO", "Manejo sobre recibo", "PCT_RECIBO", "1.5", aplica_iva=False)
        db.commit()

        comercial = db.get(Usuario, d["comercial"].id)
        incoterm = {c: db.scalars(select(Incoterm).where(Incoterm.codigo == c)).one().id
                    for c in ("EXW", "FCA", "FOB", "CIF", "CPT", "CIP", "DAP", "DDP", "CFR")}
        base = {"cliente_id": d["cliente"].id}
        imp = base | {"sentido": "IMPORTACION"}
        exp = base | {"sentido": "EXPORTACION"}
        aereo_imp = imp | {"modo": "AEREO", "origen_puerto_id": p["FRA"].id, "destino_puerto_id": p["GYE"].id}
        aereo_exp = exp | {"modo": "AEREO", "origen_puerto_id": p["GYE"].id, "destino_puerto_id": p["FRA"].id}
        lcl_imp = imp | {"modo": "LCL", "origen_puerto_id": p["CNSHA"].id, "destino_puerto_id": p["ECGYE"].id}
        lcl_exp = exp | {"modo": "LCL", "origen_puerto_id": p["ECGYE"].id, "destino_puerto_id": p["CNSHA"].id}
        fcl_imp = imp | {"modo": "FCL", "origen_puerto_id": p["CNSHA"].id, "destino_puerto_id": p["ECGYE"].id}
        fcl_exp = exp | {"modo": "FCL", "origen_puerto_id": p["ECGYE"].id, "destino_puerto_id": p["CNSHA"].id}

        def bultos(cantidad, l, a, h):
            return {"bultos": cantidad, "dimensiones": [{"cantidad": cantidad, "largo_cm": l, "ancho_cm": a, "alto_cm": h}]}

        def bultos_in(cantidad, l, a, h):
            return {"bultos": cantidad, "dimensiones": [{"cantidad": cantidad, "largo_in": l, "ancho_in": a, "alto_in": h}]}

        casos = [
            # (datos, seguro, ajuste, emitir)
            (aereo_imp | {"incoterm_id": incoterm["FCA"], "peso_kg": "10"}, False, False, True),
            (aereo_imp | {"incoterm_id": incoterm["FCA"], "peso_kg": "44.999"}, False, True, False),
            (aereo_imp | {"incoterm_id": incoterm["EXW"], "peso_kg": "120"} | bultos(4, "80", "60", "50"), False, False, True),
            (aereo_imp | {"incoterm_id": incoterm["CPT"], "peso_kg": "350.5"}, False, False, False),
            (aereo_imp | {"incoterm_id": incoterm["CIP"], "peso_kg": "800", "valor_mercancia_usd": "20000"}, True, False, True),
            (aereo_imp | {"incoterm_id": incoterm["DAP"], "peso_kg": "1500"}, False, False, False),
            (aereo_imp | {"incoterm_id": incoterm["FCA"], "unidad_peso": "LB", "peso_lb": "225"}, False, False, True),
            (aereo_imp | {"incoterm_id": incoterm["FCA"], "unidad_peso": "LB", "peso_lb": "50"}
             | bultos_in(3, "20", "16", "12"), False, True, False),
            (aereo_exp | {"incoterm_id": incoterm["FCA"], "unidad_peso": "LB", "peso_lb": "99.9"}, False, False, True),
            (aereo_exp | {"incoterm_id": incoterm["CPT"], "unidad_peso": "LB", "peso_lb": "700"}, False, False, False),
            (aereo_exp | {"incoterm_id": incoterm["DAP"], "peso_kg": "1000"}, False, True, True),
            (aereo_exp | {"incoterm_id": incoterm["CIP"], "peso_kg": "2500"}, False, False, False),
            (lcl_imp | {"incoterm_id": incoterm["FOB"], "peso_kg": "600", "cbm": "1.2", "valor_mercancia_usd": "15000"},
             True, False, True),
            (lcl_imp | {"incoterm_id": incoterm["FOB"], "peso_kg": "3500", "cbm": "2"}, False, False, False),
            (lcl_imp | {"incoterm_id": incoterm["EXW"], "peso_kg": "250"} | bultos(5, "120", "100", "90"), False, True, True),
            (lcl_imp | {"incoterm_id": incoterm["CIF"], "peso_kg": "100", "cbm": "0.35"}, False, False, False),
            (lcl_imp | {"incoterm_id": incoterm["CFR"], "peso_kg": "900", "cbm": "4.75", "valor_mercancia_usd": "8000"},
             True, False, True),
            (lcl_exp | {"incoterm_id": incoterm["FOB"], "peso_kg": "1200", "cbm": "3.1"}, True, False, False),
            (lcl_exp | {"incoterm_id": incoterm["FCA"], "peso_kg": "400"} | bultos(2, "100", "80", "70"), False, False, True),
            (lcl_exp | {"incoterm_id": incoterm["DDP"], "peso_kg": "700", "cbm": "1"}, True, True, False),
            (fcl_imp | {"incoterm_id": incoterm["FCA"], "peso_kg": "18000",
                        "contenedores": [{"tipo_equipo_id": hc.id, "cantidad": 2}, {"tipo_equipo_id": gp.id, "cantidad": 1}]},
             False, False, True),
            (fcl_imp | {"incoterm_id": incoterm["FOB"], "peso_kg": "9000",
                        "contenedores": [{"tipo_equipo_id": gp.id, "cantidad": 3}]}, False, True, False),
            (fcl_imp | {"incoterm_id": incoterm["CIF"], "peso_kg": "22000",
                        "contenedores": [{"tipo_equipo_id": hc.id, "cantidad": 1}]}, False, False, True),
            (fcl_imp | {"incoterm_id": incoterm["EXW"], "peso_kg": "5000", "valor_mercancia_usd": "50000",
                        "contenedores": [{"tipo_equipo_id": hc.id, "cantidad": 4}, {"tipo_equipo_id": gp.id, "cantidad": 2}]},
             True, False, False),
            (fcl_exp | {"incoterm_id": incoterm["FOB"], "peso_kg": "12000",
                        "contenedores": [{"tipo_equipo_id": gp.id, "cantidad": 2}]}, True, False, True),
            (fcl_exp | {"incoterm_id": incoterm["DAP"], "peso_kg": "8000",
                        "contenedores": [{"tipo_equipo_id": gp.id, "cantidad": 1}]}, False, False, False),
        ]
        creadas = 0
        for datos, seguro, ajuste, emitir in casos:
            if seguro:
                datos = {"valor_mercancia_usd": "10000"} | datos  # el seguro % del valor exige el valor
            creada = cotizaciones.crear_cotizacion(db, comercial, dict(datos))
            propuesta = cotizaciones.proponer_lineas(db, comercial, creada["id"], {})
            if seguro:
                for linea in propuesta["lineas"]:
                    if linea["bloque_incoterm"] == "SEGURO":
                        cotizaciones.actualizar_linea(db, comercial, creada["id"], linea["id"], {"incluida": True})
            if ajuste:
                linea = propuesta["lineas"][0]
                nuevo = (D(linea["precio_venta_unit_usd"]) * D("1.07")).quantize(D("0.0001"))
                cotizaciones.actualizar_linea(db, comercial, creada["id"], linea["id"],
                                              {"precio_venta_unit_usd": str(nuevo), "motivo": "Ajuste de prueba de oro"})
            if emitir:
                cotizaciones.emitir_cotizacion(db, comercial, creada["id"], None)
            creadas += 1
        # Una emitida pasa a ACEPTADA y otra a RECHAZADA (el estado no cambia el cálculo).
        emitidas = list(db.scalars(select(Cotizacion.id).where(Cotizacion.estado == "EMITIDA").order_by(Cotizacion.id)))
        for ident, datos in zip(emitidas, ({"estado": "ACEPTADA"}, {"estado": "RECHAZADA", "motivo_rechazo": "PRECIO"})):
            cotizaciones.cambiar_estado(db, comercial, ident, datos)
        print(f"sembradas {creadas} cotizaciones ({len(emitidas)} emitidas) el {hoy.isoformat()}")


# ---------- Capturar (solo lectura) ----------


def _json(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json(v) for v in valor]
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def _linea_propuesta(linea) -> dict:
    campos = ("orden", "concepto", "bloque_incoterm", "tarifa_id", "recargo_id", "proveedor_id", "tipo_equipo_id",
              "cantidad", "rate_unit", "unidad_peso", "moneda_original_id", "tasa_aplicada", "costo_unit_original",
              "minimo_original", "costo_usd", "precio_calculado_unit_usd", "precio_venta_unit_usd", "minimo_venta_usd",
              "subtotal_venta_usd", "bloque_fiscal", "aplica_iva", "rol_ingreso", "opcional", "incluida",
              "valido_hasta_origen")
    return {campo: _json(getattr(linea, campo, None)) for campo in campos}


def _elegidas(cotizacion: Cotizacion) -> dict[str, int]:
    elegidas = {}
    for linea in cotizacion.lineas:
        if linea.tarifa is not None:
            clave = str(linea.tarifa.tipo_equipo_id) if linea.tarifa.tipo_equipo_id else cotizacion.modo
            elegidas[clave] = linea.tarifa_id
    return elegidas


def _capturar(archivo: Path, fecha: str | None) -> None:
    hoy = date.fromisoformat(fecha) if fecha else fechas.hoy_ecuador()
    fechas.hoy_ecuador = lambda: hoy  # los services llaman fechas.hoy_ecuador() en cada uso
    html_capturado: list[str] = []

    def generar_pdf_falso(html: str, pie: str = "") -> bytes:
        html_capturado.append(html + "\n<!-- pie -->\n" + pie)
        return b"%PDF-falso"

    pdf.generar_pdf = generar_pdf_falso
    salida: dict[str, Any] = {"base": engine.url.database, "hoy": hoy.isoformat(), "cotizaciones": {}}
    with Session(engine) as db:
        try:
            admin = db.scalars(
                select(Usuario).join(Rol, Usuario.rol_id == Rol.id).where(Rol.codigo == "admin", Usuario.activo.is_(True)).order_by(Usuario.id)
            ).first()
            if admin is None:  # base de pruebas: un administrador temporal que se va con el rollback
                rol = db.scalars(select(Rol).where(Rol.codigo == "admin")).one()
                admin = Usuario(email="lector.oro@prueba.xps", nombre="Lector prueba de oro", hash_password="x", rol=rol)
                db.add(admin)
                db.flush()
            for ident in db.scalars(select(Cotizacion.id).order_by(Cotizacion.id)):
                cotizacion = cotizaciones.obtener_cotizacion(db, admin, ident)
                fila: dict[str, Any] = {"estado": cotizacion.estado, "modo": cotizacion.modo}
                fila["presentacion"] = _json(cotizaciones.presentar_cotizacion(db, admin, cotizacion))
                fila["carga"] = _json(cotizaciones._carga_dict(cotizacion))
                try:
                    fila["opciones_flete"] = _json(cotizaciones.opciones_flete(db, admin, ident))
                except Exception as error:  # noqa: BLE001 - se compara el error tal cual
                    fila["opciones_flete"] = f"ERROR {type(error).__name__}: {getattr(error, 'codigo', error)}"
                try:
                    with db.no_autoflush:
                        lineas, avisos, transportista = cotizaciones._proponer(
                            db, cotizacion, _elegidas(cotizacion), cotizacion.proveedor_recargos_id, hoy
                        )
                    fila["propuesta"] = {"lineas": [_linea_propuesta(l) for l in lineas], "avisos": avisos,
                                         "transportista": transportista}
                    for linea in lineas:
                        if linea in db:
                            db.expunge(linea)
                except Exception as error:  # noqa: BLE001
                    fila["propuesta"] = f"ERROR {type(error).__name__}: {getattr(error, 'codigo', error)}"
                html_capturado.clear()
                cotizaciones.pdf_cotizacion(db, admin, ident)
                html = html_capturado[0]
                fila["pdf_html_sha256"] = hashlib.sha256(html.encode()).hexdigest()
                fila["pdf_html"] = html
                salida["cotizaciones"][str(ident)] = fila
                db.expire_all()
        finally:
            db.rollback()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(salida, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"capturadas {len(salida['cotizaciones'])} cotizaciones de {salida['base']} con hoy = {hoy} → {archivo}")


# ---------- Comparar ----------


def _diferencias(antes: Any, despues: Any, ruta: str, salida: list[str]) -> None:
    if isinstance(antes, dict) and isinstance(despues, dict):
        for clave, valor in antes.items():
            if clave not in despues:
                salida.append(f"{ruta}.{clave}: falta en DESPUES")
            else:
                _diferencias(valor, despues[clave], f"{ruta}.{clave}", salida)
    elif isinstance(antes, list) and isinstance(despues, list):
        if len(antes) != len(despues):
            salida.append(f"{ruta}: {len(antes)} elementos antes y {len(despues)} después")
        for indice, (a, b) in enumerate(zip(antes, despues)):
            _diferencias(a, b, f"{ruta}[{indice}]", salida)
    elif antes != despues:
        corto = lambda v: (str(v)[:120] + "…") if len(str(v)) > 120 else v  # noqa: E731
        salida.append(f"{ruta}: {corto(antes)!r} → {corto(despues)!r}")


def _comparar(archivo_antes: Path, archivo_despues: Path) -> None:
    antes = json.loads(archivo_antes.read_text(encoding="utf-8"))
    despues = json.loads(archivo_despues.read_text(encoding="utf-8"))
    diferencias: list[str] = []
    if antes["hoy"] != despues["hoy"]:
        diferencias.append(f"hoy distinto: {antes['hoy']} → {despues['hoy']}")
    _diferencias(antes["cotizaciones"], despues["cotizaciones"], "cotizaciones", diferencias)
    lineas = sum(len(c["presentacion"]["lineas"]) for c in antes["cotizaciones"].values())
    propuestas = sum(len(c["propuesta"]["lineas"]) for c in antes["cotizaciones"].values() if isinstance(c["propuesta"], dict))
    print(f"base {antes['base']}: {len(antes['cotizaciones'])} cotizaciones, {lineas} líneas guardadas, "
          f"{propuestas} líneas recalculadas, {len(antes['cotizaciones'])} HTML de PDF")
    for diferencia in diferencias:
        print("DIFERENCIA", diferencia)
    print(f"diferencias: {len(diferencias)}")
    sys.exit(1 if diferencias else 0)


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "sembrar":
        _sembrar()
    elif accion == "capturar" and len(sys.argv) >= 3:
        fecha = sys.argv[sys.argv.index("--fecha") + 1] if "--fecha" in sys.argv else None
        _capturar(Path(sys.argv[2]), fecha)
    elif accion == "comparar" and len(sys.argv) == 4:
        _comparar(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)

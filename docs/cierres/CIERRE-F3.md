# Acta de cierre — F3 (M7 Cotizador, emisión, numeración, estados y PDF)

| Campo | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fase | F3: M7 motor de cotización, borrador y líneas por Incoterm, emisión con número, estados, duplicar y PDF |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` (la V1.1 no se usa) |
| Commit anterior | `ead5ef6` (F2) |
| Fecha de cierre | 2026-10-12 |
| Decisor | François Ramírez — Gerente General |
| Avance del proyecto | F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · F3 30 % ✅ · **proyecto 75 %** |

---

## 1. Resumen en cristiano

El sistema ya **cotiza**. El comercial elige el cliente, la ruta, el modo y el Incoterm, y describe la carga. El sistema propone solo lo que XPRESS debe cobrar según el Incoterm y el sentido (importación o exportación): el flete con la tarifa vigente y los recargos de cada puerto, eligiendo el más específico. Calcula todo en dólares con la tasa del día: el peso cobrable, el W/M, los tramos aéreos, los mínimos, el IVA (solo en lo que se factura en Ecuador) y los totales. El seguro se propone apagado y puede ir como % del valor de la mercancía. El comercial puede ajustar un precio con un motivo, y queda auditado. Al **emitir**, la cotización recibe su número COT-AAAA-NNNNN, congela tasas, precios y textos, y ya no se edita. Después se marca aceptada o rechazada (con motivo), se puede duplicar y se descarga en **PDF** con la marca XPRESS. El PDF nunca muestra costo, margen, proveedor ni tasa. Sigue el envío por correo (F4).

## 2. Alcance

### 2.1 Tablas (migración `0004`, escrita a mano)

- `contador_cotizacion` (anio PK, ultimo): numeración anual con `SELECT … FOR UPDATE` dentro de la emisión (D-F3-1).
- `cotizacion`: cabecera, carga, estado, fechas, notas, totales congelados, `iva_tasa_aplicada`, `snapshot_emision` (JSONB), rechazo, `cotizacion_origen_id`, `activo`. CHECK nombrados para: estados; número obligatorio y formato `^[A-Z]{2,10}-[0-9]{4}-[0-9]{5}$`; emitida congelada (contacto, fechas, total, IVA, snapshot); validez ordenada; motivo de rechazo y detalle con OTRO; cantidades no negativas; origen ≠ destino; moneda USD; descartar solo el borrador.
- `cotizacion_contenedor` (tipo y cantidad > 0, único por tipo).
- `linea_cotizacion`: tarifa XOR recargo; FLETE_PRINCIPAL ⇔ tarifa; unidades (incluida PCT_VALOR); bloque fiscal; rol de ingreso; tasa > 0; montos no negativos; una línea obligatoria siempre está incluida; ajuste manual ⇔ motivo; orden único.
- `recargo`: `ck_recargo_rate_unit` acepta PCT_VALOR; `ck_recargo_seguro_unidad` (SEGURO por ENVIO o PCT_VALOR) reemplaza a `ck_recargo_seguro_por_envio`; `ck_recargo_pct_valor_solo_seguro`.
- `configuracion`: las condiciones del PDF con el texto provisional "Pendiente de definir (P5)." quedan vacías (H2); el downgrade lo restaura.
- Índices: `ix_cotizacion_comercial_estado`, `ix_cotizacion_cliente_id`, `ix_cotizacion_estado_valida_hasta`, `ix_linea_cotizacion_cotizacion_id`.

### 2.2 Endpoints (`/v1/cotizaciones`, rutas fijas antes de `/{id}`)

| Ruta | Permiso | Qué hace |
|---|---|---|
| `GET ""` (estado, cliente_id, comercial_id, vencidas, desde, hasta, limit ≤ 200, offset) | token válido + alcance | Lista paginada `{items, total, limit, offset}` |
| `POST ""` | `cotizacion.crear` | Borrador sin número (cliente en el alcance, contacto del cliente, puertos según el modo, carga mínima) |
| `GET /{id}/opciones-flete` | token + alcance | Tarifas elegibles por clave (modo o tipo de equipo), ordenadas por el subtotal de venta USD |
| `POST /{id}/proponer-lineas` | `cotizacion.crear` | Líneas según el Incoterm, con el recargo más específico y avisos |
| `PATCH /{id}/lineas/{lid}` | `cotizacion.crear` | Ajuste con motivo, quitar el ajuste, incluir o excluir líneas opcionales |
| `POST /{id}/emitir` | `cotizacion.emitir` | Número, congelado, validez (solo acortarla) |
| `POST /{id}/duplicar` | `cotizacion.crear` | Borrador nuevo; intenta proponer con las mismas tarifas |
| `POST /{id}/descartar` | `cotizacion.emitir` | Borrador → `activo=false` |
| `PATCH /{id}/estado` | `cotizacion.emitir` | ACEPTADA o RECHAZADA (con motivo) desde EMITIDA o ENVIADA |
| `GET /{id}/pdf` | token + alcance | PDF desde el snapshot; el borrador, con marca de agua |
| `GET /{id}` · `PATCH /{id}` | token + alcance · `cotizacion.crear` | Detalle (el borrador se recalcula en vivo) · editar el borrador (D-F3-10) |

Sin DELETE: 405. Alcance: sin `cotizacion.ver_todas` solo las propias; una ajena da 404. `/incoterms` ahora devuelve también el `id` (el cotizador lo envía).

### 2.3 Motor (`services/cotizador.py`, una sola fuente)

Peso volumétrico Σ(cant × L × A × H)/6000 a 3 decimales; peso cobrable = max(real, volumétrico); W/M = max(CBM, kg/1000) a 4 decimales; CBM derivado de las dimensiones; cantidades por unidad (KG, CBM, WM, CONTENEDOR por tipo o por los tipos que cubre, ENVIO, PCT_VALOR = valor/100); tramo aplicable; tasa vigente (`SIN_TASA` con moneda y fecha); unitarios y mínimos a USD con 4 decimales; subtotal = max(cantidad × unitario, mínimo); con ajuste manual, cantidad × precio ajustado sin mínimo; bloque fiscal; totales a 2 decimales una vez sobre la suma; IVA solo sobre las líneas de factura con IVA; margen sin IVA (0 si no hay venta). Reutiliza `services/precio_venta.py` y `tarifas.precio_venta_kg` (extraída de `presentar_tramos` para no duplicar la fórmula por kg).

### 2.4 PDF

`app/templates/cotizacion.html` (Jinja2 con autoescape) → Playwright síncrono (`services/pdf.py`) desde un endpoint `def`. A4 con márgenes. Logo `frontend/img/xpress-logo.png`, Inter y JetBrains Mono incrustados en base64 (nada se carga de internet). Navegador en uso: **Chromium** de Playwright (`PDF_NAVEGADOR=chromium`; `msedge` disponible como alternativa). Nombre del archivo: `COT-AAAA-NNNNN_<cliente>.pdf`; el borrador, `BORRADOR-<id>_<cliente>.pdf`.

### 2.5 Pantallas y menú

`cotizaciones.html` (P10), `cotizador.html` (P9), `cotizacion.html` (P11) y el bloque "Cotizaciones recientes" en Inicio. Una sola hoja de estilos, sin estilos en línea ni HTML inyectado; las columnas de costo y margen y el aviso rojo "Bajo el costo" se dibujan solo si la clave viene en el JSON. "Enviar por correo" queda deshabilitado con el texto "Disponible en F4".

| Rol | Cotizaciones |
|---|---|
| admin, pricing | Ven todas; crean, ajustan, emiten, cambian el estado, duplican y descartan |
| comercial | Solo las propias; crea, ajusta, emite, cambia el estado, duplica y descarta; sin costo ni margen |
| gerencia | Ve todas, con costo y margen; sin botones de escritura |

## 3. Evidencia cruda

### 3.1 Migración 0004: up → down → up (2026-10-07)

| Base | Pasos | Resultado |
|---|---|---|
| `xps_pricing_test` | `upgrade head` · `downgrade 0003` · `current` (`0003`) · `upgrade head` · `current` | todos `exit: 0` · `0004 (head)` |
| `xps_pricing` | ídem | todos `exit: 0` · `0004 (head)` |

### 3.2 Conteos del seed

```
xps_pricing       alembic=0004 rol=4 permiso=15 rol_permiso=38 moneda=1 incoterm=11 configuracion=4 tipo_equipo=5 contador_cotizacion=0 cotizacion=0 cotizacion_contenedor=0 linea_cotizacion=0
                  condiciones_generales_pdf: vacia=True largo=0
                  checks_recargo=['ck_recargo_pct_valor_solo_seguro', 'ck_recargo_rate_unit', 'ck_recargo_seguro_unidad']
xps_pricing_test  (idéntico)
```

### 3.3 pytest por parada

```
P1  modelo + recargos + incoterms + configuración + seeds:   108 passed, 1 warning in 662.01s (0:11:02)
P2  motor T215–T227:                                          32 passed, 1 warning in 11.62s
P2  tramos de F2 tras extraer precio_venta_kg:                17 passed, 67 deselected, 1 warning in 198.45s
P3  borrador y líneas T228–T241:                              36 passed, 1 warning in 976.11s (0:16:16)
P4  emisión, estados y concurrencia T242–T252:                25 passed, 1 warning in 1050.74s (0:17:30)
P5  PDF T253–T256:                                             4 passed, 1 warning in 161.56s (0:02:41)
B2  frontend, incoterms, pdf, motor, concurrencia (1.ª):     6 failed, 80 passed, 1 warning in 299.52s (0:04:59)   (incidente e)
B2  frontend + incoterms, tras corregir catalogos.py:         49 passed, 1 warning in 42.06s
B2  cotizaciones + emisión (incluye T260):                    61 passed, 1 warning in 2049.03s (0:34:09)
```

Verificación de pantallas sin base (Playwright con la API simulada): 0 errores de JS en las 7 pantallas probadas; a 375 px `scrollWidth = 375` en todas; el comercial no ve costo, margen ni "Bajo el costo"; gerencia los ve y solo tiene "Vista previa PDF". Control negativo: detecta `Unexpected token ';'`.

### 3.4 Regla 18 doble

2026-10-08, proxy PID 16836 (reiniciado a las 09:48), diagnóstico de 10 conexiones OK (~2,3 s) antes de cada ciclo. Cada ciclo: procesos Python del proyecto cerrados → `DROP` / `CREATE DATABASE xps_pricing_test` → `alembic upgrade head` (`0001` → `0004`, `exit: 0`, `0004 (head)`) → suite completa.

```
Ciclo 1 (10:31:36–11:46:07):  568 tests collected in 0.34s
                              568 passed, 1 warning in 4447.17s (1:14:07)
Ciclo 2 (11:46:49–13:00:41):  568 tests collected in 0.33s
                              568 passed, 1 warning in 4408.87s (1:13:28)
```

0 failed, 0 errors, 0 skipped; N = recolectados = 568 en ambos ciclos. Desde el inicio del ciclo 1 no cambió ningún archivo de código (solo esta acta y la hoja de la compuerta).

### 3.5 Tests nuevos por archivo (de 432 a N)

| Archivo | Tests | Cubre |
|---|:-:|---|
| `tests/test_modelo_f3.py` | 33 | T208–T214 (head, seguro PCT_VALOR por API, CHECK de recargo, cotización, contenedor, línea y contador) |
| `tests/test_cotizador_motor.py` | 32 | T215–T227 (cantidades, tramos, tasas, mínimos, IVA, redondeo, ajuste, fiscal, más específico) |
| `tests/test_cotizaciones.py` | 37 | T228–T241 y T260 (borrador, Incoterm, bloques, más específico, elegibilidad, seguro, gating, alcance, ajuste, D-F3-10, listado) |
| `tests/test_cotizaciones_emision.py` | 24 | T242–T251 (emitir, validaciones, inmutabilidad, tasa congelada, duplicar, estados, descartar, vencida, notas de auditoría) |
| `tests/test_cotizaciones_concurrencia.py` | 1 | T252 (4 hilos, números 1–4 sin duplicados) |
| `tests/test_pdf.py` | 4 | T253–T256 |
| `tests/test_frontend.py` | +5 (12 → 17) | T257 (3 pantallas), T258 (menú por permiso), T259 (`id` en `/incoterms`) |
| **Total nuevos** | **136** | 432 + 136 = **568** |

T180 (`test_recargos.py`), T118 (`test_incoterms.py`) y T124 (`test_configuracion.py`) se ajustaron sin cambiar el número de tests (sección 5).

### 3.6 Compuerta de F3: tres cotizaciones de prueba

`scripts/cotizaciones_prueba_f3.py`, corrido sobre `xps_pricing_test` justo después del ciclo 2 (2026-10-08 13:01). Hoja con el cálculo manual paso a paso: `docs/cierres/F3-cotizaciones-prueba.md`. PDF en `salidas/f3/` (fuera de git).

| Cotización | Caso | Total USD |
|---|---|--:|
| COT-2026-00001 | Aérea FCA FRA → GYE: tarifa en EUR (1,085000), volumétrico 160 kg > 120 kg reales, tramo +100 | 1105.70 |
| COT-2026-00002 | LCL FOB CNSHA → ECGYE: W/M 1,2, gana el mínimo del flete y del THC, seguro 0,35 % sobre 15 000 USD | 428.31 |
| COT-2026-00003 | FCL FCA CNSHA → ECGYE: 40HC × 2 + 20GP × 1, THC específico 40HC y genérico solo para el 20GP, recargos en China (recibo de caja) y en Ecuador (factura con IVA) | 8007.50 |

**Suma de las diferencias absolutas entre el cálculo manual y el sistema (líneas y totales, incluidos costo y margen internos): 0.00.** El cálculo manual no usa el motor.

Revisión de los PDF como imagen (EJECUTOR): logo XPRESS; bloques "Recibo de Caja (IVA 0%)" y "Factura (IVA 15%)"; totales iguales a la hoja; transit time y días libres; condiciones "TEXTO DE PRUEBA"; pie "XPRESS LOGISTICS XPS S.A. · Sistema de importaciones y exportaciones"; sin nombre de proveedor, sin la tasa 1.085000, sin costo, sin margen y sin "POSTAL". El script dejó `condiciones_generales_pdf` vacía otra vez, como estaba.

**Compuerta aprobada por François Ramírez el 2026-10-12** (revisó los 3 PDF y la hoja).

### 3.7 Canario de encoding y control de secretos

Sobre los 54 archivos del commit (el canario, sobre los 52 de texto; los dos `.ttf` son binarios), incluidas esta acta y la hoja:

```
Canario de encoding: 52 OK, 0 con fallas, 52 revisados
contraseña de pricing_app (texto plano): 0 apariciones en 54 archivos
contraseña de pricing_app (codificada en URL): 0 apariciones en 54 archivos
JWT_SECRET: 0 apariciones en 54 archivos
argumento de credenciales del proxy: 0 apariciones en 54 archivos
ruta de la carpeta local de claves (con barra invertida o normal): 0 apariciones en 54 archivos
```

(En esta acta se nombran sin el texto literal, para que el propio control de secretos siga en 0.)

## 4. Decisiones

| # | Decisión |
|---|---|
| D-F3-1 | El número COT-AAAA-NNNNN se asigna al emitir, con `contador_cotizacion` y `SELECT … FOR UPDATE` en la misma transacción. El borrador se muestra como "Borrador #id". |
| D-F3-2 | BORRADOR → EMITIDA → ENVIADA → ACEPTADA/RECHAZADA; ACEPTADA y RECHAZADA desde EMITIDA o ENVIADA; ENVIADA solo por el correo (F4); RECHAZADA con motivo PRECIO, TIEMPO, COMPETENCIA u OTRO (con detalle); los finales no cambian. |
| D-F3-3 | Seguro por ENVIO o PCT_VALOR (solo en SEGURO y en USD; el costo es el porcentaje); cantidad = valor/100 con mínimo; incluir sin valor → 422. |
| D-F3-4 | Flete y seguro → recibo de caja; recargos en Ecuador → factura; en el exterior → recibo de caja. IVA = Σ factura con IVA × iva_tasa de la configuración. Margen sin IVA. |
| D-F3-5 | Volumétrico Σ(cant × L × A × H)/6000 a 3 decimales, sin redondeo IATA; cobrable = max(real, volumétrico). |
| D-F3-6 | El seguro se propone siempre apagado. |
| D-F3-7 | Un recargo por concepto: proveedor del flete antes que NULL; luego tipo de equipo > modo > todos; otros proveedores no entran. |
| D-F3-8 | FCL con varios tipos: una tarifa por tipo, todas del mismo proveedor (si no → 422). |
| D-F3-9 | Sin flete en el Incoterm, el proveedor de los recargos es opcional; sin él, solo los propios. |
| D-F3-10 | Cambiar ruta, modo, sentido, Incoterm, carga o contenedores borra las líneas; con ajustes exige `confirmar=true` (409 `AJUSTES_SE_PIERDEN`). |
| D-F3-11 | Descartar: `POST /descartar`, solo el borrador, `activo=false`, auditado. |
| D-F3-12 | Las condiciones salen de la configuración; vacías → 422 `CONDICIONES_PDF_VACIAS`. No se inventa texto. |
| D-F3-13 | El PDF sale del snapshot congelado; el borrador, como vista previa con "BORRADOR — SIN VALIDEZ" y sin número. |
| D-F3-14 | Línea de flete: rol de ingreso PRINCIPAL, sin IVA, recibo de caja (informativo). |
| D-F3-15 | El mínimo se calcula, pero una línea opcional apagada nunca se cobra: un seguro PCT_VALOR sin valor de la mercancía existe apagado (cantidad 0), no entra en los totales ni en el PDF, e incluirlo sin valor da 422 `VALOR_MERCANCIA_REQUERIDO` (T260). El motor no se cambió. |

**Huecos de la Parada 0 (aprobados por el ASESOR):**

| # | Resolución |
|---|---|
| H1 | Logo `frontend/img/xpress-logo.png` en base64, sin copiar ni renombrar. **P2 resuelto con xpress-logo.png, pendiente de que François confirme que es el oficial.** |
| H2 | La 0004 deja vacías las condiciones provisionales; emitir con texto vacío → 422 con "Cargue las condiciones generales en Configuración antes de emitir". |
| H3 | Se reutiliza `obtener_tasa_vigente` y se traduce a 422 `SIN_TASA` con moneda y fecha. |
| H4 | El mensaje de FOB con aéreo contiene "Para aéreo use FCA, CPT o CIP". |
| H5 | Textos únicos para DDP (importación) y EXW (exportación), código `NADA_QUE_COTIZAR`. |
| H6 | En FCL, el más específico por concepto y por tipo; un genérico que gana en varios tipos da una sola línea (CONTENEDOR = suma; ENVIO = 1). |
| H7 | W/M y CBM derivado a 4 decimales; peso cobrable a 3. |
| H8 | Unitarios y mínimos a USD con 4; subtotal de línea a 4; totales a 2 una vez sobre la suma; IVA sobre la base redondeada (T223 fija el comportamiento). |
| H9 | Ajuste: cantidad × precio, sin mínimo, se permite bajo el costo; `bajo_minimo_venta` para todos y `bajo_costo` solo con `costo.ver`. |
| H10 | Las notas de la tarifa no se copian; las `notas_internas` de la cotización las ve quien ve la cotización y nunca salen en el PDF. |
| H11 | El borrador duplicado nace sin número (manda D-F3-1). |
| H12 | Chromium primero; `msedge` como alternativa (`PDF_NAVEGADOR`). Quedó en uso **Chromium**. |
| H13 | `requirements-dev.txt` con `pypdf`. |
| H14 | Concurrencia en 2099 con la función de producción, 4 hilos con `threading.Barrier`, aborta si la base no termina en `_test`, limpieza en `finally`. |
| H15 | El valor de la mercancía y las notas no borran líneas. |
| H16 | Reemplazado por D-F3-14. |
| H17 | Opciones de flete ordenadas por el subtotal de venta para la carga; sin tasa, al final con aviso. |
| H18 | Transit time y días libres: valor único o rango "x–y días"; sin flete, "—". |
| H19 | Estado y descartar: `cotizacion.emitir`; duplicar: `cotizacion.crear` (con el cliente en el alcance); leer: token + alcance. |
| H20 | Validaciones de la carga (aéreo peso > 0, LCL con CBM o dimensiones, FCL con contenedores, bultos ≥ 0, origen ≠ destino, decimales máximos). |
| H21 | IVA según D-F3-4 (no §10.5). |

**Auditoría (respuesta a la Parada 1):** sin tocar el CHECK de `accion`. Emitir, estado, duplicar, proponer y ajustar → EDITAR; descartar → DESACTIVAR. La nota empieza con la acción real en mayúsculas ("EMITIR COT-…", "ESTADO EMITIDA→RECHAZADA (PRECIO)", "DUPLICAR desde #12", "AJUSTE LINEA 3: …", "DESCARTAR BORRADOR"); T251 lo verifica.

## 5. Desvíos

| Desvío | Antes | Después | Causa |
|---|---|---|---|
| T180 (F2) | `SEGURO_SOLO_POR_ENVIO` | `SEGURO_UNIDAD_INVALIDA` (el seguro admite ENVIO o PCT_VALOR) | D-F3-3 |
| T118 (F1) | "En DDP de importación no hay nada que cotizar al comprador; …" y su par EXW | "En DDP el comprador no paga nada a XPRESS; cotice al vendedor como exportación" y "En EXW el vendedor no paga nada a XPRESS; cotice al comprador como importación" | H5 |
| T124 (F1) | `condiciones_generales_pdf = "Pendiente de definir (P5)."` | `""` | H2 |
| `linea_cotizacion.tipo_equipo_id` | — | columna agregada (muestra el tipo en FCL) | aprobado en la Parada 1 |
| CHECK de contacto al emitir | — | `ck_cotizacion_congelada_si_emitida` exige `contacto_id` | aprobado en la Parada 1 |
| §11 V1.0: el duplicado "con número nuevo" | número al duplicar | sin número hasta emitir | H11, D-F3-1 |
| §10.5 V1.0: IVA sobre toda la factura | `subtotal_factura × iva` | solo las líneas de factura con `aplica_iva` | H21, D-F3-4 |
| Licencias de las fuentes | un `OFL.txt` | `OFL-Inter.txt` y `OFL-JetBrainsMono.txt` (una por fuente) | menor |
| Filtro `desde`/`hasta` del listado | — | por la fecha de creación | menor |
| `IncotermSalida` y `routers/catalogos.py` (F1) | sin `id` | con `id` | el cotizador envía `incoterm_id` |
| Pantalla de detalle (bloque A, A2 f) | el seguro apagado mostraba su subtotal (el mínimo) | la celda dice "No incluida" | D-F3-15 |

## 6. Incidentes

| # | Incidente | Causa y corrección |
|---|---|---|
| a | T124 de F1 se rompió por H2 y no estaba en la lista de la Parada 0. | El EJECUTOR se detuvo; el ASESOR aprobó el nuevo valor esperado y la regla para seguir en casos así. |
| b | 2026-10-07 23:07: la base no respondía (apagado de las 20:00, §3.3). | El EJECUTOR se detuvo. François autorizó avanzar con lo que no necesita base: pantallas, verificación con la API simulada, script de la compuerta y esta acta. Los tests de frontend, la Regla 18 y la compuerta se corrieron con la base encendida. |
| c | En la verificación con la API simulada, la tabla de líneas desbordaba a 1280 px (scrollWidth 1404). | Se quitó la columna "Bloque" (filas de título por bloque) y el ajuste pasó a la celda del concepto: scrollWidth 1280. |
| d | La herramienta del EJECUTOR bloquea algunos comandos de PowerShell por falsos positivos ("Remove-Item" ante `c:` o expresiones regulares). | Los scripts se escribieron como archivos. Sin efecto en el código. |
| e | B2 (2026-10-08): en el bloque A se agregó `id` a `IncotermSalida`, pero `routers/catalogos.py` arma esa salida a mano y no lo pasaba. `GET /v1/incoterms` y `PATCH /v1/incoterms/{codigo}` daban `ValidationError`: 5 tests de F1 (`test_incoterms.py`) y T259 en rojo (`6 failed, 80 passed`). | Error del EJECUTOR en el código de F3. Se agregó `"id"` a los campos que copia `_incoterm_salida`; ningún valor esperado cambió. `test_frontend.py` + `test_incoterms.py`: `49 passed, 1 warning in 42.06s`. Fue antes de la Regla 18. |
| f | Revisión estática del bloque A (sin base). | Se quitaron parámetros e imports sin usar (`_guardar_calculo`, `_precios`, `_nueva_linea`, `_recalcular`; 3 tests), el script de la compuerta pasó a abortar sin escribir si hay datos que chocan y a restaurar las condiciones en un `finally`. Probado en B2 y en la Regla 18. |

## 7. Deuda

| Prioridad | Deuda |
|---|---|
| **Alta (inicio de F4)** | PDF: el concepto de las líneas de recargo por CONTENEDOR de un tipo específico debe llevar el tipo ("THC destino 40HC"); hoy el cliente ve dos "THC destino" (× 1 del genérico para el 20GP y × 2 del 40HC). |
| **Alta (inicio de F4)** | PDF: separador de miles en peso, volumen y cantidades (hoy "18000.000 kg"; los montos ya lo llevan). |
| **Alta (inicio de F4)** | PDF: una FCL larga ocupa 2 páginas (aceptado); revisar que las tablas no se corten a mitad de fila. |
| Media | La Dockerfile del despliegue debe instalar Chromium de Playwright (F5). |
| Baja | El PDF se genera a pedido (~3–12 s la primera vez por el arranque del navegador); no se guarda. |
| Baja | Duración de la suite: ~74 min por ciclo (4447,17 s y 4408,87 s; 568 tests). |
| Baja | `StarletteDeprecationWarning` (sigue desde M1). |
| Nota | El listado filtra `desde`/`hasta` por la fecha de creación. |

## 8. Pendientes

- Checklists de navegador de F1 (a–h) y F2 (10 puntos): siguen pendientes, antes de F5.
- **P1** (Tencent: dominio, plantilla, adjuntos, región) y **P3** (subusuario CAM con permiso de SES): bloquean F4.
- **P2:** confirmar que `xpress-logo.png` es el logo oficial.
- **P5:** texto real de las condiciones generales (hoy vacías en dev; emitir exige cargarlas).
- Dockerfile con Playwright y Chromium (F5).
- Rotar la contraseña de `pricing_app` y la llave del proxy antes del go-live; P9 repositorio remoto.

**Fuera de git, a propósito:** `salidas/` (ignorada), `start.txt`, `frontend/image.png`, `docs/Encender-Auth-Proxy.md`, `docs/TENCENT_CLOUD.md`, `docs/TRASPASO-XPS-Pricing-Mini_F1-M1.md`, `docs/XPS-Pricing-Mini_Arquitectura_V1.1.md` y `docs/XPS-Pricing-Mini_CIERRE-M*.md`.

## 9. Checklist de navegador F3 (para François)

Con la Console abierta (F12), en `http://127.0.0.1:8000/app`, y las condiciones generales cargadas en Configuración:

1. Comercial: abre una cotización y en F12 → Network → `cotizaciones/{id}` → Response no aparecen `costo_usd`, `costo_unit_original`, `costo_total`, `margen_total` ni `margen_pct`.
2. Cotizador: aéreo con Incoterm FOB → error "Para aéreo use FCA, CPT o CIP".
3. Al proponer las líneas, el seguro aparece **apagado**; activarlo cambia el total.
4. Ajustar un precio sin motivo → error; con motivo → aparece "Ajuste: …".
5. Emitir: recibe un número COT-AAAA-NNNNN y la validez no se puede alargar.
6. Una cotización emitida no se puede editar (no hay botones de edición; por API da 409).
7. Duplicar crea un borrador nuevo, sin número y sin los ajustes.
8. Marcar rechazada sin motivo → error; con motivo → RECHAZADA.
9. El PDF no muestra el proveedor, la tasa de cambio, el costo ni el margen, y dice "XPRESS LOGISTICS XPS S.A.".
10. 375 px (Ctrl+Shift+M) sin scroll horizontal y Console sin rojo.

Resultado: **PENDIENTE**.

## 10. Avance

F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · F3 30 % ✅ · **proyecto 75 %**. Sigue F4 (correo con Tencent SES). Commit: `0a62b2a` "F3: cotizador, emisión, numeración, estados y PDF" (54 archivos, 6518 inserciones, 21 eliminaciones), más el commit "F3: acta de cierre con hash", solo con esta acta.

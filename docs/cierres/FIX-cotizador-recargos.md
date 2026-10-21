# FIX · El cotizador no muestra los recargos relacionados

| Dato | Valor |
|---|---|
| Reportado por | François Ramírez, 2026-10-21 |
| Problema | Al elegir una tarifa, no aparecen abajo los recargos del proveedor ni los cargos propios de XPRESS, separados en Recibo de Caja y Factura |
| Base revisada | `xps_pricing` (producción), solo lectura, 2026-10-21 11:40 |

## 1. Diagnóstico

### 1.1 Lo que hay cargado

| Qué | Dato real |
|---|---|
| Tarifas vigentes y activas | **1**: id 12, LCL de **GLOVAL SHIPPING**, CNSHA → ECGYE, vigente del 19/10 al 31/10/2026 (las demás son de prueba de F5 y están inactivas) |
| Recargos activos | **1**: id 5, "Servicio Logístico" de **GLOVAL SHIPPING**, modo LCL, por W/M, USD, vigente del 19/10 al 31/10. **Cargado en el puerto CNSHA (China) con lado DESTINO y bloque GASTOS_DESTINO** |
| Recargos propios de XPRESS (sin proveedor) activos | **0** (los 4 que hay son de prueba de F5 y están inactivos) |
| Cotizaciones con esa tarifa | id 5 (borrador descartado) y **COT-2026-00002** (enviada): las dos con **1 sola línea**, el flete |

### 1.2 Recargo por recargo: ¿el motor lo propone? ¿Por qué no?

Caso: COT-2026-00002, LCL, importación, FOB, CNSHA → ECGYE, tarifa 12 (GLOVAL SHIPPING). Con FOB en importación, a XPRESS le tocan el flete, el seguro y los bloques de destino.

| Recargo | Proveedor | ¿Lo propone? | Motivo |
|---|---|---|---|
| 5 · Servicio Logístico | GLOVAL SHIPPING (el del flete) | **No** | **Otro puerto:** es un gasto de **destino**, pero está cargado en **CNSHA**, que es el **origen** de la cotización. El motor busca los gastos de destino en ECGYE. Proveedor, modo, vigencia, moneda y bloque sí coinciden |
| 1 a 4 · Recargos PRUEBA F5 | propios (sin proveedor) | No | Inactivos (datos de prueba de F5). Además, el 1 y el 2 son FCL |

**Causa principal: un dato mal cargado.** El recargo de destino quedó en el puerto de origen. El formulario de Recargos acepta cualquier combinación de puerto y lado, y nada avisa en el cotizador.

### 1.3 La pantalla

- "Proponer líneas" **sí se llama** y responde 200 (logs de Cloud Run del 19/10, de 19:40 a 19:47 hora Ecuador, cotizaciones 5 y 6). Las líneas llegan y se pintan: solo había una, el flete.
- El único rastro era un aviso genérico ("Sin recargo cargado para GASTOS_DESTINO en ECGYE"), que no dice que el recargo existe pero en otro puerto.
- **Causas de diseño** que hacían que "no hiciera correlación":
  1. las líneas se proponían con un botón aparte y en otra pantalla, no al elegir la tarifa;
  2. no se veían los recargos fuera del Incoterm, ni la alternativa descartada por D-F3-7;
  3. no se veía **por qué** un recargo no aparecía.

### 1.4 ¿Cambia el cálculo de precios?

**No.** El cálculo de cada línea, los mínimos, el IVA y los totales siguen igual. La corrección cambia **qué** recargos se muestran y cómo se eligen; no **cuánto** valen. Por eso se sigue sin detenerse. Las 3 cotizaciones de F3 (1105.70 / 428.31 / 8007.50) se vigilan al centavo.

## 2. Corrección

### 2.1 Cómo queda el cotizador

1. Eliges la tarifa en el paso 5 y **los cargos se proponen solos**, abajo, en el paso 6 "Cargos de esta cotización". Ya no hay botón aparte. Si había ajustes manuales, se pide confirmación como antes (D-F3-10).
2. **Dos bloques:**
   - **Recibo de Caja (IVA 0%):** flete, seguro y recargos del exterior;
   - **Factura (IVA n%):** recargos en Ecuador.

   Cada bloque tiene su subtotal. Debajo van el IVA y el **TOTAL GENERAL**, que el backend recalcula en cada marca.
3. **Qué recargos aparecen:**
   - los del proveedor de la tarifa y los propios de XPRESS;
   - del mismo servicio y, en FCL, del tipo de contenedor (o "todos");
   - en el puerto y lado que corresponden;
   - vigentes y activos.

   **Cómo llegan marcados:**
   - los que el Incoterm asigna a XPRESS, **marcados**;
   - los demás, **desmarcados** con la etiqueta **"Fuera del Incoterm"**;
   - D-F3-7 sigue: uno por concepto. El descartado llega en gris como **"Alternativa"**; al marcarlo, se desmarca el otro.
   - Cualquier recargo se puede marcar o desmarcar (queda auditado); el flete no.
4. **Ganancia:** solo admin, pricing y gerencia (costo.ver y margen.ver).
   - por línea: costo, venta y margen;
   - abajo: costo total, venta sin IVA, margen total y margen %.

   El comercial no recibe esas claves en el JSON.
5. **"¿Por qué no aparece?"** (solo admin y pricing, permiso tarifa.editar) lista los recargos del proveedor, los propios y los de los puertos de la cotización que quedaron fuera. Cada uno lleva su motivo:
   - vencido el dd/mm/aaaa;
   - otro puerto (y, si está cruzado, en qué puerto debería estar);
   - otro lado, otro tipo de contenedor, otro servicio u otro proveedor;
   - inactivo;
   - sin tasa de cambio.
6. **Sin recargos:** si la tarifa no tiene ninguno relacionado, aparece el aviso "Esta tarifa no tiene recargos cargados para este puerto y servicio", con enlace a Recargos (solo con tarifa.editar).
7. **Servicios:** igual para AÉREO, LCL y FCL.
8. **PDF y correo:** no cambian. Solo llevan las líneas activas, sin costo, margen ni proveedor.

### 2.2 Cambios técnicos

| Dónde | Qué |
|---|---|
| Migración `0014_seleccion_recargos` | `linea_cotizacion.seleccion` (INCOTERM, FUERA_INCOTERM, ALTERNATIVA; nula en el flete y en las líneas viejas) |
| `services/cotizaciones.py` | `_proponer` agrega desmarcadas las líneas fuera del Incoterm y las alternativas. `actualizar_linea` permite marcar o desmarcar cualquier recargo (al desmarcarlo queda opcional apagado, por la regla `opcional OR incluida`) y aplica D-F3-7 al elegir una alternativa. `margen_usd` por línea (nivel margen), `sin_recargos` y `recargos_descartados()` con sus motivos |
| `routers/cotizaciones.py` | `GET /v1/cotizaciones/{id}/recargos-descartados` (tarifa.editar) |
| `frontend/js/cargos.js` (nuevo) | el panel de cargos |
| `cotizador.html` y `cotizador.js` | propuesta automática al elegir la tarifa y paso 6 |
| `cotizacion.js` | casillas en cualquier recargo, etiquetas, margen por línea y venta sin IVA |

**No cambió:** `services/cotizador.py` (precio, mínimo, IVA y totales). Las líneas desmarcadas no entran en ningún total, en la base del % sobre recibo ni en la validez.

### 2.3 Decisiones

1. **Dato mal cargado de producción:** el recargo "Servicio Logístico" (id 5) **no se tocó**; corregirlo es del gerente (Pendientes). Ahora el cotizador lo muestra en "¿Por qué no aparece?" con el puerto donde debería estar.
2. **Recargos que trae el Incoterm:** se pueden desmarcar (antes no). Al desmarcarlos pasan a ser opcionales apagados.
3. **Alternativas en FCL:** cubren su tipo de contenedor o, si son genéricas, todos los tipos de la cotización. Elegir una desmarca la del mismo concepto, bloque y tipo.
4. **"¿Por qué no aparece?":** revisa los recargos del proveedor del flete en cualquier puerto y todos los de los puertos de la cotización, incluidos los de otros proveedores y los propios.

## 3. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18, ciclo 1 (base virgen) | **841 passed** |
| Regla 18, ciclo 2 (base virgen) | **841 passed** |
| Regresión F3 (`test_regresion_f3.py`): 1105.70 / 428.31 / 8007.50 | **al centavo**, sin cambios |
| Canario de encoding (12 archivos tocados) | 12 OK |
| Humo en Chromium, 1280 y 375 px, admin y comercial (base local, caso real armado) | sin errores de consola ni de API; sin desborde horizontal |

`tests/test_fix_cotizador.py` (TFX-01 a TFX-10):
- **caso real** en FCL, LCL y AÉREO: el recargo del proveedor y el propio aparecen marcados en Factura; el de fuera del Incoterm, desmarcado en Recibo de Caja;
- **fuera del Incoterm:** marcarlo suma al total y desmarcarlo lo resta;
- **desmarcar:** un recargo del Incoterm se puede desmarcar; el flete no;
- **alternativa D-F3-7:** se elige en lugar del ganador;
- **filtros de correlación:** otro proveedor, otro puerto, otro tipo de contenedor, otro servicio, vencido, inactivo y el puerto cruzado del caso real NO aparecen en el panel y SÍ en "¿Por qué no aparece?", con su motivo;
- **sin recargos:** aviso;
- **roles:** el comercial no ve costo ni margen y recibe 403 en "¿Por qué no aparece?"; gerencia ve el margen, pero no edita ni ve los descartes;
- **PDF:** solo las líneas activas, sin proveedor ni costo;
- **pantallas:** sin innerHTML ni estilos en línea.

**Desvío** (regla del ASESOR): 4 pruebas de `test_cotizaciones.py` (T230 y T232) contaban todas las líneas. Ahora cuentan solo las del Incoterm (o las incluidas), porque llegan además las desmarcadas. T232 además verifica que los perdedores llegan como alternativa.

**Capturas:** en `salidas/fix-cotizador/` (fuera de git):
- antes: `antes_COT-2026-00002_1280.png`, `antes_COT-2026-00002_375.png` y `antes_recargos.png`, tomadas en producción;
- después, en local: `despues_local_*`;
- después, en producción: `despues_produccion_*`.

## 4. Producción

PENDIENTE_PRODUCCION

## 5. Pendientes del gerente

1. **Corregir el recargo "Servicio Logístico" de GLOVAL SHIPPING:** en Recargos, cambiar el puerto de **CNSHA** a **ECGYE** (es un gasto de destino). Si en realidad es un gasto en China, cambiar el lado a ORIGEN y el bloque a "Gastos en origen". En cuanto se corrija, aparece solo en las cotizaciones nuevas de esa ruta.
2. **Cargar los cargos propios de XPRESS** (sin proveedor): hoy no hay ninguno activo.

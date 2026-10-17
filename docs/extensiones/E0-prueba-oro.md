# E0 · Prueba de oro: las cotizaciones existentes dan exactamente lo mismo

| Dato | Valor |
|---|---|
| Fecha | 2026-10-17 |
| Script | `scripts/prueba_oro_e0.py` (sembrar · capturar · comparar) |
| Criterio | **Diferencia cero**: todo valor capturado antes de E0 debe estar igual después (lo nuevo puede agregar claves, nunca cambiar las existentes) |
| "Hoy" de las capturas | Fijo en **2026-10-17**, para que la vista en vivo de los borradores no dependa del día en que se corre |

## 1. Qué se compara, por cotización

1. **La presentación completa con nivel margen** (el administrador ve todo):
   - todas las líneas, con cantidad, tasa, costo USD, precio calculado, precio de venta, mínimo, subtotal, bloque fiscal, IVA, opcional, incluida, ajuste manual y motivo;
   - los totales: recibo de caja, factura, IVA, total, costo total, margen y margen %;
   - la carga: peso cobrable, volumétrico, base del cobro y W/M;
   - los avisos y la validez calculada.
   
   Los borradores se recalculan en vivo; las emitidas salen de lo congelado.
2. **Las opciones de flete:** las tarifas elegibles, con el precio para esa carga y en su orden.
3. **La propuesta de líneas recalculada con el motor:** `_proponer` se corre de nuevo con las mismas tarifas elegidas. Pasa por:
   - el tramo aplicable, el peso cobrable, el W/M y los contenedores;
   - los recargos más específicos, incluida la regla por tipo de equipo (H6);
   - el % sobre recibo, el seguro % del valor y el bloque fiscal.
4. **El HTML exacto del PDF:** el del borrador en vivo o el de la emitida desde su snapshot. Incluye el pie y la frase de servicio, "vía aérea" o "vía marítima · …", y la etiqueta "Aerolínea" o "Naviera / Motonave". Si el HTML es idéntico, el PDF también lo es.

La captura es de solo lectura: la sesión termina en rollback. Dos capturas seguidas del mismo estado dieron **0 diferencias**, así que la captura es determinista.

## 2. Banco de prueba (datos equivalentes a producción, con todos los casos)

`sembrar`, con el código de F5 (0006), cargó en la base de pruebas 26 cotizaciones con **121 líneas**:

| Servicio | Borradores | Emitidas | Casos cubiertos |
|---|---|---|---|
| AEREO | 6 | 4 + 1 aceptada + 1 rechazada | Tramos en kg (EUR) y en lb (USD), peso real y volumétrico, captura en lb con pulgadas, mínimo, seguro % del valor, % sobre recibo, exportación, ajustes manuales |
| LCL | 4 | 4 | W/M con CBM y con dimensiones, tarifa por CBM con MARGEN, mínimo, seguro % del valor y por envío, exportación |
| FCL | 3 | 3 | 40HC × 2 + 20GP × 1 (genérico y específico por tipo, H6), 20GP × 3, 40HC × 4 + 20GP × 2, FIJO, exportación |

**Unidades en las líneas:** ENVIO 51, KG 24, CONTENEDOR 16, WM 10, PCT_RECIBO 9, PCT_VALOR 9 y CBM 2. Además, 6 líneas con ajuste manual y 4 cotizaciones capturadas en libras.

Después de capturar el "antes", la base se copió a `xps_pricing_oro`, se migró a **0007** y se capturó el "después" con el código de E0.

## 3. Resultado en el banco de prueba

```
base xps_pricing_test: 26 cotizaciones, 121 líneas guardadas, 121 líneas recalculadas, 26 HTML de PDF
diferencias: 0
```

## 4. Resultado en producción

- **"Antes":** capturado el 2026-10-17 sobre `xps_pricing`, en solo lectura y con el código de F5 en 0006.
- **"Después":** capturado tras el respaldo 1792276818942 y la migración a 0007, con el código de E0.

```
base xps_pricing: 4 cotizaciones, 8 líneas guardadas, 0 líneas recalculadas, 4 HTML de PDF
diferencias: 0
```

"0 líneas recalculadas" significa que en producción la propuesta de líneas no se puede rehacer: las tarifas de prueba quedaron inactivas al cerrar F5. El error que devuelve el motor (`TARIFA_NO_ELEGIBLE` o `SIN_TARIFA`) se capturó y también salió idéntico. Las líneas guardadas, los totales y el HTML del PDF son iguales.

Además, la verificación HTTP contra Cloud Run (revisión `xps-pricing-00003-7l9`) confirmó el mismo total y las mismas líneas de las 4 cotizaciones y la generación de sus PDF, con "vía aérea" y "Aerolínea".

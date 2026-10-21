# Recargos vinculados a tarifas, bloque fiscal en el recargo y proveedor solo interno

| Dato | Valor |
|---|---|
| Decisor | François Ramírez, 2026-10-21 |
| Ejecutor | Claude Code |
| Antes | FIX del cotizador (`1c7eb47`, acta `f70d7df`) desplegado y verificado: revisión `xps-pricing-00014-zdl` |
| Migración | `0015_recargos_vinculos_bloque_fiscal` (0014 → 0015), escrita a mano |
| Commits | `998fa52` (código, migración, pruebas y acta) · este cierre |
| Producción | https://pricing.xpress.ec · revisión **xps-pricing-00015-j5g** · migración **0015** |

## 1. Decisiones de François

- **D-R1 · Proveedor solo interno:** el cliente nunca ve el proveedor. En el PDF, el correo y cualquier texto hacia el cliente va solo la descripción del cargo.
- **D-R2 · Vínculos:** un recargo se puede vincular a una o varias tarifas y a uno o varios servicios. Sin vínculos sigue siendo "general" y funciona como antes.
- **D-R3 · Bloque fiscal en el recargo:** cada recargo dice si va en Recibo de Caja (IVA 0%) o en Factura. En Factura se elige si aplica IVA. Esto reemplaza la regla automática por país del puerto. El flete sigue en Recibo de Caja y el seguro, como estaba.

## 2. Qué cambió

### 2.1 D-R1: proveedor solo interno

**Revisado:** PDF (snapshot), correo de la cotización (asunto, TemplateData y nombre del adjunto), boletín y su PDF, avisos de Tencent, exportación de clientes, página pública de baja.
- **Ninguno lleva el proveedor.** El snapshot del PDF ya lo excluía.
- **El concepto** nunca se armaba con el nombre del proveedor.

**Lo que sí faltaba,** en el cotizador:
- el JSON del comercial traía el proveedor en las **opciones de flete** (nombre) y en las **líneas** (`proveedor_id`, `proveedor_propio`);
- ahora esos datos solo llegan con `costo.ver` (admin, pricing y gerencia), y las líneas traen además el nombre (`proveedor`);
- el panel de cargos dibuja la columna **Proveedor** solo si llega en el JSON;
- el comercial elige la tarifa por su transportista o por su número.

### 2.2 D-R2: vínculos

**Base de datos:**
- tablas `recargo_tarifa` y `recargo_servicio`: únicas por par y auditadas;
- `recargo.puerto_id` pasa a ser opcional.

**Recargo vinculado a tarifas:**
- **no necesita puerto:** lo toma de la tarifa según su lado (ORIGEN → origen de la tarifa; DESTINO → destino). Así no se repite el error de producción;
- debe ser del **mismo proveedor** de la tarifa o propio de XPRESS, y del mismo servicio si lo indica.

**Recargo vinculado a servicios:**
- conserva su puerto;
- solo aplica a esos servicios.

**Formulario de Recargos:**
- "Vincular a tarifas": selector múltiple, filtrado por proveedor, servicio, puerto y lado;
- "Vincular a servicios";
- "Va en: Recibo de Caja / Factura" y, en Factura, "IVA de la factura";
- antes de guardar, **advertencia de coherencia (no bloquea):** un gasto de destino en un puerto del exterior, o uno de origen en Ecuador ("¿Seguro? Este gasto de destino está en un puerto de China…").

**Ficha de la tarifa:** sección **Recargos vinculados**, con la lista, "Desvincular" y "Vincular un recargo existente" (tarifa.editar y auditoría).

**Duplicar tarifa:** casilla "Copiar también los recargos vinculados", marcada por defecto (`copiar_vinculos`).

**Cotizador:**
- primero los recargos vinculados a la tarifa elegida o a su servicio, con la etiqueta interna **"Vinculado"**; después los generales, como en el FIX;
- un vinculado **le gana** a un general del mismo concepto, que queda como "Alternativa";
- un recargo vinculado a **otra** tarifa no sale como general, y "¿Por qué no aparece?" dice "está vinculado a otra tarifa (#N)";
- el resto sigue igual: el marcado por Incoterm, "Fuera del Incoterm", "Alternativa" y "¿Por qué no aparece?".

### 2.3 D-R3: bloque fiscal en el recargo

- **`recargo.bloque_fiscal`:** obligatorio (RECIBO_CAJA o FACTURA). El motor lo usa para las líneas de recargo; el seguro va siempre en Recibo de Caja.
- **En Recibo de Caja,** el recargo se guarda sin IVA.
- **Por API sin indicarlo y con puerto,** se aplica la regla de antes.
- **Subtotales, IVA y totales:** la misma fórmula.
- **Cotizaciones emitidas:** no cambian; salen de su foto congelada.

**Migración sin cambios de precio.** Cada recargo existente recibe el bloque que hoy le asigna el motor:
- seguro → Recibo de Caja;
- puerto de Ecuador → Factura;
- exterior → Recibo de Caja.

`aplica_iva` no se toca. Los recargos insertados sin bloque (scripts y bancos de prueba) toman la misma regla, por un valor por defecto del modelo.

**Recargos de producción y el bloque asignado por la migración** (lista tomada antes de migrar; la regla es la que el motor aplicaba hasta hoy):

| Id | Concepto | Proveedor | Puerto | Lado / bloque | aplica_iva | Activo | Bloque asignado |
|---|---|---|---|---|---|---|---|
| 1 | Recargo PRUEBA F5 THC 40HC | XPRESS (propio) | ECGYE (EC) | Destino · gastos en destino | sí | no | **Factura** |
| 2 | Recargo PRUEBA F5 BL | XPRESS (propio) | ECGYE (EC) | Destino · gastos en destino | sí | no | **Factura** |
| 3 | Recargo PRUEBA F5 Manejo local | XPRESS (propio) | GYE (EC) | Destino · gastos en destino | sí | no | **Factura** |
| 4 | Recargo PRUEBA F5 Seguro | XPRESS (propio) | GYE (EC) | Destino · seguro | no | no | **Recibo de Caja** (seguro) |
| 5 | Servicio Logístico | GLOVAL SHIPPING | CNSHA (CN) | Destino · gastos en destino | sí | sí | **Recibo de Caja** (puerto del exterior) |

## 3. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18, ciclo 1 (base virgen) | **853 passed** |
| Regla 18, ciclo 2 (base virgen) | **853 passed** |
| Regresión F3: 1105.70 / 428.31 / 8007.50 | **al centavo** (`test_regresion_f3.py`, con el bloque fiscal ahora tomado del recargo) |
| Migración 0015 ida y vuelta (local) | 0015 → 0014 → 0015 sin errores |
| Canario de encoding (20 archivos) | 20 OK |
| Humo en Chromium, 1280 y 375 px, admin y comercial | sin errores de consola, de página ni de API; sin desborde horizontal |

**Humo en Chromium, detalle:**
- el formulario muestra la advertencia de coherencia ("¿Seguro? Este gasto de destino está en un puerto de…");
- la ficha de la tarifa lista el recargo vinculado;
- en el cotizador, el admin ve la columna Proveedor y el comercial no; los dos ven la etiqueta "Vinculado".

`tests/test_recargos_vinculos.py` (TRV-01 a TRV-12):
- **D-R1:** el nombre exacto del proveedor no aparece en el texto del PDF, en el TemplateData, el asunto ni el adjunto del correo, ni en el JSON del comercial (líneas y opciones de flete). Admin, pricing y gerencia sí lo ven;
- **D-R2, cotizador:** un recargo vinculado sin puerto aparece con su tarifa, en el bloque correcto por su lado. No aparece con otra tarifa, y "¿Por qué no aparece?" dice "vinculado a otra tarifa (#N)". Le gana al general del mismo concepto. Funciona el vínculo por servicio;
- **D-R2, API y duplicar:** se valida el puerto requerido y el proveedor de la tarifa; la ficha de la tarifa lista sus vínculos; se audita vincular y desvincular, y el comercial recibe 403; duplicar copia los vínculos (o no, si se pide); la advertencia de coherencia funciona;
- **D-R3:** un recargo en el exterior marcado Factura con IVA cae en Factura y suma IVA; uno en Ecuador marcado Recibo de Caja cae en Recibo sin IVA. La regla por defecto es la de la migración; el seguro va siempre en Recibo; en Recibo el recargo queda sin IVA;
- **pantallas:** sin innerHTML ni estilos en línea.

**Desvío** (regla del ASESOR): TFX-01 esperaba `proveedor_propio` en el JSON del comercial. Por D-R1 ya no le llega, y la prueba lo verifica.

**Capturas:** en `salidas/recargos-vinculos/` (fuera de git):
- `formulario_recargo.png`;
- `ficha_tarifa_vinculos.png`;
- `local_cotizador_admin_*.png` y `local_cotizador_comercial_*.png`;
- en producción, `produccion_*.png`.

## 4. Producción

| Paso | Resultado |
|---|---|
| Respaldo | **1792606297099** (SUCCESSFUL, antes de migrar) |
| Migración | `xps_pricing` 0014 → **0015**. Los 5 recargos quedaron con el bloque que les daba la regla (tabla de 2.3): **5 de 5 iguales** |
| Secretos | comparados antes de desplegar: los mismos 5 en la revisión vigente y en el comando |
| Despliegue | `docs/DESPLIEGUE.md` → **xps-pricing-00015-j5g** al 100 %; URL run.app sigue apagada; 0 errores en sus logs; `procesar-lote` responde 200 por pricing.xpress.ec |
| Salud | `/v1/salud` → `{"estado":"ok","bd":"ok"}`; pricing.xpress.ec carga |
| Regresión | **COT-2026-00002:** total 160.00, md5 del snapshot `fc1fe4d0ad7ff1c57d0e3e9355de9573`, idéntico. **COT-2026-00001:** fila, estado y HTML del PDF idénticos. Las líneas solo suman la columna nueva `vinculado` (falsa); sin ella, la huella es la de antes (6b3c24b1c8cc148e) |
| Comprobación (administrador de prueba, BORRADOR duplicado de COT-2026-00002 y luego descartado) | Cotizador con la columna **Proveedor** (GLOVAL SHIPPING) solo para el admin; flete en Recibo de Caja; total 160.00. Recargos: columna "Va en" con los 5 bloques. La ficha de la tarifa 12 muestra "Recargos vinculados" (vacía). La advertencia nueva, con el recargo 5 tal como está, dice: "¿Seguro? Este gasto de destino está en un puerto de China (CNSHA)…". Sin errores de página a 1280 y 375 px. No se creó, vinculó, emitió ni envió nada. Usuarios de prueba desactivados |

## 5. Lo que François debe ajustar (no se tocó ningún dato)

1. **"Servicio Logístico" (recargo 5, GLOVAL SHIPPING):** hoy está en CNSHA con lado DESTINO, y por eso no aparece en el cotizador. Quedó en **Recibo de Caja**, porque es lo que el motor le daba en China. Lo recomendado:
   1. Recargos → Editar el recargo 5.
   2. En "Puerto o aeropuerto", elegir **"De la tarifa vinculada"**.
   3. En "Vincular a tarifas", elegir la **#12** (LCL GLOVAL SHIPPING CNSHA → ECGYE).
   4. En "Va en", elegir lo que corresponde: probablemente **Factura** y, en "IVA de la factura", **Aplica IVA**, porque es un gasto en Guayaquil.
   5. Guardar. Desde ahí sale primero al elegir esa tarifa, con la etiqueta "Vinculado".

   Si en realidad es un gasto en China: lado ORIGEN, bloque "Gastos en origen" y Recibo de Caja.
2. **Al cargar la próxima tarifa de GLOVAL,** duplicarla desde la #12: con la casilla "Copiar también los recargos vinculados", el recargo pasa solo.
3. **Cargos propios de XPRESS:** no hay ninguno activo. Al crearlos, elegir en cada uno "Va en" Recibo de Caja o Factura.
4. **Recargos 1 a 4:** son de prueba de F5 e inactivos; no hace falta tocarlos.

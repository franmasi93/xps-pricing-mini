# Recargos con alcance en cadena y tipo de carga (IMO, refrigerada, OOG…)

| Dato | Valor |
|---|---|
| Decisor | François Ramírez, 2026-10-21 |
| Ejecutor | Claude Code |
| Base | main `03b8719`, producción en la revisión 00015 |
| Migración | `0016_alcance_recargos_tipo_carga` (0015 → 0016), escrita a mano, probada ida y vuelta |
| Commits | `3d286f2` (código, migración, pruebas y acta) · este cierre |
| Producción | https://pricing.xpress.ec · revisión **xps-pricing-00016-7h4** · migración **0016** |

## 1. Decisiones

- **D-A1 · Alcance por niveles.** Cada nivel es multiselección y "Todos" (sin valores) no filtra:
  - Servicio (E0) → Modo → Tipo de contenedor → Región → País → Puerto (el del lado) → Ruta exacta (origen + destino) → Proveedor de la tarifa → Tipo de carga → Clase IMO;
  - el vínculo a tarifas (D-R2) sigue siendo el más específico;
  - un recargo aplica si cumple todos sus niveles.
- **D-A2 · Precedencia** entre recargos del mismo concepto:
  - tarifa vinculada > ruta exacta > puerto > país > región > servicio/modo > "Todos";
  - en el mismo nivel de ubicación, un tipo de carga específico le gana a "Todos" (D-T5);
  - después, el del proveedor del flete antes que el propio;
  - después, tipo de equipo > servicio > todos (D-F3-7).

  El que pierde queda como "Alternativa", con el motivo: "Perdió contra «THC», más específico (ruta exacta)".
- **D-A3 · Lado:** sigue obligatorio. Región, país y puerto se leen contra el puerto del lado (el seguro, contra el que el motor le asigna, como siempre). La ruta compara origen y destino.
- **D-A4 · Precios:** no cambia ningún precio, mínimo, IVA ni total; solo qué recargos se proponen. "Va en" y "aplica IVA" siguen siendo del recargo.
- **D-T1..D-T8 · Tipo de carga:**
  - catálogo con CRUD: GENERAL por defecto, IMO, REFRIGERADA, SOBREDIMENSIONADA, PERECIBLE y ALTO_VALOR;
  - "pide datos IMO": clase 1–9 con subclase, UN de 4 dígitos, grupo I/II/III y MSDS;
  - la tarifa dice qué tipos acepta (por defecto solo GENERAL) y qué clases IMO excluye;
  - el tipo de carga y la clase IMO son niveles del alcance;
  - el PDF lleva la línea IMO y el texto adicional de condiciones;
  - IMO sin MSDS muestra el aviso "Falta la MSDS", sin bloquear.

## 2. Qué se hizo

### 2.1 Modelo (0016)

- **`recargo_alcance` (recargo, nivel, valor):** CHECK de nivel, un valor por fila y único por (recargo, nivel, valor). `recargo_servicio` (de 0015) pasa aquí y se retira.
- **Traducción sin cambios:** cada recargo existente recibe su alcance equivalente de hoy:
  - su puerto → PUERTO;
  - su servicio, y los servicios vinculados → SERVICIO;
  - su tipo de equipo → TIPO_EQUIPO;
  - su proveedor → PROVEEDOR.

  Un valor por defecto del modelo hace lo mismo con los recargos que insertan los scripts y los bancos de prueba.
- **`recargo.alcance_firma`:** huella del alcance cuando no es el equivalente a sus columnas (vacía en todos los de antes). La exclusión `ex_recargo_vigencia_sin_superposicion` se rehízo con la huella. Así, dos recargos del mismo concepto con alcances distintos (por ejemplo, "THC" general y "THC" solo IMO) no chocan, y entre los de antes la regla sigue igual.
- **Columnas de antes:** `recargo.puerto_id`, `modo` y `tipo_equipo_id` quedan como copia del valor cuando el nivel tiene uno solo. El dueño del cargo (`proveedor_id`) fija el nivel PROVEEDOR.
- **Tipo de carga en la base:**
  - catálogo `tipo_carga`;
  - en `cotizacion`: tipo de carga (GENERAL en las existentes), clase, UN, grupo y MSDS, con sus CHECK;
  - en `tarifa`: `tipos_carga` (`["GENERAL"]` en las existentes) y `clases_imo_excluidas`.
- **`linea_cotizacion.motivo_alternativa`:** por qué perdió una alternativa.
- **`configuracion.condiciones_imo_pdf`:** el texto adicional de condiciones para IMO (config.editar, auditado).

### 2.2 Motor y API

- **Motor (`services/alcance.py`):** una sola fuente para el cotizador, "¿Por qué no aparece?", el listado y el resumen. `cotizador.elegir_mas_especifico` recibe la precedencia por parámetro; sin parámetro, hace exactamente lo de antes.
- **Recargos:**
  - `POST/PATCH` aceptan `alcance` (servicios, modos, tipos_equipo, regiones, paises, puertos, puertos_origen, puertos_destino, proveedores, tipos_carga, clases_imo);
  - la ruta exige origen y destino; la clase IMO, un tipo que pida datos IMO;
  - la respuesta trae `alcance` y `aplica_a`;
  - `GET /v1/recargos?aplica_en=<puerto>` lista lo que aplica en ese puerto;
  - la advertencia de coherencia cubre puertos, países y regiones.
- **"¿Por qué no aparece?":**
  - incluye siempre los propios y los del proveedor del flete;
  - dice el nivel: "no aplica: el alcance de región es solo Asia y USMIA es de América del Norte";
  - lista también las tarifas que no se ofrecen por el tipo de carga ("no acepta IMO clase 1").
- **Tipos de carga y cotización:**
  - `GET/POST/PATCH /v1/tipos-carga`: leer, cualquier usuario; editar, catalogo.editar. GENERAL no se desactiva;
  - la cotización acepta `tipo_carga` y los datos IMO, que se validan, se congelan al emitir y salen en el PDF.

### 2.3 Pantallas

- **Recargos:**
  - sección "¿Dónde aplica?": cada nivel con buscador y "Ninguno = todos"; región → país → puerto se filtran solos; el tipo de contenedor aparece si el servicio lo usa; la clase IMO, si el tipo es IMO;
  - resumen en una línea ("Aplica a: …");
  - el listado tiene la columna "Aplica a" y el filtro "Aplica en (puerto)".
- **Tarifas:** "Acepta tipos de carga" y "Clases IMO excluidas"; la ficha lo muestra.
- **Tipos de carga:** pantalla nueva en Catálogos (catalogo.editar).
- **Cotizador:**
  - "Tipo de carga" y los datos IMO en el paso 3;
  - el panel de cargos muestra la línea IMO y el motivo de cada alternativa;
  - "¿Por qué no aparece?" explica el nivel y las tarifas excluidas.

**Alcance asignado a cada recargo de producción por la migración** (huella vacía = equivalente a sus columnas):

| Id | Concepto | Activo | Alcance |
|---|---|---|---|
| 1 | Recargo PRUEBA F5 THC 40HC | no | PUERTO = ECGYE · SERVICIO = FCL · TIPO_EQUIPO = 40HC |
| 2 | Recargo PRUEBA F5 BL | no | PUERTO = ECGYE · SERVICIO = FCL |
| 3 | Recargo PRUEBA F5 Manejo local | no | PUERTO = GYE |
| 4 | Recargo PRUEBA F5 Seguro | no | PUERTO = GYE |
| 5 | Servicio Logístico | sí | PUERTO = CNSHA · SERVICIO = LCL · PROVEEDOR = GLOVAL SHIPPING ("Aplica a: LCL · destino CNSHA · GLOVAL SHIPPING") |

Además:
- **Tarifas:** las 12 quedaron aceptando solo GENERAL, sin clases excluidas.
- **Cotizaciones:** las 9 quedaron GENERAL.
- **Tipos de carga sembrados:** GENERAL, IMO, REFRIGERADA, SOBREDIMENSIONADA, PERECIBLE y ALTO_VALOR.

## 3. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18, ciclo 1 (base virgen) | **881 passed** |
| Regla 18, ciclo 2 (base virgen) | **881 passed** |
| Regresión F3: 1105.70 / 428.31 / 8007.50 | **al centavo** (`test_regresion_f3.py`) |
| Migración 0016 ida y vuelta (local) | 0016 → 0015 → 0016 sin errores |
| Canario de encoding (32 archivos) | 32 OK |
| Humo en Chromium, 1280 y 375 px, admin y comercial | sin errores de consola, de página ni de API; sin desborde horizontal |

**Humo en Chromium, detalle:**
- formulario de Recargos con "¿Dónde aplica?" y su resumen;
- Tipos de carga;
- cotizador IMO clase 3, con el recargo IMO y la línea "Carga peligrosa".

`tests/test_alcance_cadena.py` (TAC-01 a TAC-16):
- **TAC-01 · la migración no cambia lo que se propone.** En 9 bancos aleatorios de 28 recargos "de antes" (FCL, LCL y AÉREO, con proveedor, servicio, contenedor y puerto variados), la propuesta del motor nuevo es **idéntica** a la de la regla de antes, en recargo y selección;
- **TAC-02:** el SQL de la migración da el mismo alcance que el valor por defecto del modelo;
- **TAC-03:** cada nivel filtra, solo y combinado, con multiselección; "Todos" no filtra; la ruta exige los dos puertos; "¿Por qué no aparece?" explica por nivel;
- **TAC-04 y TAC-05:** precedencia D-A2 completa (todos < servicio < región < país < puerto < ruta < tarifa vinculada), con el motivo de cada alternativa; empate proveedor del flete frente a propio; tipo de carga específico frente a "Todos";
- **TAC-06 y TAC-07:** API (alcance, resumen, filtro `aplica_en`, ruta incompleta, clase IMO sin tipo, edición) y advertencias por país y región;
- **TAC-08 a TAC-14, tipo de carga:**
  - una tarifa que no acepta IMO no se ofrece, y una clase excluida tampoco (con su motivo);
  - el recargo IMO aparece solo con carga IMO, y el de clase 3 no aparece con clase 8;
  - validaciones IMO; GENERAL limpia los datos IMO;
  - el PDF lleva la línea IMO y el texto adicional, y una carga GENERAL no lleva ninguno de los dos;
  - catálogo con permisos; tarifas con tipos y clases;
- **TAC-15:** el comercial sigue sin costo, margen ni proveedor;
- **TAC-16:** pantallas sin innerHTML ni estilos en línea.

**Desvíos** (regla del ASESOR: decisiones aprobadas que cambian un valor esperado):
1. T124 y T136 cuentan las claves de `configuracion`: ahora son 5, con `condiciones_imo_pdf` (D-T6).
2. TRV-04: un recargo por servicio ya no lleva la etiqueta "Vinculado"; el servicio es un nivel del alcance, más débil que la tarifa vinculada (D-A2).
3. TRV-05: el puerto ya no es obligatorio (un recargo puede aplicar a todos); un recargo sin puerto pide elegir "Va en", y se le puede quitar la última tarifa.

**Capturas:** `salidas/recargos-alcance/` (fuera de git).

## 4. Producción

| Paso | Resultado |
|---|---|
| Propuesta de antes (revisión 00015) | BORRADOR duplicado de COT-2026-00002 con la tarifa 12: solo el flete LCL, 160.00 en Recibo de Caja. Borrador descartado |
| Respaldo | **1792609088026** (SUCCESSFUL, antes de migrar) |
| Migración | `xps_pricing` 0015 → **0016** (alcance de la tabla de 2.3) |
| Secretos | comparados antes de desplegar: los mismos 5 en la revisión vigente y en el comando |
| Despliegue | `docs/DESPLIEGUE.md` → **xps-pricing-00016-7h4** al 100 %; URL run.app sigue apagada; 0 errores en sus logs; `procesar-lote` y `evaluar` responden 200 |
| Salud | `/v1/salud` → `{"estado":"ok","bd":"ok"}`; pricing.xpress.ec carga |
| **Propuesta de después** | La misma cotización y la misma tarifa: **idéntica** (líneas, bloque fiscal, selección y totales) |
| Regresión | **COT-2026-00002:** total 160.00, md5 `fc1fe4d0ad7ff1c57d0e3e9355de9573`, idéntico. **COT-2026-00001:** estado y HTML del PDF idénticos. La fila y las líneas solo suman las columnas nuevas (`tipo_carga` = GENERAL, datos IMO vacíos, `motivo_alternativa` vacío); sin ellas, las huellas son las de antes |
| Comprobación (administrador de prueba, BORRADOR descartado) | Recargos con la columna "Aplica a" y el filtro "Aplica en". Pantalla Tipos de carga. Cotizador y "¿Por qué no aparece?" (el recargo 5 sigue explicado como "otro puerto… debería estar en ECGYE"). Capturas `produccion_*.png` en `salidas/recargos-alcance/`. No se emitió ni se envió nada. Usuarios de prueba desactivados |

## 5. Datos de François

No se tocó ningún dato. Sigue pendiente lo de las actas anteriores:
- **"Servicio Logístico" (recargo 5):** vincularlo a la tarifa #12 o pasarlo a ECGYE, y elegir "Va en";
- **cargos propios de XPRESS:** cargarlos con su alcance (ver los ejemplos del mensaje final).

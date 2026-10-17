# E0 · Servicios editables: inventario y plan

| Dato | Valor |
|---|---|
| Fecha | 2026-10-17 |
| Base del trabajo | `main` en `f86cdc2` (F5 cerrada, migraciones 0001–0006) |
| Respaldo de E0.0 | Cloud SQL on-demand **1792256243896** (2026-10-17 16:57 UTC, "E0.0 analisis, antes de servicios editables") |
| Producción | La base de Cloud Run es `xps_pricing` (la misma que usa `APP_ENV=dev`): **no se migra hasta el paso de producción**, después de un respaldo nuevo. El desarrollo se hace solo sobre `xps_pricing_test`. |

## 1. Inventario de lo fijo por modo, tipo de puerto y tramos

Se buscaron `AEREO`, `LCL`, `FCL`, `MARITIMO`, los tramos (`0, 45, 100…`, `0, 100, 220…`) y `solo_maritimo` en backend, migraciones, frontend, plantillas, pruebas y scripts.

### 1.1 Base de datos (CHECK vigentes en 0006)

| Tabla | CHECK | Qué fija |
|---|---|---|
| puerto | `ck_puerto_tipo` | tipo ∈ {MARITIMO, AEREO} |
| puerto | `ck_puerto_codigo_formato` | regex UN/LOCODE para MARITIMO e IATA para AEREO |
| tarifa | `ck_tarifa_modo` | modo ∈ {AEREO, LCL, FCL} |
| tarifa | `ck_tarifa_tipo_equipo_segun_modo` | (modo = FCL) = (tipo_equipo_id no nulo) |
| tarifa | `ck_tarifa_rate_unit_segun_modo` | unidades por modo |
| tarifa | `ck_tarifa_lb_solo_aereo_por_peso` | LB solo en AEREO por KG |
| tramo_aereo | `ck_tramo_aereo_desde_kg_permitido` | desde_kg ∈ {0, 45, 100, 220, 300, 500, 660, 1000, 1100, 2200} (entero) |
| recargo | `ck_recargo_modo` | modo nulo o ∈ {AEREO, LCL, FCL} |
| recargo | `ck_recargo_tipo_equipo_solo_fcl` / `ck_recargo_contenedor_solo_fcl` | tipo de equipo y CONTENEDOR solo con FCL |
| cotizacion | `ck_cotizacion_modo` | modo ∈ {AEREO, LCL, FCL} |
| incoterm | columna `solo_maritimo` | FAS, FOB, CFR y CIF no van con AEREO |

Las exclusiones de vigencia (`ex_tarifa_…`, `ex_recargo_…`) usan la columna `modo`: se conservan tal cual.

### 1.2 Backend

| Archivo | Uso fijo |
|---|---|
| `app/models/geografia.py` | `TIPOS_PUERTO`, CHECK de tipo y regex |
| `app/models/tarifas.py` | `DESDE_KG_PERMITIDOS`, `DESDE_LB_PERMITIDOS`, `DESDE_PERMITIDOS`; `TramoAereo.desde_kg` entero |
| `app/models/incoterms.py` | `solo_maritimo` |
| `app/schemas/tarifas.py`, `cotizaciones.py` | `Modo = Literal["AEREO","LCL","FCL"]`; `desde_kg: int` |
| `app/schemas/geografia.py` | `TipoPuerto = Literal["MARITIMO","AEREO"]` |
| `app/schemas/catalogos.py` | `solo_maritimo` en salida y PATCH de Incoterms |
| `app/services/tarifas.py` | `UNIDADES_TARIFA`; puerto según modo (`PUERTO_MODO_INCONSISTENTE`); tipo de equipo solo FCL; LB solo AEREO; tramos solo AEREO por KG; `DESDE_PERMITIDOS` |
| `app/services/recargos.py` | `UNIDADES_POR_MODO`, `UNIDADES_POR_PUERTO`; puerto según modo; tipo de equipo solo FCL |
| `app/services/cotizaciones.py` | puerto según modo; LCL exige CBM o dimensiones; FCL exige contenedores; peso positivo en AEREO; `_carga_dict` (peso cobrable en AEREO, W/M en LCL); claves de flete por tipo en FCL; mismo proveedor en FCL; limpiar contenedores al salir de FCL; claves al duplicar |
| `app/services/cotizador.py` | `cantidad_cobrable` por modo; `elegir_mas_especifico` con `modo != "FCL"` |
| `app/services/incoterms.py` | `solo_maritimo` y el texto "Para aéreo use FCA, CPT o CIP" |
| `app/services/geografia.py` | `PATRON_LOCODE`, `PATRON_IATA`, prefijo del país en MARITIMO, regla de cambio de ISO2 con puertos marítimos |
| `app/services/pdf.py` | `MODO_TEXTO`; "Aerolínea" si AEREO, si no "Naviera / Motonave" |
| `app/services/correo.py` | muestra del correo de prueba con `"modo": "AEREO"` |
| `app/templates/cotizacion.html` | muestra `d.modo` y `modo_texto` (sin cambios: los textos llegan del servicio) |

### 1.3 Frontend

| Archivo | Uso fijo |
|---|---|
| `tarifas.html/js` | `MODOS`, `UNIDADES`, `DESDE` (kg y lb), opciones del select de modo, tramos solo AEREO por KG, campo de equipo solo FCL, unidad de peso solo AEREO por KG |
| `recargos.html/js` | opciones de modo, campo de equipo solo FCL, etiqueta del puerto "aeropuerto/marítimo" |
| `cotizador.html/js` | opciones de modo, tipo de puerto según modo, contenedores solo FCL, "(solo marítimo)" en Incoterms |
| `geografia.html/js` | `TIPOS` y opciones MARITIMO/AEREO |
| `incoterms.js/html` | columna y casilla "Solo marítimo" |
| `cotizacion.js` | etiqueta del transportista según AEREO |
| `inicio.js`, `cotizaciones.js` | muestran el código del modo (sin lógica) |
| `login.html` | texto comercial "Aéreo, LCL y FCL" (estático, previo al ingreso; se deja) |

### 1.4 Pruebas y scripts

- **Llaman funciones puras con el código del modo:** `test_cotizador_motor.py` y `test_f4_motor.py`, con `Carga("AEREO"…)`, `cantidad_cobrable` y `elegir_mas_especifico(…, "FCL")`. Se conservan con la misma firma; si no se indica la forma de cobro, se resuelve desde el catálogo de servicios.
- **Usan modos y tipos como datos:** `fabricas.py` (`puertos_para`, `crear_puerto(tipo=…)`) y `test_tarifas.py:117` (`TipoEquipo(...)` sin servicio). Este último se resuelve con un valor por defecto del servicio en el ORM.
- **Cuentan permisos:**
  - T03, T04 y T05 (`test_seed_rbac.py`) piden 15 permisos, 38 asignaciones y la matriz §6.2.
  - T136, T138 y T208 piden `(4, 15, 38)`.
  - Desvío inevitable: el permiso nuevo `configuracion.servicios.gestionar` exige que estas pruebas excluyan los permisos de las extensiones. La matriz §6.2 queda idéntica y una prueba nueva verifica la matriz de extensiones (ver §4).
- **Dependen de textos:**
  - `test_incoterms.py` T115 lee `incoterm.solo_maritimo`: queda como propiedad derivada de `incoterm_servicio`.
  - T119 espera "Para aéreo use FCA, CPT o CIP": el texto pasa al servicio AEREO.
  - `test_f4_motor.py:118` espera "desde lb".
  - `test_f4_pdf.py` espera "Naviera / Motonave".
- **Scripts:** `cotizaciones_prueba_f3.py` crea puertos y tarifas con los códigos actuales, que siguen siendo válidos.

## 2. Diseño

### 2.1 Formas de cobro (catálogo cerrado en código)

`app/services/formas_cobro.py` registra cuatro estrategias. Cada una define:
- **Unidades:** las de tarifa y las de recargo.
- **Banderas:** si lleva tramos, tipo de equipo o admite libras.
- **Validación de la carga.**
- **Cálculo:** la cantidad cobrable y los datos de carga para la pantalla y el PDF.
- **Claves de flete:** una sola, o una por tipo de equipo.
- **Formato de tabla:** para los boletines de E1.

| Forma | Unidades de tarifa | Unidades de recargo | Reglas que mueve sin cambiar resultados |
|---|---|---|---|
| PESO_TRAMOS | KG, ENVIO | KG, ENVIO | Peso cobrable (máx. real/volumétrico ÷ 6000), tramos por peso en kg o lb, LB solo con precio por KG, peso > 0 |
| VOLUMEN_WM | WM, CBM, ENVIO | WM, CBM, ENVIO | W/M = máx(CBM, kg/1000), exige CBM o dimensiones |
| UNIDAD_EQUIPO | CONTENEDOR | CONTENEDOR, ENVIO | Exige contenedores, una clave de flete por tipo, mismo proveedor en todas las tarifas, recargos por tipo (H6) |
| TARIFA_PLANA | ENVIO | ENVIO | Cantidad 1, sin requisitos de carga |

**Recargos sin servicio:** las unidades salen del tipo de ubicación del puerto. Son la unión de las unidades de recargo de los servicios activos que usan ese tipo, sin las que exigen tipo de equipo, y reproducen exactamente `UNIDADES_POR_PUERTO`:
- AEREO → KG, ENVIO.
- MARITIMO → WM, CBM, ENVIO.

### 2.2 Tablas nuevas (migración 0007)

- **`tipo_ubicacion`** (CRUD admin, auditado). Columnas:
  - código (inmutable una vez usado);
  - nombre;
  - `regex_codigo` (opcional; se valida al guardar);
  - `ayuda_codigo`: el mensaje si el código no cumple;
  - `prefijo_pais`: el código empieza con el ISO2 del país;
  - activo.
  
  Siembra:
  - MARITIMO "Puerto marítimo" con la regex UN/LOCODE y prefijo de país;
  - AEREO "Aeropuerto" con la regex IATA;
  - TERRESTRE "Terminal terrestre", sin regex e **inactivo**.
  
  `puerto.tipo` pasa a FK a `tipo_ubicacion.codigo` y `puerto.codigo` se amplía a 10 caracteres. Sin regex, el código usa 2 a 10 letras o números.
- **`servicio`** (CRUD admin, auditado). Columnas:
  - código (inmutable una vez usado);
  - nombre;
  - `forma_cobro`;
  - `tipo_ubicacion_origen` y `tipo_ubicacion_destino`;
  - `usa_tipo_equipo`;
  - `permite_libras`;
  - orden y activo;
  - textos: `descripcion_pdf` (antes `MODO_TEXTO`), `etiqueta_transportista` (antes "Aerolínea" o "Naviera / Motonave") y `aviso_incoterm` (antes "es solo marítimo. Para aéreo use FCA, CPT o CIP").
  
  Siembra AEREO, LCL y FCL con los textos actuales idénticos. Se borra solo si nunca se usó (tarifas, recargos, cotizaciones, tipos de equipo o tramos usados). La forma de cobro tampoco cambia si el servicio ya tiene tarifas, recargos o cotizaciones.
- **`tipo_equipo.servicio_id`:** FK obligatoria; los 5 existentes quedan en FCL. Por defecto se usa el primer servicio activo con tipo de equipo (por orden).
- **`servicio_tramo`** (CRUD admin, auditado; solo servicios PESO_TRAMOS). Columnas: servicio, `unidad_peso` (KG o LB), desde (`NUMERIC(10,3)`), orden y activo.
  - Siembra AEREO KG 0, 45, 100, 300, 500, 1000 y LB 0, 100, 220, 660, 1100, 2200.
  - `tramo_aereo.desde_kg` pasa a `NUMERIC(10,3)` sin alterar valores y el CHECK fijo se reemplaza por la validación contra los tramos activos del servicio.
  - Un tramo usado por alguna tarifa no se borra ni cambia su "desde": solo se desactiva.
- **`incoterm_servicio`:** reemplaza `solo_maritimo`.
  - Siembra: LCL y FCL en los 11 Incoterms; AEREO en los 7 que no eran solo marítimos.
  - La API conserva `solo_maritimo` como dato derivado (verdadero si todos los servicios permitidos van de puerto marítimo a puerto marítimo) y agrega `servicios`.
  - Se edita en el PATCH de Incoterms (solo admin, auditado).
  - Un servicio nuevo hereda los Incoterms del servicio existente con los mismos tipos de ubicación; si no hay ninguno, recibe todos.
- **Columnas `modo` de tarifa, recargo y cotización:** conservan nombre y valores, se amplían a 10 caracteres y pasan a FK a `servicio.codigo`. Se eliminan los CHECK de 1.1.
- **Permiso `configuracion.servicios.gestionar`:** solo para admin.

### 2.3 Lógica

- **Fuente única:**
  - `app/services/servicios.py`: `servicios_activos(db)` (activos y ordenados) y `obtener_servicio(db, codigo)`.
  - La API: `GET /v1/servicios` y `GET /v1/formas-cobro`.
  - E1 y E3 usan esta fuente.
- **Tarifas, recargos y cotizaciones:**
  - Validan con servicio → forma de cobro.
  - Un servicio inactivo no se acepta para tarifas, recargos ni cotizaciones nuevas (`PADRE_INACTIVO`).
  - Lo histórico se sigue leyendo, recalculando y emitiendo igual.
- **Motor:** `Carga` gana `forma_cobro`. Si no viene, como en las pruebas de funciones puras, se resuelve desde el catálogo. `elegir_mas_especifico` recibe `por_tipo_equipo` con la misma regla de respaldo.
- **PDF:** la emisión congela `servicio` (código, nombre, descripción y etiqueta) en el snapshot. Para las emitidas antes de E0 se leen los textos del servicio, sembrados idénticos, así que el PDF sale igual.
- **Códigos de error:** se conservan todos. Los mensajes que nombraban un modo ahora nombran el servicio.
- **Moneda de cotización:** sigue siendo solo USD (`ck_cotizacion_moneda_usd`), fuera de alcance.

### 2.4 Pantallas

- **Administración → Servicios** (`servicios.html`): tabla y formulario. Al elegir la forma de cobro se muestran sus unidades y campos. La pestaña "Tramos" aparece solo en los servicios por peso.
- **Administración → Tipos de ubicación** (`tipos-ubicacion.html`).
- **Catálogos → Tipos de equipo** (`tipos-equipo.html`, nueva; antes no había pantalla), con el campo Servicio (solo servicios con tipo de equipo).
- **Incoterms:** casillas de servicios permitidos.
- **Tarifas, recargos y cotizador:**
  - "Modo" pasa a "Servicio": servicios activos y ordenados en los formularios; todos en los filtros.
  - Los campos aparecen según la forma de cobro.
  - Los tramos salen del catálogo.
- **Geografía:** los tipos salen del catálogo.

## 3. Prueba de oro

Script `scripts/prueba_oro_e0.py`:
- **sembrar:** 26 cotizaciones en `xps_pricing_test`, de los 3 modos:
  - aéreo en kg y lb con tramos, volumétrico y EUR;
  - LCL por W/M y por CBM, con mínimos;
  - FCL con 1 o 2 tipos de equipo;
  - seguro % del valor, % sobre el recibo y ajustes manuales;
  - 13 emitidas (una aceptada y otra rechazada) y 13 en borrador.
- **capturar:** solo lectura y con fecha fija. Por cotización guarda:
  - la presentación completa con costos y márgenes;
  - las opciones de flete;
  - la propuesta de líneas recalculada con el motor;
  - la carga;
  - el HTML exacto del PDF.
- **comparar:** diferencia cero exigida.

El "antes" ya está capturado con el código de F5 en `salidas/e0/oro_antes_test.json` (26) y `salidas/e0/oro_antes_prod.json` (las 4 de producción). La captura es determinista: una segunda captura dio 0 diferencias. El "después" se captura tras la 0007 y el código nuevo, en la base de pruebas y luego en producción. El resultado queda en `docs/extensiones/E0-prueba-oro.md`.

## 4. Pruebas nuevas y desvíos

- `tests/test_e0_servicios.py`:
  - CRUD y permisos de servicios, tramos y tipos de ubicación;
  - código inmutable, servicio y tramo usados que no se borran;
  - servicio inactivo que no se ofrece pero lo histórico sí;
  - Courier PESO_TRAMOS con tramos 0; 0,5; 1; 5; 10 kg cotizando 0,8 kg con PDF;
  - servicio UNIDAD_EQUIPO con un tipo de equipo nuevo;
  - TARIFA_PLANA;
  - Incoterm por servicio;
  - regex inválida rechazada;
  - migración ida y vuelta.
- **Desvío D-E0-1 (permisos):** T03, T04, T05, T136, T138 y T208 cuentan solo los permisos de §6.2 (excluyen los de `matriz_rbac.PERMISOS_EXTENSIONES`). Los valores esperados (4, 15, 38 y la matriz §6.2) no cambian.

## 5. Orden de ejecución

1. **E0.1:** modelos y servicios de catálogo (tipo_ubicacion, servicio, servicio_tramo, incoterm_servicio), estrategias y fuente única.
2. **E0.2:** migración 0007 con upgrade y downgrade probados ida y vuelta en `xps_pricing_test`.
3. **E0.3:** la lógica de tarifas, recargos, cotizaciones, motor, Incoterms, geografía y PDF pasa a servicio → forma de cobro. Suite completa y prueba de oro.
4. **E0.4:** pantallas.
5. **E0.5:**
   - Regla 18 doble;
   - commits;
   - respaldo nuevo;
   - migrar producción;
   - desplegar;
   - salud;
   - prueba de oro en producción y 3 cotizaciones con el mismo total y el mismo PDF;
   - `docs/cierres/CIERRE-E0.md`.

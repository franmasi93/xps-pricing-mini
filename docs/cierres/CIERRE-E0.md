# Acta de cierre · E0 · Servicios editables

| Dato | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini · extensiones |
| Extensión | E0 (35 % de las extensiones E0–E3) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code |
| Fecha de cierre | 2026-10-17 |
| Commits | `b13d9eb` "E0.0–E0.3: servicios editables (catálogos, migración 0007, formas de cobro y lógica)" · `09ab49c` "E0.4: pantallas…" · esta acta (ver `git log`) |
| Migración | `0007_e0_servicios_editables` (0006 → 0007) |
| Respaldos de producción | **1792256243896** (E0.0, análisis) · **1792276818942** (justo antes de migrar) |
| Producción | https://xps-pricing-809824844407.us-central1.run.app · revisión `xps-pricing-00003-7l9` |

## 1. Resumen en cristiano

Antes, los tipos de transporte estaban escritos en el código. Eran tres (aéreo, marítimo LCL y marítimo FCL), con sus tramos de peso fijos y la regla "FOB no va con aéreo" en código. Ahora son **servicios** que el administrador crea y edita desde la pantalla.

Cada servicio elige una **forma de cobro**, que define cómo se calcula:

| Forma de cobro | Cómo cobra | Equivalente anterior |
|---|---|---|
| Por peso con tramos | Por kg o lb, con tramos | El aéreo de siempre |
| Por volumen W/M | Por W/M o por m³ | LCL |
| Por unidad de equipo | Por contenedor o camión | FCL |
| Tarifa plana | Un precio por envío | — |

Además, el administrador define:
- **Dónde opera cada servicio:** los tipos de ubicación de origen y destino (aeropuerto, puerto marítimo, terminal terrestre…).
- **Los tramos de peso**, con decimales (0,5 kg para un courier).
- **Los Incoterms permitidos**, con casillas por servicio.

Para agregar un servicio como Courier o Terrestre ya **no hace falta tocar el código** (ver §9).

Lo existente quedó exactamente igual. La **prueba de oro** recalculó todas las cotizaciones con la lógica nueva y comparó línea por línea, los totales y el HTML del PDF contra la lógica anterior. **Diferencia cero:**
- 26 cotizaciones en el banco de prueba;
- las 4 de producción.

## 2. Avance por fase

| Fase | Peso | Estado |
|---|---|---|
| E0.0 Análisis y respaldo | 4 % | Hecho: inventario y plan en `docs/extensiones/E0-PLAN.md`; respaldo 1792256243896; "antes" de la prueba de oro capturado con el código de F5 |
| E0.1 Catálogos | 7 % | Hecho: servicio, tipo de ubicación, tramos por servicio, Incoterms por servicio; estrategias de forma de cobro; fuente única |
| E0.2 Migración | 7 % | Hecho: 0007 con upgrade y downgrade probados ida y vuelta (esquema y datos idénticos a 0006 tras el downgrade) |
| E0.3 Lógica | 10 % | Hecho: tarifas, recargos, cotizaciones, motor, Incoterms, geografía y PDF resuelven todo con servicio → forma de cobro |
| E0.4 Pantallas | 4 % | Hecho: Servicios (con pestaña Tramos), Tipos de ubicación, Tipos de equipo; "Modo" pasa a "Servicio" en tarifas, recargos y cotizador; Incoterms con casillas de servicios |
| E0.5 Cierre | 3 % | Hecho: Regla 18 doble, commits, respaldo, migración, despliegue y verificación. **Pendiente: el push a GitHub**, que el permiso de Claude Code bloqueó (ver §8) |
| **Total E0** | **35 %** | **35 %** (el push queda pendiente de autorización) |

## 3. Qué se construyó

### 3.1 Datos (migración 0007)

**Tablas nuevas**

| Tabla | Contenido | Siembra |
|---|---|---|
| `tipo_ubicacion` | Código, nombre, regla del código (regex opcional), mensaje de ayuda, prefijo del país, activo | MARITIMO "Puerto marítimo" (UN/LOCODE con el ISO del país) y AEREO "Aeropuerto" (IATA), con las reglas actuales; TERRESTRE "Terminal terrestre", sin regex e inactivo |
| `servicio` | Código (inmutable una vez usado), nombre, forma de cobro, tipos de ubicación de origen y destino, usa tipo de equipo, permite libras, orden, textos del PDF (descripción y etiqueta del transportista), aviso de Incoterm, activo | AEREO "Aéreo", LCL "Marítimo LCL" y FCL "Marítimo FCL", con los mismos códigos y los textos del PDF de F4, idénticos |
| `servicio_tramo` | Tramos permitidos por servicio y unidad (KG o LB), en `NUMERIC(10,3)` | AEREO, exactamente los de antes: KG 0, 45, 100, 300, 500, 1000; LB 0, 100, 220, 660, 1100, 2200 |
| `incoterm_servicio` | Servicios permitidos por Incoterm | Mismo comportamiento que `solo_maritimo`: LCL y FCL en los 11; AEREO en todos menos FAS, FOB, CFR y CIF |

**Cambios en tablas existentes**
- `tipo_equipo.servicio_id`: los 5 tipos existentes quedan en FCL.
- `puerto.tipo`: pasa a FK a `tipo_ubicacion.codigo`; `puerto.codigo` admite 10 caracteres.
- `tarifa.modo`, `recargo.modo` y `cotizacion.modo`: conservan nombre y valores y pasan a FK a `servicio.codigo`. Se quitaron los 8 CHECK por modo. Como respaldo genérico quedan "tipo de equipo y CONTENEDOR solo con servicio".
- `tramo_aereo.desde_kg`: pasa de entero a `NUMERIC(10,3)` sin alterar valores. El CHECK fijo se reemplazó por la validación contra los tramos activos del servicio.
- `incoterm.solo_maritimo`: se reemplaza por `incoterm_servicio`. La API lo sigue devolviendo como dato derivado.
- **Permiso nuevo:** `configuracion.servicios.gestionar`, solo para admin.

### 3.2 Lógica

- **`app/services/formas_cobro.py`:** las 4 estrategias. Cada una tiene sus unidades, la validación de la carga, la cantidad cobrable, los datos de carga para la pantalla y el PDF, las claves de flete y las columnas para los boletines de E1. La lógica es la de F2–F5 movida sin cambios de resultado.
- **`app/services/servicios.py`:**
  - **Fuente única:** `servicios_activos(db)`, que también usarán E1 y E3.
  - **CRUD** de servicios, tramos y tipos de ubicación, con auditoría.
  - **Reglas de uso:**
    - un servicio usado no cambia de código, forma de cobro ni ubicaciones, y no se borra;
    - un tramo usado no se borra ni cambia su "desde";
    - una regla de código nueva no puede dejar inválidos los puertos existentes.
- Tarifas, recargos, cotizaciones, motor, Incoterms, geografía y PDF ya no tienen constantes ni `if` por modo.
- La emisión congela en el snapshot el servicio y sus textos del PDF. Para las emitidas antes de E0, los textos se leen del servicio, sembrado idéntico, y el PDF sale igual.

### 3.3 API

- **Lectura** (cualquier usuario habilitado):
  - `GET /v1/servicios`;
  - `GET /v1/formas-cobro`;
  - `GET /v1/tipos-ubicacion`.
- **Escritura** (solo `configuracion.servicios.gestionar`):
  - servicios: `POST /v1/servicios`, `PATCH /v1/servicios/{id}` y `DELETE /v1/servicios/{id}` (solo si nunca se usó);
  - tramos: `POST /v1/servicios/{id}/tramos`, `PATCH /v1/servicio-tramos/{id}` y `DELETE /v1/servicio-tramos/{id}`;
  - tipos de ubicación: `POST /v1/tipos-ubicacion` y `PATCH /v1/tipos-ubicacion/{id}`.
- **Cambios en endpoints existentes:**
  - `PATCH /v1/incoterms/{codigo}` acepta `servicios` (solo admin, auditado).
  - `POST /v1/tipos-equipo` y `PATCH /v1/tipos-equipo/{id}` aceptan `servicio_id`.
  - Las cotizaciones devuelven `servicio` (nombre, forma de cobro y etiqueta del transportista).

### 3.4 Pantallas

| Pantalla | Quién | Qué |
|---|---|---|
| Administración → Servicios | Admin edita; el resto lee | Tabla y formulario. Al elegir la forma de cobro, se muestran sus unidades y campos. La pestaña **Tramos** aparece solo en los servicios por peso |
| Administración → Tipos de ubicación | Admin | Regla del código, mensaje y prefijo del país |
| Catálogos → Tipos de equipo (nueva) | Pricing y admin editan; el resto lee | Con el campo **Servicio**: solo servicios por unidad de equipo |
| Incoterms | Admin edita | Casillas de servicios permitidos; la columna "Modo" pasa a "Servicios" |
| Tarifas, recargos y cotizador | Igual que antes | "Modo" pasa a "Servicio", con los activos ordenados (los filtros muestran todos). Los campos aparecen según la forma de cobro y los tramos salen del servicio |
| Geografía | Igual que antes | Los tipos de puerto salen del catálogo, con la ayuda del código |

## 4. Pruebas

### 4.1 Suite y Regla 18 doble

| Corrida | Pruebas | Resultado |
|---|---|---|
| Diagnóstico (antes de ajustar D-E0-1) | 634 | 627 OK; las 7 fallas eran solo los conteos de permisos (D-E0-1) |
| Regla 18 · ciclo 1 (base virgen, 0001→0007) | 675 | **675 passed**, 0 fallos (1 h 33 min) |
| Regla 18 · ciclo 2 | 675 | **675 passed**, 0 fallos (1 h 34 min) |

### 4.2 Pruebas nuevas

En `tests/test_e0_servicios.py`, TE0-01 a TE0-27:
- **Siembra:** servicios, tipos, tramos e Incoterms por servicio, idénticos al comportamiento de antes.
- **Permisos:** matriz de extensiones exacta; solo el admin gestiona servicios, tramos y tipos de ubicación.
- **Auditoría:** al crear un servicio queda auditado y hereda los Incoterms del servicio con las mismas ubicaciones.
- **Validaciones:** forma incoherente, libras sin peso, código inválido, ubicación inactiva y duplicado.
- **Uso:**
  - un servicio usado no cambia de código, forma ni ubicaciones, y no se borra; uno sin uso, sí;
  - un servicio inactivo no se ofrece para tarifas ni cotizaciones nuevas, pero lo histórico sigue: su tarifa se lista y su borrador se lee y se propone;
  - un tramo usado no se borra ni cambia su "desde": se desactiva.
- **Courier por peso con tramos de 0; 0,5; 1; 5 y 10 kg, de punta a punta:**
  - 0,8 kg cae en el tramo +0,5 y da 9,60 USD;
  - se emite y el PDF muestra su descripción, su etiqueta y la aerolínea (DHL Express), nunca el proveedor.
- **Terrestre FTL por unidad de equipo** con el tipo de equipo nuevo **53TR**: el 40HC de FCL se rechaza; 2 camiones dan 2000 USD.
- **Tarifa plana:** solo por envío, sin exigir peso.
- **Recargo de un servicio nuevo.**
- **Incoterm según los servicios permitidos:** FOB con aéreo se bloquea con el mismo mensaje de antes; al permitirlo, pasa.
- **Tipos de ubicación:**
  - una regex inválida se rechaza;
  - una regla nueva que deja inválido un puerto existente se rechaza;
  - un tipo inactivo o inexistente se rechaza.
- **PDF:** el de una emitida antes de E0 conserva sus textos; una emisión nueva congela el servicio.
- **Tipo de equipo con servicio:** por defecto queda en FCL; un tipo usado no cambia de servicio.
- **Motor puro:** resuelve la forma de cobro por el catálogo.
- **Pantallas nuevas:** sin estilos en línea ni innerHTML, y el menú según permisos.

### 4.3 Prueba de oro

Detalle en `docs/extensiones/E0-prueba-oro.md`.
- **Banco de prueba:** 26 cotizaciones de los 3 modos; 121 líneas guardadas, 121 recalculadas y 26 HTML de PDF. **0 diferencias.**
- **Producción:** 4 cotizaciones, 8 líneas y 4 HTML de PDF, tras migrar `xps_pricing` a 0007: **0 diferencias**.

### 4.4 Humo en el navegador

Chromium, como admin, sobre la base de pruebas, en 10 pantallas: servicios, tipos de ubicación, tipos de equipo, tarifas, recargos, cotizador, Incoterms, geografía, cotizaciones e inicio.
- **Sin problemas:** sin errores de consola ni respuestas 4xx/5xx.
- **Se crea un servicio** por la pantalla.
- **Pestaña Tramos:** muestra los tramos del aéreo.
- **Tarifas:** el formulario muestra el tipo de equipo solo con FCL.
- **Cotizador:** ofrece los servicios activos en su orden.
- **Incoterms:** FOB trae marcados LCL y FCL.

## 5. Producción

| Paso | Resultado |
|---|---|
| Respaldo justo antes de migrar | Cloud SQL on-demand **1792276818942** (2026-10-17 22:40 UTC), SUCCESSFUL |
| Migración de `xps_pricing` | `alembic upgrade head`: 0006 → **0007 (head)** |
| Prueba de oro sobre la base real | 4 cotizaciones (1 emitida, COT-2026-00001; 3 borradores), 8 líneas y 4 HTML de PDF: **0 diferencias** |
| Despliegue | `gcloud run deploy` (mismo comando de `docs/DESPLIEGUE.md`). La revisión **xps-pricing-00003-7l9** sirve el 100 % |
| Salud | `GET /v1/salud` → `{"estado":"ok","bd":"ok"}` |
| Verificación HTTP (usuarios de prueba de F5 reactivados con claves en memoria y desactivados al final) | **19 de 19 OK**. Detalle abajo |
| Logs de la revisión nueva | 0 entradas con severity ≥ ERROR |
| Vuelta atrás, si hiciera falta | `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=xps-pricing-00002-4lk=100` y `alembic downgrade 0006`. Si ya hay servicios nuevos, se restaura el respaldo 1792276818942 |

**Qué incluyó la verificación HTTP**
- **Salud:** responde "ok" la aplicación y la base.
- **Servicios:** activos AEREO, LCL y FCL, y las 4 formas de cobro.
- **Incoterms:** FOB permite solo LCL y FCL (`solo_maritimo` = true).
- **Las 4 cotizaciones existentes:** el mismo total y los mismos subtotales por línea que antes de migrar.
  - COT-2026-00001: 296,95 USD.
  - Los borradores: 0,00, 254,95 y sin líneas.
- **Sus 4 PDF:** se generan y muestran "vía aérea" y "Aerolínea".
- **Permisos del comercial:** lee los servicios y recibe 403 al intentar crear uno.
- **Pantallas nuevas:** responden 200.

## 6. Desvíos

- **D-E0-1, conteos de permisos:** T03, T04, T05, T29, T40, T136, T138 y T208 contaban los permisos y asignaciones de §6.2 sobre toda la tabla. El permiso nuevo que pide E0 los rompía. Ahora excluyen los permisos de las extensiones (`tests/matriz_rbac.py` → `PERMISOS_EXTENSIONES`):
  - los valores esperados no cambian: 15 permisos, 38 asignaciones, la matriz §6.2 y los permisos de `/auth/yo`;
  - TE0-03 verifica aparte y exacta la matriz de las extensiones.
- **Mensajes:** los códigos de error no cambiaron. Algunos mensajes que nombraban un modo ahora nombran el servicio, por ejemplo "El servicio Aéreo va de aeropuerto a aeropuerto". Ninguna prueba de F0–F5 verificaba esos textos. El aviso de Incoterm ("FOB es solo marítimo. Para aéreo use FCA, CPT o CIP") quedó idéntico.

## 7. Decisiones tomadas

1. **Columnas "modo" sin renombrar:** conservan nombre y valores en la base y en la API (`modo` = código del servicio). En las pantallas se llaman "Servicio". Así ningún cliente de la API ni dato histórico cambia.
2. **CHECK por modo:** se reemplazaron por FK a `servicio.codigo`, más la validación en las estrategias de forma de cobro. En la base queda el respaldo genérico de que el tipo de equipo y CONTENEDOR solo van con un servicio.
3. **Recargo sin servicio:** sus unidades salen del tipo de ubicación del puerto (la unión de las unidades de los servicios activos que lo usan, sin las de equipo). Reproduce exactamente la regla anterior: aeropuerto KG/ENVIO; marítimo WM/CBM/ENVIO.
4. **Recargo con servicio:** el puerto debe ser del tipo de ubicación del lado del recargo (origen o destino del servicio).
5. **`solo_maritimo`:** queda en la API como dato derivado, para compatibilidad. El dato real es `incoterm_servicio`.
6. **Un servicio nuevo hereda los Incoterms** del servicio existente con los mismos tipos de ubicación; si no hay ninguno, recibe todos. El admin los ajusta en Incoterms. Ejemplo: Courier, de aeropuerto a aeropuerto, hereda los del aéreo.
7. **Tipo de equipo sin servicio indicado** (API o código anterior): queda en el primer servicio activo con tipo de equipo, por orden. Hoy es FCL.
8. **El código del tipo de equipo** sigue siendo de 2 dígitos y 2 letras (40HC, 53TR). No se amplió para no tocar el CHECK existente.
9. **Servicio desactivado:**
   - no se ofrece para tarifas, recargos ni cotizaciones nuevas;
   - un borrador existente se sigue editando, proponiendo y emitiendo;
   - lo emitido queda intacto.
10. **El borrado** de algo que nunca se usó se audita como DESACTIVAR con la nota "BORRADO: nunca se usó", para no cambiar el CHECK de acciones de la auditoría.
11. **Moneda de cotización:** se mantiene solo USD (`ck_cotizacion_moneda_usd`); queda fuera de alcance.
12. **Formas de cobro:** son un catálogo cerrado en código (4 estrategias); no se editan.
13. **Verificación en producción:** solo hay 4 cotizaciones, todas aéreas (una emitida, COT-2026-00001). No existen LCL ni FCL para "una por modo". Las 4 se verifican en producción (prueba de oro con la copia real y la verificación HTTP), y LCL y FCL se cubren con el banco de 26 cotizaciones.
14. **Descenso de versión:** el downgrade de 0007 se niega, sin tocar nada, si ya hay datos que la 0006 no puede representar (servicios o tipos nuevos, tramos con decimales, códigos largos). En ese caso, la vuelta atrás es restaurar el respaldo.
15. **Texto de la pantalla de ingreso:** "Aéreo, LCL y FCL" se deja como está; es texto comercial previo al ingreso.

## 8. Pendientes

- **Push a GitHub de los commits de E0:** el permiso de Claude Code lo bloqueó (los push requieren un pedido explícito de François). Hay que ejecutar `git push origin main` o autorizarlo. Mientras tanto, E1 no empieza: la regla es cerrar con commit, push y despliegue verificado.
- El tiempo de la suite subió a ~90 min o más por ciclo, por la latencia a Cloud SQL (125 ms por consulta el 2026-10-17).

## 9. Cómo agregar un servicio nuevo (guía para el gerente)

1. **Entrar como administrador** y abrir **Administración → Servicios**.
2. **Revisar el tipo de ubicación.** Si el servicio usa uno que todavía no existe o está inactivo (por ejemplo, terminal terrestre), primero ir a **Administración → Tipos de ubicación** y activarlo o crearlo.
3. **Crear el servicio.** Pulsar **Nuevo servicio** y completar:
   - **Código:** corto y en mayúsculas, como COURIER. No se puede cambiar una vez que el servicio se usa.
   - **Nombre visible:** "Courier".
   - **Forma de cobro:** al elegirla, la pantalla explica cómo cobra y qué unidades usa.
     - *Por peso con tramos* → kilos (y libras, si marca la casilla), con tramos.
     - *Por volumen (W/M)* → m³ o toneladas.
     - *Por unidad de equipo* → contenedores, camiones, etc.
     - *Tarifa plana* → un precio por envío.
   - **Tipo de ubicación de origen y de destino:** por ejemplo, aeropuerto → aeropuerto.
   - **Descripción en el PDF:** sale en la frase "cotización de servicios logísticos (…)". **Etiqueta del transportista:** por ejemplo, "Courier" o "Transportista".
   - **Orden:** en qué lugar aparece en las listas.
4. **Si cobra por peso, cargar los tramos.** Pulsar **Editar** en el servicio y abrir la pestaña **Tramos**.
   - Agregar cada "desde": 0; 0,5; 1; 5; 10…
   - El tramo **desde 0** es obligatorio.
5. **Si cobra por unidad de equipo, crear sus tipos de equipo** en **Catálogos → Tipos de equipo**, eligiendo el servicio. Ejemplo: 53TR "Camión 53'".
6. **Revisar en Incoterms** en qué términos se permite el servicio. Ya viene con los del servicio parecido, y se puede cambiar con las casillas.
7. **Cargar los puertos** (en Geografía) y **las tarifas** (en Tarifas): el servicio nuevo ya aparece en la lista "Servicio".
8. **Probar:** crear una cotización con el servicio nuevo, proponer las líneas y ver el PDF.

Para dejar de ofrecer un servicio, pulsar **Desactivar**. Lo que ya existe queda igual. Solo se puede **Borrar** un servicio que nunca se usó.

## 10. Checklist del gerente (en el navegador)

Marque cada punto cuando lo compruebe. Use su usuario administrador.

1. [ ] En **Administración → Servicios** aparecen Aéreo, Marítimo LCL y Marítimo FCL.
2. [ ] **Crear el servicio Courier:** código COURIER, por peso con tramos, de aeropuerto a aeropuerto, descripción "servicio courier".
3. [ ] **Cargar sus tramos:** en Courier, **Editar → Tramos**, agregar los tramos 0; 0,5; 1; 5 y 10 en KG.
4. [ ] **Crear una tarifa courier:** en **Tarifas → Nueva tarifa**, elegir "Courier", una ruta entre dos aeropuertos y precio por KG. Desde **Ver → Editar tramos**, cargar un costo por cada tramo.
5. [ ] **Cotizar:** en el **Cotizador**, elegir el servicio "Courier", la misma ruta, peso 0,8 kg e Incoterm FCA. Pulsar **Proponer líneas**: el flete usa el precio del tramo "+0,5".
6. [ ] **Ver el PDF:** abrir el PDF de esa cotización. Dice "servicio courier" y muestra la aerolínea, nunca el agente.
7. [ ] **Desactivar Courier:** desactívelo en **Servicios**. En **Tarifas → Nueva tarifa** y en el **Cotizador** ya no aparece; la tarifa courier se sigue viendo en la lista.
8. [ ] **Revisar una cotización vieja:** abrir la COT-2026-00001. Tiene el mismo total de antes (296,95 USD) y su PDF sale igual ("vía aérea", "Aerolínea").
9. [ ] **Comprobar los Incoterms:** en **Incoterms**, FOB permite solo "Marítimo LCL" y "Marítimo FCL".
10. [ ] **Comprobar los permisos:** con un usuario de Pricing o Comercial, el menú no muestra **Servicios** ni **Tipos de ubicación**.

Si la cotización Courier se hizo solo como prueba, puede descartarla desde su detalle mientras siga en borrador.

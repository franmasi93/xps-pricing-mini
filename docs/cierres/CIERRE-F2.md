# Acta de cierre — F2 (M5 Tarifas, tramos y recargos + M6 Clientes y contactos)

| Campo | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fase | F2: M5 Tarifas, tramos aéreos y recargos · M6 Clientes y contactos |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` (la V1.1 no se usa) |
| Commit anterior | `e00552a` (F1) |
| Fecha de cierre | 2026-10-07 |
| Decisor | François Ramírez — Gerente General |
| Avance del proyecto | F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · **proyecto 45 %** |

---

## 1. Resumen en cristiano

El sistema ya guarda las **tarifas de costo** de los agentes por ruta (aéreo, LCL y FCL), con su vigencia, y calcula solo el **precio de venta** con cuatro métodos (manual, markup, margen o fijo). Las tarifas aéreas pueden tener **tramos por peso** (−45, +45, +100, +300, +500, +1000 kg). También guarda los **recargos** de origen y destino (THC, BL, despacho, etc.) y los **clientes** con sus contactos. Dos tarifas iguales no pueden estar vigentes al mismo tiempo: la base de datos lo impide. El comercial ve solo precios de venta y solo sus propios clientes; el costo y el margen **no viajan** en lo que recibe su navegador. Cada cambio de costo, precio, vigencia, tramo, recargo o cliente queda anotado con quién, cuándo, antes y después. Sigue el cotizador (F3).

## 2. Alcance

### 2.1 Tablas (migración `0003`, escrita a mano)

`tipo_equipo`, `tarifa`, `tramo_aereo`, `recargo`, `cliente`, `contacto_cliente`. Empieza con `CREATE EXTENSION IF NOT EXISTS btree_gist` (versión 1.8, *trusted*, sin superusuario). Constraints con nombre explícito (`pk_`, `uq_`, `fk_`, `ck_`, `ix_`, `ex_`). Los CHECK que comparan columnas que pueden ser NULL usan `IS NOT NULL` / `IS NOT DISTINCT FROM` (un CHECK que da NULL se considera cumplido).

- **No superposición de vigencias (D-F2-1):**
  - `ex_tarifa_vigencia_sin_superposicion`: `EXCLUDE USING gist (proveedor_id =, modo =, origen_puerto_id =, destino_puerto_id =, COALESCE(tipo_equipo_id, 0) =, daterange(valido_desde, valido_hasta, '[]') &&) WHERE (activo)`.
  - `ex_recargo_vigencia_sin_superposicion`: `(COALESCE(proveedor_id, 0) =, puerto_id =, lado =, bloque_incoterm =, lower(concepto) =, COALESCE(modo, '') =, COALESCE(tipo_equipo_id, 0) =, daterange(...) &&) WHERE (activo)`.
- **Contacto principal único:** índice único parcial `uq_contacto_cliente_principal` sobre `(cliente_id) WHERE principal`.
- **Seed:** solo los 5 tipos de equipo (20GP, 40GP, 40HC, 20RF, 40RF). El RBAC sigue en 4 / 15 / 38: no se agregaron permisos.
- **Downgrade:** borra las 6 tablas en orden inverso y hace `DROP EXTENSION IF EXISTS btree_gist`.

### 2.2 Endpoints (`/v1`)

| Recurso | Leer | Escribir |
|---|---|---|
| Tipos de equipo (`/tipos-equipo`, `/{id}`) | cualquier token válido | `catalogo.editar` (POST, PATCH) |
| Tarifas (`/tarifas` con filtros modo, origen, destino, proveedor, tipo_equipo, vigente_en, por_vencer, activo; `/{id}`) | `tarifa.ver`, con gating de costos | `tarifa.editar` (POST, PATCH) |
| Duplicar (`POST /tarifas/{id}/duplicar`, declarado antes de `/{id}`) | — | `tarifa.editar` |
| Tramos (`/tarifas/{id}/tramos`) | `tarifa.ver`, con gating | `tarifa.editar` (PUT: reemplaza el conjunto) |
| Recargos (`/recargos` con filtros puerto, lado, bloque, proveedor, modo, vigente_en, por_vencer, activo; `/{id}`) | `tarifa.ver`, con gating | `tarifa.editar` (POST, PATCH) |
| Búsqueda de clientes (`GET /clientes/buscar?q=`, declarado antes de `/{id}`) | `cliente.ver`, con alcance; q ≥ 2 caracteres; máximo 20 | — |
| Clientes (`/clientes`, `/{id}`) | `cliente.ver`, con alcance | `cliente.editar` (POST, PATCH) |
| Contactos (`/clientes/{id}/contactos`, `/{cid}`) | `cliente.ver`, con alcance | `cliente.editar` (POST, PATCH) |

Sin DELETE en ningún recurso nuevo: 405 `METODO_NO_PERMITIDO`; la baja es `activo=false`.

### 2.3 Reglas principales

- **Precio de venta** (`services/precio_venta.py`, única fuente): MANUAL, MARKUP (`costo × (1 + p/100)`), MARGEN (`costo / (1 − p/100)`, p < 100) y FIJO (`costo + p`). Decimal a 4 decimales, ROUND_HALF_UP, en la moneda original. Nunca es un dato de entrada. Más de 4 decimales en un monto → 422 `MONTO_INVALIDO`, nunca se redondea en silencio.
- **Tarifa:** AEREO usa aeropuertos; LCL y FCL, puertos marítimos (422 `PUERTO_MODO_INCONSISTENTE`). FCL exige tipo de equipo y unidad CONTENEDOR; AEREO y LCL lo prohíben. Unidades: AEREO {KG, ENVIO}, LCL {WM, CBM, ENVIO}, FCL {CONTENEDOR}. Referencias activas (`PADRE_INACTIVO`, `MONEDA_INACTIVA`).
- **Estado de vigencia** al leer: FUTURA, VIGENTE, POR_VENCER (vigente y `valido_hasta` ≤ hoy + `dias_alerta_vencimiento`, leído de la configuración) o VENCIDA. "Hoy" = `core/fechas.hoy_ecuador()` (UTC−5 fijo), sustituible en los tests.
- **Tramos:** solo en AEREO KG; `desde_kg` ∈ {0, 45, 100, 300, 500, 1000}; el tramo 0 es obligatorio; el costo (y, con MANUAL, el precio manual) de la tarifa se iguala al tramo 0.
- **Recargo:** coherencia lado–bloque; modo compatible con el puerto; unidades por modo o, sin modo, por tipo de puerto; SEGURO solo por ENVIO; concepto normalizado; `aplica_iva` y `rol_ingreso` obligatorios, sin valor por defecto.
- **Clientes:** el alcance lo decide `cotizacion.ver_todas` (sin él, un cliente ajeno da 404 y la búsqueda no lo devuelve). Identificación en mayúsculas y sin espacios, con formato por tipo. Duplicado → 409 `CLIENTE_DUPLICADO` sin revelar datos.
- **Auditoría:** todo cambio de costo, precio, método, parámetro, mínimos, tramos, vigencia, estado y datos de cliente o contacto, con antes y después (4 decimales), en la misma transacción. Si el cambio falla, no queda registro.

### 2.4 Gating de costos (D-F2-5)

El service elige entre tres esquemas por recurso; el router devuelve lo que arma el service (`response_model=None`), sin filtrar.

| Nivel | Condición | Claves adicionales |
|---|---|---|
| Venta | sin `costo.ver` | — (las 10 claves de costo **no existen** en el JSON) |
| Costo | `costo.ver` | `costo` / `costo_kg`, `minimo`, `metodo_venta`, `parametro_venta`, `precio_venta_manual`, `minimo_venta_manual`, `notas` |
| Costo y margen | `costo.ver` **y** `margen.ver` | además `margen_unitario`, `margen_pct` |

### 2.5 Pantallas y menú por rol

`tarifas.html` (P6), `recargos.html` (P7), `clientes.html` (P8) y el bloque "Tarifas por vencer" en `inicio.html`. Una sola hoja de estilos (`xps-pricing.css`), sin estilos en línea ni `innerHTML`. Las columnas de costo y margen se dibujan solo si la clave existe en el JSON. P7 se bloquea por `/auth/yo` (`tarifa.editar` o `costo.ver`), igual que Geografía en F1.

| Rol | Menú |
|---|---|
| admin | Inicio, Tarifas, Recargos, Clientes, Incoterms, Geografía, Proveedores, Monedas y tasas, Configuración, Usuarios |
| pricing | lo mismo, menos Usuarios |
| gerencia | Inicio, Tarifas, Recargos, Clientes, Incoterms, Proveedores, Monedas y tasas (lectura) |
| comercial | Inicio, Tarifas (solo venta), Clientes (los suyos), Incoterms |

### 2.6 Services reutilizables para F3

- `services/precio_venta.precio_venta(...)` / `precio_venta_minimo(...)` / `margen(...)`.
- `services/tarifas.estado_vigencia(...)` y `filtros_vigencia(...)`.
- `core/fechas.hoy_ecuador()`.
- `services/clientes` con el alcance por `cotizacion.ver_todas`.

## 3. Evidencia cruda

### 3.1 Migración 0003: up → down → up (Parada 2)

| Base | Pasos | Resultado |
|---|---|---|
| `xps_pricing_test` | `upgrade head` · `downgrade 0002` · `current` (`0002`) · `upgrade head` · `current` | todos `exit: 0` · `0003 (head)` |
| `xps_pricing` | ídem | todos `exit: 0` · `0003 (head)` |

### 3.2 Conteos del seed, exclusiones y btree_gist (2026-10-07, después de la Regla 18)

```
xps_pricing       alembic=0003 rol=4 permiso=15 rol_permiso=38 moneda=1 incoterm=11 configuracion=4 tipo_equipo=5 tarifa=0 tramo_aereo=0 recargo=0 cliente=0 contacto_cliente=0
                  tipos_equipo=['20GP', '20RF', '40GP', '40HC', '40RF']
                  constraints_ex=['ex_recargo_vigencia_sin_superposicion (recargo)', 'ex_tarifa_vigencia_sin_superposicion (tarifa)']
                  btree_gist_instalada=1.8
xps_pricing_test  (idéntico)
```

### 3.3 pytest por parada

```
T136 + T138 (seed, tras S1/S2):                       2 passed, 1 warning in 4.52s
Fórmulas T140–T143 (sin base):                       11 passed, 1 warning in 0.04s
M5, primera corrida:                                  9 failed, 118 passed, 1 warning in 1115.77s   (incidente a)
Los 9 fallidos, tras la corrección:                   9 passed, 1 warning in 126.90s
M5 + archivos de F1 que usan la auditoría:          215 passed, 1 warning in 1421.69s (0:23:41)
M6 + T187 + test_frontend.py:                        56 passed, 1 warning in 247.72s (0:04:07)
Tras revertir :5500 (frontend, salud, login):        19 passed, 1 warning in 14.94s
T207:                                                 1 passed, 1 warning in 4.71s
```

### 3.4 Regla 18 doble (2026-10-07, día hábil, proxy PID 15548 reiniciado a las 08:49)

Cada ciclo: diagnóstico de 10 conexiones (10 de 10 OK, ~2,1–2,4 s) → procesos Python del proyecto cerrados (ninguno abierto) → `DROP` / `CREATE DATABASE xps_pricing_test` (0 conexiones abiertas) → `alembic upgrade head` (`0001` → `0002` → `0003`, `exit: 0`, `0003 (head)`) → recolección → suite completa (`tests/`).

```
Ciclo 1 (09:02:34–09:34:07):  432 tests collected in 0.45s
                              432 passed, 1 warning in 1871.63s (0:31:11)
Ciclo 2 (09:34:46–10:06:49):  432 tests collected in 0.22s
                              432 passed, 1 warning in 1903.22s (0:31:43)
```

0 failed, 0 errors, 0 skipped; N = recolectados = 432 en ambos ciclos. Sin `OperationalError` en ninguno de los dos.

### 3.5 Tests nuevos por archivo (de 262 a 432)

| Archivo | Tests | Cubre |
|---|:-:|---|
| `tests/test_seed_f2.py` | 1 | T138 |
| `tests/test_precio_venta.py` | 11 | T140–T143 |
| `tests/test_tarifas.py` | 84 | T139, T144–T176, T184, T186, T205, T206 |
| `tests/test_recargos.py` | 26 | T177–T183, T185 |
| `tests/test_delete_f2.py` | 6 | T187 (tarifas, tramos, recargos, tipos de equipo, clientes, contactos) |
| `tests/test_clientes.py` | 39 | T188–T203, T207 |
| `tests/test_frontend.py` | +3 (9 → 12) | T204 (tarifas, recargos, clientes) |
| **Total nuevos** | **170** | 262 + 170 = **432** |

`tests/test_seed_f1.py` (T136) se modificó sin cambiar su número de tests (desvío S3).

### 3.6 Canario de encoding y control de secretos (38 archivos de F2, incluida esta acta)

```
Canario de encoding: 38 OK, 0 con fallas, 38 revisados
contraseña de pricing_app (texto plano): 0 apariciones en 38 archivos
contraseña de pricing_app (codificada en URL): 0 apariciones en 38 archivos
JWT_SECRET: 0 apariciones en 38 archivos
argumento de credenciales del proxy: 0 apariciones en 38 archivos
ruta de la carpeta local de claves (con barra invertida o normal): 0 apariciones en 38 archivos
```

(En esta acta se nombran sin el texto literal, para que el propio control de secretos siga en 0.)

## 4. Decisiones

| # | Decisión |
|---|---|
| D-F2-1 | Sin vigencias superpuestas entre tarifas activas con la misma clave (proveedor, modo, origen, destino, tipo de equipo) → 409 `VIGENCIA_SUPERPUESTA` con `id_en_conflicto`. Adyacencia (hasta = desde − 1) permitida. Recargos con la clave (proveedor o null, puerto, lado, bloque, concepto normalizado, modo o null, tipo de equipo o null). Implementado con EXCLUDE (btree_gist) más verificación previa en el service; `core/errors.py` traduce el SQLSTATE 23P01 a 409. |
| D-F2-2 | Tramos solo en AEREO KG; `desde_kg` ∈ {0, 45, 100, 300, 500, 1000}; tramo 0 obligatorio; `tarifa.costo` = costo del tramo 0. GET y PUT `/tarifas/{id}/tramos`; el PUT reemplaza el conjunto en una transacción, con auditoría. |
| D-F2-3 | MANUAL: `precio_venta_manual` > 0 y parámetro null; `minimo_venta_manual` obligatorio si `minimo` > 0. MARKUP, MARGEN y FIJO: parámetro ≥ 0 y campos manuales null. MARGEN con p ≥ 100 → 422. Mínimo de venta = la misma fórmula sobre el mínimo de costo. En tramos con MANUAL, `precio_venta_kg` obligatorio; con los demás métodos, null y calculado. |
| D-F2-4 | El recargo agrega `modo` (nullable = todos los compatibles con el puerto) y `tipo_equipo_id` (solo con FCL). |
| D-F2-5 | Sin `costo.ver`, el JSON de tarifas, tramos y recargos no contiene las 10 claves de costo: se omiten, no van en null. Esquemas distintos elegidos en el service. Los errores que recibe el comercial no revelan costos. |
| D-F2-6 | Identificación en mayúsculas y sin espacios: RUC `^[0-9]{10}001$`, CEDULA `^[0-9]{10}$`, PASAPORTE `^[A-Z0-9]{5,20}$`, EXTRANJERO `^[A-Z0-9]{3,30}$`. Sin dígito verificador en V1. |
| D-F2-7 | Cliente duplicado → 409 `CLIENTE_DUPLICADO`, "Ya existe un cliente con esa identificación; solicite su asignación al administrador". Sin razón social ni comercial. |
| D-F2-8 | El seguro como % del valor de la mercancía queda fuera; en F2 un recargo SEGURO solo admite ENVIO. Pendiente P11 para F3. |
| D-F2-9 | Para un mismo (proveedor, puerto, lado, bloque, concepto), el cotizador de F3 usa **solo el recargo más específico** (tipo de equipo > modo > NULL), nunca dos a la vez. Un recargo con modo NULL y otro con modo específico son claves distintas; no se agrega lock. |
| D-F2-10 | Recargo con modo FCL: unidad en {CONTENEDOR, ENVIO} (el BL y la emisión de documentos se cobran por envío). Se valida en el service, sin migración. |
| D-F2-11 | Con tramos, cambiar `metodo_venta` → 409 `TIENE_DEPENDIENTES` (igual que modo y unidad): los precios por kg dependen del método. |

**Huecos de la Parada 1 (respuestas del ASESOR):**

| # | Respuesta |
|---|---|
| 1 | Si `minimo` = 0, `precio_venta_minimo` = 0 en todos los métodos. |
| 2 | Opción (a): modo NULL y modo específico son claves distintas; regla D-F2-9 para F3. |
| 3 | Con tramos y MANUAL, `precio_venta_manual` = `precio_venta_kg` del tramo 0, editable solo desde los tramos (PATCH directo → 422 `PRECIO_DESDE_TRAMOS`); `minimo` y `minimo_venta_manual` se editan en la tarifa. |
| 4 | `hoy_ecuador()` con desfase fijo UTC−5 (Ecuador sin horario de verano desde 1993). No se agrega `tzdata`. |
| 5 | P7 se bloquea por `/auth/yo`; el backend mantiene el gating. |
| 6 | Quien tiene `cotizacion.ver_todas` debe indicar `comercial_asignado_id` al crear → si no, 422 `COMERCIAL_ASIGNADO_REQUERIDO`. No se asigna a sí mismo. |
| 7 | `margen_unitario` y `margen_pct` salen solo con `costo.ver` y `margen.ver`. |
| 8 | Con tramos: cambiar modo o unidad → 409 `TIENE_DEPENDIENTES`; PATCH del costo → 422 `COSTO_DESDE_TRAMOS`. |
| 9 | Duración de la suite aceptada; deuda para F5. |
| 10 | Búsqueda con ILIKE sin trigramas: deuda baja. |
| 11 | En tramos, FIJO = `costo_kg + p` por kg; MARKUP y MARGEN también por kg. |
| 12 | Diferencias con la V1.0 aprobadas y registradas como desvíos. |

**Ajustes del ASESOR:**

| # | Ajuste |
|---|---|
| A1 | Unidad del recargo sin modo, validada contra el tipo de puerto: aeropuerto {KG, ENVIO}; puerto marítimo {WM, CBM, ENVIO}; CONTENEDOR solo con FCL. Con modo, manda el modo. → 422 `RATE_UNIT_INCOMPATIBLE` (T179). |
| A2 | T205: inserción directa por ORM que salta el service → la base la rechaza y la API responde 409, no 500 [tarifa, recargo]. |
| A3 | T206: la auditoría de tarifa guarda notas y costo, y `GET /auditoria` sigue en 403 para el comercial. |
| A4 | El concepto del recargo se guarda como lo escribió Pricing (btrim y espacios internos colapsados); la exclusión compara por `lower()` (T182). |
| A5 | Tests nuevos al final (T205 en adelante), sin renumerar. |
| S1 | T138 compara `alembic_version` con el head calculado desde `ScriptDirectory`, no con un número fijo. |
| S2 | T138 verifica las exclusiones con `issuperset`. |
| S3 | El cambio en T136 se registra como desvío menor. |

## 5. Desvíos respecto al documento rector

- **T136** dejaba fijo el número de migración (`"0002"`); la verificación del head pasa a T138, que la calcula desde Alembic (S3).
- **Gerencia lee P7 Recargos** (§14 P7 dice admin y pricing; se aplica §6.1, "gerencia: lectura de todo").
- **§7 no tenía** `modo` ni `tipo_equipo_id` en recargo (los agrega D-F2-4) ni `minimo_venta_manual` (D-F2-3).
- **Compuerta de checklist F1 movida de inicio de F2 a pre-commit de F2, por decisión de François, 2026-10-03.**
- **Commit de F2 con checklist F1 pendiente, por decisión de François, 2026-10-07.**
- Prefijo `ex_` para las exclusiones (el prompt listaba `pk_`, `uq_`, `fk_`, `ck_`, `ix_`).
- T207 (candidatos a comercial de P8) se agregó en el cierre, fuera de la lista aprobada en la Parada 1, por orden del ASESOR.

## 6. Incidentes

| # | Incidente | Causa y corrección |
|---|---|---|
| a | `TypeError: Object of type Decimal is not JSON serializable` en 9 tests de tramos (Parada 3, primera corrida: `9 failed, 118 passed`). | `auditoria.registrar` solo convertía los `Decimal` del primer nivel; la foto de los tramos (lista de diccionarios) llegaba a JSONB con `Decimal` adentro. Corregido con una conversión recursiva en `_serializable`. Los 9: `9 passed, 1 warning in 126.90s`. |
| b | 2026-10-04 (domingo) 10:53: el proxy no escuchaba en 127.0.0.1:5432. | El EJECUTOR no reintentó ni lo reinició; escribió tests sin base. A las 10:54 se levantó un proxy nuevo (PID 16548) fuera de la sesión del EJECUTOR. Lo reinició François Ramírez (confirmado por él el 2026-10-07). Diagnóstico posterior: 10 de 10 conexiones OK. |
| c | 2026-10-05 01:59: Paradas 4 y 5 escritas con la instancia apagada (horario §3.3). | Lo que necesitaba base (tests de M6 y `test_frontend.py`, que usa la fixture `client`) quedó para el encendido: dieron `ERROR` de conexión, no `FAILED`. Se corrieron el 2026-10-07 con el proxy reiniciado a las 08:49 (PID 15548); diagnóstico 10 de 10 OK (~2,1 s). |
| d | 2026-10-06 11:12–11:14, fuera de la sesión del EJECUTOR: captura `frontend/image.png` del login abierto con Live Server (`127.0.0.1:5500/frontend/login.html`) con 405 en `:5500/v1/auth/login`, y a las 11:14:43 cambios en `app/main.py` (CORS para `127.0.0.1:5500` y `localhost:5500`) y `frontend/js/api.js` (`BASE_API` a `http://127.0.0.1:8000/v1` cuando el puerto es 5500). | El 405 se debía a abrir el sistema con Live Server (:5500) en lugar del servidor de la aplicación. Por decisión del ASESOR se revirtieron el CORS para :5500 en `app/main.py` y el `BASE_API` de `frontend/js/api.js`. El sistema se usa solo en `http://127.0.0.1:8000/app` (regla vigente desde F1). La captura `frontend/image.png` no entra a git. Los cambios y la captura los hizo François Ramírez (confirmado por él el 2026-10-07). Verificación tras revertir: `git diff -- frontend/js/api.js` vacío; `test_frontend.py`, `test_salud.py` y `test_auth_login.py`: `19 passed, 1 warning in 14.94s`. |
| e | 2026-10-07 08:55: un primer ciclo 1 de la Regla 18 arrancó antes de resolver el incidente d. | Se detuvo a las 08:58 por orden del ASESOR (el código iba a cambiar) y su resultado no se usó. La Regla 18 doble se corrió completa después de revertir d y agregar T207. |
| f | 2026-10-07 09:01:43: el primer intento del ciclo 1 válido terminó después de 16 tests, sin resumen de pytest (exit 255), sin traceback ni error de conexión. Coincidió con un comando del EJECUTOR que lanzó el Python del proyecto en primer plano. | Causa no confirmada. Diagnóstico posterior: 10 de 10 OK. El ciclo se repitió completo desde el `DROP` (09:02:34) y, mientras corrían los ciclos, el EJECUTOR no ejecutó nada más. No se sumaron resultados parciales. |
| g | La pantalla de Clientes (P8) arma la lista de comerciales con `GET /v1/roles` y `GET /v1/usuarios?activo=true`, sin test que lo cubriera. | Se agregó T207 (`1 passed, 1 warning in 4.71s`). `/roles` ya devolvía `codigo` y `permisos`, y `/usuarios` `rol.codigo`: no hubo que cambiar endpoint ni pantalla. |

## 7. Deuda

| Prioridad | Deuda |
|---|---|
| Media | Sin paginación en `GET /tarifas` ni `GET /recargos` (los listados devuelven todo lo que cumple los filtros). |
| Baja | Búsqueda de clientes con ILIKE, sin índice de trigramas. |
| Baja | Duración de la suite: ~31–32 min (1871,63 s y 1903,22 s en la Regla 18) por ciclo (432 tests), por la latencia hacia Cloud SQL. Se evalúa en F5. |
| Baja | `StarletteDeprecationWarning` (sigue desde M1). |
| Baja | Sin Node en la PC: la sintaxis JS se verifica cargando las páginas en Edge headless. |
| Nota | T186 simula la falla del commit sustituyendo `confirmar` por una función que hace rollback y lanza el error (no hay forma realista de provocar un fallo de base después de que el service validó todo). |

## 8. Pendientes que pasan a F3 o al go-live

- **P11:** seguro como % del valor de la mercancía (F3). En F2, SEGURO solo por ENVIO (D-F2-8).
- **D-F2-9:** el cotizador usa solo el recargo más específico (tipo de equipo > modo > NULL).
- Rotar la contraseña de `pricing_app` (obligatorio antes del go-live) y restringirla a sus dos bases.
- La llave de la cuenta de servicio del proxy (en la carpeta local de claves, fuera de OneDrive) nunca entra a OneDrive, git ni chat; evaluar su rotación antes del go-live.
- Checklist a–h de F1 y checklist de navegador F2 (sección 9), ambos pendientes.
- P9: repositorio remoto (hoy no hay remoto; sin push).
- Prueba con los 4 perfiles completa en F5. Pantalla de auditoría en F5.
- Reiniciar el proxy después de cada apagado de la instancia.

## 9. Verificación en navegador

### 9.1 Checklist a–h de F1

**PENDIENTE — commit de F2 autorizado por François sin el checklist, 2026-10-07.** El checklist a–h de F1 (sección 9 de `CIERRE-F1.md`) no se ha ejecutado. La lógica de F1 sigue cubierta por sus tests automáticos (en verde en la Regla 18 de F2).

### 9.2 Checklist de navegador F2

Con la Console abierta (F12), en `http://127.0.0.1:8000/app`:

1. Pricing crea una tarifa aérea KG con tramos (−45 y +45), una LCL WM y una FCL 40HC.
2. Pricing duplica una tarifa con fechas nuevas (funciona) y otra vez con fechas superpuestas (error).
3. Comercial abre Tarifas y en F12 → Network → `tarifas` → Response no aparecen `costo`, `margen_pct`, `margen_unitario`, `minimo`, `metodo_venta` ni `notas`; la tabla no tiene columnas de costo.
4. Gerencia ve costo y margen en Tarifas, sin botones de edición.
5. Pricing crea un recargo THC FCL 40HC por CONTENEDOR y un BL FCL por ENVIO.
6. Comercial no ve Recargos en el menú; por URL (`/app/recargos.html`) recibe "No tiene permiso para esta acción".
7. Comercial crea un cliente y queda asignado a él; no ve los clientes de otro comercial.
8. Admin crea un cliente sin elegir comercial → error; con comercial → OK.
9. Contacto principal: marcar otro desmarca el anterior.
10. 375 px (Ctrl+Shift+M) sin scroll horizontal y Console sin rojo.

Resultado: **PENDIENTE**. No se ha ejecutado. La lógica está cubierta por 170 tests automáticos.

## 10. Avance

F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · **proyecto 45 %**. Sigue F3 (cotizador).

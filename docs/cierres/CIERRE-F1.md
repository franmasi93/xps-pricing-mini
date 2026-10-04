# Acta de cierre — F1 (M2 Geografía + M3 Monedas y tasas + M4 Proveedores + Incoterms + Configuración + Auditoría)

| Campo | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fase | F1 (resto): M2, M3, M4, Incoterms, Configuración y Auditoría |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` |
| Commit anterior | `4456aef` (F0 + M1) |
| Fecha de cierre | 2026-10-03 |
| Decisor | François Ramírez — Gerente General |
| Avance del proyecto | F0 5 % ✅ · F1 15 % ✅ · **proyecto 20 %** |

---

## 1. Resumen en cristiano

El sistema ya tiene los **catálogos** sobre los que se van a cargar las tarifas: regiones, países, puertos y aeropuertos; monedas con su tasa de cambio por fecha; los agentes (proveedores); la tabla de Incoterms que dice qué cobra XPRESS en cada término; y la configuración general (IVA, días de alerta). Si alguien registra una tasa que se aleja más de 20 % de la anterior (por ejemplo, el yuan escrito "al revés"), el sistema pide confirmarla. Cada cambio de tasa, moneda, Incoterm o configuración queda anotado con quién y cuándo. Cada rol ve solo las pantallas que le corresponden. Siguen las tarifas (F2).

## 2. Alcance

### 2.1 Tablas (migración `0002`, escrita a mano)

`region`, `pais`, `puerto`, `moneda`, `tasa_cambio`, `proveedor`, `incoterm`, `configuracion`, `auditoria`. Constraints con nombre explícito (`pk_`, `uq_`, `fk_`, `ck_`, `ix_`). Seed: solo USD, los 11 Incoterms 2020 y las 4 claves de configuración. El RBAC sigue en 4 / 15 / 38: no se agregaron permisos.

### 2.2 Endpoints (`/v1`)

| Módulo | Leer | Escribir |
|---|---|---|
| Regiones, países, puertos (`/regiones`, `/paises`, `/puertos`, con filtros) | cualquier token válido | `catalogo.editar` |
| Monedas (`/monedas`) | cualquier token válido | `tasa.editar` |
| Tasas (`/tasas`, `/tasas/vigente`, `/tasas/{id}`) | `costo.ver` | `tasa.editar` |
| Proveedores (`/proveedores`, con filtros) | `catalogo.editar` o `costo.ver` | `catalogo.editar` |
| Incoterms (`/incoterms`, `/incoterms/{codigo}`) | cualquier token válido | `config.editar` (PATCH) |
| Configuración (`/configuracion`) | cualquier token válido | el `permiso_edicion` de cada clave |
| Auditoría (`/auditoria`, paginada, `limit` ≤ 200) | `auditoria.ver` | — |

Sin DELETE en ningún recurso: responde 405 `METODO_NO_PERMITIDO`; la baja es `activo=false`.

### 2.3 Pantallas y menú por rol

`geografia.html`, `proveedores.html`, `monedas.html`, `incoterms.html`, `configuracion.html` (más `js/ui.js` compartido). Una sola hoja de estilos (`xps-pricing.css`), diseño de `docs/xpressdesignsystem.md`, sin estilos en línea ni `innerHTML`.

| Rol | Menú |
|---|---|
| admin | Inicio, Incoterms, Geografía, Proveedores, Monedas y tasas, Configuración, Usuarios |
| pricing | Inicio, Incoterms, Geografía, Proveedores, Monedas y tasas, Configuración (solo días de alerta) |
| gerencia | Inicio, Incoterms, Proveedores (lectura), Monedas y tasas (lectura) |
| comercial | Inicio, Incoterms |

### 2.4 Services reutilizables para F3

- `services/tasas.obtener_tasa_vigente(db, moneda, fecha) -> Decimal` — tasa más reciente ≤ fecha; sin tasa → 422; USD → 1.
- `services/incoterms.bloques_incluidos(incoterm, sentido)` — importación = bloques en true; exportación = complemento; lista vacía con advertencia en DDP importación y EXW exportación.
- `services/incoterms.validar_incoterm_modo(incoterm, modo)` — FAS, FOB, CFR y CIF con aéreo → 422.
- `services/configuracion.leer_iva_tasa(db) -> Decimal` — única fuente del IVA (la variable `IVA_TASA` del `.env` no se usa en cálculos).
- `services/auditoria.registrar(...)` — agrega el registro en la misma transacción del cambio, sin commit propio.

## 3. Evidencia cruda

### 3.1 Migración 0002: up → down → up

| Base | Pasos | Resultado |
|---|---|---|
| `xps_pricing_test` | `upgrade head` · `downgrade 0001` · `current` (`0001`) · `upgrade head` · `current` | todos `exit: 0` · `0002 (head)` |
| `xps_pricing` | ídem | todos `exit: 0` · `0002 (head)` |

### 3.2 Conteos del seed

```
xps_pricing       alembic=0002 rol=4 permiso=15 rol_permiso=38 moneda=1 incoterm=11 configuracion=4 region=0 pais=0 puerto=0 tasa_cambio=0 proveedor=0 auditoria=0 monedas=['USD'] config=['condiciones_generales_pdf', 'dias_alerta_vencimiento', 'firma_correo', 'iva_tasa']
xps_pricing_test  alembic=0002 rol=4 permiso=15 rol_permiso=38 moneda=1 incoterm=11 configuracion=4 region=0 pais=0 puerto=0 tasa_cambio=0 proveedor=0 auditoria=0 monedas=['USD'] config=['condiciones_generales_pdf', 'dias_alerta_vencimiento', 'firma_correo', 'iva_tasa']
```

### 3.3 pytest por módulo (Parte B)

```
Geografía T73–T89 + T59 de M1:          54 passed, 1 warning in 202.09s (0:03:22)
Monedas y tasas T90–T107:               31 passed, 1 warning in 108.83s (0:01:48)
Proveedores T108–T114:                  15 passed, 1 warning in 72.92s (0:01:12)
Backend F1 completo (T73–T136):        157 passed, 1 warning in 532.90s (0:08:52)
Frontend (T137 ×5 + T64/T65 de M1):      9 passed, 1 warning in 4.04s
Suite completa (Parte B):              262 passed, 1 warning in 787.49s (0:13:07)
```

162 tests nuevos: geografía 53 + monedas 9 + tasas 22 + proveedores 15 + Incoterms 32 + configuración 15 + auditoría 10 + seed 1 + frontend 5.

### 3.4 Regla 18 doble (2026-10-03, instancia encendida a mano)

Cada ciclo: procesos Python del proyecto cerrados (ninguno abierto) → `DROP` / `CREATE DATABASE xps_pricing_test` (0 conexiones abiertas) → `alembic upgrade head` (`0001` → `0002`, `0002 (head)`) → recolección → suite completa.

```
Ciclo 1:  262 tests collected in 0.08s
          262 passed, 1 warning in 623.44s (0:10:23)
Ciclo 2:  262 tests collected in 0.07s
          262 passed, 1 warning in 625.61s (0:10:25)
```

0 failed, 0 errors, 0 skipped; N = recolectados = 262 en ambos ciclos. Sin `OperationalError` en ninguno de los dos.

### 3.5 Canario de encoding y control de secretos (52 archivos de F1)

```
Canario de encoding: 52 OK, 0 con fallas, 52 revisados
contraseña de pricing_app (texto plano): 0 apariciones en 52 archivos
contraseña de pricing_app (codificada en URL): 0 apariciones en 52 archivos
JWT_SECRET: 0 apariciones en 52 archivos
argumento de credenciales del proxy: 0 apariciones en 52 archivos
ruta de la carpeta local de claves (con barra invertida o normal): 0 apariciones en 52 archivos
```

(En esta acta se nombran sin el texto literal, para que el propio control de secretos siga en 0.)

El acta se revisa aparte, junto con el stage.

## 4. Decisiones

| # | Decisión |
|---|---|
| D-F1-1 | La matriz de Incoterms de §9.1 se siembra tal cual (verificada celda por celda; T115 la compara fila por fila con una copia independiente). |
| D-F1-2 | En monedas solo se siembra USD; EUR, CNY y las demás se cargan por pantalla (§15.6). |
| D-F1-3 | Protección de tasas invertidas: `tasa_a_usd` = USD por 1 unidad. Si la tasa se aleja **más** de 20 % de su vecina, se exige confirmación (409 con `tasa_anterior` y `fecha_anterior`); el 20 % exacto no la pide. Con confirmación se guarda y la auditoría lleva la nota "desvío >20% confirmado". |
| D-F1-4 | La tabla `auditoria` se adelanta a F1. |
| D-F1-5 | No se cambia el ISO2 de un país que tiene puertos marítimos: 409 `TIENE_DEPENDIENTES` (sus códigos UN/LOCODE quedarían inconsistentes). |
| Parte A-3 | `tasa_cambio` lleva `actualizado_en`; las correcciones además quedan en la auditoría. |
| Parte A-5 | Una tasa en una moneda inactiva → 422 `MONEDA_INACTIVA`; `obtener_tasa_vigente` sí devuelve las tasas históricas de una moneda inactiva. |
| Parte A-6 | Al corregir una tasa, el desvío se mide contra las vecinas (la anterior; si no hay, la posterior), excluyendo la propia fila. |
| Parte A-7 | El código de región va de 2 a 20 caracteres (`^[A-Z0-9_]{2,20}$`). |
| Parte A-8 | Los proveedores no bloquean la desactivación de un país; un proveedor nuevo en un país inactivo → 422 `PADRE_INACTIVO`. |
| Parte A-9 | En exportación, el seguro también se propone apagado. **Nota para F3.** |
| Parte A-10 | Se permiten tasas con fecha futura; la vigente solo usa las ≤ fecha consultada. |
| Parte A-11 | Comentario en `config.py`: `IVA_TASA` no se usa en cálculos. No se quita de `.env.example`. |
| A1 | `tasa_a_usd` con más de 6 decimales → 422 `TASA_INVALIDA`; nunca se redondea en silencio (T95, 3 casos). |
| A2 | T87 con 2 casos: cambiar el país (→ `PUERTO_PAIS_INCONSISTENTE`) y cambiar el tipo (→ `CODIGO_INVALIDO`). |

## 5. Desvíos respecto al documento rector

- Configuración visible para pricing, limitada a `dias_alerta_vencimiento` (§5.2 manda sobre §14 P13).
- Gerencia lee proveedores (§14 P4 dice admin y pricing; se aplica §6.1, "gerencia: lectura de todo").
- `actualizado_en` en `tasa_cambio` (convención de §7).
- Handler global de 405 con el formato de error propio: cambia el cuerpo del `DELETE /usuarios/{id}` de M1, no su status (T59 sigue en verde).
- Código de región de 2 a 20 caracteres (el prompt decía 2 a 10).

## 6. Incidentes

| # | Incidente | Causa y corrección |
|---|---|---|
| a | `IntegrityError` crudo en lugar de 409 al editar una moneda con un código duplicado (lo detectó T135). | Leer `actor.id` de un objeto vencido después de modificar disparaba un SELECT y, con él, un autoflush del cambio. Corregido: `auditoria.id_de()` toma el id con `inspect()` sin consultar la BD, y los `actualizar_*` de geografía, monedas y proveedores modifican dentro de `no_autoflush`. |
| b | La auditoría guardaba la tasa tal como llegó (`"7.1"`) y no como quedó guardada (`7.100000`). | Se audita con la escala de la columna (6 decimales). |
| c | T104 tenía datos cruzados entre sus dos casos (la tasa "normal" tenía como vecina la invertida). | Datos separados por caso. Error del test, no del código. |
| d | Regla 18 interrumpida: el 2026-10-02 por el límite de sesión, y el 2026-10-03 por la instancia apagada (fin de semana, §3.3). | Se repitió completa con la instancia encendida a mano. |
| e | El proxy abierto desde el 2026-10-01 (PID 23988) quedó trabado después del apagado de la instancia: rechazaba las conexiones en ~0,2 s aunque la instancia ya estaba encendida. | Se reinició con autorización de François, con los mismos argumentos (PID 11812). El archivo de credenciales **no se leyó**; solo se usó su ruta. Diagnóstico posterior: 10 de 10 conexiones OK (~2,1 s). |
| f | La herramienta del EJECUTOR apaga el servidor local a las 2 h. | François enciende uvicorn en su propia PowerShell para las pruebas en el navegador. |

## 7. Deuda

| Prioridad | Deuda |
|---|---|
| Baja | `StarletteDeprecationWarning` (sigue desde M1). |
| Baja | La suite completa tarda ~10–13 min (262 tests). Causa principal: la latencia hacia Cloud SQL. La aceleración 2.10 se descartó con cifras: 241,98 s sin el cambio → 206,78 s y 203,07 s con y sin él (ruido de red); 110 hashes argon2 de ~115 ms → techo de ahorro ≤ 6 %, por debajo del 10 % exigido. Se evalúa en F5. |
| Baja | No hay Node en la PC: la sintaxis JS se verificó cargando las 9 páginas en Edge headless (sin errores de JS). |
| Documentación | `docs/Encender-Auth-Proxy.md` no reflejaba el entorno real. Se actualizó (archivo de trabajo, fuera de git). |

## 8. Pendientes que pasan a F2 o al go-live

- Rotar la contraseña de `pricing_app` (obligatorio antes del go-live).
- Restringir `pricing_app` a sus dos bases.
- El archivo de llave de la cuenta de servicio del proxy (en la carpeta local de claves, fuera de OneDrive) nunca entra a OneDrive, git ni chat; evaluar su rotación antes del go-live.
- Checklist a–h de F1 en el navegador (antes de F2).
- Prueba con los 4 perfiles completa en F5.
- P1, P3, P4 y P5.
- Pantalla de auditoría en F5 (en F1 solo existe el endpoint).
- Reiniciar el proxy después de cada apagado de la instancia.

## 9. Verificación en navegador

Checklist de F1 (con la Console abierta):

- a. Admin crea la región SUDAMERICA, el país EC y los puertos ECGYE (marítimo) y GYE (aéreo).
- b. Puerto PEXXX con país EC → error del prefijo.
- c. Moneda CNY: tasa 0.14 → se guarda; luego 7.1 en otra fecha → diálogo de confirmación.
- d. Proveedor MSL; el mismo con "msl" → error de duplicado.
- e. Incoterms: FOB en Exportación muestra solo recogida, despacho export y gastos origen.
- f. Configuración: pricing solo puede cambiar los días de alerta.
- g. El comercial no ve Geografía, Proveedores ni Monedas, y escribiendo la URL a mano recibe "No tiene permiso".
- h. 375 px sin scroll horizontal y Console sin rojo.

Resultado: PENDIENTE. El checklist a–h no se ha ejecutado. Es obligatorio antes de empezar F2. La lógica está cubierta por 162 tests automáticos.

## 10. Avance

F0 5 % ✅ · F1 15 % ✅ · **proyecto 20 %**. Sigue F2 (tarifas, tramos, recargos, clientes): 25 %.

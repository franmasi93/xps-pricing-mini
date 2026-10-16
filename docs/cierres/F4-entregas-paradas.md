# F4 — Entregas de paradas (modo autónomo del 2026-10-14 y 2026-10-15)

Documento de trabajo del EJECUTOR para que François revise lo hecho mientras no estuvo. Reglas del modo autónomo:
- Las paradas F4-2 y F4-3 se autoaprueban solo si se cumplen tres condiciones: regresión de F3 al centavo, suite completa en verde y ningún valor esperado anterior cambiado.
- Punto de parada: "LISTO PARA PRUEBA REAL".
- Sin commit, sin Tencent real y sin empezar la PARTE 2.

## Parada F4-1 (aprobada por François el 2026-10-14)

- **Plan:** D → A → B → C, aprobado.
- **Logo:** el del modelo es idéntico byte a byte a `frontend/img/xpress-logo.png` (24 583 bytes, 1085 × 207, SHA-256 `fe2eb9e2…`).
- **Dependencias aprobadas:** `tencentcloud-sdk-python-ses==3.1.135` y `cryptography==50.0.2`.

Huecos aprobados (resumen):

| Hueco | Decisión aprobada |
|---|---|
| H-F4-1 | Se guarda lo capturado en lb y pulgadas; se derivan kg y cm |
| H-F4-2 | Tramos en LB: 0/100/220/660/1100/2200. `desde_kg` = "desde, en la unidad de la tarifa" (desvío) |
| H-F4-3 | Regla fiscal real de F3 (país del puerto) |
| H-F4-4 | PCT_RECIBO con base 0 → línea 0 y aviso "Manejo sobre recibo sin base"; el mínimo solo con base > 0 |
| H-F4-5 | Transportistas distintos unidos con " / " |
| H-F4-6 | Columnas Cant. y Base según la tabla propuesta |
| H-F4-7 | Las emitidas antes de F4 nunca toman datos actuales |
| H-F4-8 | Solo las 14 claves nuevas admiten vacío |
| H-F4-9 | La llave Fernet la genera François |
| H-F4-10 | Probar, plantillas y correo de prueba funcionan con el interruptor apagado |
| H-F4-11 a H-F4-16 | Como se propusieron (H-F4-14 con el PDF generado fuera del bloqueo) |

### Línea base de la regresión de F3 (antes de tocar el motor)

`tests/test_regresion_f3.py` (T261–T263) reutiliza `preparar()` y `escenarios()` del script de F3. La base de desarrollo ya tenía FRA/GYE, EC/CN/DE y EUR que dejó el script. Para que la prueba corra también ahí, `preparar()` ahora reutiliza esos catálogos si existen y acepta un RUC propio. El `main()` del script sigue abortando si hay choques, así que su conducta no cambió.

```
tests/test_regresion_f3.py ... 3 passed, 1 warning in 81.28s   (2026-10-14 08:55)
```

## Paradas F4-2 y F4-3 (autoaprobación conjunta, 2026-10-15)

### Qué pasó el 2026-10-14

La primera suite completa (para F4-2) arrancó a las 09:42. A las 10:03 el proxy cortó las conexiones ("server closed the connection unexpectedly"): `2 failed, 165 passed, 431 errors`. Los errores y las fallas son todos de conexión (`psycopg.OperationalError`), no de código. **Esa corrida no cuenta como resultado.** La sesión quedó detenida hasta el 2026-10-15. Ese día la base respondió (`SELECT 1 = 1`, proxy escuchando en 5432) y la suite se repitió completa desde cero.

### Bloques entregados

**D (motor)**
- Constantes exactas en `app/core/unidades.py`.
- Peso cobrable en la unidad de la tarifa (`peso_cobrable_en`) y tramos en LB.
- PCT_RECIBO se calcula al final, sobre la base de las líneas de Recibo de Caja incluidas.
- El transportista se copia de la tarifa; descripción de la carga.

**A (PDF)**
- Plantilla oficial nueva, sin alto fijo: las filas no se parten y el encabezado de la tabla se repite.
- Pie nativo "Hoja X de Y".
- Datos de la empresa copiados a la foto congelada.
- Separador de miles y fechas dd/mm/aaaa.

**B (correo)**
- Cifrado Fernet y `config_correo` con caché de 60 s.
- Interfaz `ProveedorCorreo` con dos implementaciones: TencentSES y la falsa de las pruebas.
- Traducción de errores B9 por código.
- Salud con caché de 10 minutos, lista de plantillas y correo de prueba.
- Envío síncrono con `SELECT … FOR UPDATE`; el PDF se genera fuera del bloqueo.
- Bitácoras de solo inserción.

**C (pantallas)**
- C1: tarifas con transportista y unidad de peso; tramos "Desde (kg)" o "Desde (lb)".
- C2: recargos con la unidad "% sobre Recibo de Caja".
- C3: cotizador con selector KG/LB, transportista y descripción.
- C4–C7: botón real de envío, ventana de confirmación, resultado y sección "Envíos".
- C8: datos de la empresa y correo Tencent (solo admin).

### Migración 0005 (completa, escrita a mano)

Archivo: `alembic/versions/0005_f4_pdf_unidades_correo.py`. Se probó subir, bajar y volver a subir sobre `xps_pricing_test`.

| Tabla | Cambios |
|---|---|
| `tarifa` | Columnas `transportista` (Text) y `unidad_peso` (KG por defecto). Constraints `ck_tarifa_unidad_peso` y `ck_tarifa_lb_solo_aereo_por_peso` |
| `tramo_aereo` | `ck_tramo_aereo_desde_kg_permitido` pasa a 0, 45, 100, 220, 300, 500, 660, 1000, 1100, 2200; qué valores van con cada unidad lo valida el service |
| `cotizacion` | Columnas `transportista`, `descripcion_carga`, `unidad_peso` y `peso_lb`. Constraints `ck_cotizacion_unidad_peso`, `ck_cotizacion_peso_lb_segun_unidad` y `ck_cotizacion_peso_lb_no_negativo` |
| `linea_cotizacion` | Columna `unidad_peso` con `ck_linea_cotizacion_unidad_peso`; `ck_linea_cotizacion_rate_unit` suma PCT_RECIBO |
| `recargo` | `ck_recargo_rate_unit` suma PCT_RECIBO; nuevo `ck_recargo_pct_recibo_no_seguro` |
| `config_empresa` (H-F4-17) | Una sola fila (`ck_config_empresa_una_sola_fila`) con 14 textos vacíos |
| `config_correo` | Una sola fila con los valores iniciales de B2 y las llaves vacías. Constraints `ck_config_correo_una_sola_fila`, `_timeout`, `_adjunto_max` y `_plantilla_positiva` |
| `envio_correo` y `envio_correo_prueba` | CHECKs `_estado`, `_enviado_con_message_id`, `_fallido_con_codigo` y `_adjunto_bytes_no_negativo`; índice `ix_envio_correo_cotizacion_id`; trigger `fn_bitacora_solo_insercion`, que rechaza UPDATE y DELETE |

### Pruebas nuevas (T261–T300)

| Archivo | Pruebas |
|---|---|
| `tests/test_regresion_f3.py` | T261–T263: regresión de F3 al centavo |
| `tests/test_f4_motor.py` | T264–T273: bloque D |
| `tests/test_f4_pdf.py` | T274–T281: bloque A, incluido el nombre seguro del adjunto |
| `tests/test_f4_correo.py` | T282–T299: bloque B |
| `tests/test_f4_correo_concurrencia.py` | T300: dos envíos simultáneos → un solo correo a la vez |
| `tests/correo_falso.py` | Proveedor falso: sin SDK ni red |

Corridas parciales en verde:
```
D:    tests/test_f4_motor.py ........................ 14 passed in 301.92s
A:    tests/test_f4_pdf.py .......................... 12 passed + T274 passed tras corregir la prueba
B:    test_f4_correo.py + test_f4_correo_concurrencia  26 passed in 621.44s
Base: regresión + motor + tarifas + recargos ........ 145 passed in 1034.93s
```

### Suite completa (2026-10-15, base de pruebas con conexión estable)

```
inicio 2026-10-15 09:10:51
624 passed, 1 warning in 5167.65s (1:26:07)
fin 2026-10-15 10:37:00
```

La corrida tuvo 0 errores de conexión. La regresión de F3 (T261–T263) dio 1105.70 / 428.31 / 8007.50 al centavo, y ningún valor esperado anterior cambió. **Las Paradas F4-2 y F4-3 quedan AUTOAPROBADAS.** El aviso que aparece es el `StarletteDeprecationWarning`, la deuda conocida que se trata en F5-A4.

### PDF de muestra (salidas/f4/)

Los tres se generaron en `xps_pricing_test`, dentro de una transacción que se revierte al final.

| Archivo | Contenido | Hojas | Total USD |
|---|---|---|---|
| `a_aereo_LB_COT-2026-00001_….pdf` | Tarifa por LB con tramos, carga en LB | 2 | 405.00 |
| `b_lcl_PCT_RECIBO_COT-2026-00002_….pdf` | Manejo local 6 % sobre recibo, seguro encendido | 2 | 1,496.34 |
| `c_fcl_varias_hojas_COT-2026-00003_….pdf` | 60 recargos | 5 | 2,439.17 |

Capturas de la primera y la última hoja de cada uno: `salidas/f4/capturas/PDF_*_hoja*.png`.

### Simulación de pantallas (API simulada; capturas en salidas/f4/capturas/)

```
comercial detalle 1280/375     errores=[] scrollWidth=1280/375  enviar=True envios=True msgid_abreviado=True crudo=False
comercial C5 ventana 1280/375  errores=[] cc=2 bcc_visible=True adjunto='COT-2026-00004_Importadora-Nandu-S-A.pdf · 274 KB'
comercial C6 exito 1280/375    errores=[] alerta='Enviado a ana@cliente.ec · estado ENVIADA'
comercial C6 fallo 1280/375    errores=[] alerta='Envío limitado temporalmente… / Puede reintentar el envío más tarde con el mismo botón.' boton='Enviar'
gerencia detalle 1280/375      errores=[] enviar=False envios=2
admin configuracion 1280/375   errores=[] empresa=True correo=True salud_ok=4 llave_en_campo=''
comercial configuracion        errores=[] correo_oculto=True empresa_oculta=True
comercial cotizador LB         errores=[] etiqueta='Peso real (lb)' ayuda='Dimensiones por bulto (pulgadas)…' transportista=1 descripcion=1
admin tarifas / recargos       errores=[] unidad_peso_visible=True transportista=1 / pct_recibo=1
```

En "C6 fallo" se excluye de los errores de consola el aviso del navegador por el 502 simulado: es la respuesta esperada.

Capturas, a 1280 y 375 px cada una:
- `C3_cotizador_lb`
- `C5_ventana_envio`
- `C6_resultado_exito` y `C6_resultado_fallo`
- `C7_detalle_envios_comercial` y `C7_detalle_envios_gerencia`
- `C8_configuracion_admin`

### Archivos tocados

**Nuevos**
- Migración: `alembic/versions/0005_f4_pdf_unidades_correo.py`.
- Núcleo: `app/core/cifrado.py`, `app/core/unidades.py`.
- Modelo, router y esquema: `app/models/correo.py`, `app/routers/correo.py`, `app/schemas/correo.py`.
- Servicios: `app/services/correo.py`, `app/services/empresa.py`, `app/services/proveedor_correo.py`, `app/services/tencent_ses.py`.
- Pruebas: `tests/correo_falso.py`, `tests/test_f4_correo.py`, `tests/test_f4_correo_concurrencia.py`, `tests/test_f4_motor.py`, `tests/test_f4_pdf.py`, `tests/test_regresion_f3.py`.
- Este documento.

**Modificados (30 archivos, +1316 / −231)**
- Configuración y dependencias: `.env.example`, `app/config.py`, `requirements.txt`.
- Aplicación y modelos: `app/main.py`, `app/models/__init__.py`, `app/models/cotizaciones.py`, `app/models/tarifas.py`.
- Routers: `app/routers/catalogos.py`, `app/routers/cotizaciones.py`.
- Esquemas: `app/schemas/catalogos.py`, `app/schemas/cotizaciones.py`, `app/schemas/tarifas.py`.
- Servicios: `app/services/cotizaciones.py`, `app/services/cotizador.py`, `app/services/pdf.py`, `app/services/recargos.py`, `app/services/tarifas.py`.
- Plantilla del PDF: `app/templates/cotizacion.html`.
- Pantallas HTML: `frontend/configuracion.html`, `frontend/cotizacion.html`, `frontend/cotizador.html`, `frontend/recargos.html`, `frontend/tarifas.html`.
- Estilos y JS: `frontend/css/xps-pricing.css`, `frontend/js/configuracion.js`, `frontend/js/cotizacion.js`, `frontend/js/cotizador.js`, `frontend/js/recargos.js`, `frontend/js/tarifas.js`.
- Script: `scripts/cotizaciones_prueba_f3.py`.

### Huecos decididos por el EJECUTOR (para revisión de François)

| Hueco | Decisión | Motivo |
|---|---|---|
| H-F4-17 | Los 14 datos de A4 van en `config_empresa`, no en `configuracion`. **APROBADO por François el 2026-10-15** | Sembrarlos en `configuracion` obligaba a cambiar el valor esperado de T124 y T136 |
| H-F4-18 | Lugar del Incoterm en el PDF: grupos E y F (EXW, FCA, FAS, FOB) → origen; grupos C y D → destino | Es el lugar que nombra cada regla Incoterm |
| H-F4-19 | Un adjunto mayor que `adjunto_max_bytes` no llama a Tencent: deja una fila FALLIDO con `ADJUNTO_DEMASIADO_GRANDE` y responde 502 | Queda trazado en la bitácora, como cualquier fallo de envío |
| H-F4-20 | Los montos del PDF se redondean a 2 decimales con ROUND_HALF_UP | El formato de Python redondeaba al par (75.4650 → 75.46; ahora 75.47). Solo cambia cómo se imprimen las líneas, que se guardan a 4 decimales; ningún cálculo ni total guardado cambia |
| H-F4-21 | `codigo_error` de la bitácora guarda el código interno (B9). El código y el mensaje crudos de Tencent van en `respuesta_proveedor` (JSON) | La pantalla muestra solo el mensaje traducido |
| H-F4-22 | El PDF muestra siempre los dos bloques fiscales; un bloque vacío dice "Sin conceptos en este bloque" | Igual que en F3; T253 lo exige |
| H-F4-23 | En la plantilla se desactivan las formas contextuales de Inter (`calt`/`case`) | Cambiaban "(" y ")" por glifos que el texto del PDF no mapea |
| H-F4-24 | Las bitácoras son de solo inserción también en la base (trigger), además de en la API (405) | Defensa adicional |
| H-F4-25 | "(mín.)" sale cuando no hay ajuste manual, el mínimo es mayor que 0, cantidad × precio queda por debajo del mínimo y el subtotal es igual al mínimo | Definición de "se cobró el mínimo" |
| H-F4-26 | `GET /v1/cotizaciones/{id}/envio` (con `cotizacion.enviar`) arma la ventana C5; el tamaño del adjunto se mide descargando el PDF | C5 pide nombre y tamaño del adjunto |
| H-F4-27 | Cambiar `unidad_peso` o `peso_lb` borra las líneas, como cualquier cambio de carga (pide confirmación D-F3-10 si hay ajustes) | La cantidad de una tarifa en LB depende de lo capturado |
| H-F4-28 | Se fija también `tencentcloud-sdk-python-common==3.1.188` | Es dependencia del SDK; se fija igual que el SDK |
| H-F4-29 | PCT_RECIBO con base 0: también el costo vale 0 | Coherente con "la línea vale 0" de H-F4-4 |

**Desvío.** `preparar()` del script de F3 ahora reutiliza catálogos existentes y acepta otro RUC. Su `main()` sigue abortando ante choques.

**Valores esperados.** Ninguna prueba anterior cambió su valor esperado.

## Parada F4-4 · Regla 18 doble (2026-10-15)

Cada ciclo hace lo mismo:
1. Comprueba que no quedan procesos Python del `.venv`.
2. DROP y CREATE de `xps_pricing_test`.
3. `python -m alembic upgrade head` hasta 0005 (head).
4. Recolecta las pruebas.
5. Corre la suite completa.

Duración prevista: 2 × ~90 min. Arrancó a las 10:37 y terminó a las 13:31, dentro del límite de 19:10.

```
ciclo 1  inicio 2026-10-15 10:37:38 · DROP/CREATE ok · alembic exit 0 · 0005 (head) · 624 tests collected
         624 passed, 1 warning in 5148.23s (1:25:48) · fin 2026-10-15 12:03:51
ciclo 2  DROP/CREATE 12:04:07 ok · alembic exit 0 · 0005 (head) · 624 tests collected
         624 passed, 1 warning in 5206.86s (1:26:46) · fin 2026-10-15 13:31:18
```

N = 624 recolectadas; 0 failed, 0 errors, 0 skipped en los dos ciclos.

Canario de encoding sobre los 178 archivos de texto que git ve: `Canario de encoding: 178 OK, 0 con fallas, 178 revisados`.

Nota operativa: `alembic.exe` lo bloquea una política de control de aplicaciones de Windows. El script del ciclo ahora usa `python -m alembic`, que es equivalente.

**Estado: LISTO PARA PRUEBA REAL.** Me detengo aquí, antes del paso 1 de la Parada F4-4. No hay commit.

## Estado al cierre del 2026-10-15

### Avance por bloque

| Bloque | Avance | Detalle |
|---|---|---|
| D · motor (3 %) | 100 % | — |
| A · PDF (3 %) | 100 % | — |
| B · correo (5 %) | 100 % del código y las pruebas | Falta la validación contra Tencent real, que es la prueba real |
| C · pantallas (2 %) | 100 % | — |
| Prueba real (2 %) | 0 % | Pendiente de François |

Avance del proyecto: 75 % + 13 % = **88 %**. El 90 % se alcanza con la compuerta de la prueba real y el commit de F4.

### P9 · GitHub

- **Control de secretos sobre toda la historia** (5 commits, `git log -p --all`): 0 apariciones de la contraseña de la base (en texto y codificada, la de trabajo y la de pruebas), de JWT_SECRET, de "IKID" con 20 o más caracteres, de "BEGIN PRIVATE KEY", de "private_key" y de `"type": "service_account"`. CONFIG_CIFRADO_KEY todavía no existe en el `.env`, así que no aplica.
- **Archivos sensibles:** ninguno estuvo nunca en la historia. Siguen fuera de git `.env`, `salidas/`, `start.txt`, `docs/TENCENT_CLOUD.md`, `docs/Encender-Auth-Proxy.md`, `docs/TRASPASO-*` y los `CIERRE-M*.md`. `frontend/image.png` ya no existe en la carpeta.
- **Remoto:** `git remote add origin https://github.com/franmasi93/xps-pricing-mini.git` hecho; `git fetch` y `git ls-remote` responden sin ramas, es decir, el remoto está vacío.
- **Push:** `git push -u origin main` lo **bloqueó el sistema de permisos de Claude Code** (no fue Git ni GitHub). No se intentó por otra vía.
- **Push hecho el 2026-10-15** por pedido explícito de François (`git push -u origin main`): `* [new branch] main -> main`, `branch 'main' set up to track 'origin/main'`. `git log origin/main -1` → `6375d5d F3: acta de cierre con hash`. `git status -sb` → `## main...origin/main`: rama al día con el remoto; el trabajo de F4 sigue intacto y sin commit.

### Pruebas

- Suite completa: `624 passed, 1 warning in 5167.65s`.
- Regla 18 ciclo 1: `624 passed, 1 warning in 5148.23s`.
- Regla 18 ciclo 2: `624 passed, 1 warning in 5206.86s`.
- La corrida del 2026-10-14 (`2 failed, 165 passed, 431 errors`) se descartó porque fue un corte del proxy.

### Huecos nuevos decididos

H-F4-18 a H-F4-29 (tabla de arriba). H-F4-17 fue aprobado por François. Ninguno toca cálculo de precios, mínimos, IVA o totales, ni secretos, permisos o datos existentes. H-F4-20 cambia solo cómo se imprimen las líneas en el PDF.

### Qué necesita François para seguir

1. **GitHub:** hecho (P9 cerrado).
2. **CONFIG_CIFRADO_KEY (H-F4-9)**, en PowerShell, en la carpeta del proyecto:
   1. Generarla: `.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   2. Copiar el resultado al `.env` como `CONFIG_CIFRADO_KEY=<resultado>`.
   3. Guardar una copia fuera de OneDrive, en un gestor de contraseñas. En F5 va a Secret Manager con el mismo valor.
   4. Borrar del `.env` las líneas viejas `TENCENT_*` y `SES_*`.
3. **Migrar la base de trabajo:** `.\.venv\Scripts\python.exe -m alembic upgrade head` (a 0005). La Regla 18 solo tocó `xps_pricing_test`.
4. **Plantilla 72669 aprobada** en Tencent.
5. **Datos en Configuración**, como admin: las condiciones generales del PDF y los datos de la empresa (bloque nuevo "Datos de la empresa para el PDF").
6. **Prueba real**, siguiendo los pasos 2 a 7 de la Parada F4-4:
   1. En Configuración → Correo Tencent, pegar el SecretId y la SecretKey del subusuario `pricing-ses` y elegir la plantilla.
   2. "Probar conexión": los 3 puntos en verde.
   3. Activar el interruptor y guardar.
   4. "Enviar correo de prueba" a un correo de François.
   5. Enviar una cotización emitida a los **tres contactos de prueba** (Gmail, Outlook/Hotmail y @xpress.ec), que debe indicar François.
7. **Compuerta y cierre:** aprobar la compuerta y autorizar los dos commits de F4.

*La lista de arriba quedó superada por la sección siguiente: los pasos 1, 2, 3 y 5 ya están hechos.*

## Estado al cierre del 2026-10-15 · prompt autónomo hasta el 100 % (tarde)

### Motivo exacto de la parada

**FASE 2 detenida en el paso 2.2.** El prompt trae los correos de D-AUT-4 como marcadores sin llenar (`<<GMAIL>> · <<OUTLOOK>> · <<XPRESS>>`). Se preguntó y la respuesta fue "Aún no los tengo".

Sin esos correos no hay correo de prueba ni los 3 envíos. Por lo tanto:
- no hay compuerta técnica de F4;
- no hay commits de F4 (FASE 3);
- y, según 4.6, tampoco commit intermedio de F5, porque llevaría el código de F4 sin su compuerta (H-F5-4).

Se avanzó con la FASE 4 como indica el prompt.

### Fases y avance

| Fase | Estado |
|---|---|
| FASE 0 · llaves al `.env` | Hecha. Conteos: 1 aparición de cada clave en el `.env`; 0 apariciones de los valores fuera del `.env` (422 archivos revisados) |
| FASE 1 · llaves y datos | Hecha (detalle abajo) |
| FASE 2 · prueba real | 2.1 hecho (salud real en verde); detenida en 2.2 (faltan los correos) |
| FASE 3 · cierre de F4 | Pendiente de la compuerta técnica |
| FASE 4 · F5 sin François | Parte 1 hecha (A, preparación de B y C), salvo lo anotado abajo |

**Detalle de la FASE 1:**
- **1.1** `CONFIG_CIFRADO_KEY` generada y escrita directo al `.env`, sin mostrarla.
- **1.2** Script `scripts/sembrar_correo.py`.
- **1.3** La base de trabajo `xps_pricing` estaba en 0004 (1 admin activo, 0 cotizaciones) y pasó a **0005**.
- **1.4** Llaves cifradas en `config_correo` de las dos bases (SecretId `IKID****ZQ3`, estado DESHABILITADO, auditoría con llaves enmascaradas). Del `.env` se borraron las líneas `TENCENT_SEED_*` y las viejas `TENCENT_*`/`SES_*` (paso 4 de H-F4-9). Conteo final: **0 apariciones de "TENCENT_SEED" y 0 de los valores semilla en el `.env`**.
- **1.5** `scripts/cargar_configuracion_inicial.py` cargó en las dos bases las condiciones generales (7 puntos) y los datos de la empresa (14 de 14 iguales a lo aprobado), con auditoría. En la base de trabajo quedó una auditoría por entidad: `config_correo`, `config_empresa` y `configuracion`. Condiciones y cláusula pendientes de revisión legal (no bloquea).

**Salud real 2.1** (`xps_pricing_test`, `refrescar=true`):
```
dominio notificaciones.xpress.ec verificado=true · remitente pricing@notificaciones.xpress.ec existe=true ·
plantilla 72669 estado=0 "Aprobada" · error=null · todo_ok=true
```
El correo queda **DESHABILITADO en las dos bases** (2.5: sin compuerta técnica no se habilita en la de trabajo).

**MessageId de la prueba real:** todavía no hay (no hubo envíos).

**Avance del proyecto: 88 %.** F4 al 13 % de 15 %: falta la prueba real. F5 no suma hasta su cierre.

### FASE 4 · F5 parte 1

**F5-A · auditoría y deuda**

| Punto | Estado |
|---|---|
| A1 | Pantalla de Auditoría (`frontend/auditoria.html`, menú con `auditoria.ver`): filtros por entidad, usuario y fechas; paginada; detalle "campo: antes → después". Nuevo `GET /v1/auditoria/usuarios` y filtro `usuario_id` |
| A2 | Paginación de tarifas y recargos: `limit`/`offset` opcionales y total en `X-Total-Count`. Sin `limit`, la lista completa como en F2 (H-F5-1). Paginador en las dos pantallas, 25 filas, con los mismos filtros |
| A3 | `pg_trgm` se crea sin superusuario (probado en una transacción revertida). Migración **0006** con índices GIN de trigramas en `cliente.razon_social` y `cliente.ruc_o_id`; probada subiendo, bajando y volviendo a subir |
| A4 | `StarletteDeprecationWarning` ("install httpx2"). **Se documenta, no se corrige:** viene de `fastapi.testclient` y pide cambiar la dependencia de pruebas `httpx` por `httpx2`, lo que no es un cambio menor. Solo afecta a las pruebas |
| A5 | **No aplicado** (detalle abajo) |

Sobre A5: no hubo una medición por prueba (`--durations`) que justifique un cambio sin riesgo. La causa visible del tiempo (~8 s por prueba) es la latencia de cada consulta contra Cloud SQL por el proxy. Propuesta para la próxima sesión: medir con `pytest --durations=30` y aplicar solo cambios que mantengan N (D-AUT-8), por ejemplo reutilizar la conexión del motor entre pruebas dentro del mismo SAVEPOINT.

**D-AUT-7 · fuera de horario.** Una falla de **conexión** con la base (no un deadlock ni otro error de consulta) responde **503 `SISTEMA_FUERA_DE_HORARIO`**, con el horario y `Retry-After: 300`, sin detalles internos. `/v1/salud` sigue dando 200 con `"bd": "error"`, que es lo que necesita el health check de Cloud Run. Las pantallas muestran el mensaje del backend.

**F5-B · preparación del despliegue (sin tocar Google Cloud)**
- `Dockerfile`: Python 3.13-slim, dependencias fijas, Chromium de Playwright con sus librerías, usuario no root, `APP_ENV=prod`, logs JSON.
- `.dockerignore`: excluye `.env`, `.venv`, `tests`, `docs`, `salidas`, `.git` y archivos de llaves.
- **Docker no está instalado** en el equipo: no se probó la construcción local. La guía usa Cloud Build (`gcloud run deploy --source`).
- `app/config.py`: `DATABASE_URL_TEST` es opcional solo con `APP_ENV=prod` (sigue obligatoria en dev y test), y se acepta la URL por el socket de Cloud SQL (`?host=/cloudsql/...`).
- Logs estructurados: `app/core/registro.py` y `app/core/log_config.json`.
- `scripts/subir_secretos.py` sube los 3 secretos sin mostrarlos.
- Región **us-central1**, leída del nombre de conexión documentado `xps-reborn-v2:us-central1:xpress-db-reborn-v2`. La guía trae además el comando que la confirma.
- `docs/DESPLIEGUE.md`: paso a paso con lo que debe verse después de cada comando.
- `docs/go-live/`: rotación de la contraseña, restricción de `pricing_app`, backups y llave del proxy.

**F5-C · verificación**
- `docs/CHECKLIST-FINAL.md`: 51 puntos, con F1 a–h, F2, F3, M1 4–12, F4 y F5.
- `scripts/crear_usuarios_prueba.py` y `scripts/desactivar_usuarios_prueba.py`, con la lógica en `scripts/usuarios_prueba.py`.

**Pruebas nuevas**

| Prueba | Qué verifica |
|---|---|
| T301 | Fuera de horario, con una base inalcanzable de verdad |
| T302 | Paginación de tarifas y recargos |
| T303 | Pantalla, menú, filtro por usuario y permiso de Auditoría |
| T304 | Índices de trigramas y búsqueda |
| T305 | La imagen no lleva secretos (`.dockerignore` y Dockerfile) |
| T306 | Configuración de producción y error claro si falta un secreto |
| T307 | Logs estructurados sin detalles |
| T308 | Usuarios de prueba |

### Huecos nuevos (F5)

| Hueco | Decisión | Motivo |
|---|---|---|
| H-F5-1 | La paginación de tarifas y recargos es opcional (`limit`/`offset`), con el total en `X-Total-Count` | Así las pruebas de F2, que esperan una lista, no cambian su valor esperado |
| H-F5-2 | El SQL de restricción de `pricing_app` no quita el `CONNECT` a `PUBLIC` en las bases de otros sistemas sin confirmar sus roles | Podría cortar a XPS-Reborn en la misma instancia; queda como paso guiado para François |
| H-F5-3 | `DATABASE_URL_TEST` es opcional solo en prod | En Cloud Run no hay base de pruebas |
| H-F5-4 | Sin commit intermedio de F5 mientras F4 no tenga commit | El commit llevaría el código de F4 sin su compuerta técnica |
| H-F5-5 | Las llaves de Tencent se pegaron en el chat | Se recomienda rotar la SecretKey de `pricing-ses` después de la prueba real (`docs/go-live/README.md`, punto 5) |

### Mensaje ajeno a este proyecto

A las 15:35 llegó un pedido de push de la rama `wip/m10a` (commit `e64b6a1`, `verify_parity_dev_test.py`, `perfiles.json`). Esa rama y ese commit son del repositorio **XPS-Reborn-V2.1** (`franmasi93/XPS-Reborn-V2.1`), no de xps-pricing-mini. **No se tocó nada:** ni control de secretos ni push en ese repositorio. Si era para esta sesión, François debe confirmarlo y se hace en una tarea aparte.

### Pruebas (líneas crudas)

**Corridas parciales de F5, en verde:**
- T301 y login: `6 passed`
- T302: `2 passed`
- T303 con frontend y auditoría: `29 passed`
- T304–T307 con config: `6 passed`
- T308: `1 passed`

**Regla 18 doble de F5 parte 1**

Base virgen y migraciones hasta 0006, N = 634.

```
ciclo 1  inicio 2026-10-15 15:48:44 · alembic exit 0 · 0006 (head) · 634 tests collected
         634 passed, 1 warning in 5285.18s (1:28:05) · fin 2026-10-15 17:17:15
ciclo 2  2026-10-16 · DROP/CREATE ok · alembic exit 0 · 0006 (head) · 634 tests collected
         634 passed, 1 warning in 6026.74s (1:40:26) · fin 2026-10-16 10:19:10
```

Sobre el calendario de los ciclos:
- El ciclo 2 no se corrió el 2026-10-15 porque, al ritmo medido, terminaba pasadas las 19:10.
- El 2026-10-16 se corrió solo el ciclo 2, por indicación de François: un ciclo ya en verde no se repite.
- Resultado: 0 failed, 0 errors, 0 skipped en los dos ciclos.

**Controles del 2026-10-16**
- Canario de encoding sobre los 200 archivos de texto que git ve: `200 OK, 0 con fallas, 200 revisados`.
- Llaves de Tencent: **0 apariciones en todo el proyecto, incluido el `.env`**.

**Commit intermedio de F5 (4.6):** no se hizo. La Regla 18 está en verde, pero F4 sigue sin commit por falta de la compuerta técnica (H-F5-4).

### Qué necesita François, en orden

1. **Los tres correos de D-AUT-4** (Gmail, Outlook/Hotmail y @xpress.ec). Con ellos el EJECUTOR hace 2.2–2.5 y la FASE 3 (≈ 30 min, sin François).
2. **Copiar `CONFIG_CIFRADO_KEY` del `.env` a su gestor de contraseñas** (≈ 2 min). El valor es el mismo que irá a Secret Manager.
3. **Después de los commits de F4:** `git push origin main` (≈ 1 min, D-AUT-9).
4. **Compuerta visual de F4** en sus 3 buzones (≈ 10 min), cuando lleguen los correos.
5. **Rotar la SecretKey de `pricing-ses`** en Tencent CAM y pegarla en Configuración (≈ 5 min, H-F5-5).
6. **P-A · sesión de despliegue** con `docs/DESPLIEGUE.md` y `docs/go-live/` (≈ 45 min).
7. **P-B · verificación final** con `docs/CHECKLIST-FINAL.md` en producción con los 4 roles (≈ 60–90 min).
8. **Confirmar el pedido de push de `wip/m10a`**, que es de XPS-Reborn-V2.1 (≈ 1 min).

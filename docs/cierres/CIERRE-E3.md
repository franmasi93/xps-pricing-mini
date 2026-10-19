# Acta de cierre · E3 · Notificaciones y avisos

| Dato | Valor |
|---|---|
| Extensión | E3 (20 % de las extensiones E0–E3) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code (sesión autónoma del 2026-10-19) |
| Fecha de cierre | 2026-10-19 |
| Commits | `9d7d4f5` (E3.0–E3.3) · esta acta |
| Migración | `0010_e3_notificaciones` (0009 → 0010) |
| Respaldo de producción | **1792394308491** (justo antes de migrar a 0010) |
| Producción | https://xps-pricing-809824844407.us-central1.run.app · revisión **xps-pricing-00006-ghb** |
| Cloud Scheduler | **`xps-notificaciones-evaluar`**: `5 7-19 * * 1-5`, America/Guayaquil, POST a `/internal/notificaciones/evaluar` con `X-Tarea-Secreto` |
| Plan | `docs/extensiones/E3-PLAN.md` |

## 1. Resumen en cristiano

El sistema ya avisa solo de lo comercial y de pricing:

- **A los clientes:**
  - recordatorio de seguimiento de una cotización enviada sin respuesta;
  - aviso de que está por vencer y de que venció;
  - confirmación con los siguientes pasos cuando la acepta;
  - opcionalmente, nuevas tarifas en las rutas que cotizó.

  Estos avisos están **en SIMULACIÓN**: el sistema registra en la bitácora lo que habría enviado y no envía nada. Activarlos es decisión del gerente.
- **A la empresa:**
  - cotización aceptada o rechazada, con su motivo;
  - cotización sin respuesta;
  - margen bajo;
  - tarifas por vencer (un correo diario) y tarifas vencidas sin reemplazo;
  - tasa de cambio desactualizada;
  - correos fallidos;
  - campañas terminadas o con rebote alto;
  - cupo de correo cerca del tope;
  - usuario bloqueado;
  - resumen diario y semanal para la Gerencia.

  Todo llega a la **campana** de cada usuario. Por correo llega cuando Tencent aprueba la plantilla de avisos internos (hoy está rechazada; ver Pendientes).

## 2. Avance por fase

| Fase | Peso | Estado |
|---|---|---|
| E3.0 Análisis | 2 % | Hecho: contexto verificado y plan (`E3-PLAN.md`) |
| E3.1 Eventos y reglas | 5 % | Hecho: 19 eventos en código, reglas por pantalla con auditoría y siembra completa |
| E3.2 Motor | 6 % | Hecho: outbox, evaluación horaria idempotente, envío con el cupo compartido, cancelaciones y todos los controles |
| E3.3 Centro de notificaciones y pantallas | 4 % | Hecho: campana, Mis notificaciones y preferencias, Configuración → Notificaciones, Bitácora, interruptores en cotización, cliente y contacto |
| E3.4 Cierre | 3 % | Hecho, salvo la **prueba real** del resumen y del aviso interno al administrador: espera a que Tencent apruebe 72752 y 72753 (ver Pendientes) |
| **Total E3** | **20 %** | **20 %** (la prueba real queda documentada como pendiente del gerente; todo lo demás está en producción) |

## 3. Lo construido

### 3.1 Datos (0010)

| Tabla o columna | Para qué |
|---|---|
| `config_avisos` (una fila) | Modo de los avisos a clientes (**SIMULACIÓN**, ACTIVO o APAGADO), "aplicar desde" (**2026-10-19**), tope de 3 avisos por cliente por semana, días hábiles de lunes a viernes de 8 a 18 y última evaluación |
| `regla_notificacion` | Una o más reglas por evento: activa, canales (correo y/o campana), destinatarios, parámetros, plantilla, agrupación y obligatoria. Con auditoría |
| `notificacion` | El outbox y la bitácora:<br>• evento, regla, entidad, cliente, comercial y destinatario;<br>• canal y estado (PENDIENTE, ENVIADO, SIMULADO, FALLIDO, CANCELADO u OMITIDO) con su motivo;<br>• contenido (variables), programada para, intentos, message_id y leída;<br>• **`clave_idempotencia` única** |
| `preferencia_notificacion` | Qué eventos internos recibe cada usuario por correo |
| `cotizacion.avisos_activos`, `cliente.avisos_activos` y `contacto_cliente.recibir_avisos` | Interruptores "no enviar avisos" y preferencia del contacto (por defecto, sí) |
| Permisos | `notificaciones.ver` (los 4 roles), `notificaciones.reglas.gestionar` (admin) y `notificaciones.bitacora.ver` (admin y pricing) |

**Downgrade:** no se ejecuta si ya salió algún aviso real a clientes, porque la bitácora se perdería.

### 3.2 Eventos y su plantilla

| Evento | Para | Tipo | Plantilla |
|---|---|---|---|
| COT_SEGUIMIENTO (3 días; 2 recordatorios cada 4 días) | Contacto de la cotización | Por fecha | 72747 |
| COT_POR_VENCER (3 días antes) | Contacto | Por fecha | 72748 |
| COT_VENCIDA (al día siguiente; ventana de 7 días) | Contacto | Por fecha | 72749 |
| COT_ACEPTADA_CLIENTE (con 3 pasos editables) | Contacto | Inmediato | 72750 |
| TARIFA_RUTA_INTERES (**inactiva**) | Contactos que cotizaron la ruta en 6 meses | Por fecha | 72751 |
| COT_ACEPTADA y COT_RECHAZADA | Comercial y Pricing | Inmediato | 72752 |
| COT_SIN_RESPUESTA | Comercial | Por fecha | 72752 |
| COT_MARGEN_BAJO (menos de 15 % o línea bajo costo) | Pricing y Gerencia | Inmediato | 72752 |
| TARIFA_POR_VENCER (agrupado en uno diario) | Pricing | Por fecha | 72752 |
| TARIFA_SIN_REEMPLAZO | Pricing | Por fecha | 72752 |
| TASA_DESACTUALIZADA (7 días) | Pricing | Por fecha | 72752 |
| ENVIO_FALLIDO (obligatorio) | Administrador y quien envió | Inmediato | 72752 |
| CAMPANA_TERMINADA (solo campana) | Creador y administrador | Por fecha | — |
| CAMPANA_REBOTE_ALTO (más de 5 %) | Creador y administrador | Por fecha | 72752 |
| CUOTA_TENCENT_CERCA (80 %, obligatorio) | Administrador | Por fecha | 72752 |
| USUARIO_BLOQUEADO (obligatorio) | Administrador | Inmediato | 72752 |
| RESUMEN_DIARIO (07:00) y RESUMEN_SEMANAL (lunes 07:00) | Gerencia | Resumen | 72753 |

**Qué trae el resumen:**
- cotizaciones emitidas, enviadas, aceptadas y rechazadas;
- tasa de cierre, monto y margen;
- motivos de rechazo;
- rutas y servicios más cotizados;
- cotizaciones por vencer y tarifas por vencer;
- campañas del periodo.

Todo se lee de la base, y la prueba TE3-18 compara cada cifra.

### 3.3 Motor

- **Inmediatos:** se generan en la misma transacción del servicio, justo antes de su commit y dentro de un savepoint (patrón outbox). El comportamiento de aceptar, rechazar, emitir, enviar y entrar no cambió: las 738 pruebas anteriores pasan sin tocarlas.
- **Por fecha y resúmenes:** con `evaluar`, cada hora. Evaluar varias veces nunca duplica, gracias a `ON CONFLICT DO NOTHING` sobre la clave.
- **Controles de los avisos a clientes:**
  - el modo, que en APAGADO no genera nada;
  - "aplicar desde";
  - los interruptores de la cotización y del cliente;
  - la preferencia del contacto;
  - las bajas de E1 en los avisos comerciales;
  - el tope semanal;
  - el horario hábil, que reprograma al siguiente horario.
- **Cancelaciones:** aceptar, rechazar o emitir una cotización que reemplaza a otra cancela los avisos pendientes de la original.
- **Envío:**
  - con el proveedor de F4 y TriggerType 1;
  - con el cupo de E1: los avisos usan el tope total del día, es decir, la reserva que los boletines no tocan;
  - `procesar-lote` envía primero los avisos y después las campañas;
  - 3 intentos para los errores temporales;
  - un aviso que falla genera ENVIO_FALLIDO;
  - PDF adjunto opcional, si respeta `adjunto_max_bytes`.
- **Plantillas:** solo se envían las variables que tiene la plantilla, y nunca el agente o proveedor (solo el transportista).

### 3.4 Pantallas

- **Campana** junto al perfil, con el contador de no leídas, en todas las pantallas.
- **Mis notificaciones:** lista con enlace, "marcar leída" y "marcar todas". **Mis preferencias:** correo sí o no por evento interno; los obligatorios no se apagan.
- **Administración → Notificaciones:**
  - interruptor SIMULACIÓN, ACTIVO o APAGADO, con confirmación al activar;
  - "aplicar desde", tope semanal, días y horas hábiles;
  - eventos agrupados (clientes, internos y resúmenes) con el editor de la regla.
- **Administración → Bitácora de avisos:** filtros por evento, estado, destinatario, canal, comercial y fechas; contenido enviado o simulado; reenviar fallidas.
- **Cotización:** "Avisos al cliente", con el interruptor y la línea de tiempo.
- **Clientes:** en Contactos, el interruptor del cliente y "recibe avisos" por contacto.

## 4. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18 · ciclo 1 (PostgreSQL 18.6 local, base virgen 0001→0010) | **770 passed** (2 min 40 s) |
| Regla 18 · ciclo 2 (local, base virgen) | **770 passed** (2 min 46 s) |
| Ida y vuelta de 0010 | Foto del esquema 0009 antes y después: idéntica |
| Humo en Chromium | Configuración de notificaciones (editar y guardar regla), bitácora, Mis notificaciones (obligatoria bloqueada y campana visible), clientes y cotizaciones: sin errores |
| Corrida final contra `xps_pricing_test` en Cloud SQL | Ver el resumen de la sesión |

**Pruebas nuevas:** `tests/test_e3_notificaciones.py`, TE3-01 a TE3-27, con reloj simulado. Cubren:
- **Siembra, permisos y secreto** del endpoint interno.
- **Avisos al cliente por fecha:**
  - seguimiento en su momento y sin duplicar (2 recordatorios), y COT_SIN_RESPUESTA;
  - por vencer y vencida.
- **Modos:**
  - SIMULACIÓN no envía nada y deja el contenido;
  - ACTIVO envía con el cupo compartido, solo con las variables de la plantilla y sin el agente;
  - "aplicar desde" excluye el histórico;
  - APAGADO no genera.
- **Cierre y reemplazo:**
  - aceptar cancela los pendientes y avisa a la empresa y al cliente;
  - rechazar avisa con el motivo;
  - el reemplazo cancela y excluye.
- **Interruptores y límites:**
  - interruptores de cotización y cliente, preferencia del contacto y línea de tiempo;
  - horario hábil (20:00 → 08:00 del día siguiente) y tope semanal;
  - tarifa de interés con baja (enlace de baja propio) y omitida tras la baja.
- **Internos:**
  - preferencias y obligatorias;
  - tarifas por vencer agrupadas por día;
  - resumen diario con las cifras de la base;
  - margen bajo;
  - envío fallido de una cotización;
  - usuario bloqueado;
  - sin reemplazo, tasa, campaña terminada y rebote alto.
- **Campana:** marcar leída (solo las propias) y marcar todas.
- **Bitácora:** filtros y reenvío.
- **Reglas y configuración:** reglas con validaciones y auditoría; configuración (al activar sin fecha, "aplicar desde" = hoy).
- **Páginas:** sin estilos en línea ni innerHTML.

## 5. Producción

| Paso | Resultado |
|---|---|
| Respaldo | 1792394308491, SUCCESSFUL |
| Migración | `xps_pricing` 0009 → **0010**; "aplicar desde" = 2026-10-19 |
| Prueba de oro de E0, repetida | 4 cotizaciones, 8 líneas y 4 HTML de PDF: **0 diferencias** |
| Despliegue | `xps-pricing-00006-ghb`, al 100 %; logs sin errores |
| Cloud Scheduler | `xps-notificaciones-evaluar` creado; disparo forzado: la evaluación corrió |
| **Verificación (usuarios de prueba de F5 reactivados y desactivados al final)** | **13 de 13 OK**:<br>• salud y plantillas sincronizadas;<br>• SIMULACIÓN desde el 2026-10-19;<br>• 19 eventos con regla;<br>• permisos y páginas;<br>• evaluación forzada;<br>• **ningún aviso a clientes enviado ni pendiente** |
| Primera evaluación real | 2 avisos internos en la campana (campaña de prueba de E1 terminada: administrador y usuario de prueba). Ningún aviso externo |
| Prueba real del resumen diario (72753) y de un aviso interno (72752), solo al administrador | **Pendiente:** Tencent rechazó las dos plantillas. El script de verificación las prueba solo cuando están aprobadas, con una regla temporal de correo fijo al administrador. **No se envió nada** |
| Base `xps_pricing_oro` | **Borrada** (la creó E0 para la prueba de oro). Quedan `xps_pricing` y `xps_pricing_test` (y `postgres`, `xpress_dev` y `xpress_test`, de XPS-Reborn, que no se tocaron) |
| Base local `C:\Users\franc\pg18` (PostgreSQL 18.6, puerto 5433) | **Se conserva** para pruebas rápidas; solo tiene datos de prueba |
| Vuelta atrás, si hiciera falta | `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=xps-pricing-00005-wxt=100`, `gcloud scheduler jobs pause xps-notificaciones-evaluar --location us-central1` y `alembic downgrade 0009` |

## 6. Decisiones tomadas

1. **Eventos en código y reglas en la base,** una regla sembrada por evento. Agregar un evento = registrar su detector en `services/eventos.py`.
2. **Destinatarios por rol:** "jefe de Pricing" = rol `pricing`; "gerente" = rol `gerencia`. No hay un rol aparte; con E2, el gerente puede crear uno y ponerlo en la regla.
3. **"Aplicar desde" = fecha de la migración** (2026-10-19): nunca se reprocesa el histórico, ni siquiera en simulación. Al pasar a ACTIVO sin fecha, se usa la de ese día.
4. **SIMULACIÓN cuenta para el tope semanal,** así la simulación muestra lo que realmente pasaría. APAGADO no genera nada.
5. **Correos internos con la plantilla rechazada:** quedan OMITIDO con el motivo, y la campana llega igual. No se acumulan para enviarse de golpe cuando Tencent apruebe.
6. **Enlace en las plantillas internas:** si la plantilla trae el dominio fijo (`https://dominio/{{enlace}}`), se envía solo la ruta; si `{{enlace}}` es la URL completa, la URL entera. Así funcionan antes y después de la corrección que pide Tencent.
7. **Seguimiento:** solo sale el último recordatorio que corresponde, nunca una ráfaga de atrasados. COT_SIN_RESPUESTA se calcula con el mismo calendario.
8. **TARIFA_RUTA_INTERES:**
   - detecta tarifas nuevas, creadas en el último día;
   - la "baja de precio" sobre una tarifa editada no se detecta: el precio de una tarifa vigente se cambia creando otra, lo que ya dispara el aviso;
   - tiene su propio enlace de baja, que alimenta las bajas de E1.
9. **Fallos de campañas:** un solo aviso ENVIO_FALLIDO por campaña, no uno por destinatario. Un aviso que falla genera su ENVIO_FALLIDO, salvo si el que falla es un ENVIO_FALLIDO.
10. **Cifras del resumen:**
    - las aceptadas y rechazadas del periodo salen de la auditoría de cambios de estado;
    - el margen % = margen / (margen + costo) de las emitidas.
11. **Plantillas:** se usan las 72747–72753 que subió el gerente, sin crear otras (las copias del HTML están en `docs/extensiones/plantillas/`). No se generó el "diseño propio" que pedía el prompt maestro original, porque el gerente ya subió los suyos.
12. **"Mi resumen" por comercial** (opcional en el prompt): no se implementó. Se agrega como una regla más del resumen cuando se pida.
13. **Cloud Scheduler a las hh:05,** de lunes a viernes de 7 a 19, en el horario de la base. El resumen diario sale con la primera evaluación desde las 07:00.

## 7. Pendientes (acciones del gerente)

1. **Corregir 72752 (aviso interno) y 72753 (resumen) en Tencent** (Simple Email Service → Templates → Edit). Tencent pide:
   - **El enlace con el dominio fijo.** Debe ser **el dominio del sistema, no xpress.ec**, para que el enlace lleve a la pantalla: `https://xps-pricing-809824844407.us-central1.run.app/{{enlace}}` (o el dominio propio que se mapee a Cloud Run, por ejemplo `https://pricing.xpress.ec/{{enlace}}`). El sistema detecta el dominio fijo y envía solo la ruta.
   - **Menos texto libre en 72752:** etiquetas fijas delante de cada `{{detalle_NN}}`.
   - **Más texto fijo en 72753,** con la proporción de variables a 1:5 como máximo. Por ejemplo, etiquetas fijas ("Emitidas:", "Aceptadas:"…) y menos líneas variables.
   
   Después, en Plantillas de correo, pulsar "Sincronizar con Tencent".
2. **Prueba real**, cuando 72752 y 72753 estén aprobadas: ejecutar la verificación de E3, que envía solo al administrador el resumen diario y un aviso interno. También puede esperar al día hábil siguiente a las 07:05: el resumen sale a los usuarios del rol Gerencia.
3. **Activar los avisos a clientes,** cuando lo decida, tras revisar la bitácora en simulación unos días: Administración → Notificaciones → "aplicar desde" = fecha de activación → ACTIVO → Guardar.

## 8. Checklist del gerente (navegador)

1. [ ] **Revisar la simulación:** en Administración → Bitácora de avisos, filtrar Estado = Simulado y revisar unos días lo que se habría enviado. Con "Ver" se lee el contenido.
2. [ ] **Ajustar las reglas:** en Administración → Notificaciones, ajustar días, recordatorios y textos de los pasos (Editar en cada regla).
3. [ ] **Aceptación de prueba:** marcar ACEPTADA una cotización de prueba. En la campana aparece el aviso; en la cotización, "Avisos al cliente" muestra la confirmación simulada.
4. [ ] **Interruptor del cliente:** en Clientes → Contactos, probar "No enviar avisos al cliente" y "No recibir avisos" en un contacto.
5. [ ] **Preferencias:** en Mis notificaciones → Mis preferencias, apagar un aviso por correo. Los obligatorios no se dejan apagar.
6. [ ] **Plantillas internas:** corregir 72752 y 72753 en Tencent (Pendientes 1) y sincronizar.
7. [ ] **Resumen diario:** revisarlo en el correo cuando 72753 esté aprobada.
8. [ ] **Activar los avisos a clientes:** poner "aplicar desde" y pasar a ACTIVO.

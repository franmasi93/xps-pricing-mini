# Acta de cierre · E1 · Boletines de tarifas

| Dato | Valor |
|---|---|
| Extensión | E1 (30 % de las extensiones E0–E3) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code (sesión autónoma del 2026-10-18 al 19) |
| Fecha de cierre | 2026-10-19 |
| Commits | `aac4ec5` (backend) · `1e7b43e` (plantillas del gerente, pantallas, WhatsApp) · esta acta |
| Migración | `0008_e1_boletines` (0007 → 0008) |
| Respaldo de producción | **1792389261792** (justo antes de migrar a 0008) |
| Producción | https://xps-pricing-809824844407.us-central1.run.app · revisión **xps-pricing-00004-6qp** |
| Cloud Scheduler | `xps-boletines-lote`: `* 7-19 * * 1-5`, America/Guayaquil, POST a `/internal/boletines/procesar-lote` con `X-Tarea-Secreto` |
| Secretos nuevos | `xps-pricing-tareas-secreto` y `xps-pricing-tencent-eventos-token`, con acceso solo para `xps-pricing-run` |

## 1. Resumen en cristiano

El sistema ya envía boletines de tarifas vigentes a listas de contactos, con la plantilla **72746** que subió el gerente. Se probó de verdad en producción, solo al correo del administrador. El boletín:
- **No duplica tarifas:** lee las vigentes y, al enviar o programar, congela una copia de lo enviado.
- **Arma las filas** con el formato de cada forma de cobro: "• Guayaquil → Miami · USD 2.50/kg desde 100 kg · 3 días · vigente al 30/11/2026 · LATAM".
- **Adjunta un PDF** con todas las tarifas.
- **Pone en cada correo un enlace de baja propio.** Quien se da de baja queda fuera de todas las campañas y de los avisos comerciales de E3.

El envío corre por lotes desde Cloud Scheduler, dentro del horario de la base:
- respeta el tope diario, la reserva para cotizaciones y avisos, el tope por hora y el calentamiento;
- nunca envía dos veces al mismo destinatario;
- reintenta los fallos temporales;
- marca rebotes y bajas.

## 2. Avance por fase

| Fase | Peso | Estado |
|---|---|---|
| E1.0 Base | 3 % | Hecho: plan (`docs/extensiones/E1-PLAN.md`), verificación de Tencent, migración 0008 probada ida y vuelta |
| E1.1 Listas y bajas | 5 % | Hecho: listas manuales (con buscador e importación CSV) y por filtro (servicio, tipo de equipo, origen, destino, país, ciudad); bajas que aplican a todo |
| E1.2 Campañas, plantillas y vista previa | 7 % | Hecho: catálogo de plantillas sincronizado con Tencent (los 8 ID del gerente y la 72669), asistente de 4 pasos, vista previa de escritorio y móvil |
| E1.3 Motor de envío | 8 % | Hecho y **probado con Cloud Scheduler en producción** |
| E1.4 Bitácora y baja pública | 4 % | Hecho: detalle por destinatario, página pública de baja, callback de Tencent preparado |
| E1.5 Cierre | 3 % | Hecho: Regla 18 doble, despliegue, prueba real y esta acta |
| **Total E1** | **30 %** | **30 %** |

## 3. Lo construido

### 3.1 Datos (0008)

**Tablas nuevas**
- `config_masivos`, una fila. Sus valores por defecto:
  - remitente y reply-to del correo de F4;
  - lote de 50, pausa de 60 s, tope diario de 500 y tope por hora de 200;
  - reserva del 20 %;
  - PDF por defecto, 15 filas;
  - horario de lunes a viernes, de 8 a 19;
  - calentamiento opcional;
  - URL pública.
- `plantilla_correo`:
  - uso COTIZACION, BOLETIN o AVISO;
  - ID y estado en Tencent con su motivo;
  - HTML y texto reales;
  - variables detectadas.
- `lista_envio` y `lista_envio_miembro`.
- `baja_correo`: email único en minúsculas, motivo ENLACE, MANUAL o TENCENT, y revertida.
- `campana`: snapshot JSON, totales y estados borrador, programada, enviando, pausada, enviada y cancelada.
- `campana_destinatario`: único por campaña y email, estados, intentos, token de baja firmado y `message_id`.

**Siembra:** la 72669 y las 8 plantillas del gerente, por ID, con su uso y evento.

**Permisos nuevos:**
- `boletines.ver`: los 4 roles.
- `boletines.listas.gestionar`, `boletines.campanas.gestionar` y `boletines.campanas.enviar`: admin y pricing.

### 3.2 Plantillas de Tencent

- **Catálogo** en Administración → Plantillas de correo (solo admin), con auditoría:
  - **Sincronizar con Tencent** trae estado, motivo y HTML real con GetEmailTemplate: **las variables del HTML mandan**, y nunca se envía una variable que la plantilla no tenga.
  - El motor sincroniza solo una vez por hora.
  - Crear o editar llama a CreateEmailTemplate o UpdateEmailTemplate, con aviso de que vuelve a revisión. Sin permiso de la llave, queda para registrar el ID a mano.
- **Plantilla de cotización (F4):** `config_correo.plantilla_cotizacion_id` se elige del catálogo (uso COTIZACION, aprobada). El valor 72669 y el comportamiento de F4 no cambian.
- **Copias** del HTML y la guía para el gerente: `docs/extensiones/plantillas/`.

### 3.3 Boletín (72746)

| Variables | De dónde salen |
|---|---|
| `titulo` | El asunto de la campaña |
| `nombre_contacto` | El contacto |
| `texto_intro` | La campaña, hasta 160 caracteres |
| `fila_01` a `fila_15` | Las tarifas, con viñeta, según la forma de cobro. Las que no se usan van vacías |
| `mas_tarifas` | "Y X tarifas más en el PDF adjunto", o vacío |
| `vigencia` | La menor vigencia de las tarifas |
| `comercial` | Quien envía la campaña |
| `empresa_direccion`, `empresa_telefono`, `empresa_whatsapp`, `empresa_horario` | Los datos de la empresa (`config_empresa`) |
| `whatsapp_numero` | **Calculado** del WhatsApp de la empresa: sin espacios, guiones, paréntesis ni "+", con 593 si no trae código. Al guardar los datos de la empresa se valida y se muestra la vista previa `https://wa.me/…` |
| `enlace_baja` | `URL/b/{token}` |

### 3.4 Motor y endpoints sin JWT

- **`POST /internal/boletines/procesar-lote`:**
  - secreto en `X-Tarea-Secreto`; sin secreto responde 401 y sin configurar, 503;
  - activa las programadas y respeta horario, pausa y cupos;
  - toma los destinatarios con `FOR UPDATE SKIP LOCKED`, uno por transacción;
  - TriggerType 0 y `Unsubscribe = "0"`, porque se usa el enlace propio;
  - 3 intentos para los errores temporales;
  - `ReceiverHasUnsubscribed` deja al destinatario omitido y registra la baja;
  - dirección inválida o bloqueada lo deja rebotado.
- **`POST /internal/tencent/eventos/{token}`:** idempotente.
  - Hard bounce: rebotado y baja.
  - Soft bounce: reintento.
  - Queja o desuscripción: baja.
  - Con la base apagada responde 503, para que Tencent reintente si su callback lo hace.
- **`GET /b/{token}` y `/baja/{token}`:** llevan a `/app/baja.html`, sin menú ni login. Muestra el email enmascarado, permite darse de baja y deshacerlo; con un token inválido da un mensaje genérico, y con la base apagada, un mensaje amable.

### 3.5 Pantallas (menú "Boletines")

- Campañas, con filtros por estado, servicio y fechas, y una pestaña de programadas.
- Asistente de 4 pasos con borrador en cada paso:
  - pestañas de tarifas por servicio activo (la fuente única de E0), con el atajo "todas las vigentes de este servicio";
  - contador en vivo de destinatarios;
  - vista previa en un `iframe` aislado;
  - "Enviarme una prueba", y "Enviar" o "Programar" con confirmación del número exacto.
- Detalle con contadores, copia congelada y destinatarios, y botones Pausar, Reanudar y Cancelar.
- Listas, Bajas y Plantillas de correo.
- Configuración → Envíos masivos.
- Página pública de baja.

## 4. Pruebas

| Corrida | Pruebas | Resultado |
|---|---|---|
| Regla 18 · ciclo 1 (PostgreSQL 18.6 local, base virgen 0001→0008) | 717 | **717 passed** (3 min 14 s) |
| Regla 18 · ciclo 2 (local, base virgen) | 717 | **717 passed** (2 min 59 s) |
| Integración contra `xps_pricing_test` en Cloud SQL | — | Se hace en la corrida final consolidada de la sesión |

**Pruebas nuevas:** `tests/test_e1_boletines.py`, TE1-01 a TE1-34. Cubren:
- **Permisos por rol.**
- **Plantillas:**
  - creación en Tencent y variables detectadas;
  - llave sin CAM y registro manual;
  - la 72669 protegida, la importación y el máximo de 40 variables;
  - siembra de los 8 ID y sincronización con el contenido real.
- **Listas y bajas:**
  - listas manuales y por filtro, con bajas y duplicados;
  - importación de emails;
  - bajas manuales y su reversión.
- **Validaciones del envío:** tarifa vencida o sin tarifas, plantilla no aprobada o inactiva, variables sin valor, conteo confirmado distinto y quién puede enviar.
- **Envío y motor:**
  - envío completo: snapshot congelado, sin agentes, solo las variables de la plantilla y no más de 4.000 bytes;
  - motor idempotente, con tamaño de lote y topes con reserva;
  - pausar, reanudar y cancelar;
  - reintentos, rebotes y baja desde Tencent;
  - programadas y fuera de horario;
  - PDF adjunto y "Y 2 tarifas más".
- **Baja pública:** token válido, adulterado o desconocido, y deshacer; segunda campaña con el destinatario omitido.
- **Endpoints internos y callback:** el endpoint interno exige el secreto; el callback es idempotente.
- **Servicios de E0:** un servicio nuevo y un tipo de equipo nuevo aparecen sin tocar código.
- **Configuración y WhatsApp:** configuración de masivos y calentamiento; WhatsApp calculado y validado.
- **Pantallas:** sin estilos en línea ni innerHTML.

**Humo en el navegador** (Chromium, base local): campañas, asistente nuevo, listas, bajas, plantillas, configuración y baja pública, sin errores. El único 404 es el esperado de un token inválido.

## 5. Producción

| Paso | Resultado |
|---|---|
| Respaldo | 1792389261792, SUCCESSFUL |
| Migración | `xps_pricing` 0007 → **0008** |
| Prueba de oro de E0, repetida | 4 cotizaciones: **0 diferencias** después de 0008 |
| Despliegue | `xps-pricing-00004-6qp`, al 100 %; logs sin errores |
| Salud | `{"estado":"ok","bd":"ok"}` |
| Cloud Scheduler | Creado; disparo forzado: 200. Sin secreto: 401 |
| **Prueba real (solo al administrador)** | **17 de 17 OK**. Detalle abajo |

**Qué cubrió la prueba real**
1. Sincronizó las 9 plantillas.
2. "Enviarme una prueba" salió (`message_id` …18fwWd8EGC6k1).
3. Se creó la lista "Prueba interna" (solo francois-ramart@outlook.com) y una campaña con una tarifa de 1 USD marcada PRUEBA INTERNA.
4. La campaña se programó, Cloud Scheduler disparó el lote y la campaña quedó **ENVIADA**.
5. El enlace de baja llevó a la página pública y la baja se registró.
6. Una segunda campaña dejó al administrador **omitido por baja**.
7. La baja se deshizo.
8. La configuración volvió a como estaba. La lista, la tarifa, el cliente y el contacto de prueba quedaron **desactivados**, y los usuarios de prueba de F5, **desactivados**.

Antes de esa prueba se hizo una sonda real con la 72746, también solo al administrador: **Tencent aceptó 2.406 bytes de variables**. El límite de 800 bytes que da el SDK no se aplica.

Correos al administrador en la sesión: 3 (sonda, prueba y campaña), por debajo del máximo de 10 por hora.

## 6. Decisiones tomadas

1. **Plantillas del gerente:** se usan las 8 que él subió, importadas por ID (72746 para todos los boletines). No se crea ninguna otra. Los 12 diseños propios que se habían preparado se retiraron.
2. **Tamaño de las variables:** el SDK documenta 800 bytes como máximo para `TemplateData`. Un envío real de 2.406 bytes funcionó, así que se usa un tope técnico de 4.000 bytes. Las filas se llenan hasta 15 (configurable) y el resto va en el PDF.
3. **Formato de montos:** el del sistema, igual que el PDF de F4: "USD 1,850.00". Las fechas van en dd/mm/aaaa.
4. **Filas sin uso:** se envían como "". Tencent las aceptó en el envío real; no hizo falta un espacio.
5. **Enlace de baja propio** (`Unsubscribe = "0"`) en vez del de Tencent. Así la baja alimenta `baja_correo` para todas las campañas y para E3.
6. **List-Unsubscribe no se envía:** la documentación no confirma que `SmtpHeaders` lo acepte.
7. **Callback:** el SDK no tiene una API para configurarlo; queda la guía para la consola (Pendientes).
8. **Remitente de masivos:** el de F4 (pricing@notificaciones.xpress.ec) mientras no exista tarifas@. La llave no tiene permiso para crearlo (Pendientes).
   - **Recomendación futura:** un subdominio aparte para masivos (por ejemplo, boletines.xpress.ec), con su DNS verificado en Tencent, para que la reputación de los boletines no afecte a las cotizaciones.
9. **Importación "desde Excel":** por CSV (Excel lo guarda directo). Se lee en el navegador, sin dependencias nuevas.
10. **Lista "Todos los clientes activos":** es una lista por filtro sin filtros. No se siembra, para no dejar una lista de clientes reales lista para enviar; el gerente la crea en un clic.
11. **Comercial que firma** (`comercial`): quien envía la campaña.
12. **Tope diario por defecto:** 500, el cupo del nivel 1, con reserva del 20 % para cotizaciones y avisos y calentamiento opcional.
13. **Cloud Scheduler:** solo corre de lunes a viernes de 07:00 a 19:59. Lo pendiente sigue en el siguiente horario. El horario de envío de `config_masivos` es una segunda barrera, que se puede afinar.
14. **Pruebas:** con PostgreSQL 18.6 local en el puerto 5433, 3 minutos por corrida en vez de 93 en Cloud SQL. La integración contra Cloud SQL va en la corrida final consolidada.
15. **Moneda:** solo USD, como en E0.

## 7. Pendientes (acciones del gerente)

1. **Revisar en el correo** (francois-ramart@outlook.com) los 3 correos "[PRUEBA] Boletín de tarifas", en el computador y en el celular, y el PDF adjunto del de la campaña.
2. **Callback de Tencent** (rebotes y quejas en tiempo real):
   1. En la consola de SES, ir a **Callback / 回调地址** y registrar `https://xps-pricing-809824844407.us-central1.run.app/internal/tencent/eventos/<TOKEN>`.
   2. El `<TOKEN>` se ve con `gcloud secrets versions access latest --secret=xps-pricing-tencent-eventos-token --project=xps-reborn-v2`. No lo comparta.
   3. Eventos: bounce, spamreport, unsubscribe.
3. **Remitente de masivos tarifas@notificaciones.xpress.ec:** crearlo en la consola (**Sender Address**). Después elegirlo en Configuración → Envíos masivos.
4. **Permisos CAM de la llave** (opcional): `ses:CreateEmailTemplate`, `ses:UpdateEmailTemplate` y `ses:CreateEmailAddress`, para que el sistema cree y edite plantillas y remitentes por API (ver la guía).
5. **Datos de prueba:**
   - Las campañas "PRUEBA INTERNA E1" quedan en el historial, marcadas por su nombre.
   - Cliente, contacto, lista y tarifa de prueba: desactivados.

## 8. Checklist del gerente (navegador)

1. [ ] **Plantillas:** en Administración → Plantillas de correo, pulsar "Sincronizar con Tencent". La 72746 aparece **Aprobada**.
2. [ ] **Datos de la empresa:** en Configuración → Datos de la empresa, el WhatsApp muestra el enlace `https://wa.me/593…`. Ábralo para probarlo.
3. [ ] **Envíos masivos:** en Configuración → Envíos masivos, revisar el tope diario (500), la reserva (20 %), el horario y su correo de prueba.
4. [ ] **Lista de prueba:** en Boletines → Listas de envío, crear una lista manual solo con su contacto.
5. [ ] **Campaña con todas las tarifas:** en Boletines → Campañas → Nueva campaña, elegir "Xps boletin tarifas" y, en el paso 2, "Incluir todas las vigentes" en cada servicio. Paso 3: su lista.
6. [ ] **Campaña solo FCL:** crear otra campaña eligiendo solo la pestaña "Marítimo FCL".
7. [ ] **Prueba:** en el paso 4, "Enviarme una prueba" y revisarla en el celular.
8. [ ] **Baja:** abrir el enlace "dese de baja" del correo y confirmar. En Boletines → Bajas aparece su correo.
9. [ ] **Omitido:** en otra campaña con su lista, el paso 3 muestra "omitidos por baja: 1". Después revierta la baja en Bajas.
10. [ ] **Programar y cancelar:** programar una campaña para dentro de unos minutos (en horario de lunes a viernes). Pausarla o cancelarla desde su detalle.

Las campañas a clientes reales las lanza solo el gerente.

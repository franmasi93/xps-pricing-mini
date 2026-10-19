# E1 · Boletines de tarifas: plan

| Dato | Valor |
|---|---|
| Fecha | 2026-10-18 |
| Base | `main` en `b1086b8` (E0 cerrada, migración 0007) |
| Regla de oro | No se duplican tarifas. La campaña lee las vigentes y, al enviar o programar, congela una copia (snapshot JSON) de lo enviado |

## 1. Lo verificado en Tencent Cloud SES (documentación oficial, 2026-10-18)

| Tema | Lo encontrado | Decisión |
|---|---|---|
| **Variables con HTML** | La API (`SendEmail` → `Template.TemplateData`) exige un JSON de texto. La documentación del SDK que se consultó en F4 dice: "参数值不能是html等复杂类型的数据": los valores no pueden ser HTML. Las variables van como `{{nombre}}` | **Las tablas no se mandan como HTML.** Cada plantilla de Tencent trae la tabla con **filas numeradas como variables de texto** (`fila1_ruta`, `fila1_tarifa`…), hasta un máximo configurable (`limite_filas`, por defecto 10). Además, **todas** las tarifas van en un **PDF adjunto**, generado con el motor de PDF existente |
| **Tamaño** | Solicitud de hasta 8 MB; adjuntos de hasta 4 MB en total (Base64 los infla ×1,5); hasta 10 adjuntos. Ningún límite documentado por variable | El PDF respeta `adjunto_max_bytes` de la configuración de correo (F4) |
| **Destinatarios** | Hasta 50 por llamada en envío masivo | Se envía **uno por llamada**, como en F4. Así cada destinatario lleva su enlace de baja personal |
| **Cuota** | Por dominio, según su nivel de reputación: el nivel 1 (dominio nuevo) permite 500 correos por día y el 20, 1.000.000. Además, 20 correos por segundo por cuenta y 10 por hora a una misma dirección | `tope_diario` por CRUD (1000 por defecto, como pide el alcance). **El gerente debe dejarlo ≤ al límite del nivel actual de su dominio** (se ve en la consola de Tencent). El lote de 50 con pausa respeta los 20 por segundo |
| **TriggerType** | 0 = marketing o no inmediato; 1 = inmediato | Boletines con **0**; las cotizaciones de F4 siguen con 1 |
| **Unsubscribe** | El parámetro `Unsubscribe` agrega el enlace de baja propio de Tencent (0 = sin enlace; 1–11, por idioma). Quien se da de baja allí devuelve `FailedOperation.ReceiverHasUnsubscribed` | Se usa **el enlace propio del sistema** (`{{enlace_baja}}`), que alimenta `bajas_correo` para todas las campañas, con `Unsubscribe = "0"`. Si Tencent responde `ReceiverHasUnsubscribed`, el destinatario queda `omitido_baja` y se registra la baja |
| **List-Unsubscribe** | `SmtpHeaders` ("otros campos del encabezado SMTP") existe, pero **la documentación no confirma** que admita `List-Unsubscribe` | **No se envía**, para no arriesgar rechazos. Se documenta como pendiente para probar con Tencent |
| **Rebotes** | Callback configurable en la consola (eventos `delivered`, `bounce` con `soft_bounce` o `hard_bounce`, `unsubscribe`, `spamreport`…, con `bulkId` = MessageId). No documenta firma | Endpoint preparado: `POST /internal/boletines/eventos-tencent?clave=…`. Un `hard_bounce` pasa a `rebotado`; `unsubscribe` y `spamreport` pasan a baja. Además, el resultado síncrono: los errores permanentes de envío dan `rebotado` o `fallido` |

## 2. Modelo de datos (migración 0008)

| Tabla | Contenido |
|---|---|
| `config_masivos` | Una fila (id 1), editable por CRUD en el espacio de Tencent: remitente de masivos, tamaño de lote (50), pausa entre lotes en segundos, tope diario (1000), texto legal del pie, correo del administrador para pruebas, límite de filas por plantilla (10), URL pública para el enlace de baja, último lote |
| `plantilla_correo` | Nombre, ID de la plantilla en Tencent, uso (BOLETIN o AVISO), diseño local para la vista previa (GENERAL o una forma de cobro), evento o servicio sugerido, variables esperadas (JSON), activa, notas. E3 la reutiliza |
| `lista_envio` + `lista_envio_miembro` | Nombre único, descripción, tipo (MANUAL o FILTRO), filtros JSON (servicios, tipos de equipo, orígenes, destinos, países y ciudades), activa. Miembros únicos por par (lista, contacto) |
| `baja_correo` | Email único en minúsculas, motivo (ENLACE, MANUAL o TENCENT), fecha, revertida. Aplica a todas las campañas y a los avisos comerciales de E3 |
| `campana` | Nombre interno, asunto, texto de introducción, plantilla, servicios y tipos de equipo (JSON), `tarifas_ids` (JSON), `listas_ids` (JSON), adjuntar PDF, `snapshot_tarifas` (JSON, nulo hasta el envío), estado (borrador, programada, enviando, pausada, enviada o cancelada), `programada_para`, totales (destinatarios, enviados, rebotados, fallidos, omitidos), creado y enviado por, fechas |
| `campana_destinatario` | Campaña, contacto, email, nombre, estado (pendiente, enviado, rebotado, fallido, omitido_baja, omitido_duplicado o cancelado), intentos, último error, `token_baja` (único, aleatorio y firmado con HMAC), `message_id`, `enviado_en`. Único por (campaña, email) |

**Permisos nuevos:**
- `boletines.ver`: los 4 roles.
- `boletines.listas.gestionar`, `boletines.campanas.gestionar` y `boletines.campanas.enviar`: admin y pricing.

Los roles reales son admin, pricing, comercial y gerencia; el "jefe de Pricing" es el rol pricing.

## 3. Lógica

- **Servicios:** salen de la fuente única de E0 (`servicios.servicios_activos`). Cada tarifa se formatea con el método `fila_boletin` de su forma de cobro (`formas_cobro.py`): tramos en peso, W/M en volumen, tipo de equipo en unidad de equipo, precio plano. **Cero `if` por servicio.** Solo se usa el precio de venta, nunca el costo, y el transportista, **nunca el proveedor**.
- **Selección de tarifas:** todas las vigentes, por servicios, por tipos de equipo o manual. Atajo "todas las vigentes de este servicio".
- **Validaciones al enviar o programar:**
  - al menos una tarifa;
  - todas activas y vigentes en la fecha de envío: las vencidas se bloquean y se avisa de las que vencen antes de máx(7 días, `dias_alerta_vencimiento`);
  - plantilla activa, de uso BOLETIN y con todas sus variables con valor;
  - si las tarifas no caben en las filas de la plantilla, hace falta el PDF adjunto;
  - al menos un destinatario;
  - el número confirmado debe coincidir con el que calcula el backend.
- **Al enviar o programar,** en una transacción:
  - se congela el snapshot;
  - se generan los destinatarios: se deduplica por email y las bajas quedan `omitido_baja`;
  - se crea el token de baja de cada uno;
  - la campaña pasa a `enviando` o `programada`.
- **Motor por lotes** (servicio reutilizable, `services/motor_envios.py`). `POST /internal/boletines/procesar-lote`, con el secreto en el encabezado `X-Tarea-Secreto` (variable `TAREAS_SECRETO`, Secret Manager `xps-pricing-tareas-secreto`) y sin JWT. Cada llamada:
  - activa las programadas cuya hora llegó;
  - respeta la pausa entre lotes y el tope diario global (campañas + cotizaciones + pruebas del día);
  - toma hasta "tamaño de lote" pendientes con `SELECT … FOR UPDATE SKIP LOCKED`, **una fila por transacción**, así dos llamadas seguidas nunca envían dos veces lo mismo;
  - envía con el proveedor Tencent existente;
  - reintenta los fallos temporales hasta 3 intentos;
  - un error permanente da `rebotado` (dirección inválida o bloqueada) o `fallido`;
  - una baja en Tencent da `omitido_baja` y se registra la baja;
  - marca la campaña `enviada` cuando no quedan pendientes.
  
  Pausar detiene, reanudar continúa y cancelar marca los pendientes `cancelado`.
- **Cloud Scheduler:** cada minuto, de lunes a viernes de 07:00 a 19:59 (America/Guayaquil, el horario de la base), llamando al endpoint con el encabezado.
- **Baja pública:**
  - `GET /baja/{token}` lleva a una página sin login que muestra la confirmación con el email enmascarado;
  - `POST` registra la baja;
  - "deshacer" la revierte;
  - un token inválido muestra un mensaje genérico.

## 4. Plantillas de Tencent

En `app/templates/boletines/` (lo que usa la vista previa) y en una copia idéntica en `docs/extensiones/plantillas/` (lo que el gerente registra), verificada por prueba:
- **`boletin_general.html`:** introducción, resumen, filas numeradas genéricas y el aviso del PDF adjunto.
- **Una por forma de cobro:** `boletin_peso_tramos.html`, `boletin_volumen_wm.html`, `boletin_unidad_equipo.html` y `boletin_tarifa_plana.html`. Columnas según la forma.
- **Diseño:** el correo aprobado de F4 (logo, navy #000771, naranja #ED4C01), con estilos en línea y tablas que no se desbordan en el móvil.
- **Pie:** dirección de la matriz, teléfonos y horario, que salen de los datos de la empresa de F4, más el texto legal y el enlace de baja.
- **Guía:** `docs/extensiones/plantillas/GUIA-REGISTRO-TENCENT.md`.

## 5. Pantallas (menú "Boletines", según permisos)

- **Campañas:** filtros por estado, servicio y fechas, y una vista de programadas.
- **Asistente de 4 pasos,** con borrador en cada paso: contenido, tarifas, destinatarios y revisar. La vista previa de escritorio y de móvil va en un `iframe` aislado.
- **Detalle de la campaña.**
- **Listas.**
- **Plantillas.**
- **Bajas.**
- **Configuración → Envíos masivos.**
- **Página pública de baja:** con logo, sin menú ni login.

## 6. Producción

En orden:
1. Respaldo.
2. Migración 0008.
3. Secreto `xps-pricing-tareas-secreto`.
4. Despliegue con `TAREAS_SECRETO`.
5. Cloud Scheduler.
6. Salud.
7. Una sola prueba real, "Enviarme una prueba" al administrador. **Requiere una plantilla de boletín registrada y aprobada en Tencent:** si todavía no existe, queda como acción manual del gerente.

No se crean ni se envían campañas a clientes reales.

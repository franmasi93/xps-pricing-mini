# E3 · Notificaciones y avisos: plan

Peso: 20 % de E0–E3. Fases:

| Fase | Peso |
|---|---|
| E3.0 Análisis | 2 % |
| E3.1 Eventos y reglas | 5 % |
| E3.2 Motor | 6 % |
| E3.3 Centro de notificaciones y pantallas | 4 % |
| E3.4 Cierre | 3 % |

## Contexto verificado en el código

- **Cotización:**
  - estados BORRADOR, EMITIDA, ENVIADA, ACEPTADA y RECHAZADA;
  - `fecha_emision`, `valida_hasta`, `comercial_id`, `cliente_id`, `contacto_id`, `margen_pct`, `motivo_rechazo` (catálogo de E2) y `cotizacion_origen_id` (duplicar);
  - "bajo costo" es un cálculo de la línea (`subtotal_venta < costo`), no una columna.
- **Fecha de envío:** el primer `envio_correo` ENVIADO de la cotización. La cotización no guarda esa fecha.
- **Aceptación y rechazo:** quedan en `auditoria` con la nota "ESTADO X→ACEPTADA" o "ESTADO X→RECHAZADA (motivo)".
- **Otros datos:**
  - `dias_alerta_vencimiento` está en `configuracion`;
  - las tarifas tienen vigencia (`valido_desde`, `valido_hasta`);
  - las tasas de cambio, `fecha_vigencia`;
  - el usuario se bloquea en `services/auth.py` con 5 intentos.
- **E1:** proveedor de correo, cupos (`masivos`), motor por lotes, bajas (`baja_correo`) y plantillas `plantilla_correo` con uso AVISO. Las 72747–72753 del gerente están sembradas con su evento.

## Diseño

- **Eventos:** viven en código (`app/services/eventos.py`), cada uno con su detector. El motor (`app/services/notificaciones.py`) no cambia al agregar un evento.
- **Migración 0010:** `config_avisos`, `regla_notificacion`, `notificacion` (outbox y bitácora, con `clave_idempotencia` única), `preferencia_notificacion` e interruptores en la cotización, el cliente y el contacto. Agrega 3 permisos.
- **Inmediatos:** se emiten dentro de la transacción del servicio, justo antes de su commit y en un savepoint. Si generar el aviso falla, el servicio responde exactamente igual.
- **Por fecha y resúmenes:** `POST /internal/notificaciones/evaluar` (Cloud Scheduler cada hora). Además envía los pendientes.
- **Envío:** con el proveedor de F4 (TriggerType 1) y el cupo de E1. Los avisos usan el tope total del día (la reserva) y salen antes que las campañas en procesar-lote.
- **Avisos externos:** en SIMULACIÓN al desplegar. "Aplicar desde" = fecha de la migración.
- **Plantillas:** las 72747–72753 que subió el gerente. No se crean otras. Copias en `docs/extensiones/plantillas/`.

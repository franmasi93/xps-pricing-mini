# F5 — Entregas (desde el cierre de F4)

## Estado al 2026-10-16 · detenido en P-A (sesión de despliegue)

### Motivo de la parada

El prompt autónomo indica detenerse en la sesión de despliegue P-A, que necesita a François: él ejecuta cada comando de Google Cloud. Todo lo previo está hecho y subido a GitHub.

### Commits y push

| Commit | Contenido |
|---|---|
| `7743d19` | F4: formato oficial del PDF, kg/lb, recargo sobre recibo, correo Tencent administrable y bitácora (48 archivos) |
| `4af69b0` | F4: acta de cierre con hash (`docs/cierres/CIERRE-F4.md` y `docs/cierres/F4-entregas-paradas.md`) |
| `7151a47` | F5 parte 1: auditoría, deuda, preparación del despliegue y checklist (35 archivos) |

- **Push:** `git push origin main` → `6375d5d..7151a47  main -> main`. `git status -sb` → `## main...origin/main`.
- **Separación de commits:** los archivos que comparten F4 y F5 se reconstruyeron en su versión F4 para el commit de F4. Ese árbol se verificó aparte (201 + 2 = 203 pruebas en verde).
- **Estado de F5:** el commit de F5 es exactamente el estado de la Regla 18 doble de F5 (634 de 634 en los dos ciclos).

### Prueba real de F4 (compuerta técnica cumplida)

| Envío | Destinatario | MessageId |
|---|---|---|
| Correo de prueba | francois-ramart@outlook.com | `qcloudses-30-1420342617-date-20261017024530-Q8Z6v6SvKhZn1` |
| COT-2026-00001 | johnreyes638@icloud.com | `qcloudses-30-1420342617-date-20261017024841-PmRng11IcqQT1` |
| COT-2026-00002 | francisco14-2012@hotmail.com | `qcloudses-30-1420342617-date-20261017024858-6uoVS27LuPV01` |
| COT-2026-00003 | gerencia@xpress.ec | `qcloudses-30-1420342617-date-20261017024916-lWTBr0TLhk4U1` |
| COT-2026-00004 | francois-ramart@outlook.com | `qcloudses-30-1420342617-date-20261017024935-GZnUIUCU2zMN1` |
| COT-2026-00005 | brayantmayers4@gmail.com | `qcloudses-30-1420342617-date-20261017024954-CwftHonVNFwc1` |

- Todos salieron el 2026-10-16 entre 13:45 y 13:50, hora de Ecuador.
- Las 5 cotizaciones quedaron en ENVIADA, con una sola transición en la auditoría cada una.
- El correo quedó **HABILITADO en `xps_pricing`** y deshabilitado en `xps_pricing_test`.
- Detalle completo en `CIERRE-F4.md`, sección 3.4.

### Avance

**90 %** (F0–F4 cerradas). F5 (10 %) suma al cierre del proyecto.

### Resultados crudos de F5 parte 1

```
Regla 18 ciclo 1  634 passed, 1 warning in 5285.18s (1:28:05) · fin 2026-10-15 17:17:15
Regla 18 ciclo 2  634 passed, 1 warning in 6026.74s (1:40:26) · fin 2026-10-16 10:19:10
canario de los 35 archivos del commit de F5: 35 OK, 0 con fallas · secretos en esos archivos: 0
```

### Huecos

- **H-F5-1 a H-F5-5:** en `F4-entregas-paradas.md`.
- **H-F4-30:** en `CIERRE-F4.md`.

### Qué necesita François, en orden

| N° | Qué | Tiempo |
|---|---|---|
| 1 | Revisar sus buzones (compuerta visual de F4, D-AUT-2b) | ≈ 10 min |
| 2 | Copiar `CONFIG_CIFRADO_KEY` del `.env` a su gestor de contraseñas | ≈ 2 min |
| 3 | Rotar la SecretKey de `pricing-ses` en Tencent CAM y pegarla en Configuración (las llaves se pegaron en el chat; H-F5-5) | ≈ 5 min |
| 4 | **P-A · sesión de despliegue** con `docs/DESPLIEGUE.md` y `docs/go-live/`. Incluye rotar la contraseña de `pricing_app`, subir los secretos, migrar la base de trabajo a 0006 y desplegar en `us-central1` | ≈ 45 min |
| 5 | **P-B · verificación final** con `docs/CHECKLIST-FINAL.md` en producción, con los 4 roles, y una cotización real | ≈ 60–90 min |
| 6 | Confirmar el pedido de push de `wip/m10a`, que es del repositorio XPS-Reborn-V2.1 y no se tocó | ≈ 1 min |

Después de P-B viene el cierre del proyecto: `CIERRE-F5.md`, `CIERRE-PROYECTO.md`, desactivar los usuarios de prueba y el commit final → 100 %.

## Estado al 2026-10-16, 20:00 · desplegado; esperando la verificación de François (P-B)

### FASE 1 · Despliegue (D-FIN-4: comandos ejecutados por el EJECUTOR)

| Paso | Resultado |
|---|---|
| APIs | run, cloudbuild, artifactregistry, secretmanager y sqladmin habilitadas (`finished successfully`). Antes, Cloud Run estaba deshabilitado y no existía ningún servicio |
| Cuenta de servicio | `xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com` con `roles/cloudsql.client` en el proyecto y `secretAccessor` solo sobre sus 3 secretos |
| Secretos | `xps-pricing-database-url` (socket de Cloud SQL), `xps-pricing-jwt-secret` y `xps-pricing-config-cifrado-key` (D-FIN-3: del `.env` por stdin, sin mostrarse) |
| Base de trabajo | `xps_pricing`: 0005 → **0006**. Correo HABILITADO con llaves, condiciones (889 caracteres) y 14 de 14 datos de la empresa cargados, 1 admin activo |
| `.gcloudignore` (nuevo) | Excluye `.env`, `docs/`, `tests/`, `salidas/`, `start.txt` y llaves. `gcloud meta list-files-for-upload`: 0 archivos privados |
| Despliegue | `gcloud run deploy --source .` → revisión `xps-pricing-00001-lgx`; con health checks en `/v1/salud` → **`xps-pricing-00002-4lk`**, sirviendo el 100 % |
| URL | **https://xps-pricing-809824844407.us-central1.run.app** (región us-central1) |

### Comprobaciones (1.4)

```
GET /v1/salud            → {"estado":"ok","bd":"ok"}
GET /app/login.html      → 200 text/html · <title>Ingresar · XPS Pricing</title>
GET /                    → 307 → https://…/app/login.html
GET /v1/auth/yo sin token → 401 TOKEN_INVALIDO
logs                     → JSON (uvicorn.access: método, ruta y estado); 0 entradas con severity ≥ ERROR
correo (service sobre xps_pricing): HABILITADO · dominio True · remitente True · plantilla Aprobada · todo_ok True
```

**`POST /v1/correo/probar` con un admin desde producción:** pendiente; es el primer paso de François. No se usaron credenciales de admin ni se fabricaron tokens.

### B7 sin rotación (D-FIN-2)

- **Backups automáticos:** activos (`enabled=True`), diarios a las 18:00 UTC, 3 retenidos; último `2026-10-14 18:00 AUTOMATED SUCCESSFUL`. La recuperación a un punto en el tiempo (PITR) está apagada: es opcional, no bloquea.
- **Restringir `pricing_app`:** requiere el usuario `postgres`. `pricing_app` no es dueño de las bases de XPS-Reborn ni superusuario. Hoy `pricing_app` puede conectarse a `xpress_dev` y `xpress_test` por el CONNECT de PUBLIC. SQL listo en `docs/go-live/02_restringir_pricing_app.sql`; se ejecuta en Cloud SQL Studio → base `postgres` → usuario `postgres`.
- **Nota:** la instancia tiene IP pública habilitada (la usa el proxy local). Cloud Run no la usa: se conecta por el socket de Cloud SQL.

### Fuera de horario (1.6), verificado en vivo

A las 20:00 de Ecuador (01:00 UTC) la base se apagó (`STOPPED`):
- `POST /v1/auth/login` → **503 `SISTEMA_FUERA_DE_HORARIO`**, con el horario;
- `GET /v1/salud` → `{"estado":"ok","bd":"error"}`.

### FASE 2

- **2.1:** usuarios de prueba creados en `xps_pricing` a las 19:59: `prueba.admin`, `prueba.pricing`, `prueba.comercial` y `prueba.gerencia`, todos `@xpress.ec`, con cambio obligatorio de contraseña. Las contraseñas se entregaron solo en el chat (D-FIN-5).
- **El ingreso real no se alcanzó a probar:** la base se apagó un minuto después.

### Siguiente paso de François

Mañana desde las 07:00, con la base encendida, recorrer `docs/CHECKLIST-FINAL.md` en la URL de producción:
1. Primero `prueba.admin`; empezar por Configuración → Correo Tencent → "Probar conexión".
2. Después pricing, comercial y gerencia.

Devolver OK o FALLA por punto. Pendiente aparte: ejecutar `docs/go-live/02_restringir_pricing_app.sql` como `postgres`.

## Estado final · 2026-10-16, 20:40 · proyecto al 100 %

Verificación automatizada en producción (D-CIE-1): **51 de 51 OK** (`docs/cierres/F5-checklist-resultado.md`).

Detalle de la seguridad de go-live, la limpieza y la base apagada: `docs/cierres/CIERRE-F5.md`. Operación y pendientes: `docs/cierres/CIERRE-PROYECTO.md`.

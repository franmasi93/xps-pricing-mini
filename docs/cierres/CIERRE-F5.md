# Acta de cierre · F5 · auditoría, deuda, despliegue en Cloud Run, seguridad de go-live y verificación final

| Dato | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fase | F5 (10 % del proyecto) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code |
| Fecha de cierre | 2026-10-16 |
| Commits | `7151a47` "F5 parte 1: auditoría, deuda, preparación del despliegue y checklist" · `7a5c644` "F5: despliegue en Cloud Run, seguridad de go-live y verificación final" |
| Producción | https://xps-pricing-809824844407.us-central1.run.app |

## 1. Resumen en cristiano

XPS Pricing Mini está en producción en Google Cloud Run (us-central1), conectado a la base de trabajo `xps_pricing` por el conector de Cloud SQL, sin IP pública abierta. Los secretos viven en Secret Manager.

La verificación final, con los 4 roles, se hizo de forma automatizada contra producción y quedó **51 de 51 OK** con evidencia. La única cotización de prueba (COT-2026-00001) salió por correo y quedó marcada RECHAZADA, así que la primera real será la COT-2026-00002.

Al cerrar quedan:
- los datos de prueba inactivos;
- el único usuario activo, el administrador de François;
- la base en su política original (apagada).

## 2. Alcance

| Bloque | Contenido | Estado |
|---|---|---|
| F5-A · auditoría y deuda (2 %) | Pantalla de Auditoría; paginación de tarifas y recargos; índices de trigramas (0006); aviso de Starlette documentado; A5 propuesto y no aplicado | Hecho (commit `7151a47`) |
| D-AUT-7 · fuera de horario | 503 `SISTEMA_FUERA_DE_HORARIO` cuando la base no responde | Hecho y **verificado en vivo** |
| F5-B · despliegue (4 %) | Dockerfile, `.dockerignore`, `.gcloudignore`, configuración por variables, Secret Manager, cuenta de servicio mínima, conector de Cloud SQL, logs JSON, health checks, `docs/DESPLIEGUE.md` | Desplegado |
| F5-C · verificación (3 %) | `docs/CHECKLIST-FINAL.md` (51 puntos); scripts de usuarios de prueba; verificación con los 4 roles | 51 de 51 OK |
| Cierre (1 %) | Actas, limpieza, controles, commits | Esta acta |

## 3. Evidencia del despliegue

**Servicio y conexión**
- **Servicio:** `xps-pricing`, us-central1.
- **Revisiones:** `xps-pricing-00001-lgx` (despliegue inicial) y **`xps-pricing-00002-4lk`** (health checks de arranque y de vida en `/v1/salud`), sirviendo el 100 %.
- **Cuenta de servicio:** `xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com`, con `roles/cloudsql.client` en el proyecto y `secretmanager.secretAccessor` solo sobre sus 3 secretos.
- **Secretos:** `xps-pricing-database-url` (URL por el socket `/cloudsql/xps-reborn-v2:us-central1:xpress-db-reborn-v2`), `xps-pricing-jwt-secret` y `xps-pricing-config-cifrado-key` (D-FIN-3: del `.env` por stdin, sin mostrarse).
- **Variables en claro:** solo `APP_ENV=prod`, `JWT_EXPIRA_MIN=480` y `PDF_NAVEGADOR=chromium`.
- **Base de trabajo `xps_pricing`:** migrada a **0006**. Correo HABILITADO con llaves cifradas, condiciones generales y 14 datos de la empresa cargados.

**Comprobaciones**
- `GET /v1/salud` → `{"estado":"ok","bd":"ok"}`.
- El login abre en la URL `*.run.app` (`<title>Ingresar · XPS Pricing</title>`) y `/` redirige por https.
- Logs en JSON (método, ruta y estado) y 0 entradas con severity ≥ ERROR.
- **Fuera de horario, verificado en vivo dos veces** (20:00 del 2026-10-16 y 20:35, al apagar la base después del cierre): `POST /v1/auth/login` → **503 `SISTEMA_FUERA_DE_HORARIO`**, con el horario; `/v1/salud` → `{"estado":"ok","bd":"error"}`.

## 4. Seguridad de go-live (FASE 1)

| Medida | Resultado |
|---|---|
| Rotar las contraseñas de `pricing_app` y `xpress_app`, y las llaves de Tencent | **No se hace: riesgo aceptado por François (D-FIN-2)** |
| Restringir `pricing_app` (D-CIE-3) | La contraseña de `postgres` se restableció sin mostrarse y quedó **solo en Secret Manager, secreto `xps-sql-postgres`**. Se aplicó el SQL como `postgres`. Resultado **parcial**: PUBLIC ya no entra a `xpress_dev`, pero `pricing_app` todavía entra a `xpress_dev` y `xpress_test` (H-F5-6). `xpress_app` conserva el acceso a las dos bases. Detalle y propuesta en `docs/go-live/02_restringir_pricing_app.sql` |
| Redes autorizadas de la instancia | **Ninguna configurada:** no hay `0.0.0.0/0` ni rangos abiertos. La IP pública solo admite el Auth Proxy y los conectores |
| Cuenta de servicio y variables de Cloud Run | Solo `xps-pricing-run`; los 3 secretos por `--set-secrets`; ninguna variable con secretos en claro |
| `.gcloudignore` y `.dockerignore` | Excluyen `.env`, `docs/`, `tests/`, `salidas/` y llaves. `gcloud meta list-files-for-upload`: 0 archivos privados |
| Backups automáticos | Activos: diarios a las 18:00 UTC, 3 retenidos; último `AUTOMATED SUCCESSFUL` |

## 5. Verificación final con los 4 roles (D-CIE-1)

**51 de 51 puntos OK.** Detalle punto por punto en `docs/cierres/F5-checklist-resultado.md`; capturas en `salidas/f5/checklist/` (fuera de git).

Cómo se hizo:
- Playwright contra producción, a 1280 y 375 px, más la API con el token de cada rol.
- Ingreso real con cambio obligatorio de contraseña para los 4 roles; las contraseñas nuevas vivieron solo en memoria.
- Se revisaron 64 pantallas, con 0 errores de consola y 0 con scroll horizontal a 375 px.

**Reglas por la API:**
- comercial: cotización ajena → 404;
- gerencia: `POST /tarifas` → 403;
- comercial, pricing y gerencia: `/v1/correo/config` → 403;
- comercial: `/v1/configuracion/empresa` → 403;
- el comercial no recibe claves de costo ni margen.

**Envío real desde producción (D-CIE-4):** COT-2026-00001 a francois-ramart@outlook.com, con CC al segundo contacto (el mismo buzón) y copia oculta a pricing@xpress.ec. MessageId `qcloudses-30-1420342617-date-20261017092702-rqAAFBRQ4JOu1`.

**Corridas:**
- La primera se cortó por un error del script (la carrera de la pantalla de cambio de contraseña).
- En la segunda, 2 FALLA del verificador (texto de las condiciones y mayúsculas por CSS) se reevaluaron sobre la misma evidencia.
- **No hubo cambios de código en la aplicación ni revisiones nuevas.**

## 6. Limpieza en producción (D-CIE-4, D-CIE-5)

Nada se borró:
- COT-2026-00001 → **RECHAZADA** (OTRO, "Prueba de verificación final"); los 3 borradores de prueba, descartados;
- 5 tarifas, 4 recargos, 2 clientes y el proveedor "Agente PRUEBA F5 LB" → inactivos;
- los 5 usuarios de prueba → inactivos (`scripts/desactivar_usuarios_prueba.py` y el usuario extra del punto 7–9).

**Único usuario activo: `francois-ramart@outlook.com`.**

Se crearon y **quedan activos** estos catálogos reales, que producción necesita:
- regiones SUDAMERICA, NORTEAMERICA y ASIA;
- países EC, US y CN;
- puertos GYE, ECGYE, MIA y CNSHA;
- moneda CNY con tasa 0.14;
- proveedor MSL.

## 7. Base de datos fuera de horario (D-CIE-2)

| Paso | Estado |
|---|---|
| Política original | `NEVER` (STOPPED; viernes 2026-10-16, 20:08) |
| Para el trabajo | `ALWAYS` |
| Al terminar (20:35) | **`NEVER` / STOPPED, igual que estaba** |

## 8. Decisiones

| Grupo | Decisión |
|---|---|
| D-AUT-5 | Región de Cloud Run: la de la instancia, us-central1 |
| D-AUT-6 | Dirección: la URL `*.run.app`; el dominio propio queda para después |
| D-AUT-7 | Se mantiene el horario L–V 07:00–20:00; fuera de él, mensaje claro y nunca un 500 |
| D-AUT-8 | A5: no aplicado; quedó propuesto |
| D-AUT-9 | El push lo hace François, o el EJECUTOR cuando él lo pide explícitamente |
| D-FIN-1 | Compuerta visual de F4 aprobada |
| D-FIN-2 | No se rotan contraseñas ni llaves (riesgo aceptado) |
| D-FIN-3 | CONFIG_CIFRADO_KEY va a Secret Manager por stdin |
| D-FIN-4 | El EJECUTOR ejecuta los comandos de Google Cloud |
| D-FIN-5 | Usuarios de prueba en producción, con las contraseñas solo en el chat |
| D-CIE-1 | La compuerta de F5 la cumple el checklist automatizado |
| D-CIE-2 | Encender y apagar la base dejándola como estaba |
| D-CIE-3 | `postgres`, con su contraseña en Secret Manager |
| D-CIE-4 | Una sola cotización de prueba, RECHAZADA al cerrar |
| D-CIE-5 | Datos "PRUEBA F5" inactivos al cerrar |

## 9. Huecos

| Hueco | Decisión |
|---|---|
| H-F5-1 | Paginación opcional (`limit`/`offset`) con el total en `X-Total-Count` |
| H-F5-2 | No se quita el CONNECT a PUBLIC en bases ajenas sin confirmar sus roles |
| H-F5-3 | `DATABASE_URL_TEST` es opcional solo en prod |
| H-F5-4 | Sin commit de F5 antes de cerrar F4 |
| H-F5-5 | Llaves de Tencent pegadas en el chat (después, riesgo aceptado por D-FIN-2) |
| **H-F5-6 (nuevo)** | La restricción de `pricing_app` quedó parcial: es miembro de `cloudsqlsuperuser`, y `xpress_test` es de `xpress_app`. Completarla exige cambiar la membresía o la propiedad de la base, o actuar como `xpress_app`. **Decisión pendiente de François**; propuesta en el SQL de go-live |

## 10. Riesgos aceptados y abiertos

- **Riesgo aceptado (D-FIN-2):** sin rotación de la contraseña de `pricing_app` ni de la SecretKey de Tencent, que se pegó en el chat.
- **IP pública habilitada:** la instancia tiene IP pública, pero sin redes autorizadas (solo Auth Proxy y conectores). Cloud Run no la usa.
- **PITR apagado:** la recuperación a un punto en el tiempo está apagada. Los backups diarios sí están activos.
- **`pricing_app` en `cloudsqlsuperuser`:** tiene derechos de dueño sobre las bases de ese rol (H-F5-6).

## 11. Controles del cierre

- **Cambios de código desde `7151a47`:** ninguno en la aplicación. Solo `.gcloudignore` (configuración de la subida a Cloud Build) y documentos. Por eso no corresponde otra Regla 18 (3.1); la última, sobre este mismo código, dio 634 de 634 en los dos ciclos.
- **Canario de encoding:** `Canario de encoding: 204 OK, 0 con fallas, 204 revisados`.
- **Control de secretos:** sobre los 221 archivos visibles para git, sobre todo el proyecto (sin el `.env`, incluidas `salidas/` y las capturas) y sobre toda la historia de git. **0 apariciones** de cada uno de estos:
  - la contraseña de la base (texto y codificada) y la de la base de pruebas;
  - JWT_SECRET y CONFIG_CIFRADO_KEY;
  - el SecretId y la SecretKey de Tencent;
  - la contraseña nueva de `postgres` (leída en memoria desde Secret Manager);
  - cualquier "IKID" real.

  Las coincidencias de "BEGIN PRIVATE KEY" y `"service_account"` son el texto de `CIERRE-F4.md` y `F4-entregas-paradas.md` que describe el control; no son llaves.
- **git status:** sin `.env` ni `salidas/`. Los documentos privados (`docs/TENCENT_CLOUD.md`, `start.txt`, etc.) siguen sin seguimiento y no entran al commit.

## 12. Avance

F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · F3 30 % ✅ · F4 15 % ✅ · F5 10 % ✅ · **proyecto 100 %**.

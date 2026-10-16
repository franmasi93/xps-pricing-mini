# Despliegue de XPS Pricing Mini en Cloud Run

Escrito para: François, para la sesión de despliegue P-A (unos 45 minutos). El EJECUTOR guía y verifica; **cada comando que toca Google Cloud lo ejecuta François**.

**Antes de empezar:**
- Todo se ejecuta en PowerShell, desde la carpeta del proyecto (`xps-pricing-mini`).
- Ningún paso muestra secretos en pantalla. Si alguno los muestra, detente y avisa.

## Datos fijos

| Dato | Valor |
|---|---|
| Proyecto de Google Cloud | `xps-reborn-v2` |
| Instancia de Cloud SQL | `xpress-db-reborn-v2` (conexión `xps-reborn-v2:us-central1:xpress-db-reborn-v2`) |
| Región de Cloud Run (D-AUT-5, la misma de la instancia) | `us-central1` |
| Servicio | `xps-pricing` |
| Cuenta de servicio | `xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com` |
| Base de trabajo | `xps_pricing` (nunca `xps_pricing_test`) |
| Dirección (D-AUT-6) | la URL `*.run.app` que entrega Cloud Run |

## 0. Preparar la sesión

1. Abrir sesión en Google Cloud:
   ```powershell
   gcloud auth login
   gcloud config set project xps-reborn-v2
   ```
   **Debe ver:** `Updated property [core/project].`

2. Confirmar la región de la instancia:
   ```powershell
   gcloud sql instances describe xpress-db-reborn-v2 --format="value(region)"
   ```
   **Debe ver:** `us-central1`. Si aparece otra región, usar esa en todos los comandos y avisar.

3. Encender la base y el proxy local como siempre (`docs/Encender-Auth-Proxy.md`).

## 1. Seguridad del go-live (B7)

Detalle completo en `docs/go-live/README.md`.

1. **Rotar la contraseña de `pricing_app`** (24 caracteres o más). Generarla en el gestor de contraseñas y luego:
   ```powershell
   gcloud sql users set-password pricing_app --instance=xpress-db-reborn-v2 --prompt-for-password
   ```
   **Debe ver:** que pide la contraseña sin mostrarla y termina con `Updating Cloud SQL user...done.`

2. **Actualizar el `.env` local** con la contraseña nueva en `DATABASE_URL` y `DATABASE_URL_TEST`. Recuerde codificar `@` como `%40`.
   Comprobar:
   ```powershell
   .\.venv\Scripts\python.exe -c "from app.db import engine; from sqlalchemy import text; print(engine.connect().execute(text('select 1')).scalar())"
   ```
   **Debe ver:** `1`.

3. **Restringir `pricing_app` a sus dos bases.** Ejecutar `docs/go-live/02_restringir_pricing_app.sql` como usuario `postgres` (leer primero las notas del archivo).

4. **Backups automáticos:**
   ```powershell
   gcloud sql instances describe xpress-db-reborn-v2 --format="value(settings.backupConfiguration.enabled,settings.backupConfiguration.pointInTimeRecoveryEnabled)"
   ```
   **Debe ver:** `True` en el primer valor. Si dice `False`, activarlos:
   ```powershell
   gcloud sql instances patch xpress-db-reborn-v2 --backup-start-time=05:00
   ```

5. **Llave de la cuenta de servicio del proxy:** evaluar su rotación según `docs/go-live/README.md`, punto 4.

## 2. APIs y cuenta de servicio (B4)

1. Habilitar las APIs (si ya están habilitadas, no pasa nada):
   ```powershell
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com sqladmin.googleapis.com
   ```
   **Debe ver:** `Operation ... finished successfully.` o ningún mensaje de error.

2. Crear la cuenta de servicio propia del servicio:
   ```powershell
   gcloud iam service-accounts create xps-pricing-run --display-name="XPS Pricing Mini (Cloud Run)"
   ```
   **Debe ver:** `Created service account [xps-pricing-run].`

3. Darle solo **Cloud SQL Client**:
   ```powershell
   gcloud projects add-iam-policy-binding xps-reborn-v2 --member="serviceAccount:xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com" --role="roles/cloudsql.client" --condition=None
   ```
   **Debe ver:** `Updated IAM policy for project [xps-reborn-v2].`

## 3. Secretos en Secret Manager (B2)

1. Subir los tres secretos. Lee el `.env` y no muestra ningún valor:
   ```powershell
   .\.venv\Scripts\python.exe scripts\subir_secretos.py xps-reborn-v2 xps-reborn-v2:us-central1:xpress-db-reborn-v2
   ```
   **Debe ver** tres líneas, una por secreto, y al final `Listo. Ningún valor se mostró en pantalla.`:
   ```
   xps-pricing-database-url: creado y versión nueva agregada
   xps-pricing-jwt-secret: creado y versión nueva agregada
   xps-pricing-config-cifrado-key: creado y versión nueva agregada
   ```
   `CONFIG_CIFRADO_KEY` va con el **mismo** valor del `.env`. Si cambia, las llaves de Tencent guardadas en la base dejan de descifrarse.

2. Permitir que la cuenta de servicio lea **solo** esos tres secretos (Secret Manager Secret Accessor sobre cada uno):
   ```powershell
   foreach ($s in "xps-pricing-database-url","xps-pricing-jwt-secret","xps-pricing-config-cifrado-key") { gcloud secrets add-iam-policy-binding $s --member="serviceAccount:xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" }
   ```
   **Debe ver:** tres veces `Updated IAM policy for secret [...]`.

## 4. Migrar la base de trabajo

Por el proxy local, contra `xps_pricing` (`APP_ENV=dev`):
```powershell
$env:APP_ENV = "dev"; .\.venv\Scripts\python.exe -m alembic upgrade head; .\.venv\Scripts\python.exe -m alembic current; Remove-Item Env:APP_ENV
```
**Debe ver:** `0006 (head)`. La base de trabajo quedó en 0005 el 2026-10-15; este paso aplica 0006 (índices de trigramas de clientes).

## 5. Construir y desplegar (B1, B3, B5)

1. Construir la imagen con Cloud Build y desplegar. Docker no está instalado en el equipo; Cloud Build construye con el `Dockerfile` del proyecto:
   ```powershell
   gcloud run deploy xps-pricing --source . --region us-central1 --service-account xps-pricing-run@xps-reborn-v2.iam.gserviceaccount.com --add-cloudsql-instances xps-reborn-v2:us-central1:xpress-db-reborn-v2 --set-secrets "DATABASE_URL=xps-pricing-database-url:latest,JWT_SECRET=xps-pricing-jwt-secret:latest,CONFIG_CIFRADO_KEY=xps-pricing-config-cifrado-key:latest" --set-env-vars "APP_ENV=prod,JWT_EXPIRA_MIN=480,PDF_NAVEGADOR=chromium" --memory 2Gi --cpu 1 --min-instances 0 --max-instances 2 --timeout 120 --allow-unauthenticated
   ```
   - Si pregunta por crear un repositorio de Artifact Registry, responder `Y`.
   - La construcción tarda varios minutos (instala Chromium para el PDF).
   - **Debe ver** al final:
     ```
     Service [xps-pricing] revision [xps-pricing-0000x-xxx] has been deployed and is serving 100 percent of traffic.
     Service URL: https://xps-pricing-xxxxxxxxxx-uc.a.run.app
     ```

2. Health check con `/v1/salud`:
   ```powershell
   gcloud run services update xps-pricing --region us-central1 --startup-probe="httpGet.path=/v1/salud,initialDelaySeconds=5" --liveness-probe="httpGet.path=/v1/salud"
   ```
   **Debe ver:** una revisión nueva sirviendo el 100 %.

3. Verificar (reemplazar `<URL>` por la Service URL):
   ```powershell
   curl.exe -s <URL>/v1/salud
   ```
   **Debe ver:** `{"estado":"ok","bd":"ok"}`.
   - Fuera del horario de la base (L–V 07:00–20:00) verá `"bd":"error"`. La app está viva y la pantalla muestra "Sistema fuera de horario" (D-AUT-7).

4. Abrir `<URL>/app/login.html` e ingresar con el administrador de la base de trabajo.
   - Si no existe ninguno: `.\.venv\Scripts\python.exe scripts\crear_admin.py`.

## 6. Logs

```powershell
gcloud run services logs read xps-pricing --region us-central1 --limit 50
```
**Debe ver:** líneas JSON con `severity`, `logger` y `message`. Nunca contraseñas, tokens ni la cadena de conexión.

## 7. Operación diaria

| Tarea | Cómo |
|---|---|
| Nueva versión | Repetir el paso 5.1 (el mismo comando). |
| Ver revisiones o volver atrás | `gcloud run revisions list --service xps-pricing --region us-central1` y `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=<revisión>=100` |
| Cambiar un secreto | Repetir el paso 3.1 y desplegar de nuevo (paso 5.1) para que tome `latest`. |
| Correo Tencent | En la pantalla Configuración, como admin; no requiere despliegue. |
| Usuarios de la verificación final | `scripts\crear_usuarios_prueba.py trabajo` / `scripts\desactivar_usuarios_prueba.py trabajo` |

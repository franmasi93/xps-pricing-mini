# Seguridad del go-live (B7)

Escrito para: François. Él ejecuta cada paso; el EJECUTOR preparó los comandos y el SQL.

## 1. Rotar la contraseña de `pricing_app`

**No se hace: riesgo aceptado por François (D-FIN-2, 2026-10-16).** Lo que sigue queda solo como referencia.

La contraseña nueva debe tener 24 caracteres o más, generada en el gestor de contraseñas. El comando la pide sin mostrarla:

```powershell
gcloud sql users set-password pricing_app --instance=xpress-db-reborn-v2 --prompt-for-password
```

Después:
1. Actualizar `DATABASE_URL` y `DATABASE_URL_TEST` en el `.env` local (codifique `@` como `%40`).
2. Subir otra vez los secretos (`docs/DESPLIEGUE.md`, paso 3.1).
3. Si el servicio ya estaba desplegado, desplegarlo de nuevo.

**Equivalente en SQL** (como `postgres`, si prefiere psql):

```sql
\password pricing_app
```

## 2. Restringir `pricing_app` a sus dos bases

Ejecutar `02_restringir_pricing_app.sql` como `postgres`. Leer antes el aviso del archivo: no se quita el `CONNECT` a `PUBLIC` en las bases de otros sistemas sin confirmar qué roles usan.

## 3. Backups automáticos

```powershell
gcloud sql instances describe xpress-db-reborn-v2 --format="value(settings.backupConfiguration.enabled,settings.backupConfiguration.pointInTimeRecoveryEnabled)"
```

- **Esperado:** `True` y, de preferencia, `True` también para la recuperación a un punto en el tiempo.
- **Activarlos:** `gcloud sql instances patch xpress-db-reborn-v2 --backup-start-time=05:00`.
- **Restaurar un backup** (borra los datos actuales de la instancia; solo ante un desastre):
  1. Listar los backups: `gcloud sql backups list --instance=xpress-db-reborn-v2`.
  2. Restaurar: `gcloud sql backups restore <ID> --restore-instance=xpress-db-reborn-v2`.

## 4. Llave de la cuenta de servicio del proxy (evaluación)

El proxy local (`docs/Encender-Auth-Proxy.md`) usa una llave JSON de una cuenta de servicio. Cloud Run **no la necesita**: se conecta con su propia cuenta de servicio (`xps-pricing-run`, solo Cloud SQL Client).

**Recomendación:** rotar la llave del proxy después del go-live y dejar en el equipo solo la llave nueva.

1. Ver las llaves:
   ```powershell
   gcloud iam service-accounts keys list --iam-account=<cuenta-del-proxy>
   ```
2. Crear una llave nueva **fuera de OneDrive**:
   ```powershell
   gcloud iam service-accounts keys create C:\claves\proxy-nueva.json --iam-account=<cuenta-del-proxy>
   ```
3. Probar el proxy con la llave nueva.
4. Borrar la llave anterior:
   ```powershell
   gcloud iam service-accounts keys delete <ID-anterior> --iam-account=<cuenta-del-proxy>
   ```

**Mejor aún:** usar `gcloud auth application-default login` en lugar de una llave JSON.

## 5. Llaves de Tencent

**No se rotan: riesgo aceptado por François (D-FIN-2, 2026-10-16).**

Las llaves de Tencent quedaron escritas en el chat de la sesión del 2026-10-15.

Después de la prueba real:
1. Rotar la SecretKey del subusuario `pricing-ses` en Tencent CAM.
2. Pegar la nueva en Configuración → Correo Tencent.
3. Guardar.

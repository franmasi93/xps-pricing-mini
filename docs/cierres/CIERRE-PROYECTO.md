# Cierre del proyecto XPS-Pricing-Mini

| Dato | Valor |
|---|---|
| Decisor | François Ramírez |
| Ejecutor | Claude Code |
| Fecha | 2026-10-16 |
| Avance | **100 %** (F0 5 % + F1 15 % + F2 25 % + F3 30 % + F4 15 % + F5 10 %) |
| Producción | https://xps-pricing-809824844407.us-central1.run.app |
| Repositorio | https://github.com/franmasi93/xps-pricing-mini (privado) |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` |

## 1. Qué es

Es el sistema de cotizaciones de XPRESS LOGISTICS XPS S.A. Funciona así:
- **Pricing** carga tarifas (aéreas por kg o lb con tramos, LCL y FCL) y recargos por puerto.
- **El comercial** cotiza por Incoterm. El motor calcula en Decimal: peso cobrable, W/M, monedas con su tasa, mínimos, IVA y los bloques de Recibo de Caja y Factura.
- **La emisión** congela la cotización con su número COT-AAAA-NNNNN, genera el PDF oficial y la envía por correo con Tencent SES, que queda en una bitácora.
- **Gerencia** ve costos, márgenes y la auditoría.
- **Cuatro roles** con permisos (RBAC): admin, pricing, comercial y gerencia.

## 2. Fases

| Fase | Peso | Commit(s) | Contenido |
|---|---|---|---|
| F0 + M1 | 5 % | `4456aef` | Base del proyecto, autenticación JWT, RBAC (§6.2), usuarios, bloqueo, cambio de contraseña, pantallas y scripts de administración |
| F1 | 15 % | `e00552a` | Geografía, monedas y tasas, proveedores, Incoterms, configuración y auditoría |
| F2 | 25 % | `ead5ef6` | Tarifas y tramos, recargos, clientes y contactos, gating de costos y márgenes |
| F3 | 30 % | `0a62b2a` · acta `6375d5d` | Cotizador, emisión con numeración, estados, duplicado y PDF |
| F4 | 15 % | `7743d19` · acta `4af69b0` | PDF con el formato oficial, kg y lb, recargo sobre el Recibo de Caja, correo Tencent administrable y bitácora; prueba real con 5 correos |
| F5 | 10 % | `7151a47` · `7a5c644` · acta | Auditoría, paginación, trigramas, fuera de horario, despliegue en Cloud Run, seguridad de go-live, verificación final 51 de 51 |

**Pruebas:** 634 automáticas. Regla 18 doble en base virgen en cada cierre; la última, 634 de 634 en los dos ciclos. **Migraciones:** de 0001 a 0006, escritas a mano.

## 3. Cómo operar en producción

### 3.1 Encender y apagar la base

La instancia `xpress-db-reborn-v2` atiende de lunes a viernes de 07:00 a 20:00. Fuera de ese horario el sistema muestra "Sistema fuera de horario".

- **Encender a mano:** `gcloud sql instances patch xpress-db-reborn-v2 --activation-policy=ALWAYS`
- **Apagar:** `gcloud sql instances patch xpress-db-reborn-v2 --activation-policy=NEVER`
- **Ver el estado:** `gcloud sql instances describe xpress-db-reborn-v2 --format="value(state,settings.activationPolicy)"`
- **Proxy local:** después de cada encendido, reiniciarlo según `docs/Encender-Auth-Proxy.md`.

### 3.2 Desplegar una versión nueva

1. En la carpeta del proyecto, con el código en `main`, repetir el comando del paso 5.1 de `docs/DESPLIEGUE.md` (`gcloud run deploy xps-pricing --source . --region us-central1 …`).
2. Si la versión trae migraciones, antes: `$env:APP_ENV="dev"; .\.venv\Scripts\python.exe -m alembic upgrade head`, por el proxy y con la base encendida.
3. Para volver a una revisión anterior:
   ```powershell
   gcloud run revisions list --service xps-pricing --region us-central1
   gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=<revisión>=100
   ```

### 3.3 Crear usuarios

Desde la pantalla **Usuarios**, como admin, con una contraseña temporal; el primer ingreso exige cambiarla.

- **Para pruebas de verificación:** `scripts\crear_usuarios_prueba.py trabajo`. Al terminar: `scripts\desactivar_usuarios_prueba.py trabajo`.
- **Nunca se borran usuarios:** se desactivan.

### 3.4 Cambiar la configuración del correo

1. Ir a **Configuración → Correo Tencent**, como admin.
2. Hacer los cambios: región, remitente, plantilla, interruptor o llaves (de solo escritura).
3. "Probar conexión" debe dar los 3 puntos en verde antes de habilitar.
4. Cada cambio queda en la auditoría, con las llaves enmascaradas.

**La llave que cifra las llaves de Tencent** es `CONFIG_CIFRADO_KEY`. Vive en el `.env` local y en Secret Manager (`xps-pricing-config-cifrado-key`), y deben ser el mismo valor. Si se pierde, hay que volver a pegar las llaves de Tencent en la pantalla.

### 3.5 Restaurar un backup

Los backups automáticos son diarios, a las 18:00 UTC, y se conservan 3. Restaurar reemplaza los datos actuales de **toda** la instancia, incluido XPS-Reborn; solo ante un desastre:

```powershell
gcloud sql backups list --instance=xpress-db-reborn-v2
gcloud sql backups restore <ID> --restore-instance=xpress-db-reborn-v2
```

### 3.6 Secretos

| Secreto en Secret Manager | Contenido |
|---|---|
| `xps-pricing-database-url` | URL de la base por el socket de Cloud SQL |
| `xps-pricing-jwt-secret` | Firma de las sesiones |
| `xps-pricing-config-cifrado-key` | Cifrado de las llaves de correo |
| `xps-sql-postgres` | Contraseña del usuario `postgres` de la instancia (D-CIE-3) |

Ver un valor (solo si es necesario y en un equipo de confianza): `gcloud secrets versions access latest --secret=<nombre>`.

## 4. Pendientes no bloqueantes

1. **Revisión legal** de las condiciones generales y de la cláusula fundamental del PDF.
2. **MFA en la cuenta raíz de Tencent Cloud.**
3. **Cargar tarifas, recargos y clientes reales:** los de prueba quedaron inactivos. La primera cotización real será la COT-2026-00002.
4. **Dominio propio** (por ejemplo `pricing.xpress.ec`), en lugar de la URL `*.run.app`.
5. **PITR** (recuperación a un punto en el tiempo): hoy está apagada.
6. **Completar la restricción de `pricing_app` (H-F5-6):** quitarle la membresía de `cloudsqlsuperuser` (antes, darle la propiedad de `xps_pricing`) y revocar PUBLIC en `xpress_test` como `xpress_app`. Propuesta en `docs/go-live/02_restringir_pricing_app.sql`.
7. **Riesgo aceptado (D-FIN-2):** la contraseña de `pricing_app` y la SecretKey de Tencent no se rotaron.
8. **Deuda menor:**
   - `StarletteDeprecationWarning` del cliente de pruebas.
   - Tiempo de la suite (~90 min por ciclo, por la latencia a Cloud SQL); medir con `--durations` antes de optimizar.

## 5. Lo que sigue

### F6 · notificaciones y promociones

- Avisos de vencimiento de tarifas a Pricing.
- Recordatorio al comercial de las cotizaciones por vencer.
- Envío de promociones o tarifas destacadas a clientes con su consentimiento y opción de baja (otra plantilla de Tencent).
- Resumen semanal para gerencia.

### V2

- Portal del cliente para aceptar o rechazar la cotización en línea.
- Seguimiento de embarques.
- Integración con la facturación electrónica (SRI).
- Varias monedas de cotización.
- Tablero de indicadores (tasa de cierre por comercial, márgenes por ruta).
- Dominio propio con SSO.

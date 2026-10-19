# Acta de cierre · E4 · Dominio propio pricing.xpress.ec

| Dato | Valor |
|---|---|
| Decisor | François Ramírez |
| Ejecutor | Claude Code (sesión autónoma del 2026-10-19) |
| Fecha de cierre | 2026-10-19 |
| Commits | `4ba1d44` (menú lateral e inicio) · `02f8f04` (E4: URL pública, www → principal y mapeo) · `22c1347` (plantillas internas aprobadas) · esta acta |
| Migración | `0011_e4_url_publica` (0010 → 0011) |
| Respaldos | **1792417196790** (antes de migrar a 0011) · **1792419545431** (antes de desplegar 22c1347) · **1792420178861** (antes de cambiar la URL pública) |
| Producción | **https://pricing.xpress.ec** (principal) · https://www.pricing.xpress.ec (301 a la principal) · la URL de Cloud Run sigue funcionando · revisión **xps-pricing-00008-mgk** |
| URL pública del sistema | **https://pricing.xpress.ec** (cambiada el 2026-10-19 a las 09:31, con auditoría) |

## 1. Resumen en cristiano

El sistema ya abre en **https://pricing.xpress.ec**, con candado válido: el certificado es de Google y se renueva solo.
- **www.pricing.xpress.ec** lleva a la dirección principal.
- **La dirección de Cloud Run** sigue funcionando igual.
- **Todos los enlaces nuevos** (la baja de los boletines y de los avisos) ya salen con pricing.xpress.ec.
- **Plantillas internas:** el aviso interno (72752) y el resumen (72753) están aprobados en Tencent y se probaron con correos reales al administrador.
- **Avisos a clientes:** siguen en simulación.

## 2. Avance de E4

| Parte | Peso | Estado |
|---|---|---|
| Menú lateral | 15 % | Hecho (ver 3) |
| Dominio y certificado | 40 % | Hecho: los dos mapeos listos y el certificado emitido |
| URL pública cambiada y verificada | 15 % | Hecho |
| Plantillas internas y prueba real | 20 % | Hecho |
| Callback y cierre | 10 % | Hecho del lado del sistema; registrar el callback en Tencent es del gerente (Pendientes) |
| **Total E4** | **100 %** | **100 %** (un pendiente del gerente: el callback en la consola de Tencent) |

## 3. Menú lateral

**No había cambios sin commit:** el árbol de git estaba limpio. Los últimos cambios del menú son los de `4ba1d44`, pedidos por el gerente esta mañana y ya desplegados desde la revisión 00007:
- íconos;
- grupos plegables;
- buscador;
- modo compacto;
- panel deslizable en el celular;
- campana en una fila propia;
- pantalla de inicio con saludo, indicadores y "Para hoy".

No hubo nada que corregir. **Verificación en Chromium**, con administrador y comercial, en escritorio (1366 px) y celular (390 px), en inicio, cotizaciones, tarifas, boletines, notificaciones y configuración:
- **enlaces del menú:** todos válidos;
- **errores de JavaScript:** ninguno;
- **desplazamiento horizontal:** ninguno;
- **en el celular:** el panel se abre y se cierra bien;
- **comercial:** ve solo sus 9 opciones (Inicio, Tarifas, Cotizaciones, Clientes, Incoterms, Campañas, Listas, Bajas y Tipos de equipo), ninguna de administración.

## 4. Dominio

- **Método:** Cloud Run domain mapping en us-central1. **Costo: USD 0.**
- **DNS (Hostinger):** TXT de verificación en @, CNAME pricing → ghs.googlehosted.com y CNAME www.pricing → ghs.googlehosted.com. Propagado en Google (8.8.8.8) y Cloudflare (1.1.1.1). **El TXT de verificación no se borra nunca.**
- **Mapeos** (`scripts/dominio_propio.py crear`): pricing.xpress.ec y www.pricing.xpress.ec, los dos **Ready**.
- **Certificado:** Google Trust Services (WR3), CN=pricing.xpress.ec, emitido el 2026-10-19 y vigente hasta el 2027-01-17. Google lo renueva solo.

**Verificación por https://pricing.xpress.ec: 12 de 12**
- Salud por los dos dominios.
- www → principal (301).
- Login con administrador y menú nuevo.
- La cotización COT-2026-00001 abre con el **mismo total, USD 296.95**: en la API, en la base y en la pantalla.
- El PDF se genera (373 KB).
- Boletines, Configuración de notificaciones y Bitácora cargan.
- La baja con token inválido da el mensaje genérico.
- Sin errores de JavaScript (solo el 404 esperado del token inválido).

## 5. URL pública

- **Antes:** la URL de Cloud Run. **Ahora:** `https://pricing.xpress.ec`. Cambiada por la API con auditoría, con el respaldo 1792420178861 previo.
- **Enlace de baja de boletines y avisos:** ya sale `https://pricing.xpress.ec/b/<token>`.
- **Enlace de los avisos internos:** va como ruta interna (`/app/…`), porque el dominio lo pone la plantilla.

## 6. Plantillas

**Sincronizadas:** 72669 y 72746–72753 están **aprobadas y activas**. La 71711 (tarifario antiguo) está en el catálogo como **inactiva**.

**Variables reales leídas de Tencent con GetEmailTemplate:**
- **72752:** `evento`, `referencia`, `fecha`.
- **72753:** `periodo`, `kpi_emitidas`, `kpi_enviadas`, `kpi_aceptadas`, `kpi_rechazadas`, `kpi_tasa_cierre`, `kpi_monto`, `kpi_margen`.

**Ajustes en el sistema:**
- `evento` = nombre corto del aviso ("Cotización aceptada", "Margen bajo", "Tarifa por vencer"…);
- `referencia` = identificador del registro (COT-…, "Tarifa GYE→MIA LATAM", "Campaña …", el usuario…);
- `fecha` en dd/mm/aaaa hh:mm, hora de Ecuador;
- KPI con USD y separador de miles, y porcentajes con 1 decimal;
- se envían exactamente las variables de cada plantilla (prueba TE3-28).

**Botón:** en las dos plantillas aprobadas, el botón ("Revisar en el sistema" y "Ver el detalle en el sistema") **no tiene enlace**: Tencent quitó el `href`. No apunta ni a pricing.xpress.ec ni a la URL de Cloud Run. No se editó nada (Pendientes, mejora opcional).

**Copias en `docs/extensiones/plantillas/`:** se reemplazaron por el HTML aprobado y se borraron las versiones viejas.

## 7. Prueba real (solo al administrador)

| Plantilla | Destinatario | Estado | message_id |
|---|---|---|---|
| 72752, aviso interno | francois-ramart@outlook.com | ENVIADO | qcloudses-30-1420342617-date-20261019223141-3q08tV5r9xsX1 |
| 72753, resumen diario | francois-ramart@outlook.com | ENVIADO | qcloudses-30-1420342617-date-20261019223142-JZll5s4UfmWh1 |

Las reglas temporales de la prueba (ids 20 y 21) quedaron desactivadas. Los avisos a clientes siguen en **SIMULACIÓN**: ninguno enviado ni pendiente.

**Además:** en esa misma evaluación salieron el resumen diario y el semanal a **prueba.gerencia@xpress.ec**. Es el usuario de prueba de F5 con rol Gerencia, que estaba activo durante la verificación y es hoy el único usuario de ese rol, que es el destinatario de los resúmenes. Es una dirección interna (ningún cliente) y el usuario volvió a quedar desactivado.

## 8. Callback de Tencent

- **URL nueva:** `https://pricing.xpress.ec/internal/tencent/eventos/<TOKEN>`. Quedó **en el portapapeles del gerente**, sin mostrar el token.
- **Eventos recibidos hasta hoy:** ninguno. El callback todavía no está registrado en Tencent.
- **Los dos dominios** responden en ese endpoint (401 sin token válido). La URL de Cloud Run sigue aceptando callbacks.

## 9. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18 · ciclo 1 (PostgreSQL 18.6 local, base nueva 0001→0011) | **783 passed** |
| Regla 18 · ciclo 2 | **783 passed** |
| Ida y vuelta de 0011 | Esquema 0010 idéntico |
| Menú en Chromium (2 roles × 2 tamaños) | Sin errores |
| Verificación en producción | 12/12 (dominio) y 13/13 (URL pública, plantillas y prueba real) |

**Pruebas nuevas o ajustadas:** TE4-01 a TE4-08 (URL pública, ninguna URL fija en el código, www → principal, los dos dominios) y TE3-28 (variables exactas de las plantillas aprobadas).

## 10. Decisiones tomadas

1. **Menú:** no había cambios del gerente sin commit. Se verificaron los de `4ba1d44` y no hubo que corregir nada.
2. **Dominio:** Cloud Run domain mapping por la API REST, porque el componente beta de gcloud no está instalado y no hay permisos de administrador para instalarlo. Sin costo.
3. **`{{enlace}}` interno = solo la ruta (`/app/…`),** como pidió el gerente. Las URL completas (baja) salen de la URL pública del sistema.
4. **Variables de 72752:** el sistema sigue armando también las de la versión anterior (titulo, mensaje, detalle_NN), pero solo se envían las que tiene la plantilla del catálogo. Si el gerente vuelve a una versión con esas variables, funciona sin cambiar código.
5. **Las plantillas aprobadas no se editaron**, aunque el botón quedó sin enlace: editarlas las devolvería a revisión.
6. **La 71711** ya estaba inactiva en el catálogo (las importadas entran inactivas). No hubo que tocarla.

## 11. Pendientes del gerente

1. **Callback de Tencent:** en la consola de Tencent Cloud → Simple Email Service → **Callback** (回调地址), pegar la URL que está en el portapapeles (Ctrl+V). Marcar **bounce, spamreport y unsubscribe** (y delivery, open y click si están disponibles) y guardar.
2. **Destinatario de los resúmenes:** hoy ningún usuario real tiene rol Gerencia. Para recibir el resumen diario y el semanal, en **Administración → Notificaciones → Resúmenes → Editar** agregue su correo en "Correos fijos" o marque el rol Administrador. También puede dar el rol Gerencia a su usuario.
3. **(Opcional) Botón de 72752 y 72753:** en Tencent → Templates → Edit, poner el enlace del botón como `href="https://pricing.xpress.ec{{enlace}}"` y agregar la variable `{{enlace}}`. Volverá a revisión: mientras tanto esos correos internos no salen (la campana sí llega).

## 12. Checklist del gerente

1. [ ] **Entrar** por https://pricing.xpress.ec: se ve el candado y se puede ingresar.
2. [ ] **Probar el menú:** buscador, grupos, modo compacto y, en el celular, el botón ☰.
3. [ ] **Abrir una cotización y su PDF:** mismos montos de siempre.
4. [ ] **Revisar en su correo** el "aviso interno" de prueba (72752) y el "resumen diario" (72753).
5. [ ] **Registrar el callback** en Tencent (Pendientes 1).
6. [ ] **Elegir quién recibe los resúmenes** (Pendientes 2).

## 13. Baja de run.app (2026-10-19, 13:04–13:45)

**Resultado: la URL de Cloud Run quedó APAGADA.** El sistema se usa solo por https://pricing.xpress.ec. La dirección `https://xps-pricing-809824844407.us-central1.run.app` (dato histórico) responde 404 de Google. Siguen funcionando: boletines, avisos, callback de Tencent, login, PDF y baja pública.

### 13.1 Inventario de usos de run.app

| Dónde | Qué había | Qué se hizo |
|---|---|---|
| Cloud Scheduler `xps-boletines-lote` y `xps-notificaciones-evaluar` | llamaban a la URL run.app | **cambiados** a `https://pricing.xpress.ec/internal/...` |
| Callback de Tencent | ya registrado a nivel de cuenta con pricing.xpress.ec | nada que cambiar (verificado en logs) |
| Base: `config_sistema.url_publica` | ya era https://pricing.xpress.ec | nada |
| Base: `auditoria` (5 y 4 filas) | la URL vieja en el historial de cambios | se deja: es historial |
| Migraciones 0008 y 0011 | la URL como valor inicial | se dejan: ya aplicadas (historial) |
| `docs/DESPLIEGUE.md` y `docs/extensiones/E4-DOMINIO.md` | la URL run.app como dirección del sistema | **actualizados** (solo pricing.xpress.ec; "Volver atrás" nuevo) |
| Código (`app/`, `frontend/`), `scripts/`, plantillas | ninguna URL run.app | prueba TRA-07 que lo vigila |
| Secret Manager | solo nombres revisados: ninguno es una URL | nada |
| Otros jobs (`prender-db-reborn`, `apagar-db-reborn`) | no son de este sistema | **no se tocaron** |

### 13.2 Cloud Scheduler: antes → después

| Job | Antes | Después |
|---|---|---|
| `xps-boletines-lote` (`* 7-19 * * 1-5`, America/Guayaquil, POST, `X-Tarea-Secreto`) | `https://xps-pricing-809824844407.us-central1.run.app/internal/boletines/procesar-lote` | `https://pricing.xpress.ec/internal/boletines/procesar-lote` |
| `xps-notificaciones-evaluar` (`5 7-19 * * 1-5`, America/Guayaquil, POST, `X-Tarea-Secreto`) | `https://xps-pricing-809824844407.us-central1.run.app/internal/notificaciones/evaluar` | `https://pricing.xpress.ec/internal/notificaciones/evaluar` |

- **Qué cambió:** solo la URI (`gcloud scheduler jobs update http --uri`). La cabecera secreta, el horario, la zona horaria, el método y el cuerpo se conservaron. La configuración anterior se guardó, con el secreto tapado.
- **Ejecutados a mano a las 13:11:** los dos respondieron 200 por pricing.xpress.ec.
- **Después:** el lote respondió 200 cada minuto (13:12–13:17, y siguió así), también tras desplegar y después de apagar run.app (evaluar: 13:35 y 13:40; lote: cada minuto).

### 13.3 Callback de Tencent

- Desde las 09:49 **no llegó ningún evento por run.app**. Todos llegaron por pricing.xpress.ec:
  - 3 con 200 (09:58–09:59);
  - 2 con 503 durante la caída por los secretos (11:24 y 11:42), que se perdieron;
  - 1 GET con 405 a las 09:49, la comprobación de Tencent al registrar el callback.
- **Prueba:** "Enviarme una prueba" del boletín, solo a francois-ramart@outlook.com (0 pruebas en la hora anterior). El evento `delivered` llegó a las 13:33:50 por pricing.xpress.ec con 200 y quedó **vinculado al envío** (origen PRUEBA).
- **Para eso se agregó la migración 0013:** los eventos de "Enviarme una prueba" se vinculan a su envío; antes quedaban "sin vincular".
- **Defecto corregido de E1-B:** el indicador "evento nuevo" usaba `rowcount`, que con psycopg 3 vale -1; nunca marcaba un evento como nuevo. Ahora usa `RETURNING`.

### 13.4 Redirección en la aplicación (red de seguridad)

Un middleware nuevo actúa en las peticiones que llegan con un host terminado en `.run.app`. Hoy no llega ninguna, porque la URL está apagada; sirve por si se reactiva.
- **GET y HEAD:** 301 a la misma ruta y query en la URL pública del sistema (sale de la base, nunca fija en el código).
- **POST, PUT, PATCH y DELETE:** 410 con "Esta dirección ya no se usa. Use https://pricing.xpress.ec".
- **Sin cambios:** `/internal/*` y `/v1/salud`. pricing.xpress.ec tampoco cambia.
- **Si la URL pública también fuera run.app,** no redirige, para evitar un bucle.
- **Pruebas:** `tests/test_baja_run_app.py` (TRA-01 a TRA-07). TE4-01 ahora busca URLs `https://….run.app` y no el sufijo, porque el middleware lo menciona.
- **Verificado en producción antes de apagar:**
  - run.app `/app/login.html?x=1` → 301 a `https://pricing.xpress.ec/app/login.html?x=1`;
  - POST → 410;
  - `/v1/salud` → 200.

### 13.5 Apagado de la URL por defecto

- **Fuente:** documentación oficial de Cloud Run ("Disabling the default URL", en Restrict endpoint ingress). Comando GA: `gcloud run services update xps-pricing --no-default-url`; para revertir, `--default-url`.
- **Compatibilidad:** sigue entrando el tráfico del domain mapping; la URL propia es independiente.
- **Advertencia de la documentación:** Cloud Scheduler y otros servicios fallan si llaman a run.app. Aquí ya no lo hacían.
- **Apagada a las 13:35.** La revisión `xps-pricing-00013-gqs` siguió igual, con los 5 secretos. La "Service URL" quedó en `None`.
- **Verificación inmediata: 21 de 21 OK.**
  - pricing.xpress.ec: salud, login, COT-2026-00001 con su PDF (373.739 bytes), Boletines, Clientes (importación y exportación), Notificaciones y páginas;
  - baja pública (307 a la página de baja);
  - jobs con 200;
  - run.app → 404.
- **El comando de despliegue** de `docs/DESPLIEGUE.md` lleva ahora `--no-default-url`, para que un despliegue futuro no la vuelva a encender.

### 13.6 Respaldo, revisión, pruebas y commits

| Dato | Valor |
|---|---|
| Respaldo | **1792434396240** (SUCCESSFUL, antes de migrar a 0013 y desplegar) |
| Migración | `0013_eventos_prueba` (0012 → 0013), probada ida y vuelta en local |
| Secretos | comparados antes de desplegar: los mismos 5 en la revisión vigente y en el comando |
| Revisión | **xps-pricing-00013-gqs** (al 100 %; 0 errores en sus logs) |
| Prueba de oro | COT-2026-00001: fila, líneas y HTML del PDF **idénticos** antes y después |
| Pruebas | Regla 18 doble: **829 passed** + **829 passed** |
| Commits | el de esta baja (código, migración 0013, pruebas, guía, plan de E4 y esta acta) |

### 13.7 Volver atrás

1. **Reactivar la URL por defecto:** `gcloud run services update xps-pricing --region us-central1 --default-url`. No cambia los secretos.
2. **Jobs a la URL anterior** (solo con la URL reactivada):
   ```powershell
   gcloud scheduler jobs update http xps-boletines-lote --location us-central1 --uri="https://xps-pricing-809824844407.us-central1.run.app/internal/boletines/procesar-lote"
   gcloud scheduler jobs update http xps-notificaciones-evaluar --location us-central1 --uri="https://xps-pricing-809824844407.us-central1.run.app/internal/notificaciones/evaluar"
   ```
3. **Revisión anterior:** `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=xps-pricing-00012-rks=100` (tiene los 5 secretos). La 0013 es compatible con ese código.
4. **Migración:** `alembic downgrade 0012`. Los eventos de pruebas quedan como "sin vincular".

### 13.8 Pendientes del gerente

- **Ninguno bloqueante.** No quedó ningún comando bloqueado.
- **Enlaces viejos:** los boletines de prueba de E1, enviados antes de las 09:31, tienen el enlace de baja con run.app, que ya no abre. Solo se enviaron al administrador.

# Acta de cierre · E1-B · Perfil comercial, importación de clientes e historial de correos

| Dato | Valor |
|---|---|
| Decisor | François Ramírez |
| Ejecutor | Claude Code (sesión autónoma del 2026-10-19) |
| Fecha de cierre | 2026-10-19 |
| Alcance | E1-B (perfil comercial + importación alineada con Tencent) y 6-B (historial de correos y columnas visibles) |
| Migración | `0012_e1b_perfil_comercial` (0011 → 0012), probada ida y vuelta en local |
| Respaldos | **1792425740361** (antes de migrar) · **1792427594017** (antes del segundo despliegue) |
| Producción | https://pricing.xpress.ec · revisión **xps-pricing-00012-rks** (la 00011 con los 5 secretos restaurados por el gerente: ver 8.1) |
| Pruebas | 818 (34 nuevas de E1-B); Regla 18 doble en verde |

## 1. Resumen en cristiano

Cada cliente tiene ahora un **perfil comercial**: tipo de cliente, estado comercial, sector, servicios y rutas de interés, tipos de carga, volumen, frecuencia, cómo llegó, etiquetas y su consentimiento para recibir promociones.

- **Importar desde Excel:** se cargan clientes y contactos con la plantilla oficial. El sistema muestra antes qué va a crear, qué va a actualizar y qué filas tienen error (fila y columna). Nunca borra nada.
- **Boletines con consentimiento:** solo salen a contactos que reciben promociones, de clientes que aceptan promociones. El paso 3 de la campaña muestra cuántos se omiten por eso.
- **Nombre y comercial correctos:** "Estimado/a {{nombre_contacto}}:" usa el nombre del contacto. {{comercial}} es el comercial asignado al cliente, no quien envía.
- **Listas por filtro** sobre todo el perfil, combinando condiciones con Y u O, incluido el interés calculado ("cotizó FCL en los últimos 6 meses").
- **Ficha del cliente** con 3 pestañas: Datos, Perfil comercial (con lo que el cliente cotizó) y Correos (todo lo que se le envió y si llegó, se abrió o rebotó).
- **Lista de clientes** con filtros nuevos, columnas a elección de cada usuario y "Exportar a Excel" en el formato de la plantilla.

Los 3 clientes que ya existían quedaron intactos, con "acepta promociones = SÍ" por relación comercial previa.

## 2. Dónde está cada botón

| Qué | Dónde |
|---|---|
| Importar clientes | Comercial → **Clientes** → botón **Importar desde Excel** (arriba a la derecha). Dentro: **Descargar plantilla (.xlsx)** y **Descargar CSV de ejemplo** |
| Exportar clientes | Comercial → **Clientes** → **Exportar a Excel** (respeta los filtros que estén puestos) |
| Filtros nuevos | Comercial → **Clientes**: estado comercial, tipo de cliente, sector, servicio de interés, ruta de interés, etiqueta y acepta promociones |
| Columnas | Comercial → **Clientes** → **Columnas** (debajo de los filtros). Se guardan por usuario |
| Perfil comercial | Comercial → **Clientes** → **Ficha** → pestaña **Perfil comercial** |
| Historial de correos | Comercial → **Clientes** → **Ficha** → pestaña **Correos** → **Ver correo** / **Origen** |
| Área y casillas del contacto | Comercial → **Clientes** → **Contactos**: área, "Recibe promociones" y "Recibe cotizaciones" |
| Importar a una lista | Boletines → **Listas de envío** → lista manual → **Importar clientes (plantilla oficial)**. Pegar correos queda para contactos que ya existen |
| Lista por perfil | Boletines → **Listas de envío** → tipo **Por filtro** → **Perfil comercial e interés calculado** → **Agregar condición** → **Ver vista previa** |
| Omitidos por consentimiento | Boletines → **Campañas** → paso 3 (destinatarios) |
| Entregados, abiertos y clics | Boletines → **Campañas** → detalle de una campaña enviada |
| Catálogos del perfil | Administración → **Catálogos del perfil** (solo el administrador) |

## 3. Avance

| Parte | Estado |
|---|---|
| Plantilla oficial (columnas exactas, listas desplegables generadas con los catálogos vigentes, CSV de ejemplo) | Hecho |
| Modelo: perfil en cliente y contacto, catálogos con auditoría, estados comerciales fijos, interés calculado | Hecho |
| Alineación con Tencent: {{nombre_contacto}}, {{comercial}}, consentimiento en boletines y avisos, omitidos en el paso 3 | Hecho |
| Importación: vista previa, solo crear / crear y actualizar, reporte, validaciones, auditoría, máximo de filas | Hecho |
| Pantallas: ficha con perfil, contactos, Ecuador por defecto, filtros, listas por condiciones Y/O | Hecho |
| 6-B: pestaña Correos, eventos de Tencent por MessageId, contadores de campaña, columnas por usuario, exportar | Hecho |
| Pruebas, Regla 18 doble, producción y esta acta | Hecho |
| **Total E1-B** | **100 %** |

## 4. Lo construido

### 4.1 Datos (migración 0012)

- **cliente:** nombre_comercial, tipo_cliente, estado_comercial (ACTIVO por defecto), sector, servicios_interes, rutas_interes, tipos_carga y etiquetas (listas), volumen_estimado, frecuencia, origen_cliente, acepta_promociones, fecha_consentimiento y medio_consentimiento.
- **contacto_cliente:** area y recibe_promociones. "Recibe cotizaciones" es la columna recibir_avisos que ya existía (E3): no se duplicó.
- **catalogo_perfil:** los valores de las listas, sembrados con la hoja Catalogos de la plantilla. Los estados comerciales son fijos.
- **tencent_evento:** cada evento del callback, una sola vez por (MessageId, evento), vinculado a su envío.
- **preferencia_pantalla:** las columnas elegidas por cada usuario.
- **config_sistema.importacion_max_filas:** 2.000 por defecto (de 1 a 20.000).
- **Clientes existentes:** acepta_promociones = SÍ, medio RELACION_COMERCIAL_PREVIA, estado ACTIVO; sus contactos reciben promociones.

### 4.2 Plantilla e importación

- La plantilla oficial vive en `docs/extensiones/importacion/` (xlsx y csv, copia exacta de la que entregó el gerente en `docs/templates/`).
- "Descargar plantilla" la genera en el momento: misma estructura, con la hoja Catalogos al día y las listas desplegables ajustadas a los valores vigentes.
- **Hojas del Excel:** Clientes (23 columnas) y Contactos (9).
- **CSV:** una fila por contacto con prefijo `contacto_`, separador ; o , (se detecta solo) y UTF-8 con o sin BOM.
- **Booleanos:** SI/NO, Sí/No, TRUE/FALSE y 1/0.
- **Validaciones:**
  - tipo de identificación del catálogo de E2, con su formato;
  - correo válido y país activo (ISO de 2 letras);
  - comercial activo que pueda cotizar (un comercial solo importa clientes suyos);
  - valores de los catálogos y rutas "Origen>Destino" con países o puertos existentes;
  - un solo contacto principal por cliente;
  - repetidos dentro del archivo y contra la base.
- **Se ignoran solas:** la fila de descripción ("OBLIGATORIO · …") y las filas de ejemplo de la plantilla.
- **Sin cambios no es error:** una celda opcional vacía nunca borra lo guardado; los textos se comparan sin espacios de más.
- **Auditoría:** cada cliente y contacto creado o actualizado, y la importación (quién, archivo, modo, totales).
- **Sin dependencias nuevas de subida:** el archivo viaja en base64 en la vista previa y en la confirmación. Se agregó openpyxl 3.1.5 (leer y escribir .xlsx con listas desplegables; la alternativa, pandas, es mucho más pesada).

### 4.3 Alineación con Tencent

- **{{nombre_contacto}}:** el nombre del contacto; "cliente" si estuviera vacío.
- **{{comercial}}:** el comercial asignado al cliente del destinatario; si no tiene, quien envía. Aplica al boletín (72746), a la tarifa de interés (72751) y a los avisos de cotización (72747–72750).
- **Consentimiento:**
  - boletines y tarifa de interés: solo si el cliente acepta promociones Y el contacto recibe promociones;
  - avisos de cotización: solo si el contacto recibe cotizaciones.
- **"Enviarme una prueba"** muestra el correo como lo verá el primer destinatario (su nombre y su comercial), y la pantalla dice cuál.

### 4.4 Historial de correos (6-B)

- **Pestaña Correos:** une las 3 bitácoras (cotizaciones, boletines y avisos), con fecha, contacto, tipo, asunto, plantilla, estado de envío y estado de entrega, filtros por tipo y estado, y "Ver correo" con las variables reales enviadas y el enlace al origen.
- **Eventos del callback:** se guardan por MessageId. Los que no tienen envío quedan "sin vincular" (Notificaciones → Bitácora los lista por API).
- **Prioridad del estado de entrega:** baja > spam > rebote definitivo > clic > abierto > entregado > rebote temporal.
- **Campañas:** contadores de entregados, abiertos y clics.

## 5. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18, ciclo 1 (base de pruebas recreada), código final de la app | **818 passed** |
| Regla 18, ciclo 2 | **818 passed** |
| Después de agregar la prueba de los secretos de la guía (solo cambia una prueba y la guía) | test_e1b_perfil: 34 passed |
| Migración 0012 ida y vuelta (local) | 0012 → 0011 → 0012 sin errores |
| Humo en Chromium, escritorio (1366) y móvil (390): Clientes (importar, filtrar, columnas, ficha), Listas (condiciones), Catálogos del perfil, Campaña | **0 errores** de consola, de página y de API; sin desborde horizontal |

`tests/test_e1b_perfil.py` (TE1B-01 a TE1B-24) cubre:
- clientes existentes intactos y catálogos sembrados;
- permisos (admin, comercial, pricing, gerencia);
- CRUD de catálogos con auditoría y estados fijos;
- plantilla descargada igual a la oficial, y que viaja en la imagen;
- importación .xlsx y .csv (con ; y , y sin BOM);
- errores por fila y columna, duplicados, solo crear frente a crear y actualizar, filas de ejemplo, límite de filas y archivos inválidos;
- alcance del comercial e importación a una lista;
- filtros combinados de la lista de clientes e interés calculado con listas Y/O;
- consentimiento;
- {{nombre_contacto}} y {{comercial}} sin variables vacías (salvo filas de tarifas sin uso);
- historial de los 3 tipos con eventos que cambian el estado, eventos sin vincular y contadores;
- alcance del historial y columnas guardadas por usuario;
- exportar → importar con **0 cambios**;
- páginas sin estilos en línea ni innerHTML.

## 6. Producción

| Paso | Resultado |
|---|---|
| Respaldo | 1792425740361, SUCCESSFUL |
| Prueba de oro, antes de migrar | COT-2026-00001: huella de la fila, de sus líneas y del HTML del PDF. El código del PDF no cambió en E1-B (`git diff` vacío contra 265f0a3) |
| Migración | `xps_pricing` 0011 → **0012** |
| Prueba de oro, después de migrar | COT-2026-00001 **idéntica** (fila, líneas y PDF). Los 3 clientes y 3 contactos: datos de F2 **idénticos**; los 3 con acepta promociones, medio RELACION_COMERCIAL_PREVIA y estado ACTIVO; los 3 contactos reciben promociones |
| Primer despliegue | **Falló el build:** `.dockerignore` excluía `docs/` y la plantilla no entraba a la imagen. Producción siguió en la 00009, sana (la 0012 es compatible con el código anterior) |
| Despliegue | `xps-pricing-00010-pd7`, luego **`xps-pricing-00011-j9g`** (vista previa corregida, ver abajo), al 100 %. `/v1/salud` → `{"estado":"ok","bd":"ok"}`; 0 errores en los logs de la aplicación |
| **Secretos** | ⚠ **Error mío:** desplegué con el comando de `docs/DESPLIEGUE.md`, que solo tenía 3 secretos, y `--set-secrets` reemplaza la lista. Las revisiones 00010 y 00011 no tenían `TAREAS_SECRETO` ni `TENCENT_EVENTOS_TOKEN`: `procesar-lote` respondió 503 de **11:21 a 12:36**, un evento del callback (11:24) y la evaluación de avisos de las 12:05 recibieron 503. **No se envió nada indebido**: solo se detuvo el trabajo programado. **Resuelto** por el gerente a las 12:35 (revisión 00012): ver 8.1. La guía ya lleva los 5 secretos y una prueba lo vigila |
| Plantilla en pricing.xpress.ec | xlsx: hojas y columnas **iguales a la oficial**, 9 listas desplegables. CSV: encabezado oficial |
| Importación por la pantalla (archivo PRUEBA) | 2 clientes ficticios ("PRUEBA E1B IMPORTADORA UNO/DOS"), contactos Ana Prueba y Luis Prueba, **solo con francois-ramart@outlook.com**: 2 creados, 2 contactos creados, 0 errores |
| Lista por filtro tipo_cliente = IMPORTADOR | 2 contactos, los dos francois-ramart@outlook.com (1 recibiría: el mismo correo cuenta una vez). El script tenía un freno: si aparecía otro correo, no se enviaba nada |
| "Enviarme una prueba" (72746) | Enviada **solo a francois-ramart@outlook.com**, ENVIADO con MessageId. Pantalla: "como la verá **Ana Prueba** (comercial: **Prueba comercial**)". En el correo: "**Estimado/a Ana Prueba:**" y "Su asesor comercial: **Prueba comercial**", el comercial asignado; quien envió fue el administrador de prueba. La campaña **nunca se envió** |
| Hallazgo corregido en producción | En la 00010, la vista previa del paso 4 decía "Nombre del contacto" y el comercial de quien envía, aunque el correo salía bien. Ahora la vista previa usa al primer destinatario, igual que la prueba (00011, verificado con una segunda prueba al administrador) |
| Limpieza | Borradores borrados; tarifas temporales, listas y **los 10 clientes PRUEBA desactivados** (5 corridas del script: 3 fallaron antes de enviar, por errores del propio script); usuarios de prueba desactivados. 0 destinatarios de campaña con contactos PRUEBA |
| Capturas | En la carpeta de la sesión: `prod_e1b_1_vista_previa.png`, `prod_e1b_2_importacion.png`, `prod_e1b_3a_paso3.png`, `prod_e1b_3_prueba_boletin.png`, `prod_e1b_4_perfil.png` |
| Instancia | Encendida (ALWAYS) dentro del horario; la apaga el horario de las 20:00. Proxy detenido al terminar |
| Vuelta atrás, si hiciera falta | `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=xps-pricing-00009-cmx=100` (la 00009 y la 00012 tienen los 5 secretos) y `alembic downgrade 0011` |

## 7. Decisiones tomadas

1. **Clientes existentes:** acepta_promociones = SÍ, medio de consentimiento RELACION_COMERCIAL_PREVIA y estado ACTIVO. Sus contactos reciben promociones. Así los boletines siguen llegando a quienes ya los recibían.
2. **"Recibe cotizaciones" = recibir_avisos** (la casilla de avisos de E3), para no tener dos casillas con el mismo sentido.
3. **Interés calculado:** cuenta cotizaciones emitidas o posteriores (no borradores), en los últimos N meses (6 por defecto). Las rutas se comparan por país (CN>EC) o por puerto (CNSHA>ECGYE).
4. **Volumen:** en la plantilla y en la exportación va el nombre largo ("MEDIO (1 a 5 TON…)"); la base guarda el código (MEDIO). Se aceptan los dos.
5. **Etiquetas en mayúsculas,** para que "vip" y "VIP" sean la misma.
6. **Un archivo sin "principal"** nunca le quita el principal a un contacto que ya lo es.
7. **Contactos se identifican por correo dentro del cliente:** el mismo correo en dos clientes son dos contactos (así se hizo la prueba en producción).
8. **Catálogos:** el código no cambia una vez creado (lo guardan los clientes); desactivar un valor lo saca de las listas nuevas sin tocar a quien ya lo tiene.
9. **Diálogos anchos:** `.dialogo-ancho` estaba antes de `.dialogo` en el CSS y no se aplicaba en ninguna pantalla. Se corrigió la especificidad: los diálogos que lo usan (tarifas, recargos, roles, servicios, plantillas, notificaciones, listas) ahora sí miden hasta 760 px; la ficha del cliente, hasta 1.040 px.
10. **La plantilla viaja en la imagen:** `.gcloudignore` excluía `docs/` y el Dockerfile no la copiaba. Se agregó solo `docs/extensiones/importacion/`, con una prueba que lo vigila.

## 8. Pendientes del gerente

### 8.1 Secretos de Cloud Run: RESUELTO

El gerente devolvió los 2 secretos con una sola línea, sin reconstruir la imagen:

```
gcloud run services update xps-pricing --project xps-reborn-v2 --region us-central1 --update-secrets=TAREAS_SECRETO=xps-pricing-tareas-secreto:latest,TENCENT_EVENTOS_TOKEN=xps-pricing-tencent-eventos-token:latest
```

Se creó la revisión **xps-pricing-00012-rks**, con los 5 secretos y el 100 % del tráfico.

**Tiempo caído, según los registros de Cloud Run (hora Ecuador):**

| Momento | Hora |
|---|---|
| Último 200 de `procesar-lote` (revisión 00009) | 11:20 |
| Primer 503 (revisión 00010) | 11:21 |
| Evaluación de avisos con 503 (revisión 00011) | 12:05 (la siguiente, a las 13:05) |
| Revisión 00012 creada | 12:35 |
| Último 503 | 12:36 |
| Primer 200 (revisión 00012) | 12:37 (17:37 UTC) |

Fueron **unos 76 minutos** sin lote de boletines. Además se perdieron:
- una corrida horaria de la evaluación de avisos (la siguiente la cubrió);
- un evento del callback de Tencent (11:24).

La nota del gerente decía de 11:13 a 12:56 (17:56 UTC):
- las 11:13 fueron el inicio del despliegue: el servicio se cortó recién cuando la 00010 tomó el tráfico, a las 11:21;
- a las 17:56 UTC ya respondía 200: el primero fue a las 17:37 UTC.

**Regla desde ahora:**
- antes de cualquier despliegue, comparar los secretos de la revisión vigente (`gcloud run services describe xps-pricing --region us-central1`) con los del comando;
- al desplegar, usar **siempre los 5 secretos**: `DATABASE_URL`, `JWT_SECRET`, `CONFIG_CIFRADO_KEY`, `TAREAS_SECRETO` y `TENCENT_EVENTOS_TOKEN`.

`docs/DESPLIEGUE.md` ya los trae, y `tests/test_e1b_perfil.py` falla si el comando de la guía pierde alguno.

### 8.2 Otros

1. **Revisar en el correo** (francois-ramart@outlook.com) las 2 pruebas "[PRUEBA] [PRUEBA] Boletín E1-B": "Estimado/a Ana Prueba:" y el comercial "Prueba comercial".
2. **Callback de Tencent:** sigue pendiente de E4 registrarlo en la consola. Con eso se llenan "Entregados, abiertos y clics" y el estado de entrega de la pestaña Correos.
3. **Perfil de los clientes reales:** quedaron sin tipo, sector ni intereses. Se completan en la ficha o exportando a Excel, llenando y volviendo a importar con "crear y actualizar".

## 9. Checklist del gerente (navegador)

1. [ ] **Plantilla:** Clientes → Importar desde Excel → **Descargar plantilla (.xlsx)**. Abrirla: hojas Instrucciones, Clientes, Contactos y Catalogos; las listas desplegables funcionan.
2. [ ] **Importar:** llenar 1 o 2 clientes de prueba (contactos con su propio correo), subir el archivo y pulsar **Revisar archivo**. La vista previa muestra nuevos, a actualizar y errores. **Confirmar importación** y **Descargar reporte (CSV)**.
3. [ ] **Error a propósito:** poner un país "ZZ" en una fila y revisar: la fila sale con error en la columna pais y no se importa.
4. [ ] **Ficha:** abrir la Ficha del cliente → **Perfil comercial**. Revisar los datos y "Lo que cotizó".
5. [ ] **Correos:** pestaña **Correos** de un cliente que ya recibió cotizaciones o boletines. **Ver correo** muestra el correo y las variables enviadas.
6. [ ] **Columnas:** en Clientes → **Columnas**, marcar "Sector" y "Último envío". Salir y volver: siguen marcadas.
7. [ ] **Filtros:** Tipo de cliente = Importador y Acepta promociones = Sí.
8. [ ] **Exportar:** **Exportar a Excel** y volver a importar ese mismo archivo: la vista previa dice **0 cambios**.
9. [ ] **Lista por perfil:** Boletines → Listas de envío → Nueva → Por filtro → Agregar condición "Tipo de cliente = Importador" → Ver vista previa.
10. [ ] **Interés calculado:** en otra lista, condición "Cotizó el servicio = Marítimo FCL" (6 meses) → Ver vista previa.
11. [ ] **Consentimiento:** en un contacto, desmarcar "Recibe promociones". En una campaña con su lista, el paso 3 muestra "omitidos por consentimiento: 1".
12. [ ] **Prueba del boletín:** en una campaña, **Enviarme una prueba**. El aviso dice cómo la verá el primer destinatario y su comercial; en el correo, "Estimado/a <nombre>:" y el comercial asignado.
13. [ ] **Catálogos:** Administración → **Catálogos del perfil** → Sectores → **Nuevo valor**. Aparece en la plantilla que se descargue después.

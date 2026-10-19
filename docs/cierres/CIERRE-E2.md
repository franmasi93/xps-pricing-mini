# Acta de cierre · E2 · Catálogos de administración

| Dato | Valor |
|---|---|
| Extensión | E2 (15 % de las extensiones E0–E3) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code (sesión autónoma del 2026-10-19) |
| Fecha de cierre | 2026-10-19 |
| Commits | `503e27d` (E2.0–E2.3) · `4199fa2` (joins explícitos en los scripts) · esta acta |
| Migración | `0009_e2_catalogos_admin` (0008 → 0009) |
| Respaldo de producción | **1792391729204** (justo antes de migrar a 0009) |
| Producción | https://xps-pricing-809824844407.us-central1.run.app · revisión **xps-pricing-00005-wxt** |
| Plan | `docs/extensiones/E2-PLAN.md` |

## 1. Resumen en cristiano

Lo que antes estaba fijo en el código ahora lo edita el administrador por pantalla, con auditoría:

- **Roles y permisos.** Puede crear roles (por ejemplo, "Operaciones") y elegir qué permisos tiene cada uno, con la descripción de cada permiso. También puede cambiar nombre, descripción y estado. La matriz completa se ve en una tabla.
  - Cuando cambian los permisos de un rol, sus usuarios deben volver a entrar.
  - El rol Administrador está protegido: no se desactiva ni pierde "Administrar usuarios".
- **Motivos de rechazo.** Se agregan motivos nuevos y se marca cuáles exigen detalle. "Otro" siempre lo exige.
- **Tipos de identificación.** Se agregan tipos (por ejemplo, NIT) con su regla de validación y el formato que se muestra si el número no cumple.
- **Textos del PDF.** La frase de aceptación, las líneas de fecha, firma y sello, y las advertencias DDP y EXW se editan en Configuración. Se congelan al emitir: un PDF emitido no cambia.

No cambió ningún dato: todo se sembró con el texto y las reglas exactas que había.

## 2. Avance por fase

| Fase | Peso | Estado |
|---|---|---|
| E2.0 Base | 2 % | Hecho: inventario, plan y migración 0009 probada ida y vuelta (el esquema 0008 queda idéntico, byte por byte) |
| E2.1 Roles y matriz | 6 % | Hecho: CRUD, protecciones, invalidación por token_version, pantalla y matriz |
| E2.2 Motivos y tipos de identificación | 4 % | Hecho: catálogos con FK en vez de CHECK; selectores de cotización y clientes desde el catálogo |
| E2.3 Textos del PDF y cierre | 3 % | Hecho: config_textos_pdf, prueba de oro, Regla 18 doble, despliegue y esta acta |
| **Total E2** | **15 %** | **15 %** |

## 3. Lo construido

### 3.1 Datos (0009)

| Tabla | Cambio |
|---|---|
| `rol` | Agrega `descripcion`, `protegido` (solo admin), `activo` y las columnas de trazabilidad. CHECK del código y "protegido ⇒ activo" |
| `motivo_rechazo` (nueva) | codigo, nombre, exige_detalle y orden. Siembra: PRECIO, TIEMPO, COMPETENCIA y OTRO (este último exige detalle, con CHECK) |
| `cotizacion.motivo_rechazo` | Pasa de CHECK a FK al catálogo, de 11 a 30 caracteres. `ck_cotizacion_detalle_si_otro` no cambia |
| `tipo_identificacion` (nueva) | codigo, nombre, regex, formato y orden. Siembra: los 4 de F2, con su regex y formato idénticos |
| `cliente.tipo_id` | Pasa de CHECK a FK. El CHECK del formato por tipo se retira: la regla la aplica el service con el regex del catálogo |
| `config_textos_pdf` (nueva, una fila) | aceptacion_titulo, aceptacion_texto, firma_fecha, firma_firma, firma_sello, advertencia_ddp y advertencia_exw, con el texto idéntico |

El downgrade restaura los CHECK de F2 y F3. No se ejecuta si ya hay datos que usan lo nuevo (motivos o tipos nuevos en uso, o roles creados) y explica cuáles.

### 3.2 Reglas

- **Sin permisos nuevos:**
  - roles: `usuario.admin`;
  - catálogos y textos: `config.editar`.
  
  La matriz §6.2 queda igual (T40, T136, T138 y T208 no cambian).
- **Roles:**
  - el código no cambia;
  - el rol protegido no se desactiva ni pierde `usuario.admin`;
  - un rol con usuarios activos no se desactiva;
  - un rol inactivo no se asigna (`ROL_INACTIVO`).
- **Sesiones:** cambiar los permisos de un rol, o desactivarlo, sube `token_version` de sus usuarios. Quien hace el cambio no queda fuera: recarga su menú.
- **Motivos y tipos:**
  - el código no cambia, porque lo guardan las cotizaciones y los clientes;
  - desactivar los saca de las listas nuevas sin tocar lo guardado;
  - con un motivo inválido el error es `MOTIVO_RECHAZO_INVALIDO`, y con un tipo inválido, `TIPO_IDENTIFICACION_INVALIDO`.
- **Clientes:**
  - el mensaje de error es el mismo de F2: "La identificación X debe tener …";
  - al editar otros datos de un cliente no se revalida su identificación, así un cliente guardado no se traba si después cambió la regla.
- **PDF:** al emitir se copian los textos a la foto. Una cotización emitida antes de E2 no los trae y se dibuja con los de siempre.

### 3.3 Endpoints

- **Roles** (`usuario.admin`): `GET/POST /v1/roles`, `PATCH /v1/roles/{id}` y `GET /v1/roles/permisos`.
- **Motivos de rechazo:** `GET` para cualquier usuario habilitado; `POST` y `PATCH /{id}` con `config.editar`, en `/v1/motivos-rechazo`.
- **Tipos de identificación:** lo mismo, en `/v1/tipos-identificacion`.
- **Textos del PDF** (`config.editar`): `GET/PUT /v1/textos-pdf`.

### 3.4 Pantallas (Administración)

- **Roles y permisos:** lista de roles con usuarios activos y la matriz agrupada por módulo, más un diálogo para crear y editar con la lista de permisos.
- **Motivos de rechazo** y **Tipos de identificación.**
- **Configuración → Textos del PDF y advertencias.**
- **Selectores desde el catálogo:**
  - el motivo, en "Marcar como rechazada";
  - el tipo de identificación, en clientes;
  - los roles activos, en usuarios.

## 4. Pruebas

| Corrida | Resultado |
|---|---|
| Regla 18 · ciclo 1 (PostgreSQL 18.6 local, base virgen 0001→0009) | **738 passed** (2 min 41 s) |
| Regla 18 · ciclo 2 (local, base virgen) | **738 passed** (2 min 31 s) |
| Ida y vuelta de 0009 | Foto del esquema 0008 antes y después del downgrade: idéntica |
| Humo en Chromium | Roles (crear rol; usuario.admin bloqueado en el admin), motivos (crear), tipos, configuración, clientes y usuarios: sin errores |
| Integración contra `xps_pricing_test` en Cloud SQL | En la corrida final consolidada de la sesión |

**Pruebas nuevas:** `tests/test_e2_catalogos.py`, TE2-01 a TE2-17. Cubren:
- **Siembra:** idéntica a lo que estaba fijo; E2 no agrega permisos.
- **Permisos de las pantallas:** solo el administrador edita; las listas las lee cualquiera.
- **Roles:**
  - crear y asignar un rol;
  - cambiar permisos invalida sesiones, salvo la de quien hace el cambio;
  - el administrador está protegido;
  - no se desactiva un rol con usuarios y no se asigna un rol inactivo;
  - la matriz §6.2 sigue intacta en la API.
- **Motivos de rechazo:** un motivo nuevo con detalle obligatorio en un rechazo real; "Otro" protegido.
- **Tipos de identificación:** un tipo nuevo con su regla; un cliente guardado no se traba; el código no cambia.
- **Textos del PDF:** la advertencia DDP editada aparece en `NADA_QUE_COTIZAR`; los textos se congelan al emitir; una emitida antes de E2 sale idéntica.
- **Páginas:** sin estilos en línea ni innerHTML.

## 5. Producción

| Paso | Resultado |
|---|---|
| Prueba de oro del PDF, antes de migrar | El HTML del PDF de la cotización emitida de producción (COT-2026-00001), dibujado con el código anterior (fb7a4cc) y con el de E2: **idéntico** |
| Respaldo | 1792391729204, SUCCESSFUL |
| Migración | `xps_pricing` 0008 → **0009** |
| Prueba de oro de E0, repetida | 4 cotizaciones, 8 líneas y 4 HTML de PDF: **0 diferencias** |
| Despliegue | `xps-pricing-00005-wxt`, al 100 %; logs sin errores |
| **Verificación (solo lectura; usuarios de prueba de F5 reactivados y desactivados al final)** | **15 de 15 OK**. Detalle abajo |
| Vuelta atrás, si hiciera falta | `gcloud run services update-traffic xps-pricing --region us-central1 --to-revisions=xps-pricing-00004-6qp=100` y `alembic downgrade 0008` |

**Qué cubrió la verificación**
- Salud.
- Los 4 roles, con su descripción, y el admin protegido.
- 20 permisos; el comercial no ve roles.
- Los 4 motivos y los 4 tipos.
- Textos del PDF idénticos.
- Quitar `usuario.admin` al admin da 409 (sin cambios).
- Las 6 páginas cargan.
- El PDF de COT-2026-00001 se genera.

**Durante la migración:** el script de oro de E0 tenía un `join(Rol)` sin condición, que se volvió ambiguo porque `rol.creado_por` agrega una segunda FK entre usuario y rol. Se corrigió en los scripts (commit 4199fa2). El código de la aplicación ya usaba joins explícitos.

## 6. Decisiones tomadas

1. **Sin permisos nuevos:** roles con `usuario.admin` y catálogos y textos con `config.editar`, el mismo de los datos de la empresa. Así no cambian los conteos de la matriz §6.2, que la suite verifica.
2. **Los códigos de permiso no se crean por pantalla:** cada permiso lo exige el código del sistema. Un permiso que nadie revisa no serviría.
3. **El código de roles, motivos y tipos no se edita:** lo guardan los usuarios, las cotizaciones y los clientes. Para cambiarlo, se crea otro y se desactiva el viejo.
4. **Invalidación de sesiones:** al cambiar permisos o desactivar un rol, menos para quien hace el cambio, para que el administrador no se saque a sí mismo. Los permisos ya se leían de la base en cada pedido; la invalidación hace que el menú del usuario se rearme.
5. **Textos del PDF en una tabla propia** (`config_textos_pdf`) y no en `configuracion`. La suite cuenta exactamente 4 claves de configuración (T-seed F1), y así la foto de la emisión los congela juntos.
6. **Copia en el código de los textos anteriores a E2** (`pdf.TEXTOS_PDF_ANTES_DE_E2`), solo para dibujar idénticas las cotizaciones emitidas antes de E2. Los vigentes se editan en la base.
7. **Se retiró el CHECK del formato por tipo** (`ck_cliente_identificacion_formato`): con tipos editables, la regla es el regex del catálogo, que valida el service.
8. **No se convierten en CRUD**, como pide el prompt maestro: bloques de costo, métodos de venta, unidades, estados ni la lista de Incoterms.

## 7. Pendientes

Ninguno técnico. E2 no tiene acciones pendientes del gerente, salvo su checklist.

## 8. Checklist del gerente (navegador)

1. [ ] **Roles:** en Administración → Roles y permisos, ver los 4 roles y la matriz, con la descripción de cada permiso.
2. [ ] **Rol de prueba:** crear un rol de prueba (por ejemplo, "Consulta", solo con "Ver tarifas") y asignarlo a un usuario de prueba. Al entrar, ese usuario ve solo Tarifas.
3. [ ] **Sesión invalidada:** quitarle un permiso al rol de prueba. El usuario debe volver a entrar.
4. [ ] **Admin protegido:** intentar quitar "Administrar usuarios" al Administrador. El sistema no lo permite.
5. [ ] **Motivos:** en Administración → Motivos de rechazo, crear un motivo. En una cotización emitida, "Marcar rechazada" lo muestra.
6. [ ] **Tipos de identificación:** en Administración → Tipos de identificación, revisar las reglas. Al crear un cliente, el tipo muestra su formato.
7. [ ] **Textos del PDF:** en Configuración → Textos del PDF y advertencias, revisar los textos. Si edita uno, aparece en el PDF de la próxima emisión; los ya emitidos no cambian.
8. [ ] **Limpieza:** desactivar el rol, el motivo y el usuario de prueba al terminar.

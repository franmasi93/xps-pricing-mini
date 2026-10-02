# XPS-PRICING-MINI — Arquitectura del Sistema V1.0

**XPRESS LOGISTICS XPS S.A.**
Sistema independiente de tarifas, clientes y cotizaciones de carga internacional (aéreo / marítimo LCL / FCL)

| Campo | Valor |
|---|---|
| Documento | XPS-Pricing-Mini_Arquitectura_V1.0.md |
| Versión | 1.0 — borrador para ratificación |
| Fecha | 2026-09-30 |
| Dueño / decisor final | François Ramírez — Gerente General |
| Metodología | Dos Claude: ASESOR (arquitectura, prompts, compuertas) + EJECUTOR (implementación) |
| Estado | Pendiente de ratificar antes de enviar el prompt al EJECUTOR |

---

## 0. Resumen en una línea

Un sistema pequeño y rápido donde **Pricing** carga cuánto cobran los agentes (costo) y a cuánto se vende; **Comercial** arma cotizaciones con Incoterm, las emite en PDF con la marca XPRESS y las envía al cliente por correo vía Tencent Cloud SES; **Gerencia** ve márgenes. Todo con roles (RBAC), multimoneda y vigencias simples.

---

## 1. Alcance

### 1.1 Qué SÍ hace (V1)

1. Geografía: Regiones → Países → Puertos / Aeropuertos.
2. Proveedores (agentes): MSL, CHARTER LINK, SACO, GLOVAL, CRAFT y los que se agreguen.
3. Tarifas de costo y de venta: aéreo, LCL y FCL, con vigencia *desde / hasta*.
4. Recargos locales (THC, BL, handling, etc.) en origen y destino.
5. Multimoneda (USD, EUR, CNY y otras) con tasas de cambio manuales por fecha.
6. Precio de venta manual o por fórmula (markup, margen o monto fijo).
7. Libreta de clientes y contactos.
8. Cotizador con Incoterms 2020, importación o exportación.
9. PDF de cotización con identidad XPRESS y split fiscal Recibo de Caja / Factura.
10. Envío por correo vía API de Tencent Cloud SES, con bitácora.
11. Usuarios, roles y permisos (RBAC) propios.
12. Auditoría de cambios de precios.

### 1.2 Qué NO hace (queda para V2 o más adelante)

- Tarifas automáticas por API de navieras o aerolíneas.
- Modelos de ML de precios (eso vive en el diseño Pricing Standalone de Cargo Lines).
- Portal del cliente con autoservicio.
- Facturación electrónica o integración con Contífico.
- Integración con XPS-Reborn o XPS-Cargo-Lines (se deja preparada: IDs estables y API REST).
- Liquidación de tributos aduaneros (ya existe como documento aparte).
- Tasas de cambio automáticas desde internet.

---

## 2. Decisiones de negocio ratificadas

| # | Decisión | Fecha |
|---|---|---|
| D1 | Sistema **independiente**: repo, login, usuarios y base de datos propios. No depende de XPS-Reborn. | 2026-09-30 |
| D2 | **Multimoneda**: las tarifas se cargan en su moneda original; las cotizaciones salen en USD. | 2026-09-30 |
| D3 | Precio de venta **manual y por fórmula**: métodos MANUAL, MARKUP, MARGEN y FIJO; el comercial puede ajustar la línea en borrador (queda auditado). | 2026-09-30 |
| D4 | Tratamiento contable alineado a NIIF: **NIC 21** (tasa de la fecha de la operación, congelada al emitir) y **NIIF 15** (cada línea marca si XPRESS actúa como principal o como agente). | 2026-09-30 |
| D5 | Vigencias **simples**: dos fechas por tarifa o recargo. La validez de la cotización es la fecha de vencimiento más cercana entre lo que usa. | 2026-09-30 |
| D6 | Correo por **API de Tencent SES** (no SMTP), desde `pricing@notificaciones.xpress.ec`, con respuesta a `pricing@xpress.ec`. | 2026-09-30 |
| D7 | Split fiscal heredado de Cargo Lines: costos internacionales → **Recibo de Caja (IVA 0%)**; costos locales Ecuador → **Factura (IVA 15%)**. | Heredada |
| D8 | El PDF lleva el **logo oficial** (X naranja con ®), nunca un logo tipográfico simulado. | Heredada |

---

## 3. Stack e infraestructura

### 3.1 Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| API | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Migraciones | Alembic |
| Base de datos | PostgreSQL (instancia Cloud SQL existente) |
| Autenticación | JWT + contraseñas con argon2 o bcrypt |
| PDF | HTML → PDF con Playwright / Chromium |
| Correo | tencentcloud-sdk-python (servicio SES, acción SendEmail) |
| Frontend | HTML + JS vanilla, **un solo** archivo de sistema de diseño (`xps-pricing.css`) |
| Tests | pytest con aislamiento por SAVEPOINT |

### 3.2 Dónde vive

| Elemento | Dónde | Nota |
|---|---|---|
| Base de datos dev | `xps_pricing` en la instancia Cloud SQL `xpress-db-reborn-v2` (us-central1) | Sin costo de instancia adicional |
| Base de datos tests | `xps_pricing_test` en la misma instancia | Se borra y recrea en cada cierre |
| Usuario de BD | `pricing_app` (propio) | **Nunca** reutilizar `xpress_app` |
| Backend + frontend | Un solo servicio Cloud Run en us-central1; FastAPI sirve la API en `/v1` y las pantallas en `/app` | Imagen Docker basada en la imagen oficial de Playwright para Python, con memoria mínima de 1 GiB por Chromium |
| Conexión Cloud Run → BD | Conector de Cloud SQL (socket unix) | En local se usa Cloud SQL Auth Proxy |
| Secretos | Secret Manager (producción) y `.env` (local, en `.gitignore`) | |
| Correo | Tencent Cloud SES | Credenciales de un subusuario CAM con permiso solo de SES |

### 3.3 Riesgo de horario de la instancia

La instancia Cloud SQL se apaga automáticamente de 20:00 a 07:00, de lunes a viernes, y queda apagada los fines de semana. **Mientras siga así, el sistema de pricing no funciona fuera de ese horario.** Decisión pendiente para el go-live: mantener el horario, ampliarlo o separar la instancia (ver §17).

---

## 4. Estructura del repositorio

```
xps-pricing-mini/
├── .env.example              # plantilla SIN valores reales
├── .gitignore                # incluye .env desde el primer commit
├── Dockerfile
├── alembic.ini
├── alembic/
│   └── versions/
├── app/
│   ├── main.py               # FastAPI: /v1 (API) y /app (estáticos)
│   ├── config.py             # lectura de variables de entorno (pydantic-settings)
│   ├── db.py                 # engine y sesión
│   ├── core/
│   │   ├── security.py       # hash de contraseñas y JWT
│   │   ├── rbac.py           # dependencia require_permiso()
│   │   ├── money.py          # redondeo ROUND_HALF_UP y utilidades Decimal
│   │   └── errors.py         # IntegrityError → 409/422
│   ├── models/               # un archivo por módulo
│   ├── schemas/              # Pydantic de entrada y salida
│   ├── services/             # lógica de negocio, gating de dinero y commits
│   │   ├── cotizador.py      # motor de cotización (única fuente de cálculo)
│   │   ├── tasas.py          # conversión de moneda (NIC 21)
│   │   ├── precio_venta.py   # fórmulas MANUAL / MARKUP / MARGEN / FIJO
│   │   ├── pdf.py
│   │   └── correo_tencent.py
│   ├── routers/              # solo reciben y responden; sin lógica ni commits
│   └── templates/
│       └── cotizacion.html   # plantilla del PDF
├── frontend/
│   ├── css/xps-pricing.css   # ÚNICO sistema de diseño
│   ├── js/
│   ├── img/logo-xpress.png   # logo oficial entregado por François
│   └── *.html                # una pantalla por archivo
├── scripts/
│   ├── crear_admin.py        # crea el admin inicial pidiendo la contraseña por teclado
│   └── canario_encoding.py   # detecta tildes corrompidas (U+FFFD)
├── tests/
│   ├── conftest.py           # harness con SAVEPOINT
│   └── test_*.py
└── docs/
    ├── XPS-Pricing-Mini_Arquitectura_V1.0.md
    └── cierres/              # actas de cierre por fase
```

---

## 5. Configuración

### 5.1 Variables de entorno

| Variable | Ejemplo / descripción | Secreto |
|---|---|---|
| `APP_ENV` | `dev` / `test` / `prod` | No |
| `DATABASE_URL` | cadena de conexión de `xps_pricing` | **Sí** |
| `DATABASE_URL_TEST` | cadena de conexión de `xps_pricing_test` | **Sí** |
| `JWT_SECRET` | clave aleatoria de 64 bytes o más | **Sí** |
| `JWT_EXPIRA_MIN` | `480` (8 horas) | No |
| `IVA_TASA` | `15.00` | No |
| `COT_PREFIJO` | `COT` | No |
| `MONEDA_BASE` | `USD` | No |
| `TENCENT_SECRET_ID` | llave del subusuario CAM | **Sí** |
| `TENCENT_SECRET_KEY` | llave del subusuario CAM | **Sí** |
| `TENCENT_SES_REGION` | tomada de la consola de François; no se asume | No |
| `SES_FROM` | `Xpress - Tarifas <pricing@notificaciones.xpress.ec>` | No |
| `SES_REPLY_TO` | `pricing@xpress.ec` | No |
| `SES_TEMPLATE_ID` | opcional; solo si Tencent exige plantilla | No |
| `SES_MAX_ADJUNTO_MB` | según el límite confirmado en la consola | No |

### 5.2 Configuración editable por pantalla (tabla `Configuracion`)

| Clave | Valor inicial | Quién edita |
|---|---|---|
| `iva_tasa` | 15.00 | admin |
| `dias_alerta_vencimiento` | 7 | admin, pricing |
| `condiciones_generales_pdf` | texto de condiciones de la cotización | admin |
| `firma_correo` | firma del correo | admin |

Regla: la tasa de IVA **no** se escribe fija en ninguna fórmula; siempre se lee de la configuración.

---

## 6. RBAC — Roles y permisos

### 6.1 Roles

| Rol | Para quién | Resumen |
|---|---|---|
| `admin` | François / TI | Todo, incluidos los usuarios y la configuración |
| `pricing` | Departamento de Pricing | Carga tarifas, recargos, proveedores y tasas; ve costo y margen |
| `comercial` | Vendedores | Ve solo el precio de venta; maneja sus clientes; crea, emite y envía cotizaciones |
| `gerencia` | Dirección | Lectura de todo, incluidos costo y margen; no edita |

### 6.2 Matriz de permisos

| Permiso | admin | pricing | comercial | gerencia |
|---|:-:|:-:|:-:|:-:|
| `usuario.admin` | ✓ | | | |
| `config.editar` | ✓ | | | |
| `catalogo.editar` (geografía, proveedores, Incoterms) | ✓ | ✓ | | |
| `tarifa.ver` | ✓ | ✓ | ✓ | ✓ |
| `tarifa.editar` | ✓ | ✓ | | |
| `costo.ver` | ✓ | ✓ | | ✓ |
| `margen.ver` | ✓ | ✓ | | ✓ |
| `tasa.editar` | ✓ | ✓ | | |
| `cliente.ver` | ✓ | ✓ | ✓ (solo los suyos) | ✓ |
| `cliente.editar` | ✓ | | ✓ (solo los suyos) | |
| `cotizacion.crear` | ✓ | ✓ | ✓ | |
| `cotizacion.emitir` | ✓ | ✓ | ✓ | |
| `cotizacion.enviar` | ✓ | ✓ | ✓ | |
| `cotizacion.ver_todas` | ✓ | ✓ | | ✓ |
| `auditoria.ver` | ✓ | | | ✓ |

### 6.3 Reglas de RBAC

1. **Gating de dinero en la capa de servicio**, nunca solo en el router o el frontend. Sin `costo.ver`, el JSON **no contiene** los campos `costo`, `costo_usd`, `margen` ni `parametro_venta` (se omiten; no van en null).
2. Un comercial sin `cotizacion.ver_todas` solo ve sus propias cotizaciones y los clientes que tiene asignados. Intentar abrir otra da **404**, no 403, para no revelar que existe.
3. Las pantallas de costos y administración no aparecen en el menú de quien no tiene permiso, y además el backend las bloquea.
4. Los tests de permisos se escriben contra el **seed real** de roles, no contra una matriz imaginada.
5. El seed de RBAC es lo único sembrado de seguridad; el admin inicial se crea con `scripts/crear_admin.py`.

---

## 7. Modelo de datos

Convenciones: claves primarias enteras; `creado_en`, `actualizado_en` y `creado_por` en todas las tablas de negocio; constraints con nombre explícito; borrado lógico (`activo`) en catálogos, nunca borrado físico si hay referencias.

### M1 — Seguridad
- **Usuario** (email único, nombre, hash_password, rol_id, activo, ultimo_login)
- **Rol** (codigo, nombre)
- **Permiso** (codigo, descripcion)
- **RolPermiso** (rol_id, permiso_id)

### M2 — Geografía
- **Region** (codigo único, nombre)
- **Pais** (iso2 único, nombre, region_id)
- **Puerto** (codigo único UN/LOCODE o IATA, nombre, pais_id, tipo: `MARITIMO` | `AEREO`, activo)

### M3 — Monedas y tasas
- **Moneda** (codigo ISO 4217 único, nombre, simbolo, activo)
- **TasaCambio** (moneda_id, tasa_a_usd Numeric(14,6), fecha_vigencia, registrado_por). Única por (moneda, fecha_vigencia). CHECK tasa_a_usd > 0.

### M4 — Proveedores
- **Proveedor** (nombre único, pais_id, contacto, email, telefono, notas, activo)

### M5 — Tarifas y recargos
- **TipoEquipo** (codigo: 20GP, 40GP, 40HC, 20RF, 40RF; nombre)
- **Tarifa**
  - proveedor_id, modo (`AEREO` | `LCL` | `FCL`), origen_puerto_id, destino_puerto_id
  - tipo_equipo_id: obligatorio si el modo es FCL y prohibido en los demás (CHECK)
  - rate_unit (`KG` | `CBM` | `WM` | `CONTENEDOR` | `ENVIO`) y costo Numeric(14,4): **inseparables**
  - moneda_id, minimo Numeric(14,4)
  - metodo_venta (`MANUAL` | `MARKUP` | `MARGEN` | `FIJO`), parametro_venta Numeric(10,4), precio_venta_manual Numeric(14,4) nullable
  - transit_time_dias, dias_libres, notas, activo
  - valido_desde, valido_hasta (DATE), con CHECK valido_hasta >= valido_desde
  - Índice por (proveedor_id, modo, origen, destino, tipo_equipo_id, valido_desde); para FCL la clave de búsqueda es (ruta, tipo_equipo)
  - Validación: el puerto de origen y el de destino deben ser del tipo que corresponde al modo (aeropuertos para AEREO, puertos marítimos para LCL y FCL)
- **TramoAereo** (tarifa_id, desde_kg, costo_kg, precio_venta_kg nullable), para los breaks −45 / +45 / +100 / +300 / +500 / +1000
- **Recargo**
  - proveedor_id nullable, puerto_id, lado (`ORIGEN` | `DESTINO`)
  - bloque_incoterm (ver §9): `RECOGIDA_ORIGEN` | `DESPACHO_EXPORT` | `GASTOS_ORIGEN` | `SEGURO` | `GASTOS_DESTINO` | `DESPACHO_IMPORT` | `ENTREGA_FINAL`
  - concepto, rate_unit, costo, moneda_id, minimo, el mismo esquema de venta que la tarifa, aplica_iva (bool), rol_ingreso (`PRINCIPAL` | `AGENTE`)
  - valido_desde, valido_hasta, activo

### M6 — Clientes
- **Cliente** (razon_social, ruc_o_id, tipo_id: `RUC` | `CEDULA` | `PASAPORTE` | `EXTRANJERO`, pais_id, direccion, ciudad, telefono, comercial_asignado_id, notas, activo). Único por (tipo_id, ruc_o_id).
- **ContactoCliente** (cliente_id, nombre, cargo, email, telefono, principal). Máximo un contacto principal por cliente (índice parcial único).

### M7 — Cotizaciones
- **Cotizacion**
  - numero único `COT-AAAA-NNNNN` (contador anual con SELECT … FOR UPDATE)
  - cliente_id, contacto_id, comercial_id, sentido (`IMPORTACION` | `EXPORTACION`), incoterm_id, modo, origen_puerto_id, destino_puerto_id
  - carga: peso_kg Numeric(10,3), cbm Numeric(10,4), bultos, dimensiones opcionales (JSON de bultos con largo, ancho y alto en cm)
  - contenedores (para FCL): lista de (tipo_equipo, cantidad)
  - estado (`BORRADOR` | `EMITIDA` | `ENVIADA` | `ACEPTADA` | `RECHAZADA`)
  - fecha_emision, valida_hasta, moneda_cotizacion (USD), notas_cliente, notas_internas
  - totales calculados y congelados al emitir: subtotal_recibo_caja, subtotal_factura, iva, total_general, costo_total, margen_total, margen_pct
  - cotizacion_origen_id (si fue duplicada de otra)
- **LineaCotizacion** (cotizacion_id, orden, concepto, bloque_incoterm, tarifa_id o recargo_id, proveedor_id, cantidad, rate_unit, costo_original, moneda_original, tasa_aplicada, costo_usd, precio_venta_usd, subtotal_usd, bloque_fiscal: `RECIBO_CAJA` | `FACTURA`, rol_ingreso, ajuste_manual, motivo_ajuste)

### M8 — Correo y auditoría
- **EnvioCorreo** (cotizacion_id, destinatarios, cc, asunto, estado: `ENVIADO` | `FALLIDO`, message_id, respuesta_proveedor, enviado_por, fecha)
- **Auditoria** (usuario_id, entidad, entidad_id, accion, valores_antes JSON, valores_despues JSON, fecha). Se registra cualquier cambio de costo, precio de venta, tasa de cambio, ajuste manual de línea y cambio de estado de cotización.
- **Configuracion** (clave única, valor, tipo, actualizado_por)

---

## 8. Módulos y endpoints

| Módulo | Endpoints principales (`/v1`) | Permiso |
|---|---|---|
| M1 Seguridad | `POST /auth/login` · `GET /auth/yo` · CRUD `/usuarios` | `usuario.admin` |
| M2 Geografía | CRUD `/regiones` · `/paises` · `/puertos` (filtros por tipo y país) | `catalogo.editar` para escribir |
| M3 Monedas | CRUD `/monedas` · `GET/POST /tasas` · `GET /tasas/vigente?moneda=EUR&fecha=` | `tasa.editar` para escribir |
| M4 Proveedores | CRUD `/proveedores` | `catalogo.editar` |
| M5 Tarifas | CRUD `/tarifas` (filtros: modo, ruta, proveedor, vigente_en, por_vencer) · `/tarifas/{id}/tramos` · CRUD `/recargos` · `POST /tarifas/{id}/duplicar` (para renovar vigencias) | `tarifa.editar` |
| M6 Clientes | CRUD `/clientes` · `/clientes/{id}/contactos` · `GET /clientes/buscar?q=` | `cliente.editar` |
| M7 Cotizaciones | `POST /cotizaciones` (borrador) · `POST /cotizaciones/{id}/proponer-lineas` · `PATCH /cotizaciones/{id}/lineas/{lid}` · `POST /cotizaciones/{id}/emitir` · `POST /cotizaciones/{id}/duplicar` · `PATCH /cotizaciones/{id}/estado` · `GET /cotizaciones/{id}/pdf` | `cotizacion.*` |
| M8 Correo | `POST /cotizaciones/{id}/enviar` · `GET /cotizaciones/{id}/envios` | `cotizacion.enviar` |
| M8 Auditoría | `GET /auditoria` (filtros por entidad y fecha) | `auditoria.ver` |
| M8 Config | `GET/PATCH /configuracion` | `config.editar` |

Regla de rutas: las rutas fijas (`/buscar`, `/vigente`, `/proponer-lineas`) se declaran **antes** de las rutas `/{id}`.

---

## 9. Incoterms 2020 — qué cobra XPRESS según el término

La cotización está dividida en 8 bloques. El Incoterm, junto con el sentido (importación o exportación), decide qué bloques se incluyen.

### 9.1 Matriz para IMPORTACIÓN (el cliente de XPRESS es el comprador)

✓ = XPRESS lo cotiza al cliente · — = lo paga el vendedor en origen

| Incoterm | Modos | Recogida origen | Despacho export | Gastos origen | Flete principal | Seguro | Gastos destino | Despacho import | Entrega final |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| EXW | Todos | ✓ | ✓ | ✓ | ✓ | ✓ opc. | ✓ | ✓ | ✓ |
| FCA | Todos | — | — | ✓ | ✓ | ✓ opc. | ✓ | ✓ | ✓ |
| FAS | Solo marítimo | — | — | ✓ | ✓ | ✓ opc. | ✓ | ✓ | ✓ |
| FOB | Solo marítimo | — | — | — | ✓ | ✓ opc. | ✓ | ✓ | ✓ |
| CFR | Solo marítimo | — | — | — | — | ✓ opc. | ✓ | ✓ | ✓ |
| CIF | Solo marítimo | — | — | — | — | — | ✓ | ✓ | ✓ |
| CPT | Todos | — | — | — | — | ✓ opc. | ✓ | ✓ | ✓ |
| CIP | Todos | — | — | — | — | — | ✓ | ✓ | ✓ |
| DAP | Todos | — | — | — | — | — | — | ✓ | — |
| DPU | Todos | — | — | — | — | — | — | ✓ | — |
| DDP | Todos | — | — | — | — | — | — | — | — |

### 9.2 EXPORTACIÓN (el cliente de XPRESS es el vendedor)

En exportación se aplica el complemento: XPRESS cotiza los bloques que la matriz anterior marca con "—". Ejemplo: en una exportación FOB, XPRESS cobra recogida, despacho de exportación y gastos en origen hasta dejar la carga a bordo.

### 9.3 Reglas del motor con Incoterms

1. FAS, FOB, CFR y CIF **solo** se permiten con los modos LCL y FCL. Con AEREO → error 422 con el mensaje "Para aéreo use FCA, CPT o CIP".
2. El seguro marcado "opc." se propone apagado; el comercial lo activa si el cliente lo pide.
3. La matriz vive en la base de datos (tabla `Incoterm` con un indicador por bloque). Se siembra con los valores de arriba y solo `admin` puede ajustarla, con auditoría, porque en la práctica hay puertos donde los THC se negocian distinto.
4. En DDP de importación no hay nada que cotizarle al comprador. El sistema lo advierte y sugiere cotizar al vendedor como exportación.

---

## 10. Motor de cotización

Toda la lógica de cálculo vive en `services/cotizador.py`. Hay **una sola función por cálculo**, que usan la vista previa, la emisión y el PDF. Jamás se calcula nada en el frontend.

### 10.1 Cantidad cobrable

| Modo | Fórmula |
|---|---|
| AEREO | peso cobrable = max(peso real kg, Σ(L × A × H cm) / 6000) |
| LCL | W/M = max(CBM, peso kg / 1000) |
| FCL | cantidad de contenedores por tipo de equipo |

Luego: subtotal de costo = max(cantidad × costo unitario, mínimo).
En aéreo con tramos se aplica el costo por kg del tramo que corresponde al peso cobrable.

### 10.2 Selección de tarifas

Son elegibles las tarifas y recargos activos cuya vigencia cubre la **fecha de emisión**, que coinciden en ruta y modo (y en tipo de equipo si es FCL) y cuyo bloque está incluido por el Incoterm. Si hay varios proveedores para la misma ruta, el comercial ve la lista ordenada por **precio de venta** (el costo solo lo ve quien tiene `costo.ver`) y elige uno.

### 10.3 Conversión de moneda (NIC 21)

```
costo_usd = costo_original × tasa_a_usd
```
La tasa es la registrada con la fecha de vigencia más reciente que no sea posterior a la fecha de emisión. **Si no hay tasa, error 422**; nunca se asume 1. Al emitir, la tasa usada queda guardada en cada línea (`tasa_aplicada`) y no cambia aunque después se cargue una tasa nueva.

### 10.4 Precio de venta

Se aplica el primero que corresponda:

| Prioridad | Método | Fórmula | Ejemplo con costo $100 y parámetro 20 |
|---|---|---|---|
| 1 | Ajuste manual en la línea (solo en BORRADOR) | valor escrito por el comercial, con motivo obligatorio | — |
| 2 | MANUAL | `precio_venta_manual` de la tarifa (convertido a USD) | — |
| 3 | MARKUP | costo × (1 + p / 100) | $120.00 |
| 4 | MARGEN | costo / (1 − p / 100), con p < 100 | $125.00 |
| 5 | FIJO | costo + p | $120.00 |

Diferencia clave: con **MARKUP 20%** ganas el 16,7% de lo que cobras; con **MARGEN 20%** ganas exactamente el 20% de lo que cobras. El margen que muestra el sistema siempre se calcula sobre la venta.

### 10.5 Totales

```
subtotal_recibo_caja = Σ líneas con bloque_fiscal = RECIBO_CAJA        (IVA 0%)
subtotal_factura     = Σ líneas con bloque_fiscal = FACTURA
iva                  = subtotal_factura × iva_tasa / 100
total_general        = subtotal_recibo_caja + subtotal_factura + iva
costo_total          = Σ costo_usd
margen_total         = (subtotal_recibo_caja + subtotal_factura) − costo_total
margen_pct           = margen_total / (subtotal_recibo_caja + subtotal_factura) × 100
```
Los valores unitarios se manejan con Decimal a 4 decimales; solo los totales se redondean a 2 (ROUND_HALF_UP). El margen se calcula sin IVA, porque el IVA no es ingreso de XPRESS.

### 10.6 Validez

`valida_hasta` = la fecha `valido_hasta` más cercana entre todas las tarifas y recargos usados. El comercial puede **acortarla**, nunca alargarla.

---

## 11. Ciclo de vida de la cotización

```
BORRADOR ──emitir──▶ EMITIDA ──enviar (éxito)──▶ ENVIADA ──▶ ACEPTADA
    ▲                   │                            │
    │                   └──────────┬─────────────────┴──▶ RECHAZADA
    └──── duplicar ◀───────────────┘
```

- **BORRADOR:** editable; los precios se recalculan en vivo.
- **EMITIDA:** congelada (snapshot de tasas, costos, precios y textos). Genera el PDF. No se edita nunca.
- **ENVIADA:** solo si Tencent confirmó el envío. Un envío fallido deja la cotización en EMITIDA.
- **ACEPTADA / RECHAZADA:** las marca el comercial. En RECHAZADA el motivo es obligatorio (precio, tiempo, competencia, otro), para las estadísticas de V2.
- **Vencida** no es un estado guardado: se calcula al leer (hoy > valida_hasta y estado en EMITIDA o ENVIADA) y se muestra como etiqueta.
- **Duplicar:** crea un BORRADOR nuevo con número nuevo y recalcula con tarifas y tasas vigentes hoy; guarda `cotizacion_origen_id`.

---

## 12. PDF de cotización

- Generación HTML → PDF con Playwright / Chromium, desde `app/templates/cotizacion.html`.
- Identidad XPRESS: navy `#000771`, naranja `#ED4C01`, fuentes Inter y JetBrains Mono (esta para cifras), logo oficial como imagen.
- Contenido:
  - Encabezado: número, fechas de emisión y validez, comercial que atiende.
  - Cliente y contacto.
  - Ruta, modo, Incoterm y sentido.
  - Datos de la carga.
  - Líneas en dos bloques: **Recibo de Caja (IVA 0%)** y **Factura (IVA 15%)**.
  - Totales, transit time y días libres.
  - Condiciones generales y firma.
- El PDF **nunca** muestra costo, margen, proveedor ni tasa de cambio.
- El nombre del archivo es `COT-AAAA-NNNNN_<cliente>.pdf`.

---

## 13. Correo — Tencent Cloud SES

| Elemento | Valor |
|---|---|
| Método | API (`SendEmail` del SDK oficial), no SMTP |
| Remitente | `Xpress - Tarifas <pricing@notificaciones.xpress.ec>` (ya creado en la consola) |
| Responder a | `pricing@xpress.ec` |
| Adjunto | PDF en base64 |
| Credenciales | Subusuario CAM con permiso solo de SES |
| Bitácora | Cada intento en `EnvioCorreo`, con el `message_id` de Tencent |

**Pendiente de confirmar en la consola antes de construir (fase F4):**
- (a) Que `notificaciones.xpress.ec` aparezca verificado en *Sender Domain*.
- (b) Si la cuenta exige plantilla aprobada (*Email Template*) o permite contenido libre. Si exige plantilla, las variables son: nombre del contacto, número de cotización, fecha de validez y nombre del comercial.
- (c) El límite de tamaño de los adjuntos. Si el PDF lo supera → error claro; nunca se envía sin adjunto.
- (d) La región de la API.

---

## 14. Pantallas

| # | Pantalla | Roles que la ven |
|---|---|---|
| P1 | Login | Todos |
| P2 | Inicio: cotizaciones recientes y tarifas por vencer | Todos (con contenido según el rol) |
| P3 | Geografía (regiones, países, puertos) | admin, pricing |
| P4 | Proveedores | admin, pricing |
| P5 | Monedas y tasas de cambio | admin, pricing (gerencia en lectura) |
| P6 | Tarifas: listado con filtros y etiquetas "vence en ≤7 días" y "vencida"; ficha con tramos | Todos (el comercial sin columnas de costo) |
| P7 | Recargos | admin, pricing |
| P8 | Clientes y contactos | admin, pricing, comercial (los suyos), gerencia (lectura) |
| P9 | Cotizador paso a paso: cliente → sentido, ruta y modo → carga → Incoterm → líneas propuestas → ajuste → emitir | admin, pricing, comercial |
| P10 | Lista de cotizaciones con filtros por estado, cliente, comercial y vencidas | Todos (según permiso) |
| P11 | Detalle de cotización: PDF, enviar e historial de envíos | Todos (según permiso) |
| P12 | Usuarios | admin |
| P13 | Configuración | admin |
| P14 | Auditoría | admin, gerencia |

Regla de frontend: una sola hoja de estilos (`xps-pricing.css`). Se verifica en el navegador con los 4 roles, con la consola abierta, y se revisa el JSON para confirmar que el gating de costos funciona.

---

## 15. Reglas arquitectónicas transversales (heredadas de XPS-Reborn)

1. La lógica y los commits atómicos viven en los **services**; los routers solo reciben y responden.
2. El gating de dinero se hace en el **service**.
3. Todo total es un **campo calculado**, nunca un input editable.
4. `rate_value` y `rate_unit` son inseparables.
5. Dinero en `Numeric` y `Decimal` en Python; `float()` solo al serializar.
6. Sin seed data de negocio: todo se carga por CRUD. Lo único sembrado es el RBAC, los Incoterms 2020, los tipos de equipo, la moneda USD y la configuración inicial.
7. Credenciales solo en `.env` o Secret Manager; jamás en consola, logs, transcript ni commits.
8. PATCH con `model_dump(exclude_unset=True)`.
9. Contadores secuenciales con `SELECT … FOR UPDATE`.
10. `IntegrityError` se traduce a 409/422, nunca a 500.
11. Rutas fijas antes que `/{id}`.
12. Migraciones manuales con constraints nombrados y ciclo up/down/up solo por Alembic; nunca editar `alembic_version` a mano.
13. Canario de encoding en cada archivo tocado.
14. Git: nunca `git add .`; rutas explícitas; sin amend, rebase, force-push ni `reset --hard`; nada de commit sin autorización de François.
15. Verificar el **código**, no los comentarios. Evidencia, no adjetivos.

---

## 16. Pruebas y cierre

### 16.1 Harness

```
engine.connect() → connection.begin()
→ Session(bind=connection, join_transaction_mode="create_savepoint")
→ yield
→ session.close() → transaction.rollback() → connection.close()
```
Sin TRUNCATE, sin `begin_nested()` manual, sin listeners `after_commit`. El seed de RBAC es de alcance de sesión, fuera del rollback. Cada fixture crea sus propios datos y nunca asume IDs fijos. El test canario de aislamiento es permanente.

### 16.2 Tests mínimos obligatorios

| Área | Qué se prueba |
|---|---|
| RBAC | El comercial no recibe costo ni margen en el JSON de tarifas ni de cotizaciones; el comercial no ve clientes ni cotizaciones ajenas (404) |
| Fórmulas | Los 4 métodos de venta con valores exactos; MARGEN con p ≥ 100 → 422; prioridad del ajuste manual |
| Cantidades | Peso cobrable aéreo, W/M de LCL, mínimo aplicado, tramos aéreos, FCL por tipo de equipo |
| Moneda | Conversión EUR y CNY con la tasa vigente por fecha; sin tasa → 422; tasa congelada al emitir |
| Incoterms | FOB, EXW y DAP en importación dan líneas distintas; exportación FOB da el complemento; FOB con aéreo → 422 |
| Vigencias | valida_hasta = mínimo de vigencias; no se puede extender; tarifa vencida no es elegible |
| Ciclo de vida | EMITIDA es inmutable; duplicar crea BORRADOR con número nuevo; envío fallido no marca ENVIADA |
| Fiscal | IVA solo sobre el bloque FACTURA; margen sin IVA |
| Numeración | Emisiones concurrentes sin números duplicados |
| Auditoría | Un cambio de precio o de tasa deja registro con antes y después |

### 16.3 Criterio de cierre (protocolo acelerado vigente)

- Durante la sesión: cada paso corre pytest solo sobre los archivos tocados y pega la línea cruda.
- Al final de la sesión, antes del commit, la **Regla 18 doble**: matar Python → DROP y CREATE de `xps_pricing_test` → `alembic upgrade head` → pytest, dos veces, con líneas crudas idénticas (N passed, 0 failed / errors / skipped, N = recolectados).
- Mostrar `git status` y `git diff --cached` con rutas explícitas; esperar la autorización de François para el commit.
- Acta de cierre en `docs/cierres/`.

---

## 17. Roadmap

| Fase | Contenido | Peso | Compuerta de salida |
|---|---|:-:|---|
| **F0** | Repo, `.env` y `.gitignore`, conexión a las dos BD, Alembic vacío, harness con canario de aislamiento, script de crear admin, canario de encoding | 5% | Canario verde dos veces en base virgen |
| **F1** | M1 Seguridad + M2 Geografía + M3 Monedas/tasas + M4 Proveedores + tabla Incoterm sembrada + Configuración | 15% | Migración revisada por François; tests de RBAC contra el seed |
| **F2** | M5 Tarifas + tramos + recargos + M6 Clientes/contactos + auditoría de precios | 25% | Gating de costos probado en JSON |
| **F3** | M7 Motor de cotización + emisión/snapshot + duplicar + estados + PDF con el logo oficial | 30% | Tres cotizaciones de prueba (aéreo, LCL, FCL) revisadas por François contra un cálculo manual |
| **F4** | M8 Correo Tencent SES + bitácora | 15% | Un correo real recibido; "Responder" llega a pricing@xpress.ec |
| **F5** | Pantallas verificadas con los 4 roles, suite completa, Regla 18 doble, despliegue en Cloud Run, acta de cierre | 10% | Checklist de navegador completo y François aprueba con los 4 perfiles |
| | **Total** | **100%** | |

---

## 18. Pendientes y decisiones abiertas

| # | Pendiente | Quién | Bloquea |
|---|---|---|---|
| P1 | Confirmar en Tencent: dominio verificado, plantilla, límite de adjuntos y región | François | F4 |
| P2 | Entregar el archivo del logo oficial XPRESS | François | F3 |
| P3 | Crear el subusuario CAM con permiso solo de SES y guardar sus llaves en Secret Manager | François | F4 |
| P4 | Horario de la instancia Cloud SQL para el go-live (se apaga de 20:00 a 07:00 y los fines de semana) | François | Go-live |
| P5 | Texto de las condiciones generales de la cotización | François / Pricing | F3 |
| P6 | Ratificar la matriz de Incoterms de §9 (sobre todo los THC en FCA, FOB y CFR) | François / Pricing | F1 |
| P7 | Lista inicial de monedas a habilitar además de USD, EUR y CNY | Pricing | F1 |

---

## 19. V2 (fuera de alcance, para no olvidar)

- Estadísticas: tasa de cierre por ruta, comercial y motivo de rechazo.
- Alertas por correo de tarifas por vencer.
- Portal del cliente para ver y aceptar cotizaciones.
- Puente hacia XPS-Cargo-Lines: una cotización aceptada abre el embarque.
- Tasas de cambio automáticas.
- Carga masiva de tarifas desde Excel del agente.

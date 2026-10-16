# Checklist final de XPS Pricing Mini (verificación P-B en producción)

Escrito para: François. Lo recorre en la URL de producción con los 4 roles.

## Antes de empezar

1. **Abrir la URL de producción** (la `Service URL` de `docs/DESPLIEGUE.md`, paso 5.1) en el navegador, con la Console abierta (F12).
2. **Crear los usuarios de prueba:**
   ```powershell
   .\.venv\Scripts\python.exe scripts\crear_usuarios_prueba.py trabajo
   ```
   Crea `prueba.admin`, `prueba.pricing`, `prueba.comercial` y `prueba.gerencia`, todos `@xpress.ec`. Muestra las contraseñas una sola vez, y el primer ingreso exige cambiarlas.
3. **Al terminar**, darlos de baja:
   ```powershell
   .\.venv\Scripts\python.exe scripts\desactivar_usuarios_prueba.py trabajo
   ```
4. **Marcar cada punto** con ☐ OK o ☐ FALLA. Cada FALLA se corrige, se prueba y se vuelve a marcar.

En la columna **Rol**, "Navegador" es una revisión que no depende del rol con el que se entró.

## A. Seguridad y usuarios (M1, puntos 4 a 12)

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 1 | Admin | En Usuarios, crear un usuario de pricing, uno comercial y uno de gerencia | Quedan "Activo" | ☐ OK ☐ FALLA |
| 2 | Admin | Crear un usuario con un email que ya existe | "Ya existe un usuario con ese email" | ☐ OK ☐ FALLA |
| 3 | Admin | Editar el propio usuario | Rol y Activo bloqueados, con explicación | ☐ OK ☐ FALLA |
| 4 | Comercial | Primer ingreso | Exige cambiar la contraseña; luego el menú muestra solo lo que le corresponde | ☐ OK ☐ FALLA |
| 5 | Comercial | Escribir a mano `/app/usuarios.html` | "No tiene permiso para esta acción" | ☐ OK ☐ FALLA |
| 6 | Pricing y Gerencia | Repetir los puntos 4 y 5 con cada uno | Igual que con el comercial | ☐ OK ☐ FALLA |
| 7 | Cualquiera | Cambiar la contraseña desde el login | Entra con la nueva | ☐ OK ☐ FALLA |
| 8 | Cualquiera | Cinco contraseñas incorrectas seguidas | "Cuenta bloqueada… 15 minutos" | ☐ OK ☐ FALLA |
| 9 | Admin | Restablecer la contraseña de un usuario de prueba | El usuario vuelve a entrar (con cambio obligatorio) | ☐ OK ☐ FALLA |

## B. Catálogos (F1, a–h)

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 10 | Admin | Crear la región SUDAMERICA, el país EC y los puertos ECGYE (marítimo) y GYE (aéreo); si ya existen, verlos en la lista | Se guardan o ya existen, sin errores | ☐ OK ☐ FALLA |
| 11 | Admin | Crear un puerto PEXXX con país EC | Error del prefijo | ☐ OK ☐ FALLA |
| 12 | Pricing | Moneda CNY: tasa 0.14; luego 7.1 en otra fecha | La primera se guarda; la segunda pide confirmación | ☐ OK ☐ FALLA |
| 13 | Admin | Crear el proveedor MSL y luego "msl" | Error de duplicado | ☐ OK ☐ FALLA |
| 14 | Cualquiera | Incoterms: FOB en Exportación | Muestra solo recogida, despacho de exportación y gastos en origen | ☐ OK ☐ FALLA |
| 15 | Pricing | Abrir Configuración | Solo puede cambiar los días de alerta; no ve los datos de la empresa ni el correo | ☐ OK ☐ FALLA |
| 16 | Comercial | Abrir Geografía, Proveedores y Monedas, por menú y por URL | No los ve en el menú; por URL recibe "No tiene permiso" | ☐ OK ☐ FALLA |

## C. Tarifas, recargos y clientes (F2)

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 17 | Pricing | Crear una tarifa aérea KG con tramos (−45 y +45), una LCL WM y una FCL 40HC | Se guardan | ☐ OK ☐ FALLA |
| 18 | Pricing | Duplicar una tarifa con fechas nuevas; luego con fechas superpuestas | La primera funciona; la segunda da error | ☐ OK ☐ FALLA |
| 19 | Comercial | Tarifas → F12 → Network → `tarifas` → Response | No aparecen `costo`, `margen_pct`, `margen_unitario`, `minimo`, `metodo_venta` ni `notas`; la tabla no tiene columnas de costo | ☐ OK ☐ FALLA |
| 20 | Gerencia | Abrir Tarifas | Ve costo y margen, sin botones de edición | ☐ OK ☐ FALLA |
| 21 | Pricing | Crear un recargo THC FCL 40HC por CONTENEDOR y un BL FCL por ENVIO | Se guardan | ☐ OK ☐ FALLA |
| 22 | Comercial | Abrir Recargos, por menú y por `/app/recargos.html` | No está en el menú; por URL, "No tiene permiso para esta acción" | ☐ OK ☐ FALLA |
| 23 | Comercial | Crear un cliente | Queda asignado a él y no ve los clientes de otro comercial | ☐ OK ☐ FALLA |
| 24 | Admin | Crear un cliente sin comercial; luego con comercial | El primero da error; el segundo, OK | ☐ OK ☐ FALLA |
| 25 | Comercial | Marcar otro contacto como principal | Se desmarca el anterior | ☐ OK ☐ FALLA |
| 26 | Pricing | Tarifas y Recargos con más de 25 filas (o filtros amplios) | Aparece el paginador "Anterior · x–y de N · Siguiente" y respeta los filtros | ☐ OK ☐ FALLA |

## D. Cotizaciones (F3)

Requisito: las condiciones generales cargadas en Configuración.

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 27 | Comercial | Abrir una cotización → F12 → Network → `cotizaciones/{id}` | No aparecen `costo_usd`, `costo_unit_original`, `costo_total`, `margen_total` ni `margen_pct` | ☐ OK ☐ FALLA |
| 28 | Comercial | Cotizador: aéreo con Incoterm FOB | "Para aéreo use FCA, CPT o CIP" | ☐ OK ☐ FALLA |
| 29 | Comercial | Proponer las líneas y activar el seguro | El seguro aparece apagado; al activarlo cambia el total | ☐ OK ☐ FALLA |
| 30 | Comercial | Ajustar un precio sin motivo; luego con motivo | El primero da error; el segundo muestra "Ajuste: …" | ☐ OK ☐ FALLA |
| 31 | Comercial | Emitir | Recibe COT-AAAA-NNNNN y la validez no se puede alargar | ☐ OK ☐ FALLA |
| 32 | Comercial | Intentar editar una emitida | No hay botones de edición | ☐ OK ☐ FALLA |
| 33 | Comercial | Duplicar | Borrador nuevo, sin número y sin ajustes | ☐ OK ☐ FALLA |
| 34 | Comercial | Marcar rechazada sin motivo; luego con motivo | El primero da error; el segundo queda RECHAZADA | ☐ OK ☐ FALLA |
| 35 | Comercial | Abrir el PDF de una emitida | No muestra proveedor, tasa, costo ni margen; dice "XPRESS LOGISTICS XPS S.A." | ☐ OK ☐ FALLA |

## E. Correo, kg/lb, recargo sobre recibo y PDF (F4)

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 36 | Admin | Configuración → Correo Tencent | Llaves enmascaradas (IKID****ZQ3); "Probar conexión" con los 3 puntos en verde | ☐ OK ☐ FALLA |
| 37 | Pricing, Comercial y Gerencia | Abrir Configuración | No ven la sección Correo Tencent; por API `/v1/correo/config`, 403 | ☐ OK ☐ FALLA |
| 38 | Pricing | Crear una tarifa aérea por LB con tramos | Los tramos dicen "Desde (lb)" (0, 100, 220…) | ☐ OK ☐ FALLA |
| 39 | Comercial | Cotizar en LB (peso y medidas en pulgadas) con una tarifa por KG | La línea muestra "KG" con el peso convertido; el PDF muestra la carga en LB con su equivalente en kg | ☐ OK ☐ FALLA |
| 40 | Pricing y Comercial | Crear un recargo "% sobre Recibo de Caja" (6 %, mínimo 30) y cotizar | Cobra el mínimo con base chica y el 6 % con base grande; sin base, vale 0 con el aviso "Manejo sobre recibo sin base" | ☐ OK ☐ FALLA |
| 41 | Comercial | Abrir el PDF de una cotización con muchas líneas | Varias hojas, "Hoja X de Y", sin filas cortadas, el encabezado de la tabla repetido y los datos de la empresa en la hoja final | ☐ OK ☐ FALLA |
| 42 | Comercial | "Enviar por correo" con un CC | La ventana muestra Para, CC, la copia oculta, el asunto y el adjunto con su tamaño; después: "Enviado a … · estado ENVIADA" | ☐ OK ☐ FALLA |
| 43 | Comercial | Revisar la sección Envíos del detalle | Fecha, enviado por, para, CC, estado y MessageId abreviado | ☐ OK ☐ FALLA |
| 44 | Gerencia | Abrir la misma cotización | Ve los Envíos; no tiene botón de envío | ☐ OK ☐ FALLA |
| 45 | Cualquiera | Revisar el correo recibido (compuerta visual de F4) | Diseño correcto, el PDF abre, "Responder" va a pricing@xpress.ec, la copia oculta llega a pricing@xpress.ec y no hay enlace de baja | ☐ OK ☐ FALLA |

## F. F5

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 46 | Gerencia | Abrir Auditoría y filtrar por entidad, usuario y fechas | Tabla paginada con "campo: antes → después"; las llaves del correo, enmascaradas | ☐ OK ☐ FALLA |
| 47 | Comercial y Pricing | Buscar "Auditoría" en el menú y abrir `/app/auditoria.html` | No está en el menú; por URL, "No tiene permiso" | ☐ OK ☐ FALLA |
| 48 | Cualquiera | Entrar fuera del horario de la base (L–V 07:00–20:00) | "Sistema fuera de horario: atiende lunes a viernes de 07:00 a 20:00…", nunca un error 500 | ☐ OK ☐ FALLA |
| 49 | Comercial | Enviar una cotización **real** desde producción | Llega al cliente; Envíos muestra ENVIADO con MessageId | ☐ OK ☐ FALLA |

## G. Para todas las pantallas

| N° | Rol | Pasos | Resultado esperado | OK / FALLA |
|---|---|---|---|---|
| 50 | Navegador | Ver cada pantalla a 375 px (Ctrl+Shift+M) | Sin scroll horizontal | ☐ OK ☐ FALLA |
| 51 | Navegador | Revisar la Console durante todo el recorrido | Ninguna línea roja | ☐ OK ☐ FALLA |

## Compuerta

Todos los puntos en OK y la aprobación de François.

Al final, desactivar los usuarios de prueba con `scripts\desactivar_usuarios_prueba.py trabajo`.

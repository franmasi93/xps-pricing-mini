# F5 · Resultado del checklist final en producción (verificación automatizada, D-CIE-1)

| Dato | Valor |
|---|---|
| Fecha | 2026-10-16, noche (base encendida a pedido, D-CIE-2) |
| URL | https://xps-pricing-809824844407.us-central1.run.app (revisión `xps-pricing-00002-4lk`) |
| Herramienta | Playwright (interfaz, 1280 y 375 px) y API con el token de cada rol, con los 4 usuarios de prueba |
| **Resultado** | **51 de 51 puntos OK** |

Capturas en `salidas/f5/checklist/`, fuera de git. Este documento no lleva contraseñas ni tokens: las contraseñas del cambio obligatorio vivieron solo en memoria durante la ejecución.

**Corridas**

1. **Primera:** el script se detuvo en el primer ingreso. Pulsaba "Guardar" en la pantalla de cambio de contraseña antes de que la página conectara su formulario. Era un problema del script, no de la aplicación; se corrigió esperando el aviso de cambio obligatorio.
2. **Segunda:** 49 OK y 2 FALLA del **verificador**, no de la aplicación. Se reevaluaron sobre la evidencia de esa misma corrida (el PDF descargado, la captura y los datos de la API):
   - **P35:** contaba la palabra "tasas" de las condiciones generales ("tasas de cambio").
   - **P44:** buscaba "Margen", pero la pantalla lo muestra en mayúsculas por CSS.

**Sin cambios de código en la aplicación:** no hizo falta desplegar una revisión nueva.

## A. Seguridad y usuarios (M1)

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 1 | Admin | OK | Usuarios pricing, comercial y gerencia de prueba Activo; alta nueva 'Usuario PRUEBA F5' (HTTP 201) Activo | P01_usuarios_activos.png |
| 2 | Admin | OK | HTTP 409 EMAIL_DUPLICADO: Ya existe un usuario con ese email | P01_usuarios_activos.png |
| 3 | Admin | OK | Rol bloqueado=True, Activo bloqueado=True; explicación: 'No puede desactivarse ni quitarse el rol de administrador a sí mismo.' | P03_editar_propio_usuario.png |
| 4 | Comercial | OK | Primer ingreso exigió cambiar la contraseña; menú: ['Inicio', 'Tarifas', 'Cotizaciones', 'Clientes', 'Incoterms'] | comercial_01_inicio_menu.png |
| 5 | Comercial | OK | Por URL /app/usuarios.html: 'No tiene permiso para esta acción' | P05_comercial_usuarios_url.png |
| 6 | Pricing y Gerencia | OK | Cambio obligatorio en los dos; menú pricing ['Inicio', 'Tarifas', 'Recargos', 'Monedas y tasas', 'Cotizaciones', 'Clientes', 'Incoterms', 'Geografía', 'Proveedores', 'Configuración']; menú gerencia ['Inicio', 'Tarifas', 'Recargos', 'Monedas y tasas', 'Cotizaciones', 'Clientes', 'Incoterms', 'Proveedores', 'Auditoría']; usuarios.html sin permiso en ambos | P06_gerencia_usuarios_url.png |
| 7 | Cualquiera | OK | Cambio desde el panel del login (queda en inicio.html); entra con la nueva: HTTP 200 | P07_cambio_desde_login.png |
| 8 | Cualquiera | OK | Tras 5 intentos fallidos, incluso con la contraseña correcta: HTTP 429 CUENTA_BLOQUEADA; pantalla: 'Cuenta bloqueada temporalmente, intente en 15 minutos' | P08_cuenta_bloqueada.png |
| 9 | Admin | OK | Restablecer: HTTP 200; vuelve a entrar: HTTP 200, con cambio obligatorio | — |

## B. Catálogos (F1)

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 10 | Admin | OK | Región SUDAMERICA, país EC, puertos ECGYE (marítimo) y GYE (aéreo); además US/MIA y CN/CNSHA para las rutas de prueba | P10_geografia.png |
| 11 | Admin | OK | HTTP 422: El código PEXXX empieza con PE, pero el país es EC | P10_geografia.png |
| 12 | Pricing | OK | 0.14: HTTP 201; 7.1 otra fecha: HTTP 409 TASA_DESVIO_REQUIERE_CONFIRMACION (pide confirmar; no se confirmó, no se guardó) | P12_monedas.png |
| 13 | Admin | OK | MSL creado; 'msl': HTTP 409 PROVEEDOR_DUPLICADO | — |
| 14 | Cualquiera | OK | FOB en Exportación: ['recogida_origen', 'despacho_export', 'gastos_origen'] | — |
| 15 | Pricing | OK | Editables: ['dias_alerta_vencimiento']; datos de la empresa oculto=True; correo oculto=True | P15_configuracion_pricing.png |
| 16 | Comercial | OK | No están en su menú; por URL 'No tiene permiso': [True, True, True] | P16_comercial_geografia.png |

## C. Tarifas, recargos y clientes (F2)

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 17 | Pricing | OK | Aérea KG con tramos −45 y +45 (tramos HTTP 200), LCL WM y FCL 40HC, todas 'PRUEBA F5' | P17_tarifas_pricing.png |
| 18 | Pricing | OK | Duplicar con fechas nuevas: HTTP 201; con fechas superpuestas: HTTP 409 VIGENCIA_SUPERPUESTA | — |
| 19 | Comercial | OK | 4 tarifas en el JSON del comercial sin claves de costo ni margen; encabezados: ['RUTA', 'MODO', 'PROVEEDOR', 'UNIDAD', 'VENTA', 'VENTA', 'MÍNIMA', 'VIGENCIA', 'ESTADO', 'ACCIONES'] | P19_tarifas_comercial.png |
| 20 | Gerencia | OK | El JSON de gerencia trae costo y margen; botón Nueva visible=False; botones Editar=0 | P20_tarifas_gerencia.png |
| 21 | Pricing | OK | THC FCL 40HC por CONTENEDOR y BL FCL por ENVIO en ECGYE ('PRUEBA F5') | — |
| 22 | Comercial | OK | No está en su menú; por URL 'No tiene permiso para esta acción' | P22_comercial_recargos_url.png |
| 23 | Comercial | OK | Cliente creado (HTTP 201) asignado al comercial; ve: ['Cliente PRUEBA F5 S.A.'] | — |
| 24 | Admin | OK | Sin comercial: HTTP 422 COMERCIAL_ASIGNADO_REQUERIDO; con comercial: HTTP 201 | — |
| 25 | Comercial | OK | Marcar otro contacto como principal: HTTP 200; principales después: ['Contacto CC PRUEBA F5'] (se devolvió al original) | — |
| 26 | Pricing | OK | API: limit=2 → 2 filas de X-Total-Count=5; en pantalla el paginador solo aparece con más de 25 filas (oculto=True con las actuales) | P26_recargos_paginacion.png |

## D. Cotizaciones (F3)

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 27 | Comercial | OK | El JSON de la cotización para el comercial no trae costo_usd, costo_unit_original, costo_total, margen_total ni margen_pct | — |
| 28 | Comercial | OK | Aéreo con FOB: HTTP 422: FOB es solo marítimo. Para aéreo use FCA, CPT o CIP | — |
| 29 | Comercial | OK | El seguro se propone apagado; al activarlo el total pasa de 254.95 a 296.95 | — |
| 30 | Comercial | OK | Sin motivo: HTTP 422 MOTIVO_REQUERIDO; con motivo: ajuste 'PRUEBA F5: ajuste de verificación' | — |
| 31 | Comercial | OK | Alargar la validez: HTTP 422 NO_SE_PUEDE_EXTENDER; emitida: COT-2026-00001, válida hasta 2026-11-15 | — |
| 32 | Comercial | OK | Botones: ['Ver PDF', 'Descargar PDF', 'Marcar aceptada', 'Marcar rechazada', 'Enviar por correo', 'Duplicar']; botones en las líneas: 0; PATCH por API: HTTP 409 COTIZACION_NO_EDITABLE | P32_cotizacion_emitida.png |
| 33 | Comercial | OK | Duplicado: borrador #3 sin número ni ajustes (se descarta al cerrar) | — |
| 34 | Comercial | OK | Rechazar sin motivo: HTTP 422 MOTIVO_RECHAZO_REQUERIDO; con motivo OTRO queda RECHAZADA en la limpieza del cierre (D-CIE-4); estado actual ENVIADA | — |
| 35 | Comercial | OK | PDF COT-2026-00001: 2 hojas; fuera de las condiciones generales no aparece proveedor (MSL), costo, tasa ni margen (encontrados: []); 'tasas de cambio' solo en el punto 4 de las condiciones; dice 'XPRESS LOGISTICS XPS S.A.' (reevaluado: el verificador contaba el texto de las condiciones) | COT-2026-00001_Cliente-PRUEBA-F5-S-A.pdf |

## E. Correo, kg/lb, recargo sobre recibo y PDF (F4)

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 36 | Admin | OK | Probar conexión desde producción: 3 de 3 en verde; SecretId enmascarado (IKID****ZQ3), campo vacío | P36_configuracion_correo_admin.png |
| 37 | Pricing, Comercial y Gerencia | OK | Sección Correo oculta=[True, True, True]; /v1/correo/config → [403, 403, 403] | — |
| 38 | Pricing | OK | Tarifa aérea por LB con tramos desde [0, 100, 220] lb (la pantalla los rotula 'Desde (lb)') | — |
| 39 | Comercial | OK | Carga en LB (225 lb = 102.058 kg) con tarifa por KG: la línea cobra 102.0580 KG | — |
| 40 | Pricing y Comercial | OK | Base chica: cobra el mínimo (30.0000); sin base (CPT): 0.0000 con el aviso 'Manejo sobre recibo sin base'; el 6 % sobre base grande lo cubre la prueba automática T271 | — |
| 41 | Comercial | OK | 'Hoja X de 2' en cada hoja, encabezado de tabla y datos de la empresa en la hoja final (Banco Guayaquil); muchas líneas en varias hojas sin cortes: prueba automática T274 | COT-2026-00001_Cliente-PRUEBA-F5-S-A.pdf |
| 42 | Comercial | OK | Ventana: CC posibles=1, copia oculta visible=True, adjunto 'COT-2026-00001_Cliente-PRUEBA-F5-S-A.pdf · 365 KB'; resultado: 'Enviado a francois-ramart@outlook.com · estado ENVIADA' | P42_ventana_envio.png |
| 43 | Comercial | OK | Sección Envíos con 1 fila(s): [('francois-ramart@outlook.com', ['francois-ramart@outlook.com'], 'ENVIADO', 'qcloudses-30-1420342617-date-20261017092702-rqAAFBRQ4JOu1')] | P43_seccion_envios.png |
| 44 | Gerencia | OK | Gerencia ve COSTO TOTAL 243.70 y MARGEN 48.75 (16.67 %) en la pantalla (captura) y en el JSON; 1 envío visible; botones: Ver PDF y Descargar PDF, sin envío (reevaluado: el rótulo va en mayúsculas por CSS y el verificador distinguía mayúsculas) | P44_gerencia_cotizacion.png |
| 45 | Cualquiera | OK | Técnico: ENVIADO con MessageId, Responder a pricing@xpress.ec, copia oculta pricing@xpress.ec, envío sin enlace de baja (Unsubscribe=0). Diseño y PDF del correo: aprobados por François en F4 (D-FIN-1) | — |

## F. F5

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 46 | Gerencia | OK | Auditoría filtrada por 'cotizacion': 12 filas paginadas con 'campo: antes → después'; sin llaves en claro | P46_auditoria_gerencia.png |
| 47 | Comercial y Pricing | OK | No está en su menú; por URL 'No tiene permiso' en los dos | P47_comercial_auditoria_url.png |
| 48 | Cualquiera | OK | Verificado en vivo el 2026-10-16 a las 20:00 (base apagada): POST /v1/auth/login → 503 SISTEMA_FUERA_DE_HORARIO con el horario; /v1/salud → {"estado":"ok","bd":"error"} (F5-entregas.md) | — |
| 49 | Comercial | OK | Envío real desde producción a francois-ramart@outlook.com (D-CIE-4): MessageId qcloudses-30-1420342617-date-20261017092702-rqAAFBRQ4JOu1 | P43_seccion_envios.png |

## G. Todas las pantallas

| N° | Rol | Resultado | Evidencia | Captura |
|---|---|---|---|---|
| 50 | Navegador | OK | 32 pantallas a 375 px; con scroll horizontal: [] | comercial_pantalla_cotizador_375.png |
| 51 | Navegador | OK | 64 pantallas revisadas (1280 y 375 px) más los 4 ingresos; con errores en la Console: [] | — |

## Reglas de seguridad por la API (2.3)

| Verificación | Esperado | Obtenido |
|---|---|---|
| comercial: cotización ajena | 404 | 404 |
| gerencia: POST /tarifas | 403 | 403 |
| comercial: /correo/config | 403 | 403 |
| pricing: /correo/config | 403 | 403 |
| gerencia: /correo/config | 403 | 403 |
| comercial: /configuracion/empresa | 403 | 403 |
| comercial: claves de costo o margen en el JSON de tarifas y cotización | ninguna | ninguna (P19, P27) |

## Pantallas (consola y 375 px)

- Se revisaron 64 pantallas (los 4 roles, a 1280 y 375 px), más los 4 ingresos.
- Errores en la Console: 0.
- Pantallas con scroll horizontal a 375 px: 0.

## Envío real desde producción (D-CIE-4)

- **ENVIADO** a francois-ramart@outlook.com (CC francois-ramart@outlook.com, copia oculta pricing@xpress.ec) · MessageId `qcloudses-30-1420342617-date-20261017092702-rqAAFBRQ4JOu1` · 2026-10-17T01:26:56.701280+00:00


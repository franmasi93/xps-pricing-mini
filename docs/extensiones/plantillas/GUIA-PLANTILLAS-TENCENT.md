# Guía para el gerente: plantillas de correo en Tencent

Las plantillas se diseñan y se suben en la consola de Tencent Cloud SES. El sistema las **importa por su ID**, lee sus variables reales y sincroniza su estado cada hora (y cuando se pulsa "Sincronizar con Tencent").

En esta carpeta hay una copia del HTML y del texto de cada plantilla, tal como están en Tencent el 2026-10-19:
- 72669, cotización;
- 72746, boletín;
- 72747 a 72753, avisos.

## Subir o corregir una plantilla en la consola

1. **Entrar a la plantilla.** En la consola de Tencent Cloud, abrir **Simple Email Service → Templates**, en la misma región que la 72669.
2. **Crear o editar.** Para una nueva, **Create Template**: nombre, contenido HTML y texto. Para corregir una rechazada, **Edit**. Al guardar vuelve a revisión.
3. **Escribir las variables** entre llaves dobles, por ejemplo `{{nombre_contacto}}`:
   - son texto plano (Tencent no admite HTML en sus valores);
   - el máximo es de 40 por plantilla.
4. **Esperar la aprobación:** "审核通过" (aprobada).
5. **Sincronizar.** En el sistema, en **Administración → Plantillas de correo**, pulsar **Sincronizar con Tencent**:
   - el estado, el motivo y las variables se actualizan solos;
   - una plantilla nueva se importa inactiva: actívela y elija su uso.

## Qué revisa Tencent (motivos de rechazo vistos el 2026-10-19)

| Regla | Qué hacer |
|---|---|
| Proporción de variables frente a texto fijo de 1:5 como máximo | Poner como texto fijo lo que no cambia (dirección, teléfono, horario) y agregar texto de negocio fijo |
| Enlaces con dominio fijo | No usar `{{enlace}}` como enlace completo: escribir `https://dominio/{{codigo}}`, con el dominio fijo |
| Variables de texto libre demasiado amplias | Cambiar `{{mensaje}}`, `{{linea_01}}`… por campos concretos (fecha, cliente, monto) con su etiqueta fija |

## Estado al 2026-10-19, tarde (leído de Tencent con GetEmailTemplate)

| ID | Nombre | Uso | Estado | Variables reales |
|---|---|---|---|---|
| 72669 | Cotizacion_Pricing | Cotización (F4) | Aprobada | Las de F4 |
| 72746 | Xps boletin tarifas | Boletín | Aprobada, en uso | `titulo`, `nombre_contacto`, `texto_intro`, `fila_01…15`, `mas_tarifas`, `vigencia`, `comercial`, empresa_* y `enlace_baja` |
| 72747 | Xps aviso seguimiento | COT_SEGUIMIENTO | Aprobada | De la cotización y de la empresa |
| 72748 | Xps aviso porvencer | COT_POR_VENCER | Aprobada | De la cotización y de la empresa |
| 72749 | Xps aviso vencida | COT_VENCIDA | Aprobada | De la cotización y de la empresa |
| 72750 | Xps aviso aceptada | COT_ACEPTADA_CLIENTE | Aprobada | Las de la cotización y `paso_1…3` |
| 72751 | Xps aviso tarifainteres | TARIFA_RUTA_INTERES | Aprobada | Las de la tarifa y `enlace_baja` |
| 72752 | Xps interno aviso | Avisos internos | **Aprobada** | **`evento`, `referencia`, `fecha`** |
| 72753 | Xps interno resumen | Resúmenes | **Aprobada** | **`periodo`, `kpi_emitidas`, `kpi_enviadas`, `kpi_aceptadas`, `kpi_rechazadas`, `kpi_tasa_cierre`, `kpi_monto`, `kpi_margen`** |
| 71711 | XP_B2B_Tarifario_Aereo_mia_ec_sept26_v1 | Tarifario antiguo | Aprobada en Tencent; **no se usa** (inactiva en el catálogo) | — |

Copias del HTML aprobado: `72752_Xps_interno_aviso.html` y `72753_Xps_interno_resumen.html`, descargadas de Tencent. Las `.txt` son la versión de texto que arma el sistema (Tencent no devolvió parte de texto).

## El botón de 72752 y 72753 no tiene enlace

En las versiones aprobadas, los botones "Revisar en el sistema" y "Ver el detalle en el sistema" **no tienen `href`**: Tencent quitó el enlace. Se ven, pero no llevan a ninguna pantalla, ni de pricing.xpress.ec ni de la URL de Cloud Run.
- El sistema ya envía `{{enlace}}` como **ruta interna** (por ejemplo, `/app/cotizacion.html?id=12`) cuando la plantilla la tenga.
- **Mejora opcional:** editar en Tencent el botón como `href="https://pricing.xpress.ec{{enlace}}"`. Tencent sugirió el dominio fijo cuando rechazó la versión anterior, que llevaba la URL completa en la variable. Ojo: editarla la devuelve a revisión, y mientras tanto esos correos no salen (quedan OMITIDO; la campana llega igual).

## La llave API no puede crear plantillas

La llave que usa el sistema no tiene permiso CAM para `ses:CreateEmailTemplate`, `ses:UpdateEmailTemplate` ni `ses:CreateEmailAddress`. Tencent responde AuthFailure.UnauthorizedOperation. Hay dos opciones:
- **Darle el permiso a la llave:** en **CAM → Users → (usuario de la llave) → Add Policy**, agregar `QcloudSESFullAccess`, o solo esas tres acciones. Con eso, el sistema crea y edita plantillas desde su pantalla.
- **Seguir subiéndolas en la consola**, como hasta ahora, y sincronizar.

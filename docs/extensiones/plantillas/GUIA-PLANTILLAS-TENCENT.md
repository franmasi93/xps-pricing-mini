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

## Estado al 2026-10-19 (sincronizado)

| ID | Nombre | Uso | Estado |
|---|---|---|---|
| 72669 | Cotizacion_Pricing | Cotización (F4) | Aprobada |
| 72746 | Xps boletin tarifas | Boletín | **Aprobada**, en uso. Probada con envíos reales al administrador |
| 72747 | Xps aviso seguimiento | Aviso COT_SEGUIMIENTO | Aprobada |
| 72748 | Xps aviso porvencer | Aviso COT_POR_VENCER | Aprobada |
| 72749 | Xps aviso vencida | Aviso COT_VENCIDA | Aprobada |
| 72750 | Xps aviso aceptada | Aviso COT_ACEPTADA_CLIENTE | Aprobada |
| 72751 | Xps aviso tarifainteres | Aviso TARIFA_RUTA_INTERES | Aprobada |
| 72752 | Xps interno aviso | Aviso interno | **Rechazada.** Motivo: `{{enlace}}` es una URL completa y `{{mensaje}}`/`{{detalle_*}}` son texto libre. Corrección sugerida por Tencent: `https://xpress.ec/{{enlace}}` con el dominio fijo, y campos controlados en vez de texto libre |
| 72753 | Xps interno resumen | Resumen | **Rechazada.** Motivo: `{{enlace}}` lleva la URL completa y la proporción de variables es de 1:2,5. Corrección: dominio fijo (`https://xpress.ec/{{enlace}}`), más texto fijo y menos variables |

## El dominio del enlace en 72752 y 72753

Tencent sugiere `https://xpress.ec/{{enlace}}`. Sin embargo, el enlace tiene que llevar a la pantalla del sistema, así que el dominio fijo debe ser **el del sistema**:
- `https://xps-pricing-809824844407.us-central1.run.app/{{enlace}}`;
- o un dominio propio mapeado a Cloud Run, por ejemplo `https://pricing.xpress.ec/{{enlace}}`.

Con el dominio fijo en la plantilla, el sistema envía en `{{enlace}}` solo la ruta (por ejemplo, `app/cotizacion.html?id=12`). Lo detecta solo al sincronizar.

## La llave API no puede crear plantillas

La llave que usa el sistema no tiene permiso CAM para `ses:CreateEmailTemplate`, `ses:UpdateEmailTemplate` ni `ses:CreateEmailAddress`. Tencent responde AuthFailure.UnauthorizedOperation. Hay dos opciones:
- **Darle el permiso a la llave:** en **CAM → Users → (usuario de la llave) → Add Policy**, agregar `QcloudSESFullAccess`, o solo esas tres acciones. Con eso, el sistema crea y edita plantillas desde su pantalla.
- **Seguir subiéndolas en la consola**, como hasta ahora, y sincronizar.

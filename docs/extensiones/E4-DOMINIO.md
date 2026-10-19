# E4 · Dominio propio pricing.xpress.ec

**Objetivo:** abrir el sistema en **https://pricing.xpress.ec**, con **https://www.pricing.xpress.ec** redirigiendo a la principal. La dirección de Cloud Run (`https://xps-pricing-809824844407.us-central1.run.app`) sigue funcionando. Los correos siguen saliendo de notificaciones.xpress.ec por Tencent; este cambio no los toca.

## 1. Dónde se administra el DNS de xpress.ec (verificado el 2026-10-19)

```
nslookup -type=NS xpress.ec  →  hermes.dns-parking.com · artemis.dns-parking.com   (SOA: dns.hostinger.com)
```

**El DNS de xpress.ec está en Hostinger, no en Reinec.**
- Los registros se editan en **hPanel de Hostinger → Dominios → xpress.ec → DNS / Nameservers → Administrar registros DNS**.
- Lo que se creó en el cPanel de Reinec (pricing.xpress.ec A 66.85.131.26, www.pricing, cpanel, webmail, DKIM, SPF, SRV…) **no tiene efecto**: ningún servidor del mundo lo consulta, porque los nameservers del dominio son los de Hostinger. Hoy, en el DNS real, **pricing.xpress.ec no existe** (NXDOMAIN).
- Por eso cPanel puede regenerar sus registros sin causar problemas: no forman parte del DNS que manda. **No cambie los nameservers a Reinec:** se perderían todos los registros que viven en Hostinger (sitio web, correo y los de notificaciones.xpress.ec para Tencent).
- Lo creado en Reinec puede quedarse o borrarse (cPanel → Dominios → Subdominios → pricing → Eliminar). Para este cambio da igual.

Otros datos del DNS real:
- TTL por defecto de 10 minutos: los cambios propagan rápido.
- CAA de xpress.ec: autoriza `pki.goog` y `letsencrypt.org`, así que Google puede emitir el certificado.

## 2. Método elegido: Cloud Run domain mapping (sin costo)

| Opción | Resultado |
|---|---|
| **a) Cloud Run domain mapping en us-central1** | **Elegida.** Está disponible para el proyecto: la API respondió y el mapeo se pudo crear. **Costo: USD 0**; el certificado HTTPS lo da Google, gratis y automático. Solo falta que la cuenta `francois.ramart@gmail.com` verifique la propiedad de xpress.ec en Google Search Console: Google lo exige y respondió "Caller is not authorized to administer the domain pricing.xpress.ec". |
| b) Firebase Hosting con rewrite | No hace falta: a) está disponible. |
| c) Balanceador HTTPS con NEG serverless | No hace falta. Costaría alrededor de USD 18–20 al mes (regla de reenvío) más el tráfico. |

La redirección de www.pricing.xpress.ec a pricing.xpress.ec (301) la hace el propio sistema: los dos nombres se mapean al mismo servicio.

## 3. Verificar xpress.ec en Google (una sola vez, unos 5 minutos)

1. **Abrir Search Console** con la cuenta **francois.ramart@gmail.com** (la misma de Google Cloud): https://search.google.com/search-console/welcome
2. **Elegir "Dominio"** (a la izquierda), escribir **xpress.ec** y pulsar Continuar.
3. **Copiar el valor que muestra Google.** Es un registro TXT como `google-site-verification=AbCdEf123…`.
4. **Agregar ese TXT en Hostinger,** en el nombre **@** (es decir, **xpress.ec**, no pricing). Ver la tabla, fila 1.
5. **Esperar unos 10 minutos y pulsar "Verificar"** en Search Console. Si dice que no lo encuentra, esperar un poco más y repetir.

> **Por qué en xpress.ec y no en pricing.xpress.ec:** pricing llevará un CNAME, y un CNAME no puede convivir con un TXT en el mismo nombre. Agregar un TXT en la raíz no afecta a nada más: puede haber varios TXT y el SPF de xpress.ec sigue igual.

## 4. Cambios en el DNS de Hostinger (tabla exacta)

### AGREGAR

| # | Tipo | Nombre | Valor | TTL |
|---|---|---|---|---|
| 1 | TXT | `@` (xpress.ec) | `google-site-verification=…` (el valor exacto que da Search Console en el paso 3) | 3600 |
| 2 | CNAME | `pricing` | `ghs.googlehosted.com.` | 3600 |
| 3 | CNAME | `www.pricing` | `ghs.googlehosted.com.` | 3600 |

> Con la verificación hecha, el sistema confirma los valores de las filas 2 y 3 con `python scripts/dominio_propio.py crear`. Para subdominios, Google siempre pide CNAME a `ghs.googlehosted.com`. Si mostrara otro valor, use el que muestre.

### MODIFICAR

Nada en Hostinger. Los A de pricing y www.pricing (→ 66.85.131.26) **solo existen en el cPanel de Reinec**, que no es el DNS del dominio. En Hostinger no hay registros de pricing que cambiar.

### ELIMINAR

Nada en Hostinger. Solo revise que **no exista ya otro registro con el nombre `pricing` o `www.pricing`** (A, AAAA, TXT o CNAME). Si existiera, bórrelo antes de crear el CNAME, porque un CNAME no puede convivir con otros registros en el mismo nombre. Hoy no hay ninguno.

### OPCIONAL (Reinec cPanel)

Lo creado en el cPanel de Reinec no se usa:
- los A de pricing, www.pricing, cpanel, webmail, whm, webdisk, autodiscover, autoconfig, cpcalendars y cpcontacts .pricing;
- los SRV y TXT de _caldav, _caldavs, _carddav, _carddavs y _autodiscover;
- el DKIM y el SPF de pricing.

Borrarlos es opcional y no cambia nada: cPanel → Dominios → Subdominios → pricing.xpress.ec → Eliminar. Si cPanel los vuelve a crear, tampoco importa, por lo explicado en la sección 1.

### Paso a paso en Hostinger (hPanel)

1. **Entrar a la zona DNS.** Entre a https://hpanel.hostinger.com, luego **Dominios → xpress.ec → DNS / Nameservers**, pestaña **Registros DNS**.
2. **Agregar el TXT de verificación.** En "Agregar nuevo registro" elija **Tipo: TXT**, **Nombre: @**, **Valor:** el de Search Console, **TTL: 3600**, y pulse **Agregar registro**.
3. **Agregar el CNAME de pricing.** **Tipo: CNAME**, **Nombre: pricing**, **Apunta a: ghs.googlehosted.com**, **TTL: 3600**, y pulse **Agregar registro**.
4. **Agregar el CNAME de www.pricing.** **Tipo: CNAME**, **Nombre: www.pricing**, **Apunta a: ghs.googlehosted.com**, **TTL: 3600**, y pulse **Agregar registro**.
5. **No tocar ningún otro registro.**

## 5. Lo que hace el sistema (ya está listo)

- **Configuración → URL pública del sistema** (tabla `config_sistema`, migración 0011, con auditoría y permiso `config.editar`):
  - es la única fuente de los enlaces: baja de boletines y avisos, enlaces de los avisos internos y resúmenes, y botones de las plantillas;
  - **queda en la dirección de Cloud Run** hasta que pricing.xpress.ec abra con HTTPS.
- **Ningún dominio está fijo en el código.** La prueba TE4-01 lo verifica: la URL de Cloud Run solo existe en la base y en la migración que la siembra.
- **Funciona con cualquier dominio:** no hay CORS ni cookies (la sesión es un token y la API usa rutas relativas). TE4-08 prueba el ingreso con los dos dominios.
- **www.pricing.xpress.ec redirige a pricing.xpress.ec:** 301 en GET, y 308 en POST para no perder el cuerpo.
- **Callback de Tencent:** el endpoint es el mismo en los dos dominios. La URL de Cloud Run sigue aceptando callbacks.

## 6. Pasos que faltan (en orden)

1. **Gerente:** verificar xpress.ec en Search Console (sección 3) y agregar en Hostinger las 3 filas de la tabla (sección 4).
2. **Sistema** (Claude Code, o cualquiera con gcloud): `python scripts/dominio_propio.py crear`, y después `python scripts/dominio_propio.py estado` hasta ver `listo=('True', …)` y el certificado `True`. Suele tardar de 15 minutos a 1 hora después de que el DNS propaga.
3. **Comprobar en https://pricing.xpress.ec:** login, una cotización, el PDF, la baja pública (`/b/<token>`) y `/v1/salud`.
4. **Cambiar la URL pública:** recién entonces, en Configuración → URL pública del sistema, poner `https://pricing.xpress.ec` y Guardar.
5. **Tencent:** actualizar 72752 y 72753 (sección 7) y el callback (sección 8).

## 7. Plantillas internas 72752 y 72753

En `docs/extensiones/plantillas/` están:
- `72752_Xps_interno_aviso_pricing-xpress-ec.html`;
- `72753_Xps_interno_resumen_pricing-xpress-ec.html`.

Tienen el mismo contenido que las vigentes. Solo cambia el botón: `href={{enlace}}` → `href="https://pricing.xpress.ec{{enlace}}"`. Con el dominio fijo, el sistema detecta el cambio al sincronizar y envía en `{{enlace}}` solo la ruta (por ejemplo, `/app/cotizacion.html?id=12`).

**Cómo editarlas en Tencent:**
1. En la consola de Tencent Cloud, abrir **Simple Email Service → Templates → Xps interno aviso (72752) → Edit**.
2. Reemplazar el contenido HTML por el de `72752_Xps_interno_aviso_pricing-xpress-ec.html` y guardar.
3. Repetir con **Xps interno resumen (72753)** y `72753_Xps_interno_resumen_pricing-xpress-ec.html`.
4. Esperar la aprobación y, en el sistema, ir a **Administración → Plantillas de correo → Sincronizar con Tencent**.

> **Aviso:** Tencent también pidió menos texto libre en 72752 y más texto fijo en 72753 (proporción de variables 1:5). Este cambio corrige el enlace, que fue el primer motivo. Si Tencent vuelve a rechazar por los otros motivos, se ajustan como dice la guía `GUIA-PLANTILLAS-TENCENT.md`.

Las demás plantillas no cambian: sus enlaces (por ejemplo, el de baja) salen de variables que ya toman la URL pública.

## 8. Callback de Tencent

La URL nueva es `https://pricing.xpress.ec/internal/tencent/eventos/<TOKEN>`. Se entrega copiada al portapapeles, sin mostrar el token. Se registra en la consola de SES (Callback) **después** de que pricing.xpress.ec abra con HTTPS. La dirección de Cloud Run sigue aceptando callbacks mientras tanto.

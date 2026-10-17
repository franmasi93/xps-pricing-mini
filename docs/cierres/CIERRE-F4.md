# Acta de cierre · F4 · formato oficial del PDF, kg/lb, recargo sobre recibo, correo Tencent y bitácora

| Dato | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fase | F4 (15 % del proyecto) |
| Decisor | François Ramírez |
| Ejecutor | Claude Code |
| Fecha de cierre | 2026-10-16 |
| Commit de código | `7743d19` "F4: formato oficial del PDF, kg/lb, recargo sobre recibo, correo Tencent administrable y bitácora" |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` |
| Entregas por parada | `docs/cierres/F4-entregas-paradas.md` |

## 1. Resumen en cristiano

Las cotizaciones salen ahora con el PDF oficial de XPRESS:
- tarjetas de referencia, transporte y carga;
- bloques de Recibo de Caja y Factura;
- banda de total;
- hoja final con condiciones, aceptación, contactos y datos de pago.

El PDF fluye a las hojas que haga falta, sin cortar filas, y numera "Hoja X de Y".

Además:
- La carga y las tarifas aéreas se pueden manejar en libras. El motor sigue calculando en kg exactos.
- Existe el recargo "% sobre el Recibo de Caja" (por ejemplo, Manejo local 6 % con mínimo 30).
- Cada cotización emitida se envía por correo desde la pantalla, con Tencent SES, y queda en una bitácora.
- El administrador configura el correo y sus llaves desde Configuración; las llaves van cifradas y nunca se ven en claro.

**Prueba real:** el 2026-10-16 salieron 5 correos reales a Gmail, Hotmail, iCloud, Outlook y @xpress.ec, los 5 con MessageId.

## 2. Alcance

| Bloque | Peso | Contenido |
|---|---|---|
| D · motor | 3 % | Transportista; kg/lb con constantes exactas en Decimal; tramos en LB (0/100/220/660/1100/2200); recargo PCT_RECIBO calculado al final; descripción de la carga |
| A · PDF | 3 % | Plantilla oficial sin alto fijo; filas que no se parten y encabezado repetido; pie nativo "Hoja X de Y"; datos de la empresa copiados a la foto congelada; separador de miles; fechas dd/mm/aaaa |
| B · correo | 5 % | Cifrado Fernet; `config_correo` con caché de 60 s; `ProveedorCorreo` (TencentSES y la falsa); traducción B9 por código; salud (caché de 10 min); plantillas; correo de prueba; envío síncrono con `SELECT … FOR UPDATE`; bitácoras de solo inserción |
| C · pantallas | 2 % | Tarifas, recargos, cotizador KG/LB, envío con confirmación y resultado, sección Envíos, Configuración (empresa y correo, solo admin) |
| Prueba real | 2 % | Salud, correo de prueba y 5 envíos reales |

**Migración `0005`, escrita a mano:**
- Columnas nuevas en `tarifa`, `cotizacion` y `linea_cotizacion`.
- PCT_RECIBO en los CHECKs.
- Tramos en LB.
- Tablas `config_empresa`, `config_correo`, `envio_correo` y `envio_correo_prueba`, con el trigger de solo inserción.

El detalle de los constraints está en las entregas, sección F4-2/F4-3.

## 3. Evidencia cruda

### 3.1 Regresión de F3 (T261–T263)

Las tres cotizaciones de la compuerta de F3 dan el mismo total al centavo:
- COT-2026-00001 = 1105.70
- COT-2026-00002 = 428.31
- COT-2026-00003 = 8007.50

Línea base, antes de tocar el motor: `3 passed in 81.28s` (2026-10-14). Volvió a pasar en cada suite y en cada ciclo de la Regla 18.

### 3.2 Suite completa y Regla 18 doble de F4 (estado F4, N = 624)

```
suite completa 2026-10-15  624 passed, 1 warning in 5167.65s (1:26:07)
ciclo 1        2026-10-15  DROP/CREATE ok · alembic 0005 (head) · 624 collected · 624 passed, 1 warning in 5148.23s
ciclo 2        2026-10-15  DROP/CREATE ok · alembic 0005 (head) · 624 collected · 624 passed, 1 warning in 5206.86s
```

0 failed, 0 errors, 0 skipped. La corrida del 2026-10-14 (`431 errors`) se descartó porque fue un corte del proxy.

### 3.3 Verificación del árbol del commit

Los archivos que F4 comparte con F5 se reconstruyeron revirtiendo los cambios de F5, y se probaron en una copia aparte (HEAD + F4) antes del commit:

```
árbol F4 (HEAD + 39 archivos de F4 + 9 reconstruidos) · import app.main ok
regresion_f3, f4_motor, f4_pdf, f4_correo, frontend, config, configuracion, tarifas, recargos, pdf:
2 failed, 201 passed in 2268.85s (0:37:48)
```

Las 2 fallas (T124 `test_seed_4_claves` y T279 `test_api_datos_de_la_empresa`) eran por los datos de la prueba real en `xps_pricing_test`: condiciones generales y datos de la empresa cargados. Con esos dos datos de vuelta en vacío (estado virgen, solo en la base de pruebas):

```
2 passed in 5.95s
```

Las dos ya habían pasado en la Regla 18 sobre base virgen. Ningún valor esperado cambió.

### 3.4 Prueba real (compuerta técnica D-AUT-2a) · `xps_pricing_test`, 2026-10-16

**Salud** (`refrescar=true`): dominio `notificaciones.xpress.ec` verificado, remitente `pricing@notificaciones.xpress.ec` existente, plantilla 72669 **Aprobada** (estado 0).

**Correo de prueba** a francois-ramart@outlook.com:
```
ENVIADO · MessageId qcloudses-30-1420342617-date-20261017024530-Q8Z6v6SvKhZn1 · 2026-10-16 13:45:21 (Ecuador)
```

**Envíos:** cliente "CLIENTE PRUEBA F4 S.A." con 5 contactos y una cotización emitida por contacto (H-F4-30). Cada cotización es aérea en LB con Manejo local 6 % sobre recibo; total USD 646.50.

| Cotización | Destinatario | Estado | MessageId | Fecha y hora (Ecuador) | request_id |
|---|---|---|---|---|---|
| COT-2026-00001 | johnreyes638@icloud.com | ENVIADO | `qcloudses-30-1420342617-date-20261017024841-PmRng11IcqQT1` | 2026-10-16 13:48:28 | `3249f710-f864-4a24-8bae-f8f7055f3dbf` |
| COT-2026-00002 | francisco14-2012@hotmail.com | ENVIADO | `qcloudses-30-1420342617-date-20261017024858-6uoVS27LuPV01` | 2026-10-16 13:48:48 | `3f07c993-4626-4c16-b274-0f617415821b` |
| COT-2026-00003 | gerencia@xpress.ec | ENVIADO | `qcloudses-30-1420342617-date-20261017024916-lWTBr0TLhk4U1` | 2026-10-16 13:49:06 | `a073e119-ff62-42ff-80ac-abdf6f84220b` |
| COT-2026-00004 | francois-ramart@outlook.com | ENVIADO | `qcloudses-30-1420342617-date-20261017024935-GZnUIUCU2zMN1` | 2026-10-16 13:49:24 | `6cdc4327-cd64-479b-a296-9c0ecb4894f3` |
| COT-2026-00005 | brayantmayers4@gmail.com | ENVIADO | `qcloudses-30-1420342617-date-20261017024954-CwftHonVNFwc1` | 2026-10-16 13:49:42 | `a7f36afa-45d5-4951-a3a6-462652f54fb9` |

Lo que se verificó en los 5:
- las 5 cotizaciones quedaron en **ENVIADA**;
- la transición ENVIAR quedó **una sola vez** en la auditoría de cada una;
- la copia oculta fue a pricing@xpress.ec;
- el adjunto fue `COT-2026-0000N_CLIENTE-PRUEBA-F4-S-A.pdf` (~445 KB).

Ninguno devolvió DESTINATARIO_BLOQUEADO ni EMAIL_INVALIDO.

**Resultado de la compuerta técnica: CUMPLIDA (5 de 5).**

**Estado del correo al cierre:** HABILITADO en `xps_pricing` (validado contra Tencent antes de guardar); DESHABILITADO en `xps_pricing_test`.

### 3.5 Compuerta visual (D-AUT-2b)

**(b) visual: PENDIENTE de François.** Revisar en los buzones:
- el diseño del correo;
- que el PDF abra con el formato oficial;
- que "Responder" vaya a pricing@xpress.ec;
- que la copia oculta llegue a pricing@xpress.ec;
- que no haya enlace de baja.

Si encuentra algo, se corrige como primer punto de F5.

### 3.6 Controles del cierre

- **Canario de encoding:** `200 OK, 0 con fallas, 200 revisados` (2026-10-16).
- **Control de secretos sobre los archivos visibles para git y sobre toda la historia:** 0 apariciones de la contraseña de la base (texto y codificada), JWT_SECRET, CONFIG_CIFRADO_KEY, el SecretId y la SecretKey de Tencent, e "IKID" real.
  - Las 2 coincidencias de "BEGIN PRIVATE KEY" y `"service_account"` son el texto del acta de entregas que describe el control; no son llaves.
- **Llaves de Tencent en todo el proyecto, incluido el `.env`:** 0. Las llaves viven solo cifradas en `config_correo`.
- **git status:** sin `.env` ni `salidas/`.

## 4. Decisiones

| N° | Decisión |
|---|---|
| D-F4-1 | 1 lb = 0.45359237 kg y 1 in = 2.54 cm, exactos, en Decimal. El motor trabaja en kg a 3 decimales y el volumétrico en cm |
| D-F4-2 | Lo capturado en libras y pulgadas se guarda tal cual y de ahí se derivan kg y cm. Una tarifa en LB usa lo capturado si gana el peso real (H-F4-1) |
| D-F4-3 | PCT_RECIBO: cantidad = base / 100 y precio = porcentaje. Base = líneas de Recibo de Caja incluidas, sin PCT_RECIBO. Con base 0 la línea vale 0, con aviso; el mínimo solo con base > 0 (H-F4-4). Bloque fiscal según la regla de F3 (país del puerto, H-F4-3) |
| D-F4-4 | Los datos de la empresa van en `config_empresa` (una fila) y se copian a la foto al emitir (H-F4-17, aprobado) |
| D-F4-5 | Las llaves de Tencent van cifradas con Fernet (`CONFIG_CIFRADO_KEY`). Sin esa llave el correo queda "No configurado" y el sistema arranca igual |
| D-F4-6 | Envío: validaciones → PDF desde la foto congelada fuera del bloqueo → `SELECT … FOR UPDATE` → envío → bitácora y auditoría (H-F4-14) |
| D-F4-7 | Errores traducidos por código (B9). El código interno va a la bitácora y la respuesta cruda de Tencent queda solo en `respuesta_proveedor` (H-F4-21) |
| D-F4-8 | Prueba real en `xps_pricing_test` (D-AUT-3), con 5 correos (D-AUT-4) |

## 5. Huecos

- **Aprobados por François:** H-F4-1 a H-F4-16 (Parada F4-1); H-F4-17; H-F4-18 a H-F4-29 (D-AUT-1).
- **Nuevo, H-F4-30 (decidido en la prueba real):** el sistema envía al contacto de la cotización, que queda congelado al emitir. Para mandar un correo por contacto sin alterar una emitida, se emitieron 5 cotizaciones iguales, cada una con su contacto; así cada PDF muestra el email correcto de su destinatario.

## 6. Desvíos

- **`desde_kg` en una tarifa por libra** significa "desde, en libras". La columna conserva su nombre (H-F4-2).
- **`preparar()` del script de F3** reutiliza catálogos existentes y acepta otro RUC, para servir a las pruebas de regresión. Su `main()` sigue abortando ante choques. Aprobado por D-AUT-1.
- **Commits del 2026-10-16, no del día de la Regla 18 (2026-10-15).** La compuerta técnica dependía de los correos de prueba, que llegaron el 2026-10-16.

## 7. Dependencias nuevas (versiones fijas)

| Paquete | Versión | Uso |
|---|---|---|
| `cryptography` | 50.0.2 | Cifrado Fernet |
| `tencentcloud-sdk-python-ses` | 3.1.135 | SDK de correo; se importa solo en `app/services/tencent_ses.py` |
| `tencentcloud-sdk-python-common` | 3.1.188 | Dependencia del SDK (H-F4-28) |

Las tres instalan en Python 3.13.14.

## 8. Incidentes

- **2026-10-14, 10:03:** el proxy cortó la conexión a mitad de la suite. La corrida se descartó y se repitió completa el 2026-10-15.
- **Ventana de push:** el sistema de permisos de Claude Code bloquea el push. Lo ejecuta François (D-AUT-9).
- **Llaves en el chat:** las llaves de Tencent se pegaron en el chat. Se recomienda rotar la SecretKey de `pricing-ses` (`docs/go-live/README.md`, punto 5).

## 9. Deuda

| Nivel | Deuda |
|---|---|
| Baja | `StarletteDeprecationWarning` del cliente de pruebas (documentado en F5-A4) |
| Baja | El PDF tarda unos segundos la primera vez por el arranque de Chromium; se genera a pedido y no se guarda |
| Baja | Las condiciones generales y la cláusula fundamental están pendientes de revisión legal (no bloquea) |

## 10. Pendientes

1. Compuerta visual (b) de François.
2. Rotar la SecretKey de Tencent después de la prueba.
3. Copiar `CONFIG_CIFRADO_KEY` del `.env` al gestor de contraseñas. En F5 va a Secret Manager con el mismo valor.

## 11. Avance

F0 5 % ✅ · F1 15 % ✅ · F2 25 % ✅ · F3 30 % ✅ · F4 15 % ✅ · **proyecto 90 %**. Sigue F5 (auditoría, deuda, despliegue y verificación final).

## Anexo · decisiones de François del 2026-10-16

- **(b) visual: APROBADA por François el 2026-10-16** (D-FIN-1). El diseño del correo quedó excelente y la copia oculta llega bien. Con esto la compuerta de F4 queda completa: técnica y visual.
- **Riesgo aceptado por François (D-FIN-2):** no se rotan la SecretKey de Tencent (aunque se pegó en el chat) ni la contraseña de `pricing_app`. Sale de los pendientes y no se vuelve a proponer.
- **CONFIG_CIFRADO_KEY (D-FIN-3):** pasa directo del `.env` a Secret Manager por la entrada estándar de gcloud, sin mostrarse. Secret Manager queda como copia de respaldo de François; reemplaza el pendiente "copiar al gestor de contraseñas".
- **Pendientes de la sección 10:** los tres quedan resueltos o reemplazados por este anexo.

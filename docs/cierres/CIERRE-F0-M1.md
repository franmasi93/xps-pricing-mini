# Acta de cierre — F0 + M1 Seguridad

| Campo | Valor |
|---|---|
| Proyecto | XPS-Pricing-Mini |
| Fases | F0 (esqueleto) y M1 (Seguridad) |
| Documento rector | `docs/XPS-Pricing-Mini_Arquitectura_V1.0.md` |
| Fecha de cierre | 2026-10-02 |
| Decisor | François Ramírez — Gerente General |
| Avance del proyecto | ~10 % |

---

## 1. Alcance cerrado

**F0 — Esqueleto**
- Repositorio git (rama `main`), `.gitignore` creado antes que cualquier otro archivo, `.env.example` con las 15 variables de §5.1.
- `app/config.py` (pydantic-settings): obligatorias `APP_ENV`, `DATABASE_URL`, `DATABASE_URL_TEST`, `JWT_SECRET`, `JWT_EXPIRA_MIN`; con valor por defecto `IVA_TASA`, `COT_PREFIJO`, `MONEDA_BASE`; opcionales hasta F4 las de Tencent SES. Valida el prefijo `postgresql+psycopg://`, un solo `@` y host legible en las URL, `JWT_SECRET` de 64+ caracteres y que dev y test sean bases distintas. Los errores nombran la variable, nunca su valor.
- `app/db.py` (SQLAlchemy 2.0 + psycopg v3), Alembic apuntando a `DATABASE_URL` o `DATABASE_URL_TEST` con `APP_ENV=test`.
- Harness de tests con SAVEPOINT (§16.1) y canario de aislamiento permanente.
- `scripts/canario_encoding.py`.

**M1 — Seguridad**
- Tablas `rol`, `permiso`, `rol_permiso`, `usuario` con constraints nombrados; email único sin distinguir mayúsculas (`uq_usuario_email_lower`) y guardado en minúsculas (`ck_usuario_email_minusculas`).
- Migración `0001` escrita a mano con el seed RBAC de §6.2: 4 roles, 15 permisos, 38 pares.
- Seguridad: argon2, JWT HS256 (`sub`, `tv`, `iat`, `exp`), validación por request de usuario activo y `token_version`, login con mensaje genérico y hash ficticio, bloqueo de 15 min al 5º fallo, `forzar_cambio_password` con 403 `PASSWORD_CAMBIO_REQUERIDO`.
- `core/rbac.py`: `require_permiso()` y `tiene_permiso()`, con permisos leídos de la BD.
- Endpoints `/v1`: `GET /salud`, `POST /auth/login`, `GET /auth/yo`, `POST /auth/cambiar-password`, `GET /roles`, `GET|POST /usuarios`, `GET|PATCH /usuarios/{id}`, `POST /usuarios/{id}/restablecer-password`. Sin DELETE (405).
- Reglas: un admin no puede desactivarse ni quitarse el rol (409); siempre queda al menos un admin activo (`SELECT … FOR UPDATE`, 409); email duplicado → 409; `IntegrityError` nunca termina en 500.
- Pantallas en `/app`: login, cambiar contraseña, inicio y usuarios. Una sola hoja de estilos (`frontend/css/xps-pricing.css`).
- Scripts de consola: `scripts/crear_admin.py` y `scripts/restablecer_admin.py`.

## 2. Evidencia

### 2.1 Regla 18 doble (base virgen, 2026-10-02)

Cada ciclo: procesos Python del proyecto detenidos → `DROP DATABASE` / `CREATE DATABASE xps_pricing_test` (conectado a `postgres` como `pricing_app`, 0 conexiones abiertas) → `alembic upgrade head` (`0001 (head)`) → suite completa.

```
Ciclo 1:  100 tests collected in 0.04s
          100 passed, 1 warning in 190.83s (0:03:10)
Ciclo 2:  100 tests collected in 0.05s
          100 passed, 1 warning in 178.46s (0:02:58)
```

0 failed, 0 errors, 0 skipped; N = recolectados = 100 en ambas corridas. Sin `OperationalError` de conexión.

Composición de N = 100: 89 de la Parte 3 (T01–T63 con parametrizaciones) + 4 frontend (T64 ×3 rutas, T65) + 3 `restablecer_admin` (T70–T72) + 2 canario de aislamiento (T66–T67) + 2 configuración (T68–T69).

### 2.2 Canario de encoding (archivos de texto del commit)

```
Canario de encoding: 63 OK, 0 con fallas, 63 revisados
```

Los dos PNG de `frontend/img/` no aplican. El acta se revisa por separado.

### 2.3 Seed RBAC (después de la Regla 18)

```
xps_pricing       rol=4 permiso=15 rol_permiso=38 usuario=1 alembic_version=0001 por_rol={'admin': 15, 'comercial': 6, 'gerencia': 6, 'pricing': 11}
xps_pricing_test  rol=4 permiso=15 rol_permiso=38 usuario=0 alembic_version=0001 por_rol={'admin': 15, 'comercial': 6, 'gerencia': 6, 'pricing': 11}
```

La migración se probó con up → down → up en ambas bases (Parte 2).

## 3. Desvíos

| Desvío | Motivo |
|---|---|
| Python 3.13.14 en lugar de 3.12 | Autorizado por François; §3.1 se actualiza en la próxima versión del documento. |
| `SQLAlchemy==2.0.36`, `alembic==1.14.0`, `psycopg[binary]==3.2.3` (versiones de XPS-Reborn) | Smart App Control bloqueaba las DLL de SQLAlchemy 2.1.1 y psycopg-binary 3.3.6; François no lo desactiva. Reborn usa además `psycopg2-binary`; el criterio aceptado fue que psycopg v3 importa bien. |
| Logos `frontend/img/xpress-logo.png` y `xpress-logo-blanco.png` en lugar de `logo-xpress.png` (§4) | Archivos entregados por François; no se renombran. |
| `crear_token(usuario_id, token_version)` en lugar de recibir el usuario | `core/security.py` no depende de los modelos. Sin cambio de comportamiento. |
| T64 parametrizado con 3 rutas (`/`, `/app`, `/app/`) | +2 tests respecto del diseño. |
| `forzar_cambio_password = False` en `restablecer_password_admin` | La contraseña la elige el propio admin en su consola, no es temporal. Mismo criterio que `crear_admin_inicial`. |

## 4. Cambios por orden directa de François

- Rediseño de las pantallas con `docs/xpressdesignsystem.md`; reemplaza la regla 4 del prompt de la Parte 4 (encabezado navy con logo blanco).
- Login nuevo (panel navy con logo blanco, capacidades, formulario con "Mostrar" y aviso de Bloq Mayús) y ajuste de T65, que ahora verifica `xpress-logo-blanco.png`. Las tres capacidades del login describen el alcance planificado; hoy solo existe M1.
- Corrección del logo deformado en el login y el menú lateral (el contenedor flex lo estiraba).
- Cambio de contraseña desde el login, reutilizando `/auth/login` (sujeto al bloqueo) y `/auth/cambiar-password`; sin endpoints nuevos.
- `scripts/restablecer_admin.py`, `restablecer_password_admin` y T70–T72 (fuera del alcance original; motivo: François no recordaba la contraseña del admin). Confirmación explícita `s/N` en `restablecer_admin.py` y también en `crear_admin.py`.
- Pie del login: "XPRESS LOGISTICS XPS S.A. · Sistema de importaciones y exportaciones".
- Razón social que emite las cotizaciones (F3): **"XPRESS LOGISTICS XPS S.A."**, sin "POSTAL". Este sistema es el de importaciones y exportaciones.
- El TRASPASO no entra al repo: es un documento de trabajo entre chats y describe una debilidad de credenciales pendiente de rotar.

## 5. Incidentes

| Incidente | Resolución |
|---|---|
| El canario de encoding se escribió corrupto: la herramienta de escritura convirtió las secuencias de escape Unicode (barra invertida seguida de la letra u) en caracteres reales, y el canario falló sobre sí mismo. | Patrones construidos con `chr()`; control negativo con archivos corruptos en el scratchpad. |
| La contraseña de `pricing_app` contenía `@` sin codificar en las URL → `getaddrinfo failed`. | François rehízo el `.env` codificando la contraseña en URL; se agregó la validación de un solo `@` y host legible en `config.py`, con test. |
| `alembic init` generó `alembic/README`, fuera de alcance. | Borrado (aprobado). |
| Cortes de conexión intermitentes el 2026-10-01 (~10:05 y ~10:08): la primera conexión de la corrida tardaba ~55 s y terminaba en "server closed the connection unexpectedly". | Causa no confirmada (falta el log del proxy). Un diagnóstico de 10 conexiones nuevas dio 10/10 ok (~2,1 s cada una). **No se reprodujo en la Regla 18.** Queda abierto para observación. |
| Atribuí el primer corte a un reinicio del proxy; no lo era (el proxy activo había arrancado a las 09:12). | Autocorrección registrada. |
| El servidor local lanzado desde la sesión del ejecutor se detuvo al llegar a su tiempo máximo (2 h); François abrió la app en `:5500` (Live Server de VS Code), que no tiene la API. | Se indicó encender uvicorn desde PowerShell y usar `http://127.0.0.1:8000/app`. |

## 6. Verificación en navegador

Checklist de 14 puntos (vigente; reemplazó al de 12 por el rediseño, el login nuevo y el cambio de contraseña desde el login):

1. `127.0.0.1:8000/app` → login nuevo, panel navy, logo sin deformar.
2. "Mostrar" contraseña y Bloq Mayús.
3. Entrar como admin → menú lateral blanco, perfil al pie, Inicio y Usuarios.
4. Crear usuarios de pricing, comercial y gerencia → Activo.
5. Email repetido → "Ya existe un usuario con ese email".
6. Editar el propio usuario → Rol y Activo bloqueados con explicación.
7. Entrar con comercial → cambio obligatorio; menú solo Inicio.
8. `/app/usuarios.html` a mano → "No tiene permiso para esta acción".
9. Repetir 7 y 8 con pricing y gerencia.
10. Cambiar contraseña desde el login.
11. 5 contraseñas incorrectas → "Cuenta bloqueada… 15 minutos".
12. Restablecer contraseña como admin → vuelve a entrar.
13. Ancho 375 px sin scroll horizontal.
14. Ninguna línea roja en la Console.

**Resultado:** aprobado por François **de forma global, sin desglose por punto**.

**Constancia:** al momento de la Regla 18, la base `xps_pricing` tiene un solo usuario (el admin `francois-ramart@outlook.com`, último ingreso 2026-10-02 14:53:46 UTC). Se constata el ingreso del admin (puntos 1 y 3); la base no muestra los usuarios de prueba que crean los puntos 4 a 12. François mantuvo la aprobación global.

## 7. Deuda

| Prioridad | Deuda |
|---|---|
| Baja | `StarletteDeprecationWarning` (httpx con el TestClient de FastAPI 0.142.2); no se cambia a `httpx2` por ahora. |
| Baja | Suite lenta (~1,8–1,9 s por test; 100 tests en ~3 min). Se revisa después del cierre. |
| F3 | Las fuentes (Inter, JetBrains Mono) se cargan desde Google Fonts; el PDF las necesita dentro del repo. |
| Documentación | `docs/xpressdesignsystem.md` menciona `dashboard.html` e `index.html` como referencia y no existen en el repo; lo corrige François en una próxima versión. |

## 8. Pendientes abiertos

- **Obligatorio antes del go-live:** rotar la contraseña de `pricing_app` a 24+ caracteres (quedó expuesta en una captura; mitigado porque la instancia solo acepta conexiones por el Auth Proxy con IAM).
- Restringir `pricing_app` a sus dos bases.
- Corregir 'POSTAL' en el encabezado del TRASPASO (documento de trabajo, fuera del repo). El encabezado de la Arquitectura V1.0 se corrigió en este commit.
- P1 a P10 del TRASPASO.
- Corte de conexión intermitente del 2026-10-01: sin causa confirmada (ver §5).

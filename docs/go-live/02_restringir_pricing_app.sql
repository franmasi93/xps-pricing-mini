-- B7 · Restringir pricing_app a sus bases (xps_pricing y xps_pricing_test).
-- Lo ejecuta François con el usuario postgres. pricing_app no puede hacerlo: no es dueño de esas bases ni superusuario.
-- Dónde ejecutarlo: Google Cloud Console → SQL → xpress-db-reborn-v2 → Cloud SQL Studio → base "postgres" → usuario
-- "postgres". También sirve psql por el proxy local.
--
-- Situación al 2026-10-16 (consulta de solo lectura con pricing_app):
--   bases: cloudsqladmin, postgres, xpress_dev, xpress_test, xps_pricing, xps_pricing_test
--   roles con login: postgres, pricing_app, xpress_app (XPS-Reborn)
--   conexiones activas: xpress_test ← xpress_app; xps_pricing ← pricing_app
--   PUBLIC (y por eso pricing_app) puede conectarse a TODAS las bases.
--
-- Qué hace: en las dos bases de XPS-Reborn concede CONNECT a xpress_app y se lo quita a PUBLIC. Así pricing_app ya no
-- entra a ellas y XPS-Reborn sigue funcionando.
-- No se tocan cloudsqladmin, que es interna de Cloud SQL, ni postgres. pricing_app necesita entrar a postgres para
-- recrear xps_pricing_test en la Regla 18, y ahí no tiene permisos sobre datos.

-- 1) Verificación antes del cambio.
SELECT d.datname AS base,
       has_database_privilege('public', d.datname, 'CONNECT') AS public_conecta,
       has_database_privilege('pricing_app', d.datname, 'CONNECT') AS pricing_app_conecta,
       has_database_privilege('xpress_app', d.datname, 'CONNECT') AS xpress_app_conecta
FROM pg_database d
WHERE NOT d.datistemplate
ORDER BY d.datname;

-- 2) Cambio, en una sola transacción.
BEGIN;
GRANT CONNECT ON DATABASE xpress_dev TO xpress_app;
GRANT CONNECT ON DATABASE xpress_test TO xpress_app;
GRANT CONNECT ON DATABASE xps_pricing TO pricing_app;
GRANT CONNECT ON DATABASE xps_pricing_test TO pricing_app;
REVOKE CONNECT ON DATABASE xpress_dev FROM PUBLIC;
REVOKE CONNECT ON DATABASE xpress_test FROM PUBLIC;
REVOKE CONNECT ON DATABASE xpress_dev FROM pricing_app;
REVOKE CONNECT ON DATABASE xpress_test FROM pricing_app;
COMMIT;

-- 3) Verificación después: repetir la consulta del paso 1. Esperado:
--    xpress_dev y xpress_test → public_conecta = false, pricing_app_conecta = false, xpress_app_conecta = true.
--    xps_pricing y xps_pricing_test → pricing_app_conecta = true.
--    Después, abrir XPS-Reborn y comprobar que sigue funcionando.
--
-- Para deshacer (si XPS-Reborn dejara de conectarse):
--    GRANT CONNECT ON DATABASE xpress_dev TO PUBLIC;
--    GRANT CONNECT ON DATABASE xpress_test TO PUBLIC;

-- ===== RESULTADO DE LA APLICACIÓN (2026-10-16, D-CIE-3) =====
-- Se ejecutó como postgres. La contraseña de postgres se restableció y quedó SOLO en Secret Manager: secreto
-- xps-sql-postgres. Las 7 sentencias del paso 2 corrieron sin error; la de xps_pricing_test se omitió porque pricing_app
-- ya es su dueño. Después:
--   xpress_dev        public=false  pricing_app=TRUE   xpress_app=true
--   xpress_test       public=TRUE   pricing_app=TRUE   xpress_app=true
--   xps_pricing       public=true   pricing_app=true
--   xps_pricing_test  public=true   pricing_app=true
-- Restricción PARCIAL (hueco H-F5-6):
--   * xpress_dev: pricing_app sigue entrando porque es MIEMBRO de cloudsqlsuperuser, dueño de esa base.
--   * xpress_test: el REVOKE de PUBLIC no tuvo efecto (PostgreSQL solo avisa): el dueño es xpress_app y postgres no es
--     miembro de ese rol.
-- xpress_app conserva el acceso a las dos bases; no hubo que deshacer nada.
-- Para completarlo (decisión de François; puede afectar las migraciones de Pricing):
--   1) ALTER DATABASE xps_pricing OWNER TO pricing_app;   -- pricing_app conserva sus derechos sobre su base
--   2) REVOKE cloudsqlsuperuser FROM pricing_app;         -- deja de heredar derechos de dueño sobre xpress_dev
--   3) Como xpress_app (o un miembro de ese rol): REVOKE CONNECT ON DATABASE xpress_test FROM PUBLIC;
--   Después: Regla 18 y una migración de prueba para confirmar que pricing_app sigue migrando.

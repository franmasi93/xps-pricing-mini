-- B7 · Restringir pricing_app a sus dos bases (xps_pricing y xps_pricing_test).
-- Lo ejecuta François como usuario postgres (Cloud SQL Studio o psql por el proxy). NO lo ejecuta el EJECUTOR.
--
-- PostgreSQL concede CONNECT a PUBLIC en cada base nueva. Por eso pricing_app puede abrir conexiones a las bases de
-- otros sistemas de la misma instancia (aunque no tenga permisos sobre sus tablas).
-- La forma limpia de cerrarlo es quitar el CONNECT a PUBLIC en esas bases y concederlo solo a sus dueños.
-- AVISO: antes de quitar el CONNECT a PUBLIC en una base de otro sistema (por ejemplo XPS-Reborn), confirme qué roles
-- se conectan a ella y concédaselo explícitamente; si no, ese sistema puede dejar de conectarse.

-- 1) Verificación: bases de la instancia, su dueño y si PUBLIC o pricing_app pueden conectarse.
SELECT d.datname AS base,
       pg_get_userbyid(d.datdba) AS dueno,
       has_database_privilege('public', d.datname, 'CONNECT') AS public_conecta,
       has_database_privilege('pricing_app', d.datname, 'CONNECT') AS pricing_app_conecta
FROM pg_database d
WHERE NOT d.datistemplate
ORDER BY d.datname;

-- 2) pricing_app conserva sus dos bases (explícito, por si luego se quita el CONNECT a PUBLIC también aquí).
GRANT CONNECT ON DATABASE xps_pricing TO pricing_app;
GRANT CONNECT ON DATABASE xps_pricing_test TO pricing_app;

-- 3) Por cada base que NO sea de Pricing (reemplace <base> y <rol_del_sistema> según la verificación del paso 1):
--    BEGIN;
--    GRANT CONNECT ON DATABASE <base> TO <rol_del_sistema>;   -- uno por cada rol que usa esa base
--    REVOKE CONNECT ON DATABASE <base> FROM PUBLIC;
--    REVOKE CONNECT ON DATABASE <base> FROM pricing_app;      -- por si se le concedió explícitamente
--    COMMIT;
--
--    Bases de otros sistemas encontradas el 2026-10-15 (consulta de solo lectura): ver la lista al final del archivo.

-- 4) Comprobación final: repetir la consulta del paso 1. Esperado: pricing_app_conecta = true solo en xps_pricing y
--    xps_pricing_test.

-- Propósito:
--   Agregar únicamente los privilegios mínimos que requiere H3.3 para el
--   flujo de asignación inicial sobre un ambiente ya existente.
--
-- Alcance:
--   - no modifica datos
--   - no revoca privilegios preexistentes ajenos a esta migración
--   - no toca AWS automáticamente; solo queda versionado para ejecución
--     controlada por un administrador autorizado
--
-- Ambiente objetivo:
--   AWS DEV / ambientes ya provisionados con drift histórico de privilegios
--
-- Relación con 001_create_tpi_app_role.sql:
--   001 sigue siendo el bootstrap base para ambientes nuevos.
--   006 representa la evolución incremental necesaria para un ambiente existente.
--
-- Preflight:
--   Verificar que el resultado actual coincide con el drift documentado antes
--   de aplicar los grants.
--
-- Rollback:
--   Revoke únicamente los privilegios agregados por este script.

BEGIN;

SELECT
    has_schema_privilege('tpi_app', 'tpi', 'USAGE') AS schema_usage_before;

SELECT
    table_name,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'SELECT') AS can_select_before,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'INSERT') AS can_insert_before,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'UPDATE') AS can_update_before,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'DELETE') AS can_delete_before
FROM (
    VALUES
        ('asesores'),
        ('asignaciones'),
        ('auditoria'),
        ('leads')
) AS t(table_name)
ORDER BY table_name;

GRANT SELECT ON TABLE tpi.asesores TO tpi_app;

GRANT SELECT, INSERT ON TABLE tpi.asignaciones TO tpi_app;

GRANT INSERT ON TABLE tpi.auditoria TO tpi_app;

SELECT
    has_schema_privilege('tpi_app', 'tpi', 'USAGE') AS schema_usage_after;

SELECT
    table_name,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'SELECT') AS can_select_after,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'INSERT') AS can_insert_after,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'UPDATE') AS can_update_after,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'DELETE') AS can_delete_after
FROM (
    VALUES
        ('asesores'),
        ('asignaciones'),
        ('auditoria'),
        ('leads')
) AS t(table_name)
ORDER BY table_name;

COMMIT;

-- Rollback propuesto:
-- BEGIN;
-- REVOKE INSERT ON TABLE tpi.auditoria FROM tpi_app;
-- REVOKE SELECT, INSERT ON TABLE tpi.asignaciones FROM tpi_app;
-- REVOKE SELECT ON TABLE tpi.asesores FROM tpi_app;
-- COMMIT;

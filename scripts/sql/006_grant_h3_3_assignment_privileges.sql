-- H3.3 incremental privilege migration for an already-provisioned environment.
--
-- Scope:
--   - no business data changes
--   - no revocations beyond the rollback block at the end
--   - no schema changes
--   - aborts if the observed AWS DEV baseline is not the expected drift state
--
-- Expected preflight for AWS DEV:
--   schema tpi USAGE      = true
--   asesores SELECT       = false
--   asignaciones SELECT   = false
--   asignaciones INSERT   = false
--   auditoria INSERT      = false
--   leads SELECT          = true
--   leads UPDATE          = true
--
-- Rollback:
--   Revoke only the privileges added by this migration.

BEGIN;

DO $$
DECLARE
    v_schema_usage boolean;
    v_asesores_select boolean;
    v_asignaciones_select boolean;
    v_asignaciones_insert boolean;
    v_auditoria_insert boolean;
    v_leads_select boolean;
    v_leads_update boolean;
BEGIN
    SELECT
        has_schema_privilege('tpi_app', 'tpi', 'USAGE'),
        has_table_privilege('tpi_app', 'tpi.asesores', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.asignaciones', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.asignaciones', 'INSERT'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'INSERT'),
        has_table_privilege('tpi_app', 'tpi.leads', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.leads', 'UPDATE')
    INTO
        v_schema_usage,
        v_asesores_select,
        v_asignaciones_select,
        v_asignaciones_insert,
        v_auditoria_insert,
        v_leads_select,
        v_leads_update;

    IF NOT (
        v_schema_usage
        AND NOT v_asesores_select
        AND NOT v_asignaciones_select
        AND NOT v_asignaciones_insert
        AND NOT v_auditoria_insert
        AND v_leads_select
        AND v_leads_update
    ) THEN
        RAISE EXCEPTION
            '006 preflight failed: expected AWS DEV drift baseline does not match the actual privilege state';
    END IF;
END
$$;

GRANT SELECT ON TABLE tpi.asesores TO tpi_app;

GRANT SELECT, INSERT ON TABLE tpi.asignaciones TO tpi_app;

GRANT INSERT ON TABLE tpi.auditoria TO tpi_app;

DO $$
DECLARE
    v_schema_usage boolean;
    v_asesores_select boolean;
    v_asignaciones_select boolean;
    v_asignaciones_insert boolean;
    v_auditoria_insert boolean;
    v_leads_select boolean;
    v_leads_update boolean;
BEGIN
    SELECT
        has_schema_privilege('tpi_app', 'tpi', 'USAGE'),
        has_table_privilege('tpi_app', 'tpi.asesores', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.asignaciones', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.asignaciones', 'INSERT'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'INSERT'),
        has_table_privilege('tpi_app', 'tpi.leads', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.leads', 'UPDATE')
    INTO
        v_schema_usage,
        v_asesores_select,
        v_asignaciones_select,
        v_asignaciones_insert,
        v_auditoria_insert,
        v_leads_select,
        v_leads_update;

    IF NOT (
        v_schema_usage
        AND v_asesores_select
        AND v_asignaciones_select
        AND v_asignaciones_insert
        AND v_auditoria_insert
        AND v_leads_select
        AND v_leads_update
    ) THEN
        RAISE EXCEPTION
            '006 postflight failed: expected minimum privilege contract was not reached';
    END IF;
END
$$;

COMMIT;

-- Rollback:
-- BEGIN;
-- REVOKE INSERT ON TABLE tpi.auditoria FROM tpi_app;
-- REVOKE SELECT, INSERT ON TABLE tpi.asignaciones FROM tpi_app;
-- REVOKE SELECT ON TABLE tpi.asesores FROM tpi_app;
-- COMMIT;

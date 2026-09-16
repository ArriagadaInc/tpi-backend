-- H3.3.3 / migracion 007 rollback: REVOKE SELECT y DROP VIEW.
--
-- Idempotente y transaccional: solo actua si la vista existe. No toca tpi.auditoria ni
-- ningun otro privilegio; revierte unicamente el objeto y el grant creados por el forward.
--
-- Aplicar solo tras evaluar el rollback conforme al Harness (aws-failure-analysis y
-- rollback_authorization); nunca de forma automatica ni por eliminacion directa.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_views
        WHERE schemaname = 'tpi' AND viewname = 'v_asignacion_auditoria'
    ) THEN
        EXECUTE 'REVOKE SELECT ON tpi.v_asignacion_auditoria FROM tpi_app';
        EXECUTE 'DROP VIEW tpi.v_asignacion_auditoria';
    END IF;
END
$$;

COMMIT;

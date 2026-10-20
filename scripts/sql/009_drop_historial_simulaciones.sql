-- SIM-HISTORIAL-LINEA-TIEMPO / migracion 009 rollback: REVOKE SELECT y DROP VIEW.
--
-- Idempotente y transaccional: solo actua si la vista existe. No toca tpi.auditoria ni
-- ningun otro privilegio; revierte unicamente el objeto y el grant creados por el forward.
-- No modifica ni ejecuta 005/006/007/008.
--
-- Aplicar solo tras evaluar el rollback conforme al Harness (aws-failure-analysis y
-- rollback_authorization); nunca de forma automatica ni por eliminacion directa.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_views
        WHERE schemaname = 'tpi' AND viewname = 'v_historial_simulaciones'
    ) THEN
        EXECUTE 'REVOKE SELECT ON tpi.v_historial_simulaciones FROM tpi_app';
        EXECUTE 'DROP VIEW tpi.v_historial_simulaciones';
    END IF;
END
$$;

COMMIT;

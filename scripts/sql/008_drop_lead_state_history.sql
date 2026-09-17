-- H3.3.4 / migracion 008 rollback: REVOKE SELECT, DROP VIEW y DROP INDEX.
--
-- Idempotente y transaccional: solo actua si la vista/indice existen. No toca
-- tpi.auditoria (ni sus datos) ni ningun otro privilegio; revierte unicamente los
-- objetos creados por el forward de la migracion 008. No modifica ni ejecuta 005/006/007.
--
-- Aplicar solo tras evaluar el rollback conforme al Harness (aws-failure-analysis y
-- rollback_authorization); nunca de forma automatica ni por eliminacion directa.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_views
        WHERE schemaname = 'tpi' AND viewname = 'v_historial_estado_lead'
    ) THEN
        EXECUTE 'REVOKE SELECT ON tpi.v_historial_estado_lead FROM tpi_app';
        EXECUTE 'DROP VIEW tpi.v_historial_estado_lead';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'tpi'
          AND tablename = 'auditoria'
          AND indexname = 'auditoria_state_history_idx'
    ) THEN
        EXECUTE 'DROP INDEX tpi.auditoria_state_history_idx';
    END IF;
END
$$;

COMMIT;

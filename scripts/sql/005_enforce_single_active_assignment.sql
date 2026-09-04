-- Enforce a single active assignment per lead.
-- Safe to apply after validating that no duplicated active rows exist.
-- Rollback:
--   DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM tpi.asignaciones
        WHERE estado_asignacion = 'activa'
        GROUP BY id_lead
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Cannot create unique active assignment index because duplicate active assignments exist';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS asignaciones_one_active_per_lead_uq
    ON tpi.asignaciones (id_lead)
    WHERE estado_asignacion = 'activa';

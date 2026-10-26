-- CRM-AGENDA-1-MIGRACION / migracion 010 rollback: revierte la ampliacion de tpi.citas y
-- tpi.asesores para la agenda de reuniones.
--
-- Idempotente y transaccional: solo actua sobre los objetos y columnas creados por el
-- forward (scripts/sql/010_extend_citas_agenda.sql). Aborta con un mensaje claro si
-- tpi.citas tiene filas, para no perder reuniones.
--
-- No elimina la tabla tpi.citas, no elimina la extension btree_gist y no toca
-- tpi.auditoria ni las demas tablas.
--
-- Aplicar solo tras evaluar el rollback conforme al Harness; nunca de forma automatica ni
-- por eliminacion directa.

BEGIN;

DO $$
DECLARE
    v_filas bigint;
BEGIN
    SELECT count(*) INTO v_filas FROM tpi.citas;
    IF v_filas > 0 THEN
        RAISE EXCEPTION
            '010 rollback failed: tpi.citas tiene % filas; la reversa no se aplica para no perder reuniones',
            v_filas;
    END IF;
END
$$;

-- Revoca unicamente los privilegios nuevos concedidos a tpi_app por el forward.
REVOKE SELECT, INSERT, UPDATE ON tpi.citas FROM tpi_app;

-- Restricciones e indices creados por el forward.
ALTER TABLE tpi.citas DROP CONSTRAINT IF EXISTS citas_responsable_no_superposicion_excl;
DROP INDEX IF EXISTS tpi.citas_one_agendada_per_lead_uq;
DROP INDEX IF EXISTS tpi.citas_fecha_hora_idx;
ALTER TABLE tpi.citas DROP CONSTRAINT IF EXISTS citas_estado_cita_check;
ALTER TABLE tpi.citas DROP CONSTRAINT IF EXISTS citas_fecha_hora_fin_gt_inicio_chk;

-- Columnas nuevas de tpi.citas.
ALTER TABLE tpi.citas
    DROP COLUMN IF EXISTS fecha_hora_fin,
    DROP COLUMN IF EXISTS agendada_por_subject,
    DROP COLUMN IF EXISTS agendada_por_nombre,
    DROP COLUMN IF EXISTS nota,
    DROP COLUMN IF EXISTS motivo_cancelacion,
    DROP COLUMN IF EXISTS updated_at;

-- Revertir id_asesor a opcional (como estaba antes del forward).
ALTER TABLE tpi.citas ALTER COLUMN id_asesor DROP NOT NULL;

-- Columna nueva de tpi.asesores.
ALTER TABLE tpi.asesores DROP COLUMN IF EXISTS atiende_reuniones;

COMMIT;

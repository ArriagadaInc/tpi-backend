-- TPI AWS DEV only: seed the two development advisors used by H3.3.5.
--
-- Run MANUALLY by the human operator (never the Harness, never the Deployer) after
-- the D5 operational preflight documented in docs/H3_3_5_DEV_RUNBOOK.md.
-- Target: tpi-postgres-dev, database `tpi`, schema `tpi`, administrative role
-- (for example `tpi_admin`). NEVER run this script in staging or production.
--
-- This is a DEV-only artifact under scripts/sql/dev/. It is NOT a numbered migration
-- (scripts/sql/NNN_*) and must never be applied by any production pipeline.
--
-- Scope (strict):
--   * Asesor Desarrollo 1 and Asesor Desarrollo 2 only.
--   * No identities, no passwords, no hashes.
--   * No write to tpi.asignaciones.
--   * No grant changes (tpi_app keeps SELECT-only on tpi.asesores).
--
-- Idempotence contract (D6), per normalized name lower(nombre):
--   * absent                      -> INSERT (adopts the freshly generated UUID);
--   * exactly one compatible row  -> adopt its id_asesor (no-op, never overwritten);
--   * incompatible row            -> ABORT (whole transaction rolls back);
--   * ambiguous (more than one)   -> ABORT.
-- A second execution produces the same result and never duplicates or overwrites.

BEGIN;

DO $$
DECLARE
    v_database name;
    v_role text;
    v_nombre text;
    v_count integer;
    v_id_asesor uuid;
    v_rol text;
    v_estado text;
    advisors text[] := ARRAY['Asesor Desarrollo 1', 'Asesor Desarrollo 2'];
BEGIN
    -- Base validation
    v_database := current_database();
    IF v_database <> 'tpi' THEN
        RAISE EXCEPTION 'seed aborted: expected database "tpi", got "%"', v_database;
    END IF;

    -- Schema validation
    IF to_regclass('tpi.asesores') IS NULL THEN
        RAISE EXCEPTION 'seed aborted: tpi.asesores does not exist';
    END IF;

    -- User validation: the application role is SELECT-only on tpi.asesores and must
    -- never write. The operator must be a role with USAGE on tpi and INSERT on the table.
    v_role := current_user;
    IF v_role = 'tpi_app' THEN
        RAISE EXCEPTION 'seed aborted: tpi_app is SELECT-only on tpi.asesores';
    END IF;
    IF NOT has_schema_privilege(v_role, 'tpi', 'USAGE') THEN
        RAISE EXCEPTION 'seed aborted: current user "%" lacks USAGE on schema tpi', v_role;
    END IF;
    IF NOT has_table_privilege(v_role, 'tpi.asesores', 'INSERT') THEN
        RAISE EXCEPTION 'seed aborted: current user "%" lacks INSERT on tpi.asesores', v_role;
    END IF;

    FOREACH v_nombre IN ARRAY advisors LOOP
        SELECT count(*) INTO v_count
        FROM tpi.asesores
        WHERE lower(nombre) = lower(v_nombre);

        IF v_count = 0 THEN
            INSERT INTO tpi.asesores (nombre)
            VALUES (v_nombre)
            RETURNING id_asesor INTO v_id_asesor;
            RAISE NOTICE 'advisor "%" created, id_asesor=%', v_nombre, v_id_asesor;

        ELSIF v_count = 1 THEN
            SELECT id_asesor, rol, estado_disponibilidad
            INTO v_id_asesor, v_rol, v_estado
            FROM tpi.asesores
            WHERE lower(nombre) = lower(v_nombre);

            IF lower(v_rol) <> 'asesor' OR lower(v_estado) <> 'activo' THEN
                RAISE EXCEPTION
                    'seed aborted: existing advisor "%" is incompatible (rol=%, estado_disponibilidad=%)',
                    v_nombre, v_rol, v_estado;
            END IF;

            -- Compatible: adopt the existing UUID without touching the row.
            RAISE NOTICE 'advisor "%" adopted, id_asesor=%', v_nombre, v_id_asesor;

        ELSE
            RAISE EXCEPTION
                'seed aborted: ambiguous advisors for "%" (% rows)', v_nombre, v_count;
        END IF;
    END LOOP;

    -- Final self-verification (same transaction): each name must resolve to exactly
    -- one active advisor.
    FOREACH v_nombre IN ARRAY advisors LOOP
        SELECT count(*) INTO v_count
        FROM tpi.asesores
        WHERE lower(nombre) = lower(v_nombre)
          AND rol = 'asesor'
          AND estado_disponibilidad = 'activo';

        IF v_count <> 1 THEN
            RAISE EXCEPTION
                'seed aborted: verification failed for "%" (% active advisors)', v_nombre, v_count;
        END IF;
    END LOOP;
END
$$;

COMMIT;

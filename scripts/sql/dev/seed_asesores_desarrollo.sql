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
-- Idempotence contract (D6), per normalized name lower(btrim(nombre)):
--   * absent                      -> INSERT (adopts the freshly generated UUID);
--   * exactly one compatible row  -> adopt its id_asesor (no-op, never overwritten);
--   * incompatible row            -> ABORT (whole transaction rolls back);
--   * ambiguous (more than one)   -> ABORT.
-- A second execution produces the same result and never duplicates or overwrites.
--
-- The NOT NULL columns `rol` and `estado_disponibilidad` are set explicitly
-- ('asesor'/'activo'); the seed never relies on column defaults, which the versioned
-- DDL (scripts/init_test_database.py) declares WITHOUT defaults.

BEGIN;

DO $$
DECLARE
    v_expected_db text;
    v_role text;
    v_nombre text;
    v_count integer;
    v_id_asesor uuid;
    v_rol text;
    v_estado text;
    advisors text[] := ARRAY['Asesor Desarrollo 1', 'Asesor Desarrollo 2'];
BEGIN
    -- Base validation. Expected database defaults to `tpi`; the integration test
    -- overrides it with `SET tpi.seed_expected_database = current_database()` so the
    -- same SQL can be executed against the ephemeral PostgreSQL without weakening the
    -- DEV default.
    v_expected_db := COALESCE(
        NULLIF(current_setting('tpi.seed_expected_database', true), ''),
        'tpi'
    );
    IF current_database() <> v_expected_db THEN
        RAISE EXCEPTION
            'seed aborted: expected database "%", got "%"',
            v_expected_db, current_database();
    END IF;

    -- Schema validation.
    IF to_regclass('tpi.asesores') IS NULL THEN
        RAISE EXCEPTION 'seed aborted: tpi.asesores does not exist';
    END IF;

    -- User validation: the operator must actually hold USAGE on tpi and INSERT on
    -- tpi.asesores. The application role is SELECT-only on tpi.asesores, so it is
    -- rejected by the privilege check (no hardcoded role name).
    v_role := current_user;
    IF NOT has_schema_privilege(v_role, 'tpi', 'USAGE') THEN
        RAISE EXCEPTION 'seed aborted: current user "%" lacks USAGE on schema tpi', v_role;
    END IF;
    IF NOT has_table_privilege(v_role, 'tpi.asesores', 'INSERT') THEN
        RAISE EXCEPTION 'seed aborted: current user "%" lacks INSERT on tpi.asesores', v_role;
    END IF;

    FOREACH v_nombre IN ARRAY advisors LOOP
        SELECT count(*) INTO v_count
        FROM tpi.asesores
        WHERE lower(btrim(nombre)) = lower(btrim(v_nombre));

        IF v_count = 0 THEN
            INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad)
            VALUES (v_nombre, 'asesor', 'activo')
            RETURNING id_asesor INTO v_id_asesor;
            RAISE NOTICE 'advisor "%" created, id_asesor=%', v_nombre, v_id_asesor;

        ELSIF v_count = 1 THEN
            SELECT id_asesor, rol, estado_disponibilidad
            INTO v_id_asesor, v_rol, v_estado
            FROM tpi.asesores
            WHERE lower(btrim(nombre)) = lower(btrim(v_nombre));

            -- NULL-safe comparison: a NULL rol/estado is incompatible and must abort,
            -- not fall through silently.
            IF lower(v_rol) IS DISTINCT FROM 'asesor'
               OR lower(v_estado) IS DISTINCT FROM 'activo' THEN
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
        WHERE lower(btrim(nombre)) = lower(btrim(v_nombre))
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

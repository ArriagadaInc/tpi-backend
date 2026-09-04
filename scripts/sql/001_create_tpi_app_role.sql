-- Tu Pension Inteligente backoffice
-- Least-privilege role for application access to PostgreSQL / Amazon RDS.
--
-- Usage:
--   1. Connect with psql as an administrative role such as tpi_admin:
--        psql -h <rds-endpoint> -p 5432 -U tpi_admin -d tpi -W
--   2. Inside psql, run:
--        \set ON_ERROR_STOP on
--        \i scripts/sql/001_create_tpi_app_role.sql
--   3. Set or rotate the password interactively after the grants:
--        \password tpi_app
--
-- Notes:
-- - This script aligns with the state validated manually against Amazon RDS on
--   2026-08-07.
-- - Never commit a real password in this file, shell history, or versioned docs.

\set app_role tpi_app

DO $$
DECLARE
    target_role text := :'app_role';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = target_role) THEN
        EXECUTE format(
            'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
            target_role
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
            target_role
        );
    END IF;
END
$$;

COMMENT ON ROLE :"app_role" IS
    'Least-privilege application role for Tu Pension Inteligente backoffice';

GRANT CONNECT ON DATABASE tpi TO :"app_role";
GRANT USAGE ON SCHEMA tpi TO :"app_role";

GRANT SELECT ON TABLE
    tpi.catalogo_afp,
    tpi.catalogo_genero,
    tpi.catalogo_estado_civil,
    tpi.asesores
TO :"app_role";

-- H3.3 minimum bootstrap contract:
-- - read-only advisors
-- - create/read assignments for initial assignment flow
-- - append-only audit trail
GRANT SELECT, INSERT, UPDATE ON TABLE
    tpi.personas,
    tpi.leads,
    tpi.consentimientos
TO :"app_role";

GRANT SELECT, INSERT ON TABLE
    tpi.asignaciones
TO :"app_role";

GRANT INSERT ON TABLE
    tpi.auditoria
TO :"app_role";

ALTER ROLE :"app_role" IN DATABASE tpi SET search_path = tpi, public;

-- Current validated schema state:
-- - tpi_app does not receive DELETE.
-- - Schema tpi currently has no sequences.
-- - This script does not grant default privileges for future tables or sequences.
--   If the schema evolves, add only the explicit grants required by reviewed app code.

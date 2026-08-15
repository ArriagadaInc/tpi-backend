-- TPI AWS DEV only: allow cleanup of fictitious leads created for DEV testing.
-- Run as the approved database administrator against tpi-postgres-dev.
-- Never run this script in staging or production.

\set app_role tpi_app

GRANT DELETE ON TABLE
    tpi.consentimientos,
    tpi.leads
TO :"app_role";

-- Intentionally excluded:
-- - tpi.personas: RDS DEV has other foreign-key references to personas.
-- - operational tables: cleanup never deletes their records.

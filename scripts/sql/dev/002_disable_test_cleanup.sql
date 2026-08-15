-- TPI AWS DEV only rollback for 002_enable_test_cleanup.sql.
-- Run as the approved database administrator against tpi-postgres-dev.
-- Never run this script in staging or production.

\set app_role tpi_app

REVOKE DELETE ON TABLE
    tpi.consentimientos,
    tpi.leads
FROM :"app_role";

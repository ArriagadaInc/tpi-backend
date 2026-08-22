-- H2.5C rollback: execute only after the public API has been disabled.
-- This removes no lead data. It removes only short-lived idempotency metadata.
BEGIN;

REVOKE SELECT, INSERT, UPDATE, DELETE ON tpi.api_idempotency FROM tpi_app;
DROP TABLE IF EXISTS tpi.api_idempotency;

COMMIT;

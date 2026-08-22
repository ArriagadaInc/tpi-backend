-- H2.5C: public API idempotency. Apply with an administrative role before the
-- public API is enabled. This table intentionally does not store request PII.
BEGIN;

CREATE TABLE IF NOT EXISTS tpi.api_idempotency (
    idempotency_key UUID PRIMARY KEY,
    payload_fingerprint CHAR(64) NOT NULL,
    lead_id UUID REFERENCES tpi.leads(id_lead) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS api_idempotency_expires_at_idx
    ON tpi.api_idempotency (expires_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON tpi.api_idempotency TO tpi_app;

COMMIT;

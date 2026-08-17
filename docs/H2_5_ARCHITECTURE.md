# H2.5 Architecture

## Scope

H2.5 separates TPI DEV into a public lead-capture surface and a protected
operational backoffice. This document describes local, versioned architecture;
no domain, Route 53 resource, IAM permission, secret, network rule, or AWS
deployment has been created by this change.

## Routing

```text
tpi-dev-lab.com                  -> Caddy -> static front/ + FastAPI /api/*
backoffice.tpi-dev-lab.com       -> Caddy -> private Streamlit
                                             -> SimpleDevAuth
```

The names are proposed only. Caddy is the sole public listener; both Streamlit
containers expose port 8000 or 8501 only to the Compose network. Hostname
routing keeps the authentication responsibility in the private application,
not in Caddy.

## Boundaries

- `front/`: static public landing and lead form.
- `app/api`: HTTP adapter with versioned DTOs and no SQL/SNS implementation.
- `app/backoffice_app.py` and `app/pages`: private operational presentation.
- `app/auth`: DEV-only identity/session boundary.
- `app/services`: application behavior, including post-commit event publication.
- `app/repositories`: PostgreSQL-only persistence.
- `app/notifications`: safe event contract and SNS adapter.

The public API calls `SolicitudService`; neither the static frontend nor routes
may write SQL or publish SNS messages directly.

## Security

Public input remains subject to DTO, Pydantic, service, repository, catalog,
consent, and transaction validations. Public errors and logs are safe and omit
PII. The API accepts only JSON with a bounded body, requires an idempotency key,
uses a HMAC fingerprint without persisting the payload, applies an in-memory
DEV-only rate limit, and receives a honeypot signal without storing it. CAPTCHA
and managed multi-instance abuse protection remain production follow-ups.

The HMAC key is supplied only as `API_IDEMPOTENCY_HMAC_SECRET`, a dedicated
runtime secret distinct from database and authentication secrets. API startup
fails closed when it is missing. The idempotency table has a primary key on the
client UUID and `ON DELETE SET NULL` for its short-lived lead reference, so DEV
test-lead cleanup cannot be blocked by metadata. Its only secondary index is
`expires_at`, used for opportunistic expiry cleanup.

SimpleDevAuth consumes `AUTH_USERS_JSON` only in the backoffice service. Missing
or invalid auth data denies private access but cannot block public lead capture.
The future production replacement is managed HTTPS plus OIDC/IdP and RBAC.

## Rollback

### A. Backoffice/authentication-only rollback

If the private boundary fails, remove the `backoffice` hostname route or roll
back only the `backoffice` service. Keep the public hostname, static frontend,
`api` service, and shared `SolicitudService` flow running. Authentication must
not be disabled to expose private pages; the private surface remains fail-closed.

No RDS, schema, grants, SNS, or public-flow change is needed for this recovery.

### B. Complete H2.5 to H2.4 rollback

Deploy the approved H2.4 application revision and remove the H2.5 Caddy/Compose
routing after controlled recovery. This returns to the former single Streamlit
surface and its current IP allowlist. Remove the exact auth-secret IAM
permission only after the private revision no longer runs. RDS, SNS, database
schema, and DEV cleanup remain unchanged.

If the public API is also removed, first disable it and then apply
`scripts/sql/003_drop_api_idempotency.sql` with an administrative database role.
That script revokes the exact `tpi_app` grant and drops only idempotency metadata.

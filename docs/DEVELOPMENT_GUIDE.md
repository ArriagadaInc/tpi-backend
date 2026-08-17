# Development Guide

## Architecture

TPI has two presentation surfaces that share the same application core:

```text
Static public frontend              Private backoffice
front/ + FastAPI                    app/backoffice_app.py
          |                                  |
          |                           SimpleDevAuth (DEV only)
          +---------------+------------------+
                          |
                    SolicitudService
                     |              |
                Repository       LeadCreatedEvent
                     |              |
                PostgreSQL        SNS publisher
```

The public site never imports the authentication boundary. The backoffice calls
`require_authenticated_user()` before reading or rendering operational data.
Both presentations use the same Pydantic contracts and `SolicitudService`; no
Streamlit page accesses PostgreSQL or SNS directly.

## Local setup

```bash
python -m pip install --requirement requirements/dev.lock
python -m pip install --no-deps -e .
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Use an untracked `.env` for local database settings. The public API runs at
`http://127.0.0.1:8000`; Caddy serves `front/` and routes `/api/*` in Compose.
For the local private entrypoint:

```bash
streamlit run app/backoffice_app.py
```

`APP_ENV=testing` and `AUTH_ENABLED=false` are permitted for automated tests.
`AUTH_ENABLED=false` remains the versioned runtime default.

## Public form

`app/api/schemas.py` defines `PublicLeadCreateRequest` v1 and maps it explicitly
to `RegistrarSolicitudRequest`. FastAPI is only an HTTP adapter: Pydantic, the
service, and repository retain server-side validation, normalisation,
transactional persistence, and post-commit notification behavior. The static
form loads approved active catalogs from `GET /api/v1/catalogs` and submits to
`POST /api/v1/leads`.

The API requires three independent consents and a mandatory `saldo_afp`; it
never turns an empty balance into zero. It has no CORS middleware because Caddy
serves the frontend and API from the same origin.

`POST /api/v1/leads` requires a UUID `Idempotency-Key`. PostgreSQL stores only
the key, a HMAC-SHA256 fingerprint, result lead ID and 24-hour expiration. A
replay with the same payload returns the same lead; a changed payload returns
`409`. Expired rows are cleaned opportunistically on a new request. Configure
`API_IDEMPOTENCY_HMAC_SECRET` through a dedicated runtime secret before any AWS
deployment. The API refuses to start without it; it must never reuse database
or authentication credentials.

Before production, add rate limiting and a bot-control adapter at the public
edge or API boundary. CAPTCHA is not part of DEV.

## Private auth boundary

SimpleDevAuth is **DEV ONLY**. It uses Argon2id hashes supplied at runtime in
`AUTH_USERS_JSON`; passwords and hashes are never versioned or stored in
Streamlit session state. The `AuthProvider` protocol and `AuthenticatedUser`
contract isolate future OIDC/Cognito/Entra adapters.

The private boundary fails closed on absent or malformed auth configuration,
invalid hashes, unsupported `AUTH_MODE`, missing session, or unknown roles.
Those failures must not affect the public landing or form.

## Docker and Caddy

Docker Compose runs three services:

```text
Caddy :80/:443
  tpi-dev-lab.com             -> static front/ and api:8000 (/api/*)
  backoffice.tpi-dev-lab.com  -> backoffice:8501
```

Only Caddy publishes host ports. The `api` service receives no `AUTH_USERS_JSON`;
the private service alone receives it. The API rate limit is intentionally
in-memory and valid only for the DEV single instance. `X-Forwarded-For` is read
only when its direct proxy belongs to `API_TRUSTED_PROXY_CIDRS`. Production must
move abuse protection to managed edge infrastructure. Validate locally with:

```bash
docker build --tag tpi-backoffice:local .
docker compose config --quiet
docker compose build
```

The domains and AWS deployment remain pending approval. Caddy, SimpleDevAuth,
and the temporary DEV domain are not production architecture.

## Configuration

- `APP_ENV`: controls environment safeguards.
- `DEV_DELETE_ENABLED`: permits cleanup only when `APP_ENV=aws-dev`.
- `LEAD_NOTIFICATIONS_ENABLED`: permits SNS publishing after a successful DB commit.
- `AUTH_ENABLED` and `AUTH_MODE=simple-dev`: enable the private DEV boundary.
- `AUTH_USERS_JSON`: private runtime secret only.
- `API_IDEMPOTENCY_HMAC_SECRET`: dedicated public API runtime secret for non-reversible
  idempotency fingerprints; never version it.
- `API_MAX_REQUEST_BYTES`, `API_RATE_LIMIT_REQUESTS`,
  `API_RATE_LIMIT_WINDOW_SECONDS`, `API_TRUSTED_PROXY_CIDRS`: public API DEV
  safeguards.

## Tests and quality gates

```bash
pytest tests/ --cov=app --cov-fail-under=85
ruff check app/ tests/ scripts/
black --check app/ tests/ scripts/
mypy app/ --ignore-missing-imports
bandit -r app/ --severity-level medium --confidence-level medium
pip-audit --requirement requirements/runtime.lock
docker build --tag tpi-backoffice:local .
docker compose config --quiet
```

CI uses PostgreSQL testing and fake authentication/publishers. It never calls
AWS RDS, Secrets Manager, or SNS.

## Rollback and production direction

### A. Backoffice/authentication-only rollback

If only private authentication or the backoffice fails, remove the
`backoffice` Caddy route or roll back only the `backoffice` service to its last
known healthy private revision. Keep the static public frontend, `api` service,
its Caddy route, and lead creation online. Do not turn off authentication to
make the private surface public: failed private authentication remains
fail-closed.

This rollback does not change RDS, database grants, H2.3 cleanup, SNS, or the
public application service flow.

### B. Complete H2.5 to H2.4 rollback

For a complete rollback, deploy the approved H2.4 revision and remove the
H2.5 Compose/Caddy routing only after controlled recovery. This restores the
previous single Streamlit surface and its existing IP allowlist. Revoke the
H2.5C idempotency-table grant only if the public API is no longer deployed, then
apply `scripts/sql/003_drop_api_idempotency.sql`. This removes only short-lived
idempotency metadata, and does not alter RDS, H2.3 cleanup, or SNS.

Future production uses `tupensioninteligente.cl`, managed HTTPS, OIDC with a
professional IdP, MFA where required, RBAC, and public anti-abuse controls.

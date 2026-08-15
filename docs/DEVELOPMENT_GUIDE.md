# Development Guide

## Purpose

This guide is the starting point for developers maintaining the TPI backoffice.
It describes the supported local workflow and the boundaries used by AWS DEV.
Use only synthetic data in local and DEV environments.

## Architecture

```text
Streamlit UI -> Services -> Repositories -> PostgreSQL
                     |
                     -> Lead event publisher -> SNS
```

Authentication is an access boundary before Streamlit pages. It does not alter
services, repositories, database permissions, lead creation, DEV cleanup, or
lead notifications.

## Local setup

1. Create a Python 3.12 virtual environment.
2. Install the locked development dependencies:

```bash
python -m pip install --requirement requirements/dev.lock
python -m pip install --no-deps -e .
```

3. Copy `.env.example` to an untracked `.env` and provide only local database
configuration.
4. Run Streamlit:

```bash
streamlit run app/streamlit_app.py
```

`AUTH_ENABLED=false` is the safe versioned default. Local and testing runs do
not require SimpleDevAuth unless it is explicitly enabled.

## SimpleDevAuth (DEV ONLY)

AWS DEV will use `AUTH_MODE=simple-dev` with `AUTH_ENABLED=true`. The secret
value is injected at runtime into `AUTH_USERS_JSON`; it is never versioned in
`.env`, Docker, source code, documentation, or logs.

The secret schema is:

```json
{
  "users": [
    {
      "subject": "stable-internal-id",
      "username": "approved-user",
      "display_name": "Approved User",
      "role": "tester",
      "password_hash": "argon2id-hash"
    }
  ]
}
```

Passwords are verified with Argon2id. Session state keeps only an immutable
`AuthenticatedUser` and local throttle metadata. It never keeps passwords or
hashes. Missing, malformed, or unsupported auth configuration denies access.

Pages call `require_authenticated_user()` and do not depend on a concrete
identity provider. `AuthProvider` can later be implemented by OIDC without
changing business layers.

## AWS DEV deployment (pending DNS approval)

The approved topology is Docker Compose in the existing Elastic Beanstalk
single-instance environment:

```text
Internet -> Caddy :80/:443 -> Streamlit :8501 (internal only)
```

Caddy performs HTTP-to-HTTPS redirection, automatic ACME certificate management,
and the WebSocket-capable reverse proxy. The prerequisite is a public DNS CNAME
for `dev.tupensioninteligente.cl` to the Elastic Beanstalk environment CNAME.
No AWS, DNS, IAM, secret, or deployment change is permitted before that is
confirmed.

The Elastic Beanstalk instance role will receive exactly
`secretsmanager:GetSecretValue` on the exact ARN of `tpi/dev/auth-users`.
It must not receive access to the administrative database secret.

## Feature flags

- `DEV_DELETE_ENABLED`: enables DEV test-data cleanup only with `APP_ENV=aws-dev`.
- `LEAD_NOTIFICATIONS_ENABLED`: enables SNS lead event publishing in DEV.
- `AUTH_ENABLED`: turns on the DEV auth boundary. It defaults to `false`.
- `AUTH_MODE`: must be `simple-dev` for this milestone. Unknown modes fail closed.

## Quality gates

```bash
pytest tests/ --cov=app --cov-fail-under=85
ruff check app/ tests/ scripts/
black --check app/ tests/ scripts/
mypy app/ --ignore-missing-imports
bandit -r app/ --severity-level medium --confidence-level medium
pip-audit --requirement requirements/runtime.lock
docker build --tag tpi-backoffice:local .
docker compose config --quiet
docker compose build streamlit
```

Tests use the CI PostgreSQL service and fakes for identity and AWS boundaries;
they never need AWS Secrets Manager or the DEV RDS instance.

## Rollback

For an authentication incident, deploy the H2.4 application revision and
restore the temporary HTTP `/32` allowlist only for controlled recovery. Remove
the exact auth-secret IAM permission only after no running revision depends on
it. Do not modify RDS, database grants, H2.3 cleanup, or SNS during this
rollback.

## Production direction

SimpleDevAuth and instance-local Caddy certificates are DEV-only. Production
must use managed HTTPS, OIDC with a professional identity provider, appropriate
MFA, and authorization policy/RBAC.

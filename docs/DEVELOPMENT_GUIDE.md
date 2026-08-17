# Development Guide

## Architecture

TPI has two presentation surfaces that share the same application core:

```text
Public landing/form                 Private backoffice
app/streamlit_app.py                app/backoffice_app.py
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
streamlit run app/streamlit_app.py
```

Use an untracked `.env` for local database settings. The public entrypoint is
available at `http://localhost:8501`. For the local private entrypoint:

```bash
streamlit run app/backoffice_app.py
```

`APP_ENV=testing` and `AUTH_ENABLED=false` are permitted for automated tests.
`AUTH_ENABLED=false` remains the versioned runtime default.

## Public form

`app/presentation/public/solicitud_form.py` converts bounded UI data into
`RegistrarSolicitudRequest`. Pydantic, the service, and repository retain all
server-side validation, normalisation, transactional persistence, and
post-commit notification behavior. The public form is not an API replacement;
it is prepared to be replaced later by an HTTP client calling the same
application contract.

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
  tpi-dev-lab.com             -> public:8501
  backoffice.tpi-dev-lab.com  -> backoffice:8501
```

Only Caddy publishes host ports. `public` receives no `AUTH_USERS_JSON` value;
the private service alone receives it. Validate locally with:

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
known healthy private revision. Keep the `public` service, its Caddy route, and
lead creation online. Do not turn off authentication to make the private
surface public: failed private authentication remains fail-closed.

This rollback does not change RDS, database grants, H2.3 cleanup, SNS, or the
public application service flow.

### B. Complete H2.5 to H2.4 rollback

For a complete rollback, deploy the approved H2.4 revision and remove the
H2.5 Compose/Caddy routing only after controlled recovery. This restores the
previous single Streamlit surface and its existing IP allowlist. Do not alter
RDS, database grants, H2.3 cleanup, or SNS.

Future production uses `tupensioninteligente.cl`, managed HTTPS, OIDC with a
professional IdP, MFA where required, RBAC, and public anti-abuse controls.

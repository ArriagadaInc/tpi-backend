# H2.5 Architecture

## Scope

H2.5 separates TPI DEV into a public lead-capture surface and a protected
operational backoffice. This document describes local, versioned architecture;
no domain, Route 53 resource, IAM permission, secret, network rule, or AWS
deployment has been created by this change.

## Routing

```text
tpi-dev-lab.com                  -> Caddy -> public Streamlit
backoffice.tpi-dev-lab.com       -> Caddy -> private Streamlit
                                             -> SimpleDevAuth
```

The names are proposed only. Caddy is the sole public listener; both Streamlit
containers expose port 8501 only to the Compose network. Hostname routing keeps
the authentication responsibility in the private application, not in Caddy.

## Boundaries

- `app/presentation/public`: landing and reusable public lead form.
- `app/backoffice_app.py` and `app/pages`: private operational presentation.
- `app/auth`: DEV-only identity/session boundary.
- `app/services`: application behavior, including post-commit event publication.
- `app/repositories`: PostgreSQL-only persistence.
- `app/notifications`: safe event contract and SNS adapter.

The public form and any future API must call `SolicitudService`; neither may
write SQL or publish SNS messages directly.

## Security

Public input remains subject to Pydantic, service, repository, catalog, consent,
and transaction validations. Public errors and logs are safe and omit PII.
Rate limiting, honeypot/CAPTCHA, and a public API gateway are deliberate
production follow-ups, not H2.5 scope.

SimpleDevAuth consumes `AUTH_USERS_JSON` only in the backoffice service. Missing
or invalid auth data denies private access but cannot block public lead capture.
The future production replacement is managed HTTPS plus OIDC/IdP and RBAC.

## Rollback

### A. Backoffice/authentication-only rollback

If the private boundary fails, remove the `backoffice` hostname route or roll
back only the `backoffice` service. Keep the public hostname, `public` service,
and shared `SolicitudService` flow running. Authentication must not be disabled
to expose private pages; the private surface remains fail-closed.

No RDS, schema, grants, SNS, or public-flow change is needed for this recovery.

### B. Complete H2.5 to H2.4 rollback

Deploy the approved H2.4 application revision and remove the H2.5 Caddy/Compose
routing after controlled recovery. This returns to the former single Streamlit
surface and its current IP allowlist. Remove the exact auth-secret IAM
permission only after the private revision no longer runs. RDS, SNS, database
schema, and DEV cleanup remain unchanged.

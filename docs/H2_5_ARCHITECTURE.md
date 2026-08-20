# H2.5 Architecture

## Scope

H2.5 separates TPI DEV into a public lead-capture surface and a protected
operational backoffice. This document describes local, versioned architecture;
no domain, Route 53 resource, IAM permission, secret, network rule, or AWS
deployment has been created by this change.

## Routing

```text
dev.genialabs.cl                  -> Caddy -> static front/ + FastAPI /api/*
backoffice.dev.genialabs.cl       -> Caddy -> private Streamlit
                                             -> SimpleDevAuth
```

The names are proposed only. Caddy is the sole public listener; both Streamlit
containers expose port 8000 or 8501 only to the Compose network. Hostname
routing keeps the authentication responsibility in the private application,
not in Caddy.

For local H2.5C validation, `docker-compose.local.yml` supplies PostgreSQL and
the idempotent schema initializer. Caddy uses `http://tpi.localhost` and
`http://backoffice.tpi.localhost`, bound only to loopback. This local override
uses a fictitious HMAC, disabled SNS and an untracked Argon2id auth hash; it is
not an AWS artifact and cannot access AWS RDS, SNS or Secrets Manager.

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

### BLUE/GREEN IAM isolation

BLUE and GREEN must never share IAM identity. Cloning an Elastic Beanstalk
environment configuration is not the same as cloning its IAM role or EC2
instance profile. `IamInstanceProfile` is an environment-specific setting and
must be versioned, reviewed, and validated independently for each environment.

The operational guardrail is a preflight script:
`deployment/aws/check_eb_iam_isolation.py`.
It fails closed when BLUE and GREEN use the same instance profile or the same
IAM role, and it prints the resolved profile and role for both environments on
success.

As a longer-term drift control, IAM roles, instance profiles, and Elastic
Beanstalk environment settings should move progressively into IaC so that
identity isolation is enforced structurally instead of by manual review.

SimpleDevAuth consumes `AUTH_USERS_JSON` only in the backoffice service. Missing
or invalid auth data denies private access but cannot block public lead capture.
The future production replacement is managed HTTPS plus OIDC/IdP and RBAC.

## Container vulnerability gate

As of 2026-08-19, published ECR candidates must have zero CRITICAL findings.
The Caddy image removes curl/libcurl because Caddy uses its Go HTTP stack and
neither its entrypoint nor healthcheck invokes curl. This removes the unused
affected component rather than accepting CVE-2026-6276 or CVE-2026-5773 as a
DEV exception.

The application image is pinned to the official Python 3.12.13 Alpine 3.24
digest, which provides SQLite 3.53.2. H2.5D treats both HIGH and CRITICAL ECR
findings as deployment blockers; a candidate must be rebuilt and scanned clean
before it can be deployed.

Every immutable image remains subject to ECR scan-on-push. A future dependency
on SQLite or curl/libcurl requires an explicit security review and a currently
fixed vendor package. This does not replace production enhanced scanning.

## Elastic Beanstalk ECR bundle

Elastic Beanstalk receives a minimal source bundle generated with
`deployment/build_eb_ecr_bundle.py`. The ZIP contains exactly one root entry:
`docker-compose.yml`. Its entry name is written with POSIX `/` separators, so
Linux `unzip` can extract it deterministically.

The rendered compose references the approved application and Caddy images by
full SHA-256 digest. It contains no `build:` directive, source code, Dockerfile,
`.ebextensions`, environment files, or secrets. Runtime configuration and
infrastructure remain persisted as Elastic Beanstalk environment settings;
application versions do not reapply IAM, VPC, subnet, security-group, instance,
or scaling configuration.

GitHub Actions on Ubuntu generates and validates the canonical artifact using
`unzip -t`, extraction into a temporary directory, and `docker compose config`.
The workflow uploads the ZIP as a build artifact with a separate, non-secret
manifest containing the runtime Git SHA, image digests, generation time, and
bundle SHA-256. A bundle that contains backslashes, nested paths, extra files,
mutable image tags, host ports for API/Streamlit, or build directives fails
validation.

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

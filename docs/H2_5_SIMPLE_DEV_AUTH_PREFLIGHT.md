# H2.5 - SimpleDevAuth and Caddy Preflight

## Scope and approval gate

This document records the approved preflight and local implementation boundary.
The repository contains the SimpleDevAuth, Compose, Caddy, tests, and
documentation preparation, but this work does not create or modify AWS
resources, DNS records, Security Groups, secrets, users, or IAM policies.
SimpleDevAuth is explicitly **DEV ONLY**. It is not approved for staging or
production, where HTTPS managed by AWS plus OIDC, a professional IdP, MFA when
appropriate, and RBAC are required.

## A. Proposed Caddy and Elastic Beanstalk topology

Keep the existing Elastic Beanstalk Docker Single Instance environment and
replace its single-container runtime with Docker Compose:

```text
Internet
  -> Caddy container:80/:443
  -> Streamlit container:8501 (internal Docker network only)
  -> SimpleDevAuth boundary
  -> TPI services, repositories, RDS, and SNS unchanged
```

Docker Compose is the smallest compatible integration: Elastic Beanstalk
expects the Compose deployment to provide its own proxy container, so Caddy can
be the only service exposing host ports 80 and 443. Streamlit has no host port
mapping. Caddy reverse proxy supports Streamlit WebSockets, redirects HTTP to
HTTPS, and obtains/renews certificates automatically after DNS and ports are
valid.

Prepared repository files:

- `docker-compose.yml`: `caddy` and `streamlit` services.
- `deployment/caddy/Caddyfile`: domain-based reverse proxy only.
- `.ebextensions/02-h2-5-simple-dev-auth.config`: safe defaults and declared
  environment-secret reference, never secret values.
- `.platform/hooks/`: Docker Compose health/log integration required by the EB
  platform.
- `deployment/iam/tpi-backoffice-dev-read-auth-users-secret.json`: exact
  secret-resource policy.

Conceptual Compose fragment, with final Caddy image pinned to a digest at
implementation time:

```yaml
services:
  streamlit:
    build: .
    expose: ["8501"]

  caddy:
    image: caddy:<approved-version-and-digest>
    ports: ["80:80", "443:443"]
    volumes:
      - ./deployment/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [streamlit]
```

The Caddyfile will contain only `{$TPI_DEV_DOMAIN}` and
`reverse_proxy streamlit:8501`; no credentials or certificate material are
versioned. Caddy state is local to the DEV instance. It can reissue a
certificate after instance replacement, which is acceptable for DEV but one
reason this topology is not a production design.

## B. Deployment files to change after approval

In addition to the Compose and deployment files above, implementation would
modify only these application boundaries:

- `app/config/settings.py`: `AUTH_ENABLED`, `AUTH_MODE`, and a secret-backed
  auth-users configuration with fail-closed validation.
- `app/auth/`: immutable user model, provider protocol, SimpleDevAuth adapter,
  guard, session/throttle helpers, and exports.
- `app/streamlit_app.py`, `app/pages/*`, and common header: invoke the common
  guard before accessing data and render login/logout only through `app/auth/`.
- `pyproject.toml` and `requirements/runtime.lock`: explicit Argon2id library
  dependency, expected to be `argon2-cffi` pinned in the runtime lock.
- CI: preserve `docker build` and add Docker Compose validation/build once the
  deployment switches to Compose.
- Tests and DEV-only documentation listed in the H2.5 scope.

`SolicitudService`, `SolicitudRepository`, PostgreSQL schemas/grants,
LeadCreatedEvent, SNS publisher, and business forms are not changed.

## C. DNS prerequisite

Proposed name: `dev.tupensioninteligente.cl`.

Preflight found no Route 53 Hosted Zone in account `821656895812`. Public DNS
for `tupensioninteligente.cl` delegates to `dns1` through `dns4.datatecno.com`.
No CNAME was found for the proposed DEV host. AWS cannot create the required
record from the available account.

Before AWS implementation, the DNS administrator must confirm control of the
DataTecno zone and approve this record:

```text
dev.tupensioninteligente.cl.  CNAME  tpi-backoffice-dev-821656895812.us-east-2.elasticbeanstalk.com.
```

Use a short temporary TTL, such as 300 seconds, for the cutover. A CNAME to the
Elastic Beanstalk environment CNAME avoids depending on a changing instance
public IP. DNS control is a hard blocker: Caddy cannot obtain a publicly trusted
certificate without a resolvable public hostname under approved control.

## D. Required Security Group ports

The current application SG allows TCP 80 only from two temporary `/32` rules.
After a complete authenticated HTTPS deployment is ready, replace those web
rules with:

| Port | Source | Purpose |
|---|---|---|
| TCP 80 | `0.0.0.0/0` | ACME HTTP challenge and HTTP-to-HTTPS redirect only |
| TCP 443 | `0.0.0.0/0` | Caddy TLS endpoint and authenticated application access |

Do not create inbound rules for TCP 22, 8501, or 5432. Streamlit remains
internal to Docker; RDS remains SG-to-SG on TCP 5432. The existing DBeaver
administrative rule is not changed.

The cutover order must avoid a credential-over-HTTP window: deploy Compose,
auth fail-closed, and Caddy configuration first; then coordinate DNS and the
public 80/443 rules; verify certificate and HTTPS; only then set
`AUTH_ENABLED=true`. Public port 80 serves no app content beyond Caddy's ACME
challenge/redirect.

## E. Certificate strategy

Caddy Automatic HTTPS is the proposed certificate strategy. With the approved
domain resolving to the EB CNAME and public access to ports 80 and 443, Caddy
uses ACME, stores managed certificate state in its mounted `/data` volume,
renews automatically, and redirects HTTP to HTTPS. No private certificate or
manual renewal is committed or administered.

This is intentionally a lightweight DEV solution. It is not a substitute for
ALB plus ACM in production.

## F. Auth users secret

Create one DEV-only AWS Secrets Manager secret after approval:

```text
tpi/dev/auth-users
```

Its JSON shape contains only stable identity metadata and Argon2id password
hashes, never plaintext passwords:

```json
{
  "users": [
    {
      "subject": "<stable-internal-id>",
      "username": "<approved-username>",
      "display_name": "<approved-display-name>",
      "role": "tester",
      "password_hash": "<argon2id-hash>"
    }
  ]
}
```

Elastic Beanstalk injects the secret into an environment-secret variable. The
application parses it as a secret value and never logs, caches in session, or
returns its contents. `AUTH_ENABLED=false` remains the versioned default. In a
deployed environment, missing/invalid users configuration, unknown `AUTH_MODE`,
or disabled auth fails closed. `production` with disabled or SimpleDevAuth is
also rejected; only local/testing fakes may bypass real secret loading.

## G. IAM proposal

Attach one inline policy to `tpi-backoffice-dev-ec2-role` after the secret
exists:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "<exact ARN of tpi/dev/auth-users>"
}
```

No wildcard resource, `secretsmanager:*`, admin database secret access, Cognito
permission, or database permission change is proposed.

## H. app/auth design

```text
app/auth/
  models.py       AuthenticatedUser (frozen, typed)
  provider.py     AuthProvider protocol
  simple_dev.py   Argon2id verification and secret configuration adapter
  guards.py       session, login UI, logout, and fail-closed page guard
  __init__.py     narrow public API
```

`AuthenticatedUser` contains `subject`, `username`, `display_name`, and role.
Known initial role is `tester`; `admin`, `advisor`, `operations`, and `readonly`
are reserved contract values. Unknown roles deny access safely. Pages call only
`require_authenticated_user()`; they do not parse users, hashes, secrets, or
Streamlit session keys.

The SimpleDevAuth provider verifies passwords with `argon2-cffi` using Argon2id.
Passwords exist only as an input during verification. On an unknown username,
the provider performs an equivalent safe verification path using a configured
valid hash before returning the same generic failure, reducing trivial user
enumeration timing differences.

Session state holds only `AuthenticatedUser` and throttle metadata, never a
password or hash. Streamlit session state is tied to a WebSocket, so refresh or
new browser tabs require login again; this is an intentional DEV limitation.
Logout removes all auth/session keys and reruns into the login screen.

Failed login protection is intentionally local: five failed attempts in one
session trigger a short, increasing temporary block and a generic error. It is
not distributed rate limiting and must be replaced by an IdP in production.

## I. New dependencies

- `argon2-cffi`, explicit runtime dependency and exact runtime-lock entries.
- Caddy official image, pinned by immutable digest in Compose.

No AWS SDK, SMTP, Cognito SDK, password helper of unknown provenance, or custom
cryptography is proposed.

## J. Tests planned

- Unit: valid/invalid/unknown credentials, disabled auth, invalid mode, absent
  or malformed secret JSON, invalid hash, valid/unknown roles, session creation,
  logout, guards, and per-session throttling.
- Security: no plaintext password/hash/secret in tracked files or logs, strict
  secret IAM resource, no Secrets Manager wildcard, database-admin secret still
  absent from runtime IAM, invalid config fail-closed, and protected pages deny
  direct access.
- Integration: existing PostgreSQL registration, notification, and DEV cleanup
  contracts remain unchanged under a fake authenticated user.
- E2E: fake auth login, register, consult, detail, delete test lead, logout,
  and direct-page denial after logout. CI never calls AWS Secrets Manager.
- Deployment: existing Docker build remains required; Compose parse/build,
  Caddy-to-Streamlit WebSocket behavior, HTTPS redirect, and closed 8501 must
  be verified before AWS cutover.

All existing gates remain: pytest, coverage >=85%, Ruff, Black, MyPy, Bandit,
pip-audit, Docker build, and new Compose build validation.

## K. Rollback

1. Set `AUTH_ENABLED=false` only as part of redeploying/rolling back to H2.4;
   a disabled DEV auth config must never open protected content.
2. Deploy the previous H2.4 Docker version and restore the temporary HTTP
   `/32` allowlist only for controlled incident recovery.
3. Remove the exact auth-secret IAM policy after no running version references
   it.
4. Retain the auth secret and Caddy state until recovery is confirmed, then
   delete deliberately if the feature is abandoned.

RDS, PostgreSQL grants, H2.3 cleanup, H2.4 SNS, and database secrets are not
affected by rollback.

## L. Risks and constraints

- DNS administration at DataTecno is currently unconfirmed and blocks ACME.
- Caddy certificate state is instance-local; instance replacement may cause
  reissuance and is acceptable only for low-volume DEV.
- The `t3.micro` must be observed under Caddy plus Streamlit memory/CPU load.
- HTTP 80 must be internet reachable for ACME redirect/challenge. It must never
  serve login or application content directly.
- SimpleDevAuth session throttling is per session, not a distributed defense.
- This design is not an approved production authentication or TLS architecture.

## M. Incremental cost estimate

- Caddy and Docker Compose: no separate AWS service charge; minor existing EC2
  compute/memory overhead only.
- One Secrets Manager secret: approximately USD 0.40/month plus negligible API
  calls at DEV volume.
- DNS: no incremental AWS cost if the existing external DataTecno zone is used;
  any domain/provider fee is outside this account.
- Certificates: no Caddy/ACME certificate fee expected.

No ALB, Cognito, CloudFront, ACM, Route 53 Hosted Zone, or new database
resource is proposed for this H2.5 approach.

## Sources

- [Elastic Beanstalk Docker Compose environments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/create_deploy_docker.container.console.html)
- [Elastic Beanstalk Docker Compose quick start](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/docker-compose-quickstart.html)
- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Caddy reverse proxy quick start](https://caddyserver.com/docs/quick-starts/reverse-proxy)
- [Streamlit session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)

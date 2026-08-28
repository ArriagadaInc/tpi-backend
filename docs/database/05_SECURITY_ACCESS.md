Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-08-28
Fuente: PostgreSQL RDS + scripts versionados + init_test_database.py

# 05 Security and Access

## Access Principles

- secrets are never committed
- `.env` is local only
- AWS and production receive configuration through environment injection or
  a secrets manager
- the runtime must use the least privilege necessary
- the application must fail closed when auth or SSL prerequisites are missing

## Roles

### `tpi_admin`

- administrative role
- used for manual schema work, inspection, and migration execution
- must not be used by the application runtime

### `tpi_app`

- application runtime role
- intended for the backoffice in local, testing, AWS DEV, and future
  production
- should operate with least privilege

## Declared Privileges in the Repository

From `scripts/sql/001_create_tpi_app_role.sql`:

- `CONNECT` on database `tpi`
- `USAGE` on schema `tpi`
- `SELECT` on catalog tables and `tpi.asesores`
- `SELECT`, `INSERT`, `UPDATE` on `tpi.personas`, `tpi.leads`,
  `tpi.consentimientos`, and `tpi.asignaciones`

DEV-only helper:

- `scripts/sql/dev/002_enable_test_cleanup.sql` grants `DELETE` on
  `tpi.leads` and `tpi.consentimientos`

## Security Contradiction to Track

Repository code currently writes audit rows:

- `app/repositories/solicitud_repository.py` inserts into `tpi.auditoria`

However, the visible `001_create_tpi_app_role.sql` script does not declare a
grant on `tpi.auditoria`.

Status:

- pending validation against the actual AWS role bootstrap
- do not assume this is resolved until it is explicitly confirmed

## SSL / TLS

Required behavior:

- `local`: SSL may be disabled
- `testing`: explicit environment choice
- `aws-dev`: SSL must be enforced, typically `require`
- `production`: `verify-full` plus a trusted RDS CA bundle

Operational rule:

- if AWS or production is missing SSL configuration, fail closed

## `subject` as Technical Actor Identifier

Current H3.3 assignment traces use `AuthenticatedUser.subject` for
`asignado_por`.

Why it is acceptable:

- stable by contract
- not a display label
- not an advisor mapping
- not a direct PII field in the current app contract

Validation note:

- it must remain short enough for `VARCHAR(150)`
- if the identity provider changes the format or length, revalidate the
  assignment trace contract

## What `tpi_app` Should Be Able to Do

Confirmed by the application and repository contract:

- connect to the database
- read the schema and operational tables
- create/update leads and personas during registration
- create assignment rows
- read advisors
- write traceability rows when the audit permission is available

Not allowed:

- create roles
- create databases
- modify schema ad hoc
- bypass SSL in AWS or production

## Secrets and Configuration

Supported configuration contract:

- `DATABASE_URL`
- or discrete `DATABASE_*` fields

Do not store in the repository:

- database passwords
- tokens
- private certificates
- raw connection strings with secrets embedded


# PostgreSQL and Amazon RDS Connection

This document describes the database connection architecture for the
Tu Pension Inteligente backoffice as of August 7, 2026.

## Summary

- The application uses a single PostgreSQL access path based on
  `psycopg` and `psycopg_pool`.
- Configuration is centralized in `app/config/settings.py`.
- Streamlit pages reuse the same process-wide pool; the pool is not recreated
  on every rerun.
- Local, testing, AWS development, and future production use the same
  configuration contract.
- Secrets are read from environment variables. `.env` is allowed only for local
  development and is ignored by git.

## Connection Architecture

```
Streamlit UI
    -> services
    -> repositories
    -> app.database.connection
    -> psycopg_pool.ConnectionPool
    -> PostgreSQL / Amazon RDS
```

Key modules:

- `app/config/settings.py`: typed settings and environment precedence
- `app/database/connection.py`: singleton pool, transaction safety, safe errors
- `app/database/healthcheck.py`: ping, schema access, `tpi.leads`, effective user
- `app/database/errors.py`: classified errors and safe Streamlit messages

## Environment Variables

Minimum supported variables:

```text
APP_ENV
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USER
DATABASE_PASSWORD
DATABASE_SSLMODE
DATABASE_SSLROOTCERT
DATABASE_CONNECT_TIMEOUT
DATABASE_POOL_MIN_SIZE
DATABASE_POOL_MAX_SIZE
DATABASE_POOL_TIMEOUT
```

Additional supported variables:

```text
DATABASE_URL
DATABASE_SCHEMA
APP_NAME
APP_DEBUG
LOG_LEVEL
LOG_FILE
ALLOW_DEMO_MODE
```

Precedence:

1. `DATABASE_URL`, if defined.
2. `DATABASE_*` discrete variables.
3. Safe local defaults only when `APP_ENV=local`.

Important details:

- When `DATABASE_URL` is used, host, port, database, user, and password come
  from the URL.
- Pool settings always come from `DATABASE_POOL_*`.
- `DATABASE_SSLMODE` and `DATABASE_SSLROOTCERT` must still be explicit for
  AWS and production unless they are already encoded in `DATABASE_URL`.

## Environment Matrix

| Ambiente   | Base                   | Credenciales         | SSL           | Datos                 |
| ---------- | ---------------------- | -------------------- | ------------- | --------------------- |
| Local      | PostgreSQL local       | `.env` no versionado | Opcional      | Desarrollo            |
| Testing    | PostgreSQL aislado     | Fixtures/CI secrets  | Segun entorno | Ficticios             |
| AWS dev    | RDS `tpi-postgres-dev` | Variables/secretos   | Obligatorio   | Desarrollo controlado |
| Produccion | RDS privada            | AWS Secrets Manager  | `verify-full` | Reales                |

## Local Example

```env
APP_ENV=local
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=tpi_local
DATABASE_USER=tpi_app
DATABASE_PASSWORD=<local-secret>
DATABASE_SCHEMA=tpi
DATABASE_SSLMODE=disable
DATABASE_CONNECT_TIMEOUT=10
DATABASE_POOL_MIN_SIZE=1
DATABASE_POOL_MAX_SIZE=5
DATABASE_POOL_TIMEOUT=30
```

## AWS Development Example

```env
APP_ENV=aws-dev
DATABASE_HOST=<rds-endpoint>
DATABASE_PORT=5432
DATABASE_NAME=tpi
DATABASE_USER=tpi_app
DATABASE_PASSWORD=<secret>
DATABASE_SCHEMA=tpi
DATABASE_SSLMODE=require
DATABASE_CONNECT_TIMEOUT=10
DATABASE_POOL_MIN_SIZE=1
DATABASE_POOL_MAX_SIZE=5
DATABASE_POOL_TIMEOUT=30
```

## Production Recommendation

Recommended source of secrets:

- deployment environment variables injected by the runtime, or
- AWS Secrets Manager consumed by the deployment platform

Recommended production settings:

```env
APP_ENV=production
DATABASE_HOST=<private-rds-endpoint>
DATABASE_PORT=5432
DATABASE_NAME=tpi
DATABASE_USER=tpi_app
DATABASE_PASSWORD=<secret>
DATABASE_SCHEMA=tpi
DATABASE_SSLMODE=verify-full
DATABASE_SSLROOTCERT=/path/to/global-bundle.pem
DATABASE_CONNECT_TIMEOUT=10
DATABASE_POOL_MIN_SIZE=2
DATABASE_POOL_MAX_SIZE=10
DATABASE_POOL_TIMEOUT=30
```

Do not commit:

- `.env`
- real passwords
- real endpoints with embedded credentials
- private certificates

## SSL / TLS Strategy

- `local`: `disable` by default
- `testing`: explicit according to the test environment
- `aws-dev`: `DATABASE_SSLMODE` must be one of `require`, `verify-ca`,
  or `verify-full`
- `production`: `DATABASE_SSLMODE=verify-full` and a valid
  `DATABASE_SSLROOTCERT` are required

Why this matters:

- `require` encrypts traffic for AWS development
- `verify-full` adds server identity verification for production

## Pooling Strategy

The application uses a single shared `ConnectionPool`.

Behavior:

- initialized lazily
- reused across Streamlit reruns
- sizes controlled by `DATABASE_POOL_MIN_SIZE` and `DATABASE_POOL_MAX_SIZE`
- acquisition wait controlled by `DATABASE_POOL_TIMEOUT`
- TCP connect timeout controlled by `DATABASE_CONNECT_TIMEOUT`
- `commit` only after successful writes
- `rollback` on exceptions and before returning connections to the pool if
  a transaction is still open

When to consider RDS Proxy:

- concurrent users grow significantly
- the application is deployed in multiple instances
- connection limits on RDS become a real constraint

## Application Role `tpi_app`

Versioned script:

- `scripts/sql/001_create_tpi_app_role.sql`

Execution notes:

- run manually with an administrative role such as `tpi_admin`
- execute the script from an interactive `psql` session
- set or rotate the password afterwards with `\password tpi_app`
- do not store the password in the script, shell history, or versioned docs

Granted privileges:

- `CONNECT` on database `tpi`
- `USAGE` on schema `tpi`
- `SELECT` on catalog tables used by the backoffice
- `SELECT`, `INSERT`, `UPDATE` on:
  - `tpi.personas`
  - `tpi.leads`
  - `tpi.consentimientos`

Not granted:

- `DELETE`
- `CREATEDB`
- `CREATEROLE`
- `SUPERUSER`
- schema modification privileges

Current scope boundaries:

- schema `tpi` currently has no sequences, so no sequence grants are versioned
- no default privileges are granted for future tables or sequences
- if the schema evolves, grant only the explicit privileges required by reviewed app code
- the schema can contain additional operational tables such as `auditoria`, `eventos_lead`, `citas`, `asignaciones`, `campanas_atribucion`, `fichas_diagnosticas` and `ingesta_google_sheets`, but the current backoffice UI does not use them and `tpi_app` is not granted access to them by this script

## Health Check

The application verifies:

- `SELECT 1`
- current database name
- effective database user
- schema `tpi` visibility
- read access to `tpi.leads`

The UI only shows a safe status such as `BD: Conectada`.
It does not expose endpoint, password, or low-level driver details.

## Testing Strategy

Do not run automated tests against AWS RDS.

Automated coverage in this repo uses:

- unit tests with mocked settings, pool, and connection errors
- integration tests against an isolated PostgreSQL instance
- CI PostgreSQL service bootstrapped by `scripts/init_test_database.py`

Relevant tests:

- `tests/unit/test_database_settings.py`
- `tests/unit/test_database_errors.py`
- `tests/unit/test_database_connection.py`
- `tests/unit/test_database_healthcheck.py`
- `tests/integration/test_database_runtime.py`

## Common Errors

| Scenario | Symptom | Action |
| -------- | ------- | ------ |
| Missing variables | configuration error at startup | complete `DATABASE_*` values |
| DNS / bad endpoint | host resolution error | verify RDS endpoint and security group reachability |
| Invalid credentials | authentication error | rotate secret and confirm `tpi_app` password |
| Missing SSL in AWS | SSL mode validation error | set `DATABASE_SSLMODE=require` or stronger |
| Pool exhausted | connection acquisition timeout | raise pool size carefully or reduce parallel load |
| Database unavailable | operational error | verify RDS status and allowed source IP |

## Credential Rotation

If a password or credential-like value was ever committed:

1. rotate the database secret immediately
2. update the deployment secret source
3. update local `.env` only where required
4. invalidate old copies in notes, tickets, and docs

This repository previously contained credential-like values in historical
documentation. Treat those values as compromised and rotate them if they were
ever used outside a local demo environment.

## Deployment Procedure

1. Create or update the `tpi_app` role on RDS with
   `scripts/sql/001_create_tpi_app_role.sql`.
2. Configure `APP_ENV=aws-dev` or `APP_ENV=production`.
3. Inject `DATABASE_*` secrets through the deployment environment or
   Secrets Manager integration.
4. For production, install the AWS RDS CA bundle and set
   `DATABASE_SSLROOTCERT`.
5. Run `python scripts/verify_database_connection.py`.
6. Run the application and confirm the health indicator reports
   `BD: Conectada`.

## Manual AWS Validation Procedure

Run only when you have approved connectivity and secrets for RDS.

1. Record the initial count of `tpi.leads`.
2. Connect as `tpi_app`, never `tpi_admin`.
3. Execute `SELECT 1`.
4. Confirm the effective user, database, and schema access.
5. Query only the lead count, not raw rows.
6. Insert one clearly identified fictitious lead.
7. Read it back through the application.
8. Confirm trace fields such as `estado_lead`, `created_at`,
   `origen_lead`, and `fuente_actual`.
9. Remove or deactivate the fictitious record using the approved procedure.
10. Confirm the final count is coherent with the initial state.

## Rollback Procedure

The rollback must not delete the RDS instance, the `tpi` schema, tables, or
the backup `tpi_local.backup`.

Rollback steps:

1. Restore the previous environment variables or point `APP_ENV=local`.
2. Reapply the previous local `.env` values if a temporary local fallback is
   required.
3. Stop the application and call `close_pool()` by restarting the process.
4. Revert the code commit that introduced the RDS-ready connection layer.
5. To disable `tpi_app` temporarily without deleting it:
   `ALTER ROLE tpi_app NOLOGIN;`
6. Re-enable it later with:
   `ALTER ROLE tpi_app LOGIN;`

## Files Relevant to This Change

- `app/config/settings.py`
- `app/database/connection.py`
- `app/database/errors.py`
- `app/database/healthcheck.py`
- `scripts/sql/001_create_tpi_app_role.sql`
- `scripts/verify_database_connection.py`
- `.env.example`
- `docker-compose.yml`

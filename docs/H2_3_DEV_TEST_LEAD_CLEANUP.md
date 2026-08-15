# H2.3 - DEV test lead cleanup

## Objective

H2.3 allows an explicitly authorized AWS DEV user to create, inspect, and
remove fictitious leads. It does not add a production deletion capability.

```
Streamlit detail view
        |
SolicitudService.delete_test_lead()
        |
SolicitudRepository.delete_test_lead()
        |
PostgreSQL transaction
```

The Streamlit page does not execute SQL. The service owns the environment
guard and safe user result; the repository owns the parameterized transaction.

## Environment guard and feature flag

`DEV_DELETE_ENABLED` defaults to `false` in `Settings` and `.env.example`.
Cleanup is effective only when both conditions hold:

```
APP_ENV == aws-dev
DEV_DELETE_ENABLED == true
```

Every other combination is denied by `SolicitudService`, including
`production + true` and `local + true`. The button is also absent unless the
same service guard is effective. The versioned Elastic Beanstalk configuration
keeps `DEV_DELETE_ENABLED=false`. Set it to `true` only as an environment
property on `tpi-backoffice-dev` during the approved H2.3 deployment; never
add it to staging or production.

All pages call the shared header. In `aws-dev` it renders the visible
`AMBIENTE DE DESARROLLO` banner from `APP_ENV`.

## Delete behavior

The detail view exposes `ELIMINAR LEAD DE PRUEBA` only in effective AWS DEV.
It requires both:

1. The checkbox confirming the record is test data.
2. The exact text `ELIMINAR`.

`delete_test_lead` validates the UUID, verifies the lead exists, and returns a
typed safe result. A second invocation returns `not_found`; it does not expose
a database exception.

The transaction locks the target lead, deletes its `tpi.consentimientos`, then
deletes the target `tpi.leads` row. All statements use parameters and have a
`WHERE id_lead = %s` predicate. A failure rolls back the entire transaction.

Personas are intentionally retained. The RDS DEV inventory found that
`tpi.auditoria` can reference `tpi.personas`; the application role cannot
inspect or delete operational audit data. H2.3 therefore does not grant
`DELETE` on `tpi.personas`, even when a persona has no remaining leads.

The actual RDS DEV foreign-key inventory also found these tables referencing
`tpi.leads`: `asignaciones`, `auditoria`, `campanas_atribucion`, `citas`,
`consentimientos`, `eventos_lead`, `fichas_diagnosticas`, and
`ingesta_google_sheets`. H2.3 never deletes operational rows. If one blocks a
lead deletion, PostgreSQL raises an FK violation, the transaction rolls back,
and the service reports a safe `blocked` result.

## PostgreSQL permissions

Apply only in AWS DEV, as the approved database administrator:

```sql
\i scripts/sql/dev/002_enable_test_cleanup.sql
```

The script grants `tpi_app` only:

- `DELETE` on `tpi.consentimientos`
- `DELETE` on `tpi.leads`

It does not grant `DELETE ON ALL TABLES`, future default privileges, or any
delete permission on `personas` or operational tables. Existing `SELECT`,
`INSERT`, and `UPDATE` grants are unchanged.

Rollback is independent of RDS and Elastic Beanstalk:

1. Set `DEV_DELETE_ENABLED=false` on `tpi-backoffice-dev` and deploy/restart.
2. Run `scripts/sql/dev/002_disable_test_cleanup.sql` as the approved DB
   administrator.
3. Verify `tpi_app` no longer has `DELETE` on `leads` and `consentimientos`.

Never run either script in staging or production.

The DEV-only grant was applied using the existing administrative secret
`tpi/dev/database-admin-password` from the local `tpi-dev` AWS CLI profile.
It is used only for temporary `tpi_admin` administration and is not available
to the Elastic Beanstalk instance role or to `tpi_app`. Do not reset the RDS
administrator password or reuse the application secret for administration.

## Access restriction

H2.3 keeps the H2.2 application security group behavior:

- HTTP 80 is restricted to explicitly authorized public IP `/32` rules.
- No public 22, 8501, or 5432 rules are created.
- RDS PostgreSQL access remains application security group to RDS security
  group on TCP 5432.

To authorize Diego later, obtain his current public IP and add a second,
independent TCP/80 `/32` inbound rule to `tpi-backoffice-dev-sg`. Do not widen
the existing rule and never use `0.0.0.0/0`.

## Logging and observability

The service writes only structured minimum events to stdout for CloudWatch:

```
event=test_lead_deleted environment=aws-dev lead_id=<uuid> result=success
event=test_lead_delete_failed environment=aws-dev lead_id=<uuid> result=<status>
```

It never logs RUT, email, phone, payloads, database URLs, or passwords.

## Tests

Unit and security tests cover every environment/flag combination, invalid UUID,
not-found idempotency, safe repository failures, parameterized SQL, and the
production guard. PostgreSQL integration tests use the CI test database and
cover:

- one lead: consent and lead removed, persona retained;
- shared persona: one lead removed, the other lead and persona retained;
- operational FK failure: consent deletion rolls back with the lead deletion.

The Streamlit E2E test exercises opening detail, both confirmations, invoking
the service, and showing success. AWS smoke testing must use only fictitious
data and verify creation, lookup, deletion, RDS cleanup, person retention, and
CloudWatch logs.

## AWS DEV deployment validation

H2.3 was deployed as Elastic Beanstalk version `h2-3-3d5ded341436` to
`tpi-backoffice-dev`. The versioned configuration still has
`DEV_DELETE_ENABLED=false`; the environment property was set independently to
`true` only after the application version reached `Ready/Green`.

The deployed container was validated through SSM without SSH. It is `healthy`,
runs as `appuser`, has `APP_ENV=aws-dev` and `DEV_DELETE_ENABLED=true`, and its
runtime health check reports PostgreSQL connectivity, schema access, and
`tpi.leads` access. The restricted public URL returned HTTP 200 for both `/`
and `/_stcore/health` (`ok`). Rendering the deployed entrypoint confirmed the
visible `AMBIENTE DE DESARROLLO` banner.

The real smoke test used a generated fictitious person and completed create,
consult, delete, lead absence, consent absence, and retained-person checks.
No lead identifier or test-person data is recorded here. CloudWatch application
stdout/stderr has seven-day retention; its post-deployment review found no
password, token, email, phone, or RUT pattern in the application log events
reviewed.

## Known limitations

AWS DEV remains HTTP-only, IP-restricted, and Single Instance. Identity-based
authentication, HTTPS, staging, production cleanup, and business-flow changes
remain out of scope for H2.3.

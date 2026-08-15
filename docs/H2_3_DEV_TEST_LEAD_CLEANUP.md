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

At implementation time, AWS Secrets Manager contains only the application
secret `tpi/dev/database-password`; it does not contain credentials for the
RDS administrator `tpi_admin`. Do not reset the RDS administrator password or
reuse the application secret to work around this. The approved administrator
access is required to apply the DEV-only grant before deployment.

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

## Known limitations

AWS DEV remains HTTP-only, IP-restricted, and Single Instance. Identity-based
authentication, HTTPS, staging, production cleanup, and business-flow changes
remain out of scope for H2.3.

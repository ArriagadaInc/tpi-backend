Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-08-28
Fuente: PostgreSQL RDS + scripts versionados + init_test_database.py

# 04 Migrations

## Scope

This document inventories the versioned SQL scripts and bootstrap utilities
that define the repository contract for the database layer.

It does not describe ad-hoc manual changes. If a change is not reproducible
through versioned scripts, it should be treated as drift.

## Chronological Inventory

| Script | Purpose | Dependency | Status | Environment | Rollback |
| ------ | ------- | ---------- | ------ | ----------- | -------- |
| `scripts/sql/001_create_tpi_app_role.sql` | Create the least-privilege application role | Existing database and schema `tpi` | Versioned and used for deployment planning | Local admin / AWS admin | Manual revoke / role disable if needed |
| `scripts/sql/003_create_api_idempotency.sql` | Create the public-API idempotency table | `tpi.leads` | Versioned; runtime feature gate dependent | Admin deployment | `scripts/sql/003_drop_api_idempotency.sql` |
| `scripts/sql/003_drop_api_idempotency.sql` | Rollback for idempotency table | `tpi.api_idempotency` exists | Versioned rollback script | Admin deployment | Drop table and revoke grants |
| `scripts/sql/004_create_lead_assignments.sql` | Create assignment table and indexes | `tpi.leads`, `tpi.asesores` | Versioned; aligned with AWS DEV physical contract | Admin deployment | Drop table / indexes if needed in a controlled rollback |
| `scripts/sql/005_enforce_single_active_assignment.sql` | Enforce one active assignment per lead | `tpi.asignaciones` existing data | Prepared, not executed in AWS DEV yet | Admin deployment | `DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq` |
| `scripts/sql/dev/002_enable_test_cleanup.sql` | DEV-only delete grant for controlled cleanup | `tpi.leads`, `tpi.consentimientos` | DEV-only helper | AWS DEV only | `scripts/sql/dev/002_disable_test_cleanup.sql` |
| `scripts/sql/dev/002_disable_test_cleanup.sql` | Revoke the DEV-only delete grant | Previous enable script applied | DEV-only rollback helper | AWS DEV only | Revoke delete grant |

## Current State vs Target State

### AWS DEV current physical state

- `tpi.asignaciones` exists
- the partial UNIQUE index for active assignment does not exist yet
- duplicate active assignments are still structurally possible

### Target state after migration `005`

- at most one active assignment per `id_lead`
- the database enforces the invariant
- application code still performs validation and conflict translation

## Migration `005` Notes

The prepared migration follows this model:

1. preflight query checks for duplicate active assignments
2. abort if duplicates already exist
3. create a partial UNIQUE index on `id_lead`
4. scope the index to `estado_asignacion = 'activa'`

Important:

- this migration does not change business data
- it only adds integrity protection
- it is not executed on AWS DEV yet

## Bootstrap vs Migration

`scripts/init_test_database.py` is not a runtime migration.

It is the test bootstrap that recreates the schema contract for CI and
integration tests, including the assignment table and the partial UNIQUE
index that tests need to validate integrity behavior.

## Drift Rule

If AWS DEV diverges from the versioned scripts, the fix should be a migration.

Do not manually patch schema drift in AWS when the change is meant to be
versioned and repeatable.


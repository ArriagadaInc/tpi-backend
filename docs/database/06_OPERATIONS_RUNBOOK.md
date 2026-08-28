Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-08-28
Fuente: PostgreSQL RDS + scripts versionados + init_test_database.py

# 06 Operations Runbook

## Purpose

This runbook covers the operational steps needed to validate, inspect, migrate,
verify, and roll back the database layer.

## 1. Validate Connectivity

Read-only checks:

```sql
SELECT version();
SELECT current_database();
SELECT current_user;
```

Validate schema visibility:

```sql
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'tpi';
```

Validate table presence:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'tpi'
ORDER BY table_name;
```

## 2. Inspect Tables, Indexes, and FK

Useful catalog queries:

```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'tpi'
ORDER BY tablename, indexname;
```

```sql
SELECT conrelid::regclass AS table_name,
       conname,
       contype,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'tpi'::regnamespace
ORDER BY conrelid::regclass::text, conname;
```

## 3. Read-Only Inspection

When validating AWS DEV, use the dedicated inspection script and keep the
session read-only.

Rule:

- no `INSERT`
- no `UPDATE`
- no `DELETE`
- no `ALTER`
- no `CREATE`
- no `DROP`

## 4. Preflight Before Migration `005`

Check for duplicate active assignments:

```sql
SELECT id_lead, COUNT(*) AS active_rows
FROM tpi.asignaciones
WHERE estado_asignacion = 'activa'
GROUP BY id_lead
HAVING COUNT(*) > 1
ORDER BY active_rows DESC, id_lead;
```

If this returns rows:

- do not create the partial UNIQUE index yet
- resolve the duplicates by an approved business decision
- then rerun the migration preflight

## 5. Apply a Migration

Recommended process:

1. confirm the repository commit SHA that declares the migration
2. confirm the target environment
3. run the preflight query
4. apply the migration in the approved admin session
5. verify the resulting constraints and indexes
6. record the result in release notes or change log

Do not patch schema drift manually if the fix is meant to be versioned.

## 6. Verify a Migration

After migration `005`, verify:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'tpi'
  AND tablename = 'asignaciones'
  AND indexname = 'asignaciones_one_active_per_lead_uq';
```

```sql
SELECT id_lead
FROM tpi.asignaciones
WHERE estado_asignacion = 'activa'
GROUP BY id_lead
HAVING COUNT(*) > 1;
```

Expected:

- the partial unique index exists
- the duplicate query returns no rows

## 7. Rollback

For migration `005` the rollback is:

```sql
DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq;
```

Rollback rules:

- only remove the integrity object that was added
- do not delete business data
- do not remove the schema or the RDS instance

## 8. Backup and Restore

Use approved AWS or PostgreSQL backup mechanisms only.

Examples:

- automated RDS snapshot
- approved `pg_dump` / `pg_restore` workflow

Never use manual schema edits as a substitute for a reproducible backup or
migration path.

## 9. Post-Deploy Checks

After a release deployment:

- run the application health check
- confirm database connectivity
- confirm `tpi.leads` is accessible
- confirm the assignment flow if H3.3 is in scope
- confirm the audit trail is generated when the app contract says it should be

## 10. Healthcheck

The runtime healthcheck should remain lightweight and safe:

- `SELECT 1`
- current database
- current user
- schema visibility
- table accessibility

Use `python scripts/verify_database_connection.py` for a quick operational
check outside the UI.


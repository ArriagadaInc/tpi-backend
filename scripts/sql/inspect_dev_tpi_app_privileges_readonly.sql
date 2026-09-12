-- Purpose:
--   Read-only inspection of the effective privileges granted to role tpi_app
--   in AWS DEV.
--
-- Environment:
--   AWS DEV / tpi-postgres-dev
--
-- Safety:
--   - metadata and privilege inspection only
--   - no INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, GRANT, or REVOKE
--   - no PII or business rows are selected
--   - safe to execute from DBeaver as a normal SQL script
--
-- Expected usage:
--   Open this file in DBeaver connected to AWS DEV and run the full script.
--   Review the result grids to compare observed privileges with the versioned
--   role script in the repository.
--
-- Last validated physical context:
--   2026-08-28
--
-- Source of truth:
--   AWS DEV physical role grants + versioned repository scripts

BEGIN TRANSACTION READ ONLY;

SELECT
    has_schema_privilege('tpi_app', 'tpi', 'USAGE') AS schema_usage;

SELECT
    table_name,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'SELECT') AS can_select,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'INSERT') AS can_insert,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'UPDATE') AS can_update,
    has_table_privilege('tpi_app', 'tpi.' || table_name, 'DELETE') AS can_delete
FROM (
    VALUES
        ('leads'),
        ('personas'),
        ('asesores'),
        ('asignaciones'),
        ('auditoria')
) AS t(table_name)
ORDER BY table_name;

SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'tpi_app'
  AND table_schema = 'tpi'
ORDER BY table_name, privilege_type;

SELECT
    parent.rolname AS granted_role,
    child.rolname AS member_role,
    am.admin_option,
    pg_has_role('tpi_app', parent.rolname, 'USAGE') AS effective_for_tpi_app
FROM pg_auth_members am
JOIN pg_roles child
    ON child.oid = am.member
JOIN pg_roles parent
    ON parent.oid = am.roleid
WHERE child.rolname = 'tpi_app'
ORDER BY parent.rolname;

SELECT
    rolname AS effective_role,
    rolinherit
FROM pg_roles
WHERE pg_has_role('tpi_app', rolname, 'USAGE')
ORDER BY rolname;

SELECT
    has_table_privilege('tpi_app', 'tpi.auditoria', 'INSERT') AS can_insert_auditoria,
    has_table_privilege('tpi_app', 'tpi.auditoria', 'SELECT') AS can_select_auditoria,
    has_table_privilege('tpi_app', 'tpi.auditoria', 'UPDATE') AS can_update_auditoria,
    has_table_privilege('tpi_app', 'tpi.auditoria', 'DELETE') AS can_delete_auditoria;

COMMIT;

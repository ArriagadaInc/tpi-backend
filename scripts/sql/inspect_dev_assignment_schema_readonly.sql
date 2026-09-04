-- Purpose: Read-only inspection of the physical assignment schema in AWS DEV.
-- Target environment: AWS DEV (tpi-postgres-dev).
-- Scope: metadata only, no writes, no DDL, no side effects.
-- PII: this script must not return lead rows, person rows, or raw_payload contents.
-- Date: 2026-08-27
--
-- Execution instructions:
-- 1. Open this file in DBeaver connected to AWS DEV.
-- 2. Ensure the connection uses a read-only administrative or inspection-capable role.
-- 3. Execute the whole script.
-- 4. Copy the result sets in order and share them back for comparison.
--
-- Safety:
-- - Uses SELECT only.
-- - Reads catalog/metadata tables only.
-- - Does not mutate data or schema.

BEGIN TRANSACTION READ ONLY;

SELECT
    current_database() AS database_name,
    current_user AS effective_user,
    current_schema AS effective_schema,
    version() AS server_version;

SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind AS relation_kind,
    pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'tpi'
  AND c.relname IN ('asignaciones', 'leads', 'auditoria')
ORDER BY c.relname;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale
FROM information_schema.columns c
WHERE c.table_schema = 'tpi'
  AND c.table_name = 'asignaciones'
ORDER BY c.ordinal_position;

SELECT
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'tpi'
  AND tc.table_name = 'asignaciones'
ORDER BY tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

SELECT
    i.relname AS index_name,
    ix.indisprimary AS is_primary,
    ix.indisunique AS is_unique,
    ix.indpred IS NOT NULL AS is_partial,
    pg_get_indexdef(ix.indexrelid) AS index_def
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'tpi'
  AND t.relname = 'asignaciones'
ORDER BY i.relname;

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS constraint_def
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'tpi'
  AND t.relname = 'asignaciones'
ORDER BY con.contype, con.conname;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = 'tpi'
  AND c.table_name = 'leads'
  AND c.column_name IN (
      'id_lead',
      'estado_lead',
      'created_at',
      'updated_at',
      'raw_payload',
      'id_persona'
        )
ORDER BY c.ordinal_position;

SELECT
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'tpi'
  AND tc.table_name = 'leads'
  AND (
      tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK')
      OR kcu.column_name IN ('estado_lead', 'id_persona')
  )
ORDER BY tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

SELECT
    i.relname AS index_name,
    ix.indisprimary AS is_primary,
    ix.indisunique AS is_unique,
    ix.indpred IS NOT NULL AS is_partial,
    pg_get_indexdef(ix.indexrelid) AS index_def
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'tpi'
  AND t.relname = 'leads'
ORDER BY i.relname;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = 'tpi'
  AND c.table_name = 'auditoria'
ORDER BY c.ordinal_position;



SELECT
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'tpi'
  AND tc.table_name = 'auditoria'
ORDER BY tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

SELECT
    i.relname AS index_name,
    ix.indisprimary AS is_primary,
    ix.indisunique AS is_unique,
    ix.indpred IS NOT NULL AS is_partial,
    pg_get_indexdef(ix.indexrelid) AS index_def
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'tpi'
  AND t.relname = 'auditoria'
ORDER BY i.relname;

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS constraint_def
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'tpi'
  AND t.relname = 'auditoria'
ORDER BY con.contype, con.conname;

WITH assignment_fk AS (
    SELECT
        con.oid AS con_oid,
        nsp_ref.nspname AS ref_schema,
        cls_ref.relname AS ref_table
    FROM pg_constraint con
    JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
    JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
    JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
    JOIN pg_namespace nsp_ref ON nsp_ref.oid = cls_ref.relnamespace
    WHERE nsp_assign.nspname = 'tpi'
      AND cls_assign.relname = 'asignaciones'
      AND con.contype = 'f'
      AND EXISTS (
          SELECT 1
          FROM unnest(con.conkey) AS k(attnum)
          JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
          WHERE att.attname = 'id_asesor'
      )
    LIMIT 1
)
SELECT
    'referenced_by_id_asesor' AS relation_role,
    ref_schema,
    ref_table,
    con_oid::text AS constraint_oid
FROM assignment_fk;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = (
        SELECT nsp_ref.nspname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        JOIN pg_namespace nsp_ref ON nsp_ref.oid = cls_ref.relnamespace
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
  AND c.table_name = (
        SELECT cls_ref.relname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
ORDER BY c.ordinal_position;

SELECT
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = (
        SELECT nsp_ref.nspname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        JOIN pg_namespace nsp_ref ON nsp_ref.oid = cls_ref.relnamespace
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
  AND tc.table_name = (
        SELECT cls_ref.relname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
ORDER BY tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

SELECT
    i.relname AS index_name,
    ix.indisprimary AS is_primary,
    ix.indisunique AS is_unique,
    ix.indpred IS NOT NULL AS is_partial,
    pg_get_indexdef(ix.indexrelid) AS index_def
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = (
        SELECT nsp_ref.nspname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        JOIN pg_namespace nsp_ref ON nsp_ref.oid = cls_ref.relnamespace
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
  AND t.relname = (
        SELECT cls_ref.relname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
ORDER BY i.relname;

SELECT
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    pg_get_constraintdef(con.oid) AS constraint_def
FROM pg_constraint con
JOIN pg_class t ON t.oid = con.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = (
        SELECT nsp_ref.nspname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        JOIN pg_namespace nsp_ref ON nsp_ref.oid = cls_ref.relnamespace
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
  AND t.relname = (
        SELECT cls_ref.relname
        FROM pg_constraint con
        JOIN pg_class cls_assign ON cls_assign.oid = con.conrelid
        JOIN pg_namespace nsp_assign ON nsp_assign.oid = cls_assign.relnamespace
        JOIN pg_class cls_ref ON cls_ref.oid = con.confrelid
        WHERE nsp_assign.nspname = 'tpi'
          AND cls_assign.relname = 'asignaciones'
          AND con.contype = 'f'
          AND EXISTS (
              SELECT 1
              FROM unnest(con.conkey) AS k(attnum)
              JOIN pg_attribute att ON att.attrelid = cls_assign.oid AND att.attnum = k.attnum
              WHERE att.attname = 'id_asesor'
          )
        LIMIT 1
    )
ORDER BY con.contype, con.conname;

SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'tpi'
  AND tc.table_name = 'leads'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND tc.constraint_name = (
        SELECT tc2.constraint_name
        FROM information_schema.table_constraints tc2
        JOIN information_schema.key_column_usage kcu2
          ON tc2.constraint_name = kcu2.constraint_name
         AND tc2.table_schema = kcu2.table_schema
        WHERE tc2.table_schema = 'tpi'
          AND tc2.table_name = 'leads'
          AND kcu2.column_name = 'estado_lead'
          AND tc2.constraint_type = 'FOREIGN KEY'
        LIMIT 1
    )
ORDER BY tc.constraint_name;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = 'tpi'
  AND c.table_name = (
        SELECT ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'tpi'
          AND tc.table_name = 'leads'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'estado_lead'
        LIMIT 1
    )
ORDER BY c.ordinal_position;

SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    ccu.table_schema AS foreign_table_schema,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'tpi'
  AND tc.table_name = 'asignaciones'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND tc.constraint_name = (
        SELECT tc2.constraint_name
        FROM information_schema.table_constraints tc2
        JOIN information_schema.key_column_usage kcu2
          ON tc2.constraint_name = kcu2.constraint_name
         AND tc2.table_schema = kcu2.table_schema
        WHERE tc2.table_schema = 'tpi'
          AND tc2.table_name = 'asignaciones'
          AND kcu2.column_name = 'estado_asignacion'
          AND tc2.constraint_type = 'FOREIGN KEY'
        LIMIT 1
    )
ORDER BY tc.constraint_name;

SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = 'tpi'
  AND c.table_name = (
        SELECT ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'tpi'
          AND tc.table_name = 'asignaciones'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'estado_asignacion'
        LIMIT 1
    )
ORDER BY c.ordinal_position;

COMMIT;

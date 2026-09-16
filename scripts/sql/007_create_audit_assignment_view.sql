-- H3.3.3 / migracion 007: read model SQL sanitizado (vista, no tabla) sobre tpi.auditoria.
--
-- Objetivo:
--   Exponer a tpi_app una vista de solo lectura con la trazabilidad de la asignacion
--   de leads que ya se registra en tpi.auditoria, sin conceder acceso directo a la
--   tabla (append-only se mantiene intacto) y sin duplicar estado_anterior/estado_nuevo
--   en tpi.asignaciones (decisión de arquitectura aprobada).
--
-- Contrato de la vista:
--   - Filtro fijo: accion = 'asignacion_lead' AND tabla_afectada = 'tpi.asignaciones'.
--   - Columnas permitidas UNICAMENTE:
--       id_auditoria, id_lead, fecha_hora, actor_subject,
--       id_asesor, estado_anterior, estado_nuevo.
--     NO expone el JSON crudo (detalle), id_persona, id_usuario, ip_origen ni otros eventos.
--   - id_asesor es UUID, no numerico. Se valida con CASE y una expresion regular canonica
--     de UUID case-insensitive ANTES del cast; un valor no-UUID proyecta NULL solo en esa
--     fila y la vista sigue devolviendo el resto de filas sin lanzar excepcion.
--   - security_barrier (PostgreSQL >= 9.5; compatible con PostgreSQL 15 y el RDS objetivo).
--   - REVOKE ALL ... FROM PUBLIC.
--   - GRANT SELECT unicamente a tpi_app.
--   - NO modifica los privilegios de tpi_app sobre tpi.auditoria
--     (SELECT/UPDATE/DELETE continuan false; contrato append-only vigente desde 006).
--
-- Orden estable: la vista NO impone orden (PostgreSQL no lo garantiza en vistas); el
-- orden estable (fecha_hora DESC, id_auditoria DESC) lo aplica la consulta del
-- repositorio. Ver app/repositories/solicitud_repository.py.
--
-- Preflight/postflight: este script esta orientado a AWS DEV (ejecutado por tpi_admin).
-- El preflight aborta si tpi_app ya posee SELECT/UPDATE/DELETE directo sobre
-- tpi.auditoria (drift de seguridad). En CI el usuario de conexion es superuser y este
-- script no se ejecuta: los tests de integracion replican el DDL de la vista y verifican
-- el contrato con un rol de minimo privilegio.
--
-- Este script NO se aplica en AWS RDS DEV en la etapa de desarrollo: su aplicacion queda
-- condicionada a la aprobacion humana explicita del migration candidate (AC-5) y ocurre
-- en una etapa posterior gestionada por Human Gate.
--
-- Rollback: scripts/sql/007_drop_audit_assignment_view.sql

BEGIN;

DO $$
DECLARE
    v_schema_usage boolean;
    v_auditoria_select boolean;
    v_auditoria_update boolean;
    v_auditoria_delete boolean;
BEGIN
    SELECT
        has_schema_privilege('tpi_app', 'tpi', 'USAGE'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'UPDATE'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'DELETE')
    INTO
        v_schema_usage,
        v_auditoria_select,
        v_auditoria_update,
        v_auditoria_delete;

    IF NOT (
        v_schema_usage
        AND NOT v_auditoria_select
        AND NOT v_auditoria_update
        AND NOT v_auditoria_delete
    ) THEN
        RAISE EXCEPTION
            '007 preflight failed: tpi_app posee privilegios directos sobre tpi.auditoria o falta USAGE sobre tpi';
    END IF;
END
$$;

CREATE OR REPLACE VIEW tpi.v_asignacion_auditoria
WITH (security_barrier = true) AS
SELECT
    a.id_auditoria,
    a.id_lead,
    a.fecha_hora,
    a.detalle->>'actor_subject' AS actor_subject,
    CASE
        WHEN a.detalle->>'id_asesor' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN (a.detalle->>'id_asesor')::uuid
        ELSE NULL
    END AS id_asesor,
    a.detalle->>'estado_anterior' AS estado_anterior,
    a.detalle->>'estado_nuevo' AS estado_nuevo
FROM tpi.auditoria a
WHERE a.accion = 'asignacion_lead'
  AND a.tabla_afectada = 'tpi.asignaciones';

REVOKE ALL ON tpi.v_asignacion_auditoria FROM PUBLIC;
GRANT SELECT ON tpi.v_asignacion_auditoria TO tpi_app;

DO $$
DECLARE
    v_app_select boolean;
    v_public_any boolean;
    v_auditoria_select boolean;
    v_auditoria_update boolean;
    v_auditoria_delete boolean;
BEGIN
    SELECT
        has_table_privilege('tpi_app', 'tpi.v_asignacion_auditoria', 'SELECT'),
        COALESCE((
            SELECT bool_or(grantee = 0)
            FROM aclexplode(c.relacl)
        ), false),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'UPDATE'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'DELETE')
    INTO
        v_app_select,
        v_public_any,
        v_auditoria_select,
        v_auditoria_update,
        v_auditoria_delete
    FROM pg_class c
    WHERE c.oid = 'tpi.v_asignacion_auditoria'::regclass;

    IF NOT (
        v_app_select
        AND NOT v_public_any
        AND NOT v_auditoria_select
        AND NOT v_auditoria_update
        AND NOT v_auditoria_delete
    ) THEN
        RAISE EXCEPTION
            '007 postflight failed: contrato de privilegios de la vista no alcanzado';
    END IF;
END
$$;

COMMIT;

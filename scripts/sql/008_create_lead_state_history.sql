-- H3.3.4 / migracion 008: read model SQL sanitizado (vista) sobre tpi.auditoria
-- para el historial integral de cambios generales de estado de un lead.
--
-- Objetivo:
--   Exponer a tpi_app una vista de solo lectura con la trazabilidad de los cambios
--   generales de estado_lead que ya se registran en tpi.auditoria (accion
--   'cambio_estado_lead'), sin conceder acceso directo a la tabla (append-only se
--   mantiene intacto) y sin duplicar estado_anterior/estado_nuevo en tpi.leads
--   (decision de arquitectura aprobada, mismo patron que la migracion 007).
--
-- Contrato de la vista:
--   - Filtro fijo: accion = 'cambio_estado_lead' AND tabla_afectada = 'tpi.leads'.
--   - Columnas permitidas UNICAMENTE:
--       id_auditoria, id_lead, fecha_hora, actor_subject,
--       estado_anterior, estado_nuevo.
--     NO expone el JSON crudo (detalle), id_persona, id_usuario, ip_origen ni otros
--     eventos (asignaciones, notas, etc.).
--   - security_barrier (PostgreSQL >= 9.5; compatible con PostgreSQL 15/17 y el RDS
--     objetivo).
--   - REVOKE ALL ... FROM PUBLIC.
--   - GRANT SELECT unicamente a tpi_app.
--   - NO modifica los privilegios de tpi_app sobre tpi.auditoria
--     (SELECT/UPDATE/DELETE continuan false; contrato append-only vigente desde 006).
--
-- Indice de apoyo:
--   - auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora).
--     Justificado por EXPLAIN real (ver evidencia H3.3.4): reduce la consulta de
--     timeline de un lead de un Seq Scan sobre toda la tabla a un Index Scan acotado
--     (~40x menos latencia y ~90x menos buffers a 100k filas) y tambien acota la
--     agregacion por fecha/accion requerida por la Parte B.
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
-- Rollback: scripts/sql/008_drop_lead_state_history.sql

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
            '008 preflight failed: tpi_app posee privilegios directos sobre tpi.auditoria o falta USAGE sobre tpi';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS auditoria_state_history_idx
    ON tpi.auditoria (accion, tabla_afectada, id_lead, fecha_hora);

CREATE OR REPLACE VIEW tpi.v_historial_estado_lead
WITH (security_barrier = true) AS
SELECT
    a.id_auditoria,
    a.id_lead,
    a.fecha_hora,
    a.detalle->>'actor_subject' AS actor_subject,
    a.detalle->>'estado_anterior' AS estado_anterior,
    a.detalle->>'estado_nuevo' AS estado_nuevo
FROM tpi.auditoria a
WHERE a.accion = 'cambio_estado_lead'
  AND a.tabla_afectada = 'tpi.leads';

REVOKE ALL ON tpi.v_historial_estado_lead FROM PUBLIC;
GRANT SELECT ON tpi.v_historial_estado_lead TO tpi_app;

DO $$
DECLARE
    v_app_select boolean;
    v_public_any boolean;
    v_auditoria_select boolean;
    v_auditoria_update boolean;
    v_auditoria_delete boolean;
    v_index_exists boolean;
BEGIN
    SELECT
        has_table_privilege('tpi_app', 'tpi.v_historial_estado_lead', 'SELECT'),
        COALESCE((
            SELECT bool_or(grantee = 0)
            FROM aclexplode(c.relacl)
        ), false),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'SELECT'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'UPDATE'),
        has_table_privilege('tpi_app', 'tpi.auditoria', 'DELETE'),
        EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'tpi'
              AND tablename = 'auditoria'
              AND indexname = 'auditoria_state_history_idx'
        )
    INTO
        v_app_select,
        v_public_any,
        v_auditoria_select,
        v_auditoria_update,
        v_auditoria_delete,
        v_index_exists
    FROM pg_class c
    WHERE c.oid = 'tpi.v_historial_estado_lead'::regclass;

    IF NOT (
        v_app_select
        AND NOT v_public_any
        AND NOT v_auditoria_select
        AND NOT v_auditoria_update
        AND NOT v_auditoria_delete
        AND v_index_exists
    ) THEN
        RAISE EXCEPTION
            '008 postflight failed: contrato de privilegios de la vista no alcanzado';
    END IF;
END
$$;

COMMIT;

-- CRM-AGENDA-4-HISTORIAL-MIGRACION / migracion 011: read model SQL sanitizado (vista) sobre
-- tpi.auditoria para el historial del lead con los eventos de la agenda de reuniones.
--
-- Objetivo:
--   Exponer a tpi_app una vista de solo lectura con los eventos del agendamiento
--   (cita_agendada, cita_reagendada, cita_cancelada, cita_realizada y cita_no_asistio)
--   registrados en tpi.auditoria, sin conceder acceso directo a la tabla (append-only se
--   mantiene intacto) y sin duplicar estado en tpi.citas.
--
-- Contrato de la vista:
--   - Filtro fijo: accion IN ('cita_agendada', 'cita_reagendada', 'cita_cancelada',
--     'cita_realizada', 'cita_no_asistio') AND tabla_afectada = 'tpi.citas'.
--   - Columnas permitidas UNICAMENTE:
--       id_auditoria, id_lead, fecha_hora, accion, actor_subject,
--       id_cita (UUID), responsable_id (UUID, puede ser NULL),
--       estado_anterior, estado_nuevo,
--       fecha_hora_anterior (TIMESTAMPTZ, puede ser NULL) y
--       fecha_hora_nueva (TIMESTAMPTZ, puede ser NULL).
--     NO expone el detalle crudo, id_persona, id_usuario ni ip_origen. La nota y el motivo
--     de cancelacion de la reunion no se registran en la auditoria de la agenda
--     (AgendaRepository._insert_cita_audit) y no llegan nunca a esta vista.
--   - id_cita y responsable_id se validan con CASE y una expresion regular canonica de UUID
--     case-insensitive ANTES del cast; un valor no-UUID proyecta NULL solo en esa fila y la
--     vista sigue devolviendo el resto de filas sin lanzar excepcion.
--   - fecha_hora_anterior y fecha_hora_nueva se proyectan como TIMESTAMPTZ. El escritor real
--     (AgendaRepository._insert_cita_audit) las guarda como ISO 8601 con zona horaria
--     (datetime.isoformat() de un datetime timezone-aware) o JSON null; ambos valores se
--     convierten de forma segura al tipo de destino.
--   - security_barrier (PostgreSQL >= 9.5; compatible con PostgreSQL 15/17 y el RDS objetivo).
--   - REVOKE ALL ... FROM PUBLIC.
--   - GRANT SELECT unicamente a tpi_app (sin SELECT sobre tpi.auditoria).
--   - NO modifica los privilegios de tpi_app sobre tpi.auditoria
--     (SELECT/UPDATE/DELETE continuan false; contrato append-only vigente desde 006).
--
-- Indice de apoyo: no se crea ninguno nuevo. La consulta de historial (accion, tabla_afectada,
-- id_lead, orden por fecha_hora) queda servida por el indice de apoyo existente de la migracion
-- 008 `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)`, cuyas
-- columnas lideres coinciden con el filtro de esta vista.
--
-- Orden estable: la vista NO impone orden (PostgreSQL no lo garantiza en vistas); el orden
-- estable (fecha_hora DESC, id_auditoria DESC) lo aplica la consulta del repositorio.
--
-- Preflight/postflight: este script esta orientado a AWS DEV (ejecutado por tpi_admin).
-- El preflight aborta si tpi_app ya posee SELECT/UPDATE/DELETE directo sobre tpi.auditoria
-- (drift de seguridad). En CI el usuario de conexion es superuser y este script no se ejecuta:
-- los tests de integracion replican el DDL de la vista y verifican el contrato con un rol de
-- minimo privilegio.
--
-- Este script NO se aplica en AWS RDS DEV en la etapa de desarrollo: su aplicacion queda
-- condicionada a la aprobacion humana explicita del migration candidate y ocurre en una
-- etapa posterior gestionada por Human Gate.
--
-- Rollback: scripts/sql/011_drop_historial_agenda.sql

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
            '011 preflight failed: tpi_app posee privilegios directos sobre tpi.auditoria o falta USAGE sobre tpi';
    END IF;
END
$$;

CREATE OR REPLACE VIEW tpi.v_historial_agenda
WITH (security_barrier = true) AS
SELECT
    a.id_auditoria,
    a.id_lead,
    a.fecha_hora,
    a.accion,
    a.detalle->>'actor_subject' AS actor_subject,
    CASE
        WHEN a.detalle->>'id_cita' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN (a.detalle->>'id_cita')::uuid
        ELSE NULL
    END AS id_cita,
    CASE
        WHEN a.detalle->>'responsable_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN (a.detalle->>'responsable_id')::uuid
        ELSE NULL
    END AS responsable_id,
    a.detalle->>'estado_anterior' AS estado_anterior,
    a.detalle->>'estado_nuevo' AS estado_nuevo,
    (a.detalle->>'fecha_hora_anterior')::timestamptz AS fecha_hora_anterior,
    (a.detalle->>'fecha_hora_nueva')::timestamptz AS fecha_hora_nueva
FROM tpi.auditoria a
WHERE a.accion IN ('cita_agendada', 'cita_reagendada', 'cita_cancelada', 'cita_realizada', 'cita_no_asistio')
  AND a.tabla_afectada = 'tpi.citas';

REVOKE ALL ON tpi.v_historial_agenda FROM PUBLIC;
GRANT SELECT ON tpi.v_historial_agenda TO tpi_app;

DO $$
DECLARE
    v_app_select boolean;
    v_public_any boolean;
    v_auditoria_select boolean;
    v_auditoria_update boolean;
    v_auditoria_delete boolean;
BEGIN
    SELECT
        has_table_privilege('tpi_app', 'tpi.v_historial_agenda', 'SELECT'),
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
    WHERE c.oid = 'tpi.v_historial_agenda'::regclass;

    IF NOT (
        v_app_select
        AND NOT v_public_any
        AND NOT v_auditoria_select
        AND NOT v_auditoria_update
        AND NOT v_auditoria_delete
    ) THEN
        RAISE EXCEPTION
            '011 postflight failed: contrato de privilegios de la vista no alcanzado';
    END IF;
END
$$;

COMMIT;

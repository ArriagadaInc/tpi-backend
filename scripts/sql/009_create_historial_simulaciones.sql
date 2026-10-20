-- SIM-HISTORIAL-LINEA-TIEMPO / migracion 009: read model SQL sanitizado (vista) sobre
-- tpi.auditoria para el historial de simulaciones de renta vitalicia generadas por lead.
--
-- Objetivo:
--   Exponer a tpi_app una vista de solo lectura con TODA la evidencia registrada por cada
--   simulacion (accion 'simulacion_renta_vitalicia'), sin censurar ningun dato (decision del
--   humano, 2026-10-19), sin conceder acceso directo a la tabla (append-only se mantiene
--   intacto) y sin duplicar estado en tpi.leads.
--
-- Contrato de la vista:
--   - Filtro fijo: accion = 'simulacion_renta_vitalicia' AND tabla_afectada = 'tpi.leads'.
--   - Columnas:
--       id_auditoria, id_lead, fecha_hora, actor_subject,
--       tipo_escenario, version_modelo, codigo_verificacion,
--       entradas (JSONB completo) y resultado (JSONB completo).
--     El detalle de simulacion no contiene nombres, RUT, correo ni telefono
--     (SIM-EVIDENCIA-ENTRADAS); las fechas de nacimiento y la composicion familiar son los
--     datos personales minimos del grupo familiar y se exponen completos por decision del
--     humano (2026-10-19: no se censura ningun dato registrado).
--   - NO expone el JSON crudo completo (detalle), id_persona, id_usuario ni ip_origen; expone
--     exactamente las partes funcionales del detalle (entradas y resultado) mas los metadatos
--     de raiz necesarios para la linea de tiempo.
--   - security_barrier (PostgreSQL >= 9.5; compatible con PostgreSQL 15/17 y el RDS objetivo).
--   - REVOKE ALL ... FROM PUBLIC.
--   - GRANT SELECT unicamente a tpi_app (sin SELECT sobre tpi.auditoria).
--   - NO modifica los privilegios de tpi_app sobre tpi.auditoria
--     (SELECT/UPDATE/DELETE continuan false; contrato append-only vigente desde 006).
--
-- Indice de apoyo: no se crea ninguno nuevo. La consulta de timeline (accion, tabla_afectada,
-- id_lead, orden por fecha_hora) queda servida por el indice de apoyo existente de la migracion
-- 008 `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)`, cuyas
-- columnas lideres coinciden exactamente con el filtro de esta vista y su consulta de repositorio.
--
-- Orden estable: la vista NO impone orden (PostgreSQL no lo garantiza en vistas); el orden
-- estable (fecha_hora DESC, id_auditoria DESC) lo aplica la consulta del repositorio.
-- Ver app/repositories/solicitud_repository.py.
--
-- Preflight/postflight: este script esta orientado a AWS DEV (ejecutado por tpi_admin).
-- El preflight aborta si tpi_app ya posee SELECT/UPDATE/DELETE directo sobre tpi.auditoria
-- (drift de seguridad). En CI el usuario de conexion es superuser y este script no se ejecuta:
-- los tests de integracion replican el DDL de la vista y verifican el contrato con un rol de
-- minimo privilegio.
--
-- Este script NO se aplica en AWS RDS DEV en la etapa de desarrollo: su aplicacion queda
-- condicionada a la aprobacion humana explicita del migration candidate (AC-5) y ocurre en una
-- etapa posterior gestionada por Human Gate.
--
-- Rollback: scripts/sql/009_drop_historial_simulaciones.sql

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
            '009 preflight failed: tpi_app posee privilegios directos sobre tpi.auditoria o falta USAGE sobre tpi';
    END IF;
END
$$;

CREATE OR REPLACE VIEW tpi.v_historial_simulaciones
WITH (security_barrier = true) AS
SELECT
    a.id_auditoria,
    a.id_lead,
    a.fecha_hora,
    a.detalle->>'actor_subject' AS actor_subject,
    a.detalle->>'tipo_escenario' AS tipo_escenario,
    a.detalle->>'version_modelo' AS version_modelo,
    a.detalle->>'codigo_verificacion' AS codigo_verificacion,
    a.detalle->'entradas' AS entradas,
    a.detalle->'resultado' AS resultado
FROM tpi.auditoria a
WHERE a.accion = 'simulacion_renta_vitalicia'
  AND a.tabla_afectada = 'tpi.leads';

REVOKE ALL ON tpi.v_historial_simulaciones FROM PUBLIC;
GRANT SELECT ON tpi.v_historial_simulaciones TO tpi_app;

DO $$
DECLARE
    v_app_select boolean;
    v_public_any boolean;
    v_auditoria_select boolean;
    v_auditoria_update boolean;
    v_auditoria_delete boolean;
BEGIN
    SELECT
        has_table_privilege('tpi_app', 'tpi.v_historial_simulaciones', 'SELECT'),
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
    WHERE c.oid = 'tpi.v_historial_simulaciones'::regclass;

    IF NOT (
        v_app_select
        AND NOT v_public_any
        AND NOT v_auditoria_select
        AND NOT v_auditoria_update
        AND NOT v_auditoria_delete
    ) THEN
        RAISE EXCEPTION
            '009 postflight failed: contrato de privilegios de la vista no alcanzado';
    END IF;
END
$$;

COMMIT;

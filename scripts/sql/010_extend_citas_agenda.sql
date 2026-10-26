-- CRM-AGENDA-1-MIGRACION / migracion 010: ampliar tpi.citas y tpi.asesores para la agenda
-- de reuniones del CRM (seccion 6 de docs/AGENDA_REUNIONES_DISENO.md).
--
-- Objetivo:
--   Preparar el esquema que sostiene la agenda de reuniones sin crear una tabla nueva:
--   tpi.citas la crea hoy setup_db.py del proyecto tpi-data-pipeline (CREATE TABLE IF NOT
--   EXISTS, 0 filas en DEV) y este script la amplia. Se deja tpi.asesores con la marca
--   atiende_reuniones para distinguir a quienes pueden ser responsables de una reunion
--   (Socios CEO/CTO con rol 'socio' y Coordinadores con rol 'asesor' y la marca en true).
--
-- Preflight (aborta con mensaje claro):
--   - falta el esquema tpi
--   - tpi.citas tiene filas (se exige vacia para no tocar reuniones existentes)
--   - btree_gist no puede crearse (la restriccion EXCLUDE la exige)
--
-- Cambios:
--   - CREATE EXTENSION IF NOT EXISTS btree_gist.
--   - tpi.citas: id_asesor pasa a NOT NULL (responsable de la asesoria); columnas nuevas
--     fecha_hora_fin (TIMESTAMPTZ NOT NULL, CHECK > fecha_hora), agendada_por_subject y
--     agendada_por_nombre (texto, sin FK), nota (texto), motivo_cancelacion (texto) y
--     updated_at (TIMESTAMPTZ NOT NULL DEFAULT now()); CHECK de estado_cita (agendada,
--     realizada, no_asistio, cancelada); indice unico parcial (una agendada por lead);
--     EXCLUDE USING gist (el responsable no se pisa) e indice por fecha_hora.
--   - tpi.asesores: atiende_reuniones BOOLEAN NOT NULL DEFAULT false.
--   - Privilegios: REVOKE ALL sobre tpi.citas FROM PUBLIC y GRANT SELECT, INSERT, UPDATE a
--     tpi_app (sin DELETE). No toca los privilegios de tpi_app sobre tpi.auditoria ni sobre
--     las demas tablas.
--
-- Este script NO se aplica en AWS RDS DEV en la etapa de desarrollo: su aplicacion es
-- change_class D y ocurre en una etapa posterior gestionada por Human Gate (el humano la
-- aplica con tpi_admin tras comprobar que RDS permite btree_gist).
--
-- Rollback: scripts/sql/010_drop_citas_agenda.sql

BEGIN;

DO $$
DECLARE
    v_schema boolean;
    v_filas bigint;
BEGIN
    SELECT to_regnamespace('tpi') IS NOT NULL INTO v_schema;
    IF NOT v_schema THEN
        RAISE EXCEPTION '010 preflight failed: falta el esquema tpi';
    END IF;

    SELECT count(*) INTO v_filas FROM tpi.citas;
    IF v_filas > 0 THEN
        RAISE EXCEPTION
            '010 preflight failed: tpi.citas no esta vacia (tiene % filas); la migracion exige la tabla vacia para no tocar reuniones existentes',
            v_filas;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'btree_gist') THEN
        RAISE EXCEPTION
            '010 preflight failed: la extension btree_gist no esta disponible en el servidor (la restriccion EXCLUDE la exige; la alternativa es un candado de transaccion por responsable)';
    END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- tpi.citas: columnas nuevas de la agenda.
ALTER TABLE tpi.citas
    ADD COLUMN fecha_hora_fin TIMESTAMPTZ NOT NULL,
    ADD COLUMN agendada_por_subject TEXT,
    ADD COLUMN agendada_por_nombre TEXT,
    ADD COLUMN nota TEXT,
    ADD COLUMN motivo_cancelacion TEXT,
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- El responsable de la asesoria pasa a ser obligatorio.
ALTER TABLE tpi.citas ALTER COLUMN id_asesor SET NOT NULL;

ALTER TABLE tpi.citas
    ADD CONSTRAINT citas_fecha_hora_fin_gt_inicio_chk
    CHECK (fecha_hora_fin > fecha_hora);

ALTER TABLE tpi.citas
    ADD CONSTRAINT citas_estado_cita_check
    CHECK (estado_cita IN ('agendada', 'realizada', 'no_asistio', 'cancelada'));

-- Una sola reunion agendada por lead.
CREATE UNIQUE INDEX citas_one_agendada_per_lead_uq
    ON tpi.citas (id_lead)
    WHERE estado_cita = 'agendada';

-- Indice de lectura para pintar el calendario por semana.
CREATE INDEX citas_fecha_hora_idx
    ON tpi.citas (fecha_hora);

-- El responsable no puede tener dos reuniones que se pisen.
ALTER TABLE tpi.citas
    ADD CONSTRAINT citas_responsable_no_superposicion_excl
    EXCLUDE USING gist (
        id_asesor WITH =,
        tstzrange(fecha_hora, fecha_hora_fin) WITH &&
    )
    WHERE (estado_cita = 'agendada');

-- tpi.asesores: marca de quien puede ser responsable de una reunion.
ALTER TABLE tpi.asesores
    ADD COLUMN atiende_reuniones BOOLEAN NOT NULL DEFAULT false;

-- Privilegios sobre tpi.citas: solo SELECT, INSERT y UPDATE para tpi_app, sin DELETE.
-- No se tocan los privilegios de tpi_app sobre tpi.auditoria ni sobre las demas tablas.
REVOKE ALL ON tpi.citas FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON tpi.citas TO tpi_app;

COMMIT;

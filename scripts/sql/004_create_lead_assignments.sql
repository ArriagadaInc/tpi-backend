-- Formal CRM lead assignment model.
-- Adds explicit assignment history and audit-friendly fields without overloading leads.raw_payload.

CREATE TABLE IF NOT EXISTS tpi.asignaciones (
    id_asignacion UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_lead UUID NOT NULL REFERENCES tpi.leads(id_lead),
    id_asesor UUID NOT NULL REFERENCES tpi.asesores(id_asesor),
    fecha_asignacion TIMESTAMPTZ NOT NULL DEFAULT now(),
    asignado_por VARCHAR(150),
    regla_asignacion VARCHAR(100),
    estado_asignacion VARCHAR(50) NOT NULL DEFAULT 'activa',
    observacion TEXT
);

CREATE INDEX IF NOT EXISTS asignaciones_id_lead_idx
    ON tpi.asignaciones (id_lead);

CREATE INDEX IF NOT EXISTS asignaciones_id_asesor_idx
    ON tpi.asignaciones (id_asesor);

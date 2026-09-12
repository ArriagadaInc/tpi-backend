"""Inicializa una base PostgreSQL efímera para la suite de CI."""

import psycopg

from app.config.settings import settings

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS tpi;

CREATE TABLE IF NOT EXISTS tpi.catalogo_genero (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    orden_visual INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tpi.catalogo_estado_civil (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    orden_visual INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tpi.catalogo_afp (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    orden_visual INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tpi.personas (
    id_persona UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rut VARCHAR(12) NOT NULL UNIQUE,
    nombre_completo VARCHAR(200) NOT NULL,
    email VARCHAR(150),
    telefono VARCHAR(30),
    fecha_nacimiento DATE,
    genero VARCHAR(30),
    estado_civil VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tpi.leads (
    id_lead UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_persona UUID NOT NULL REFERENCES tpi.personas(id_persona),
    fecha_ingreso TIMESTAMPTZ NOT NULL,
    afp_actual VARCHAR(80),
    saldo_afp NUMERIC(14, 2),
    comentarios TEXT,
    estado_lead VARCHAR(50) NOT NULL DEFAULT 'nuevo',
    prioridad VARCHAR(30),
    origen_lead VARCHAR(100) NOT NULL DEFAULT 'formulario_web',
    fuente_actual VARCHAR(100) NOT NULL DEFAULT 'google_sheets',
    raw_payload JSONB,
    genero_id UUID REFERENCES tpi.catalogo_genero(id),
    estado_civil_id UUID REFERENCES tpi.catalogo_estado_civil(id),
    afp_id UUID REFERENCES tpi.catalogo_afp(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tpi.asesores (
    id_asesor UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(150) NOT NULL,
    email VARCHAR(150),
    rol VARCHAR(50) NOT NULL,
    estado_disponibilidad VARCHAR(50) NOT NULL,
    especialidad VARCHAR(100),
    carga_activa INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS asesores_nombre_lower_uq
    ON tpi.asesores (lower(nombre));

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

CREATE UNIQUE INDEX IF NOT EXISTS asignaciones_one_active_per_lead_uq
    ON tpi.asignaciones (id_lead)
    WHERE estado_asignacion = 'activa';

CREATE TABLE IF NOT EXISTS tpi.consentimientos (
    id_consentimiento UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_persona UUID NOT NULL REFERENCES tpi.personas(id_persona),
    id_lead UUID REFERENCES tpi.leads(id_lead),
    acepta_terminos BOOLEAN NOT NULL DEFAULT FALSE,
    acepta_politica_privacidad BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_aceptacion TIMESTAMPTZ,
    version_terminos VARCHAR(50),
    version_politica VARCHAR(50),
    ip_origen VARCHAR(80),
    user_agent TEXT,
    finalidad_contacto BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mirrors the real operational dependency that must block test cleanup.
CREATE TABLE IF NOT EXISTS tpi.auditoria (
    id_auditoria UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario UUID,
    id_persona UUID REFERENCES tpi.personas(id_persona),
    id_lead UUID REFERENCES tpi.leads(id_lead),
    accion VARCHAR(100) NOT NULL,
    tabla_afectada VARCHAR(100) NOT NULL,
    fecha_hora TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_origen VARCHAR(80),
    detalle JSONB
);

-- Stores no payload or PII: only a keyed fingerprint and the resulting lead id.
CREATE TABLE IF NOT EXISTS tpi.api_idempotency (
    idempotency_key UUID PRIMARY KEY,
    payload_fingerprint CHAR(64) NOT NULL,
    lead_id UUID REFERENCES tpi.leads(id_lead) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS api_idempotency_expires_at_idx
    ON tpi.api_idempotency (expires_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_assignment_runtime') THEN
        CREATE ROLE tpi_assignment_runtime
            LOGIN
            PASSWORD 'tpi_assignment_runtime_password'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    ELSE
        ALTER ROLE tpi_assignment_runtime
            LOGIN
            PASSWORD 'tpi_assignment_runtime_password'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), 'tpi_assignment_runtime');
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', 'tpi', 'tpi_assignment_runtime');
    EXECUTE format('GRANT SELECT ON TABLE %I.%I TO %I', 'tpi', 'asesores', 'tpi_assignment_runtime');
    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I.%I TO %I', 'tpi', 'asignaciones', 'tpi_assignment_runtime');
    EXECUTE format('GRANT INSERT ON TABLE %I.%I TO %I', 'tpi', 'auditoria', 'tpi_assignment_runtime');
    EXECUTE format('GRANT SELECT, UPDATE ON TABLE %I.%I TO %I', 'tpi', 'leads', 'tpi_assignment_runtime');
    EXECUTE format('ALTER ROLE %I IN DATABASE %I SET search_path = %I, public',
        'tpi_assignment_runtime',
        current_database(),
        'tpi'
    );
END
$$;

INSERT INTO tpi.catalogo_genero (codigo, nombre, activo, orden_visual)
VALUES
    ('FEMENINO', 'Femenino', TRUE, 10),
    ('MASCULINO', 'Masculino', TRUE, 20)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tpi.catalogo_estado_civil (codigo, nombre, activo, orden_visual)
VALUES
    ('SOLTERO', 'Soltero/a', TRUE, 10),
    ('CASADO', 'Casado/a', TRUE, 20),
    ('DIVORCIADO', 'Divorciado/a', TRUE, 30),
    ('VIUDO', 'Viudo/a', TRUE, 40)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tpi.catalogo_afp (codigo, nombre, activo, orden_visual)
VALUES
    ('HABITAT', 'Habitat', TRUE, 10),
    ('CAPITAL', 'Capital', TRUE, 20),
    ('CUPRUM', 'Cuprum', TRUE, 30),
    ('MODELO', 'Modelo', TRUE, 40),
    ('PLANVITAL', 'PlanVital', TRUE, 50),
    ('PROVIDA', 'Provida', TRUE, 60),
    ('UNO', 'Uno', TRUE, 70)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO tpi.asesores (
    id_asesor,
    nombre,
    email,
    rol,
    estado_disponibilidad,
    especialidad,
    carga_activa,
    created_at
)
VALUES
    ('44444444-4444-4444-4444-444444444441', 'Asesor Demo 1', 'asesor1@example.com', 'asesor', 'activo', 'General', 0, now()),
    ('44444444-4444-4444-4444-444444444442', 'Asesor Demo 2', 'asesor2@example.com', 'asesor', 'activo', 'General', 0, now()),
    ('44444444-4444-4444-4444-444444444443', 'Asesor Demo 3', 'asesor3@example.com', 'asesor', 'activo', 'General', 0, now()),
    ('44444444-4444-4444-4444-444444444444', 'Asesor Demo 4', 'asesor4@example.com', 'asesor', 'activo', 'General', 0, now())
ON CONFLICT (id_asesor) DO NOTHING;
"""


def main() -> None:
    """Crea el esquema mínimo y carga catálogos controlados."""
    with psycopg.connect(settings.get_database_url(), autocommit=True) as conn:
        conn.execute(SCHEMA_SQL)


if __name__ == "__main__":
    main()

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
    id_persona UUID REFERENCES tpi.personas(id_persona),
    id_lead UUID REFERENCES tpi.leads(id_lead)
);

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
"""


def main() -> None:
    """Crea el esquema mínimo y carga catálogos controlados."""
    with psycopg.connect(settings.get_database_url(), autocommit=True) as conn:
        conn.execute(SCHEMA_SQL)


if __name__ == "__main__":
    main()

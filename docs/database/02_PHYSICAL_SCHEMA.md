Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-08-28
Fuente: PostgreSQL RDS + scripts versionados + init_test_database.py

# 02 Physical Schema

## Reading Rules

- This document distinguishes between:
  - AWS DEV physical state
  - repository/test contract
  - future target state after pending migrations
- When a table or field was not directly revalidated in AWS DEV, it is marked
  as `No validado todavia en AWS DEV`.
- No real PII is shown here.

## Physical Snapshot

### `tpi.leads`

Estado AWS DEV:

- `estado_lead` is `VARCHAR`
- `raw_payload` exists and is not operational
- `estado_lead` has a normal index
- no ENUM or catalog governs the values

Contract source for full column layout:

- `scripts/init_test_database.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_lead` | UUID | No | `gen_random_uuid()` | PK | Lead identifier |
| `id_persona` | UUID | No | none | FK -> `tpi.personas(id_persona)` | Link to person |
| `fecha_ingreso` | TIMESTAMPTZ | No | none | - | Ingestion timestamp |
| `afp_actual` | VARCHAR(80) | Yes | none | - | Current AFP text |
| `saldo_afp` | NUMERIC(14,2) | Yes | none | - | Balance shown as presentation later |
| `comentarios` | TEXT | Yes | none | - | Lead notes |
| `estado_lead` | VARCHAR(50) | No | `'nuevo'` | Index observed in AWS DEV | Functional lead state |
| `prioridad` | VARCHAR(30) | Yes | none | - | Priority label |
| `origen_lead` | VARCHAR(100) | No | `'formulario_web'` | - | Source channel |
| `fuente_actual` | VARCHAR(100) | No | `'google_sheets'` | - | Current origin/source |
| `raw_payload` | JSONB | Yes | none | - | Ingestion payload only |
| `genero_id` | UUID | Yes | none | FK -> `tpi.catalogo_genero(id)` | Optional demographic reference |
| `estado_civil_id` | UUID | Yes | none | FK -> `tpi.catalogo_estado_civil(id)` | Optional civil-status reference |
| `afp_id` | UUID | Yes | none | FK -> `tpi.catalogo_afp(id)` | Optional AFP reference |
| `created_at` | TIMESTAMPTZ | No | `now()` | - | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | No | `now()` | - | Update timestamp |

Notes:

- `raw_payload` is auxiliary only.
- `estado_lead` is governed primarily by application code.
- `estado_lead='asignado'` must only be produced by `assign_lead`.
- The AWS DEV inspection did not identify a state catalog or ENUM for lead
  states.

### `tpi.personas`

Contract source:

- `scripts/init_test_database.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_persona` | UUID | No | `gen_random_uuid()` | PK | Person identifier |
| `rut` | VARCHAR(12) | No | none | UNIQUE | Identity document |
| `nombre_completo` | VARCHAR(200) | No | none | - | Display name |
| `email` | VARCHAR(150) | Yes | none | - | Contact email |
| `telefono` | VARCHAR(30) | Yes | none | - | Contact phone |
| `fecha_nacimiento` | DATE | Yes | none | - | Date of birth |
| `genero` | VARCHAR(30) | Yes | none | - | Legacy text field |
| `estado_civil` | VARCHAR(50) | Yes | none | - | Legacy text field |
| `created_at` | TIMESTAMPTZ | No | `now()` | - | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | No | `now()` | - | Update timestamp |

Status:

- `No validado todavia en AWS DEV` at column level in this document

### `tpi.asesores`

Estado AWS DEV:

- table exists
- `id_asesor` is the PK
- `lower(nombre)` has a UNIQUE index
- advisors validated in AWS DEV were operationally active and had role
  `asesor`

Contract source:

- `scripts/init_test_database.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_asesor` | UUID | No | `gen_random_uuid()` | PK | Advisor identifier |
| `nombre` | VARCHAR(150) | No | none | UNIQUE index on `lower(nombre)` | Advisor display/identity text |
| `email` | VARCHAR(150) | Yes | none | - | Contact or login-related value if present |
| `rol` | VARCHAR(50) | No | none | - | Operational role |
| `estado_disponibilidad` | VARCHAR(50) | No | none | - | Availability flag |
| `especialidad` | VARCHAR(100) | Yes | none | - | Advisor specialty |
| `carga_activa` | INTEGER | No | `0` | - | Load counter |
| `created_at` | TIMESTAMPTZ | No | `now()` | - | Creation timestamp |

Notes:

- `email` is not declared UNIQUE in the current validated contract.
- The domain term is `asesor`; the UX may display `Ejecutivo`.
- The current H3.3 assignment flow does not require mapping the authenticated
  user to `id_asesor`.

### `tpi.asignaciones`

Estado AWS DEV:

- table exists
- source of truth for lead-advisor relation
- no UNIQUE partial index exists yet
- multiple active rows for one lead are possible today unless prevented by the
  application

Contract source:

- `scripts/sql/004_create_lead_assignments.sql`
- AWS DEV physical inspection

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_asignacion` | UUID | No | `gen_random_uuid()` | PK | Assignment identifier |
| `id_lead` | UUID | No | none | FK -> `tpi.leads(id_lead)`; normal index | Lead reference |
| `id_asesor` | UUID | No | none | FK -> `tpi.asesores(id_asesor)`; normal index | Advisor reference |
| `fecha_asignacion` | TIMESTAMPTZ | No | `now()` | - | Assignment timestamp |
| `asignado_por` | VARCHAR(150) | Yes | none | - | Technical actor trace |
| `regla_asignacion` | VARCHAR(100) | Yes | none | - | Assignment rule name |
| `estado_asignacion` | VARCHAR(50) | No | `'activa'` | - | Assignment lifecycle state |
| `observacion` | TEXT | Yes | none | - | Optional note |

Indexes:

- `asignaciones_id_lead_idx`
- `asignaciones_id_asesor_idx`

Notes:

- `estado_asignacion='activa'` is the canonical active value.
- The partial unique index is pending migration `005_enforce_single_active_assignment.sql`.

### `tpi.auditoria`

Estado AWS DEV:

- table exists
- used for traceability events
- `detalle` is JSONB and can hold assignment metadata

Contract source:

- AWS DEV physical inspection
- `scripts/init_test_database.py`
- repository write path in `app/repositories/solicitud_repository.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_auditoria` | UUID | No | `gen_random_uuid()` | PK | Audit event identifier |
| `id_usuario` | UUID | Yes | none | - | Optional user reference |
| `id_persona` | UUID | Yes | none | FK -> `tpi.personas(id_persona)` | Person involved in event |
| `id_lead` | UUID | Yes | none | FK -> `tpi.leads(id_lead)` | Lead involved in event |
| `accion` | VARCHAR(100) | No | none | - | Business action name |
| `tabla_afectada` | VARCHAR(100) | No | none | - | Affected table name |
| `fecha_hora` | TIMESTAMPTZ | No | `now()` | - | Event timestamp |
| `ip_origen` | VARCHAR(80) | Yes | none | - | Source IP if available |
| `detalle` | JSONB | Yes | none | - | Structured metadata |

Notes:

- `detalle` is the correct place for event metadata such as:
  - actor subject
  - assignment rule
  - previous/new state
  - advisor id
- `detalle` must not be used as an operational relationship store.

### `tpi.consentimientos`

Contract source:

- `scripts/init_test_database.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `id_consentimiento` | UUID | No | `gen_random_uuid()` | PK | Consent record identifier |
| `id_persona` | UUID | No | none | FK -> `tpi.personas(id_persona)` | Person reference |
| `id_lead` | UUID | Yes | none | FK -> `tpi.leads(id_lead)` | Optional lead reference |
| `acepta_terminos` | BOOLEAN | No | `FALSE` | - | Terms acceptance |
| `acepta_politica_privacidad` | BOOLEAN | No | `FALSE` | - | Privacy acceptance |
| `fecha_aceptacion` | TIMESTAMPTZ | Yes | none | - | Acceptance timestamp |
| `version_terminos` | VARCHAR(50) | Yes | none | - | Terms version |
| `version_politica` | VARCHAR(50) | Yes | none | - | Privacy policy version |
| `ip_origen` | VARCHAR(80) | Yes | none | - | Source IP |
| `user_agent` | TEXT | Yes | none | - | Browser metadata |
| `finalidad_contacto` | BOOLEAN | No | `FALSE` | - | Contact permission |
| `created_at` | TIMESTAMPTZ | No | `now()` | - | Creation timestamp |

Status:

- `No validado todavia en AWS DEV` at column level in this document

### Catalog tables

Contract source:

- `scripts/init_test_database.py`

Shared shape:

- `id` UUID PK DEFAULT `gen_random_uuid()`
- `codigo` VARCHAR(50) NOT NULL UNIQUE
- `nombre` VARCHAR(100) NOT NULL
- `activo` BOOLEAN NOT NULL DEFAULT `TRUE`
- `orden_visual` INTEGER NOT NULL
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT `now()`
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT `now()`

Tables:

- `tpi.catalogo_afp`
- `tpi.catalogo_genero`
- `tpi.catalogo_estado_civil`

Status:

- `No validado todavia en AWS DEV` at column level in this document

### `tpi.api_idempotency`

Contract source:

- `scripts/sql/003_create_api_idempotency.sql`
- `scripts/init_test_database.py`

| Columna | Tipo | Nullable | Default | PK / FK / UNIQUE / Index | Proposito |
| ------- | ---- | -------- | ------- | ------------------------ | --------- |
| `idempotency_key` | UUID | No | none | PK | Request identity |
| `payload_fingerprint` | CHAR(64) | No | none | - | Request fingerprint |
| `lead_id` | UUID | Yes | none | FK -> `tpi.leads(id_lead)` ON DELETE SET NULL | Resulting lead reference |
| `created_at` | TIMESTAMPTZ | No | `now()` | Index on `expires_at` | Creation timestamp |
| `expires_at` | TIMESTAMPTZ | No | none | CHECK `expires_at > created_at` | Expiration timestamp |

Status:

- `No validado todavia en AWS DEV` in this release note

## Key Divergences

- AWS DEV already has `tpi.asignaciones` but still lacks the partial unique
  index for one active assignment per lead.
- `tpi.asesores.email` is not UNIQUE in the current validated contract.
- `tpi.leads.estado_lead` and `tpi.asignaciones.estado_asignacion` are plain
  `VARCHAR` columns, not enums.


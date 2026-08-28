Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-08-28
Fuente: PostgreSQL RDS + scripts versionados + init_test_database.py

# 03 Business Rules

## State Governance

### `estado_lead`

Observed in AWS DEV:

- `nuevo`
- `pendiente`
- `asignado`
- `contactado`
- `ficha_generada`
- `no_califica`
- `perdido`

Repository canonical contract additionally includes:

- `prospecto`
- `citado`
- `en_tramite`
- `expediente`
- `cerrado`
- `duplicado`
- `dormido`

Interpretation:

- PostgreSQL stores the field as `VARCHAR`.
- The application governs the vocabulary.
- There is no state catalog and no ENUM in the validated physical schema.
- `pendiente` is treated by the application as a legacy alias for `nuevo`.

### `estado_asignacion`

Current canonical active value:

- `activa`

Rules:

- use `activa` as the only canonical active value
- do not write case variants or semantic synonyms
- keep the canonical value centralized in code

## Assignment Contract for H3.3

H3.3 implements initial assignment only.

Allowed:

- create a new active assignment when none exists
- update the lead state to `asignado` as part of the same transaction
- record audit metadata for the event

Not allowed:

- reassignment
- auto-assignment
- closing the previous assignment silently
- direct generic transition to `asignado`

If an active assignment already exists:

- return a business conflict
- do not modify any row

## Transition Rule

`estado_lead='asignado'` must only be produced by the assignment operation.

This means:

- the UI must not offer `asignado` in the generic state selector
- the backend must reject `update_lead_status(..., "asignado")`
- the service layer must only allow `asignado` through `assign_lead`

## Actor and Advisor

- actor = authenticated user who executes the operation
- advisor = selected `id_asesor` that receives the lead

These are separate concepts.

The current H3.3 contract does not require mapping the authenticated user to
an advisor record.

## `asignado_por`

The operational assignment row stores `asignado_por` as a technical actor
identifier.

Current rule:

- use `AuthenticatedUser.subject`
- keep it stable and non-display oriented
- do not use `display_name`
- do not use an advisor mapping for H3.3

This value must fit the declared `VARCHAR(150)` contract.

## Transaction Model

```text
BEGIN
  validate authenticated user
  validate lead
  validate advisor
  lock lead
  check active assignment
  insert assignment
  update lead -> asignado
  register audit
COMMIT
```

If any step fails:

```text
ROLLBACK
```

## Concurrency Rules

The design must prevent two active assignments for the same lead.

Layered protection:

1. transaction boundary
2. `SELECT ... FOR UPDATE` on the lead
3. application validation
4. partial UNIQUE index on active assignments
5. explicit conflict handling for uniqueness violations

## Future Work Not Yet Implemented

- `reassign_lead(...)`
- advisor workload automation
- SLA rules
- scoring
- auto-derivation logic

These are intentionally out of scope for H3.3.


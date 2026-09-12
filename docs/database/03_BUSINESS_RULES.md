Estado: vigente
Ambiente de referencia: AWS DEV
Ultima inspeccion: 2026-08-28
Fuente: AWS DEV + scripts versionados + `init_test_database.py`

# 03 Reglas de Negocio

## Gobernanza de estados

### `estado_lead`

Observado en AWS DEV:

- `nuevo`
- `pendiente`
- `asignado`
- `contactado`
- `ficha_generada`
- `no_califica`
- `perdido`

El contrato canonico del repositorio ademas incluye:

- `prospecto`
- `citado`
- `en_tramite`
- `expediente`
- `cerrado`
- `duplicado`
- `dormido`

Interpretacion:

- PostgreSQL almacena el campo como `VARCHAR`.
- La aplicacion gobierna el vocabulario.
- No existe catalogo de estados ni ENUM en el esquema fisico validado.
- `pendiente` se trata como alias legacy de `nuevo`.

### `estado_asignacion`

Current canonical active value:

- `activa`

Reglas:

- usar `activa` como unico valor canonico activo
- no escribir variantes en mayusculas/minusculas ni sinonimos semanticos
- mantener el valor canonico centralizado en codigo

## Contrato de asignacion para H3.3

H3.3 implements initial assignment only.

Permitido:

- create a new active assignment when none exists
- update the lead state to `asignado` as part of the same transaction
- record audit metadata for the event

No permitido:

- reassignment
- auto-assignment
- closing the previous assignment silently
- direct generic transition to `asignado`

If an active assignment already exists:

- return a business conflict
- do not modify any row

## Regla de transicion

`estado_lead='asignado'` must only be produced by the assignment operation.

Esto implica:

- la UI no debe ofrecer `asignado` en el selector generico de estados
- el backend debe rechazar `update_lead_status(..., "asignado")`
- la capa de servicio solo debe permitir `asignado` a traves de `assign_lead`

## Actor y asesor

- actor = authenticated user who executes the operation
- advisor = selected `id_asesor` that receives the lead

Son conceptos separados.

El contrato actual de H3.3 no requiere mapear el usuario autenticado a un
registro de asesor.

## `asignado_por`

The operational assignment row stores `asignado_por` as a technical actor
identifier.

Regla actual:

- usar `AuthenticatedUser.subject`
- mantenerlo estable y no orientado a presentacion
- no usar `display_name`
- no usar un mapping de asesor para H3.3

This value must fit the declared `VARCHAR(150)` contract.

## Contrato de privilegio minimo

```ini
auditoria = append-only para tpi_app
asesores = read-only para tpi_app
asignaciones = create/read para H3.3 inicial
```

## Modelo transaccional

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

## Reglas de concurrencia

The design must prevent two active assignments for the same lead.

Layered protection:

1. transaction boundary
2. `SELECT ... FOR UPDATE` on the lead
3. validacion de aplicacion
4. indice UNIQUE parcial sobre asignaciones activas
5. manejo explicito de conflictos por unicidad

Nota operativa:

- el lead se bloquea con `SELECT ... FOR UPDATE`
- el asesor se valida en modo solo lectura
- H3.3 no necesita lock de escritura sobre `tpi.asesores`

## Trabajo futuro aun no implementado

- `reassign_lead(...)`
- advisor workload automation
- SLA rules
- scoring
- auto-derivation logic

Esto permanece fuera del alcance de H3.3.

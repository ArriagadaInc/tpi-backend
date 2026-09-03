Estado: vigente
Ambiente de referencia: AWS DEV
Validacion fisica AWS DEV: completa para las migraciones H3.3 ejecutadas
Ultima inspeccion: 2026-09-03
Fuente: scripts versionados + `init_test_database.py` + evidencia AWS DEV

# 04 Migraciones

## Alcance

Este documento inventaria los scripts SQL versionados y los artefactos de
bootstrap que definen el contrato reproducible del esquema.

No describe cambios manuales ad hoc. Si un cambio no puede reproducirse mediante
scripts versionados, debe tratarse como drift.

## Inventario cronologico

| Script | Proposito | Dependencia | Estado | Ambiente | Rollback |
| ------ | --------- | ----------- | ------ | -------- | -------- |
| `scripts/sql/001_create_tpi_app_role.sql` | Crear el rol de aplicacion con base minima | Base de datos y esquema `tpi` existentes | Versionado y alineado con el bootstrap minimo de H3.3 para ambientes nuevos | Bootstrap nuevo / administracion | Revocacion manual o deshabilitacion del rol |
| `scripts/sql/003_create_api_idempotency.sql` | Crear la tabla de idempotencia de la API publica | `tpi.leads` | Versionado | Despliegue administrado | `scripts/sql/003_drop_api_idempotency.sql` |
| `scripts/sql/003_drop_api_idempotency.sql` | Revertir la tabla de idempotencia | `tpi.api_idempotency` existente | Versionado | Despliegue administrado | Eliminar tabla y revocar grants |
| `scripts/sql/004_create_lead_assignments.sql` | Crear `tpi.asignaciones` e indices basicos | `tpi.leads`, `tpi.asesores` | Versionado y alineado con el contrato fisico observado | Despliegue administrado | Drop controlado de tabla/indices si hiciera falta |
| `scripts/sql/005_enforce_single_active_assignment.sql` | Garantizar una asignacion activa por lead | `tpi.asignaciones` con datos existentes | Ejecutado y verificado en AWS DEV el 2026-09-03; preflight: 0 duplicados activos | AWS DEV | `DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq` |
| `scripts/sql/006_grant_h3_3_assignment_privileges.sql` | Agregar los privilegios minimos que requiere H3.3 inicial | `tpi_app`, `tpi.asesores`, `tpi.asignaciones`, `tpi.auditoria`, `tpi.leads` | Ejecutado y verificado en AWS DEV el 2026-09-03 | AWS DEV existente | Revoke solo de los privilegios agregados por este script, conforme al preflight |
| `scripts/sql/dev/002_enable_test_cleanup.sql` | Conceder DELETE solo para limpieza controlada en DEV | `tpi.leads`, `tpi.consentimientos` | Ayuda DEV-only | AWS DEV solamente | `scripts/sql/dev/002_disable_test_cleanup.sql` |
| `scripts/sql/dev/002_disable_test_cleanup.sql` | Revocar el DELETE DEV-only | Script de habilitacion previo | Ayuda DEV-only | AWS DEV solamente | Revocar DELETE |

## Estado actual vs estado objetivo

### AWS DEV actual

- `tpi.asignaciones` existe
- existe `tpi.asignaciones_one_active_per_lead_uq`, UNIQUE sobre `id_lead` cuando `estado_asignacion = 'activa'`
- `tpi_app` tiene los privilegios H3.3 verificados sobre `tpi.asesores`, `tpi.asignaciones` y `tpi.auditoria`
- `tpi_app` conserva privilegios efectivos adicionales sobre `tpi.leads` y
  `tpi.personas` que forman parte del estado historico del ambiente

### Estado observado H3.3 en AWS DEV

- al menos para el flujo de asignacion inicial:
  - `tpi.asesores`: `SELECT`
  - `tpi.asignaciones`: `SELECT`, `INSERT`
  - `tpi.auditoria`: `INSERT`
  - `tpi.leads`: `SELECT`, `UPDATE`
- una sola asignacion activa por `id_lead`
- trazabilidad sin ampliar privilegios mas de lo necesario

Evidencia postflight del 2026-09-03:

- `005`: preflight sin duplicados activos; indice parcial creado y verificado
- `006`: privilegios postflight coinciden con el contrato H3.3
- no se modificaron datos de negocio

Operador y commit SHA de la ejecucion: Pendiente de registro operativo.

## Notas sobre `005`

La migracion `005` no cambia datos de negocio. Solo agrega integridad.

Modelo:

1. preflight para detectar duplicados activos
2. aborto si ya existen filas duplicadas
3. creacion del indice parcial unico
4. validacion posterior de que ya no existen conflictos estructurales

Resultado AWS DEV 2026-09-03: aplicado correctamente; indice
`tpi.asignaciones_one_active_per_lead_uq` verificado.

## Bootstrap vs migracion incremental

`scripts/init_test_database.py` no es una migracion de runtime.

Es el bootstrap de testing que recrea el contrato necesario para CI e
integracion, incluyendo la tabla de asignaciones y la proteccion por indice
parcial que los tests necesitan validar.

`001_create_tpi_app_role.sql` sigue siendo el bootstrap base para ambientes
nuevos. Versiona el contrato minimo reproducible para H3.3 en ambientes
futuros, incluyendo `tpi.asesores` read-only, `tpi.asignaciones` read/create
y `tpi.auditoria` append-only.

`006_grant_h3_3_assignment_privileges.sql` representa la evolucion
incremental necesaria para ambientes ya existentes como AWS DEV. Su preflight
aborta si el estado observado no coincide con el drift documentado.

## Regla de drift

Si AWS DEV diverge del contrato versionado, la correccion debe modelarse como
migracion o grant versionado.

No se debe parchar manualmente el schema drift cuando el cambio debe quedar
reproducible.

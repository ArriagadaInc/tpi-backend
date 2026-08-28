Estado: vigente
Ambiente de referencia: AWS DEV
Ultima inspeccion: 2026-08-28
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
| `scripts/sql/001_create_tpi_app_role.sql` | Crear el rol de aplicacion con base minima | Base de datos y esquema `tpi` existentes | Versionado, pero no reproduce por completo el estado observado en AWS DEV | Bootstrap nuevo / administracion | Revocacion manual o deshabilitacion del rol |
| `scripts/sql/003_create_api_idempotency.sql` | Crear la tabla de idempotencia de la API publica | `tpi.leads` | Versionado | Despliegue administrado | `scripts/sql/003_drop_api_idempotency.sql` |
| `scripts/sql/003_drop_api_idempotency.sql` | Revertir la tabla de idempotencia | `tpi.api_idempotency` existente | Versionado | Despliegue administrado | Eliminar tabla y revocar grants |
| `scripts/sql/004_create_lead_assignments.sql` | Crear `tpi.asignaciones` e indices basicos | `tpi.leads`, `tpi.asesores` | Versionado y alineado con el contrato fisico observado | Despliegue administrado | Drop controlado de tabla/indices si hiciera falta |
| `scripts/sql/005_enforce_single_active_assignment.sql` | Garantizar una asignacion activa por lead | `tpi.asignaciones` con datos existentes | Preparado, no ejecutado todavia en AWS DEV | Despliegue administrado | `DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq` |
| `scripts/sql/006_grant_h3_3_assignment_privileges.sql` | Agregar los privilegios minimos que requiere H3.3 inicial | `tpi_app`, `tpi.asesores`, `tpi.asignaciones`, `tpi.auditoria`, `tpi.leads` | Propuesto, no ejecutado todavia | AWS DEV existente / ambientes ya provisionados | Revoke solo de los privilegios agregados por este script |
| `scripts/sql/dev/002_enable_test_cleanup.sql` | Conceder DELETE solo para limpieza controlada en DEV | `tpi.leads`, `tpi.consentimientos` | Ayuda DEV-only | AWS DEV solamente | `scripts/sql/dev/002_disable_test_cleanup.sql` |
| `scripts/sql/dev/002_disable_test_cleanup.sql` | Revocar el DELETE DEV-only | Script de habilitacion previo | Ayuda DEV-only | AWS DEV solamente | Revocar DELETE |

## Estado actual vs estado objetivo

### AWS DEV actual

- `tpi.asignaciones` existe
- la llave parcial unica para una sola asignacion activa todavia no existe
- `tpi_app` no tiene permisos efectivos sobre `tpi.asesores`, `tpi.asignaciones`
  ni `tpi.auditoria`
- `tpi_app` conserva privilegios efectivos adicionales sobre `tpi.leads` y
  `tpi.personas` que forman parte del estado historico del ambiente

### Estado objetivo H3.3

- al menos para el flujo de asignacion inicial:
  - `tpi.asesores`: `SELECT`
  - `tpi.asignaciones`: `SELECT`, `INSERT`
  - `tpi.auditoria`: `INSERT`
  - `tpi.leads`: `SELECT`, `UPDATE`
- una sola asignacion activa por `id_lead`
- trazabilidad sin ampliar privilegios mas de lo necesario

## Notas sobre `005`

La migracion `005` no cambia datos de negocio. Solo agrega integridad.

Modelo:

1. preflight para detectar duplicados activos
2. aborto si ya existen filas duplicadas
3. creacion del indice parcial unico
4. validacion posterior de que ya no existen conflictos estructurales

## Bootstrap vs migracion incremental

`scripts/init_test_database.py` no es una migracion de runtime.

Es el bootstrap de testing que recrea el contrato necesario para CI e
integracion, incluyendo la tabla de asignaciones y la proteccion por indice
parcial que los tests necesitan validar.

`001_create_tpi_app_role.sql` sigue siendo el bootstrap base para ambientes
nuevos, mientras que `006_grant_h3_3_assignment_privileges.sql` representa la
evolucion incremental necesaria para ambientes ya existentes como AWS DEV.

## Regla de drift

Si AWS DEV diverge del contrato versionado, la correccion debe modelarse como
migracion o grant versionado.

No se debe parchar manualmente el schema drift cuando el cambio debe quedar
reproducible.

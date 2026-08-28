Estado: vigente
Ambiente de referencia: AWS DEV
Ultima inspeccion: 2026-08-28
Fuente: privilegios efectivos en AWS DEV + scripts versionados + `init_test_database.py`

# 06 Runbook Operacional

## Proposito

Este runbook cubre los pasos operativos para validar, inspeccionar, migrar,
verificar y revertir la capa de datos.

## 1. Validar conectividad

Comprobaciones de solo lectura:

```sql
SELECT version();
SELECT current_database();
SELECT current_user;
```

Validar visibilidad del esquema:

```sql
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'tpi';
```

Validar presencia de tablas:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'tpi'
ORDER BY table_name;
```

## 2. Inspeccionar tablas, indices y FK

Consultas utiles de catalogo:

```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'tpi'
ORDER BY tablename, indexname;
```

```sql
SELECT conrelid::regclass AS table_name,
       conname,
       contype,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'tpi'::regnamespace
ORDER BY conrelid::regclass::text, conname;
```

## 3. Inspeccion de privilegios

Usar el script versionado:

- `scripts/sql/inspect_dev_tpi_app_privileges_readonly.sql`

Este script:

- ejecuta `BEGIN TRANSACTION READ ONLY`
- no modifica datos
- no ejecuta funciones con efectos laterales
- permite comparar privilegios efectivos versus grants declarados

Comprobaciones relevantes:

- `tpi_app` tiene `USAGE` sobre `tpi`
- `tpi_app` puede o no puede operar sobre `tpi.personas`, `tpi.leads`,
  `tpi.asesores`, `tpi.asignaciones` y `tpi.auditoria`
- el permiso sobre `tpi.auditoria` debe verificarse de forma independiente
- la ausencia de membresias de roles debe quedar documentada junto con la
  ausencia de herencia

## 4. Preflight antes de la migracion `005`

Comprobar duplicados activos:

```sql
SELECT id_lead, COUNT(*) AS active_rows
FROM tpi.asignaciones
WHERE estado_asignacion = 'activa'
GROUP BY id_lead
HAVING COUNT(*) > 1
ORDER BY active_rows DESC, id_lead;
```

Si la consulta devuelve filas:

- no crear todavia el indice parcial unico
- resolver los duplicados mediante una decision de negocio aprobada
- repetir el preflight antes de aplicar `005`

## 5. Aplicar una migracion

Proceso recomendado:

1. confirmar el SHA del commit que declara la migracion
2. confirmar el ambiente objetivo
3. ejecutar el preflight
4. aplicar la migracion en la sesion administrativa aprobada
5. verificar los indices y privilegios resultantes
6. registrar el resultado en notas de release o bitacora

No parchar drift manual cuando el cambio debe quedar versionado.

## 6. Verificar una migracion

Despues de `005`, verificar:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'tpi'
  AND tablename = 'asignaciones'
  AND indexname = 'asignaciones_one_active_per_lead_uq';
```

```sql
SELECT id_lead
FROM tpi.asignaciones
WHERE estado_asignacion = 'activa'
GROUP BY id_lead
HAVING COUNT(*) > 1;
```

Esperado:

- el indice parcial unico existe
- la consulta de duplicados no retorna filas

## 7. Verificar permisos despues de `006`

Despues de aplicar `scripts/sql/006_grant_h3_3_assignment_privileges.sql`,
validar nuevamente:

- `USAGE` en `tpi`
- `SELECT` en `tpi.asesores`
- `SELECT`, `INSERT` en `tpi.asignaciones`
- `INSERT` en `tpi.auditoria`
- `SELECT`, `UPDATE` en `tpi.leads`

La verificacion debe distinguir:

- privilegio efectivo
- grant directo
- privilegio heredado por membresia

## 8. Rollback

Rollback de `005`:

```sql
DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq;
```

Reglas de rollback:

- solo eliminar el objeto de integridad agregado
- no borrar datos de negocio
- no eliminar el esquema ni la instancia RDS

Rollback de `006`:

- revocar unicamente los privilegios agregados por esa migracion
- no revocar privilegios preexistentes no relacionados
- no tocar datos

## 9. Backup and Restore

Usar solo mecanismos aprobados de AWS o PostgreSQL.

Ejemplos:

- automated RDS snapshot
- approved `pg_dump` / `pg_restore` workflow

Nunca usar ediciones manuales del esquema como sustituto de una ruta
reproducible de backup o migracion.

## 10. Controles post-despliegue

Despues de un despliegue:

- ejecutar el healthcheck de la aplicacion
- confirmar conectividad a la base
- confirmar acceso a `tpi.leads`
- confirmar el flujo de asignacion si H3.3 esta activo
- confirmar que la trazabilidad se genera cuando el contrato de la app lo
  requiere

## 11. Healthcheck

El healthcheck de runtime debe seguir siendo liviano y seguro:

- `SELECT 1`
- current database
- current user
- schema visibility
- table accessibility

Usar `python scripts/verify_database_connection.py` para una validacion rapida
fuera de la UI.

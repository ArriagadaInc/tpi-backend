---
name: tpi-sql-migrations
role: developer
load_when: "DEVELOPING solo en tareas clase D que versionan DDL o grants"
sources: [database_docs, release_contract_v2, handoff_h33]
---

# tpi-sql-migrations

## 1. Cuando se carga
Tareas `change_class: D` que agregan scripts en `scripts/sql/`.

## 2. Puede
- Versionar migraciones idempotentes o con preflight explicito y script de rollback.
- Actualizar `scripts/init_test_database.py` y `docs/database/04_MIGRATIONS.md`.
- Probar la migracion contra PostgreSQL local efimero.

## 3. No puede
- Ejecutar migraciones contra AWS RDS (clase D en AWS = BLOCKED_HUMAN).
- Reejecutar o modificar 005/006 (ya aplicadas en DEV).
- Parchar drift manualmente sin script versionado.
- Incluir migraciones en tareas que no sean clase D.

## 4. Precondiciones
- `tasks/current.yaml` con `change_class: D`.
- Inventario de `docs/database/04_MIGRATIONS.md` y regla de drift leidos.

## 5. Comandos y herramientas
- PostgreSQL local; `psql` contra la base de pruebas; `pytest tests/integration -q`.

## 6. Evidencia obligatoria
- `migrations_included: true`; en `assumptions`: preflight, rollback y privilegios afectados.
- Resultado de aplicar y revertir la migracion en local.

## 7. STOP
- La migracion requiere datos reales o credenciales administrativas.
- No existe rollback seguro para el cambio.

## 8. Fuentes
- `docs/database/04_MIGRATIONS.md`, `06_OPERATIONS_RUNBOOK.md`, `07_TESTING_AND_INTEGRITY.md`.
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` seccion 10 (migraciones fuera del deploy).
- `docs/BITACORA.md` entrada 2026-09-12 (005/006 aplicadas).

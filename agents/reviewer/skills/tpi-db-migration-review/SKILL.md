---
name: tpi-db-migration-review
role: reviewer
load_when: "REVIEWING cuando el diff toca scripts/sql, init_test_database.py o repositorios"
sources: [database_docs, release_contract_v2, handoff_h33]
---

# tpi-db-migration-review

## 1. Cuando se carga
Diffs con SQL, cambios de repositorio o `migrations_included: true`.

## 2. Puede
- Aplicar y revertir la migracion en PostgreSQL local efimero.

## 3. No puede
- Conectarse a RDS de AWS o ejecutar migraciones en AWS.

## 4. Precondiciones
- Inventario de `docs/database/04_MIGRATIONS.md` y contrato de privilegios de `05_SECURITY_ACCESS.md`.

## 5. Comandos y herramientas
- PostgreSQL local; `pytest tests/integration -q`.

## 6. Evidencia obligatoria
- Checks: `migration_class_d_only`, `preflight_present`, `rollback_present`, `least_privilege_grants`,
  `no_rerun_005_006`, `bootstrap_consistent`, `no_invented_model`.

## 7. STOP
- Migracion en tarea no clase D, sin rollback, o que reejecuta 005/006: REJECTED blocker.

## 8. Fuentes
- `docs/database/`; `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` seccion 10; `docs/BITACORA.md` 2026-09-12.

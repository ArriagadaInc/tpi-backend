---
name: tpi-postgresql-repository
role: developer
load_when: "DEVELOPING cuando la tarea toca app/repositories, consultas SQL o transacciones"
sources: [database_docs, technical_decisions]
---

# tpi-postgresql-repository

## 1. Cuando se carga
Cambios en `app/repositories/solicitud_repository.py`, `app/database/` o consultas SQL.

## 2. Puede
- Escribir SQL parametrizado con psycopg3 y `dict_row`, transacciones atomicas y `SELECT ... FOR UPDATE`.
- Ajustar `scripts/init_test_database.py` para reflejar el contrato fisico en tests.

## 3. No puede
- Construir SQL por concatenacion de entradas.
- Asumir columnas o tablas que no esten en `docs/database/02_PHYSICAL_SCHEMA.md`.
- Usar `leads.raw_payload` como relacion operacional.
- Requerir privilegios de `tpi_app` mayores a los documentados sin una tarea clase D.

## 4. Precondiciones
- PostgreSQL local de pruebas (`docker compose -f docker-compose.yml -f docker-compose.local.yml up postgres db-init`).
- Reglas de negocio de `docs/database/03_BUSINESS_RULES.md` leidas.

## 5. Comandos y herramientas
- `python scripts/init_test_database.py` con variables `DATABASE_*` locales ficticias.
- `pytest tests/integration -q` (marker integration).

## 6. Evidencia obligatoria
- Tests de integracion que cubran commit, rollback y conflicto de concurrencia cuando aplique.
- En `assumptions`: privilegios requeridos por `tpi_app` si cambian.

## 7. STOP
- El cambio exige DDL o grants nuevos: la tarea debe ser clase D; si no lo es, detener y reportar.
- Diferencia entre esquema fisico documentado y el bootstrap de tests.

## 8. Fuentes
- `docs/database/01_ARCHITECTURE.md`, `02_PHYSICAL_SCHEMA.md`, `03_BUSINESS_RULES.md`, `05_SECURITY_ACCESS.md`.
- `docs/DECISIONES_TECNICAS.md` decisiones 1, 2, 7, 8 (repository, transacciones, paginacion, joins).

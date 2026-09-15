---
name: tpi-testing
role: developer
load_when: "Siempre en DEVELOPING"
sources: [engineering_standards, ci_workflow]
---

# tpi-testing

## 1. Cuando se carga
Toda sesion del Developer en DEVELOPING.

## 2. Puede
- Agregar tests unit/integration/e2e/security con markers declarados en `pyproject.toml`.
- Usar fakes de autenticacion y publishers (CI nunca llama AWS).

## 3. No puede
- Omitir, desactivar o marcar `skip` tests sin causa registrada.
- Bajar la cobertura minima (85%) ni excluir modulos para subirla.
- Usar datos personales reales, credenciales o endpoints AWS en tests.

## 4. Precondiciones
- Dependencias de `requirements/dev.lock` instaladas.
- PostgreSQL local para tests de integracion.

## 5. Comandos y herramientas
- `pytest tests/ --cov=app --cov-fail-under=85`
- `ruff check app/ tests/ scripts/ deployment/`
- `black --check app/ tests/ scripts/ deployment/`
- `mypy app/ --ignore-missing-imports`
- `bandit -r app/ --severity-level medium --confidence-level medium`
- `pip-audit --requirement requirements/runtime.lock`
- `docker build --tag tpi-backoffice:local .` cuando cambia la app desplegable.

## 6. Evidencia obligatoria
- `tests`: comando exacto y PASS/FAIL. `quality_gates`: ruff, black, mypy, pytest_coverage, bandit,
  pip_audit, docker_build (PASS/FAIL) y CI del PR verde.
- Cada criterio de aceptacion mapeado a tests o marcado `pending_verification` si es humano.

## 7. STOP
- Un gate falla por causa ajena a la tarea: registrar `BLOCKER:` y detener, no mezclar fixes.
- CI del PR falla y no se entiende la causa.

## 8. Fuentes
- `docs/ENGINEERING_STANDARDS.md` (DoD; su 80% esta superado por el gate 85%).
- `.github/workflows/ci.yml`.

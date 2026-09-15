---
name: tpi-test-quality-review
role: reviewer
load_when: "REVIEWING"
sources: [engineering_standards, ci_workflow]
---

# tpi-test-quality-review

## 1. Cuando se carga
Toda revision de software.

## 2. Puede
- Correr la suite completa y comparar con lo declarado por el Developer.
- Consultar el CI del SHA exacto.

## 3. No puede
- Agregar o arreglar tests.

## 4. Precondiciones
- `developer-*.json` con `tests` y `quality_gates`.

## 5. Comandos y herramientas
- `gh pr checks <pr>`; `gh run list --commit <head_sha>`; `gh run view <id>`.
- `pytest tests/ --cov=app --cov-fail-under=85` en el worktree de revision.

## 6. Evidencia obligatoria
- `ci`: `run_id` y `conclusion` del workflow CI sobre el `reviewed_sha`.
- Checks: `ci_green_exact_sha`, `coverage_85`, `tests_cover_acceptance_criteria`,
  `tests_validate_behavior_not_coverage`, `no_skipped_without_cause`.

## 7. STOP
- CI no verde o no ejecutado sobre el SHA exacto: REJECTED (no aprobar por resultados locales).

## 8. Fuentes
- `docs/ENGINEERING_STANDARDS.md`; `.github/workflows/ci.yml`.

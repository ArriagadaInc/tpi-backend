---
name: tpi-code-architecture-review
role: reviewer
load_when: "REVIEWING"
sources: [technical_decisions, database_docs, engineering_standards, h33_web_ux, python_design_patterns_skill]
---

# tpi-code-architecture-review

## 1. Cuando se carga
Toda revision de software en REVIEWING.

## 2. Puede
- Leer el diff del PR en el SHA exacto (`gh pr diff`, worktree de revision).
- Ejecutar tests y analisis estatico localmente.
- Detectar señales de sobreingenieria con este checklist minimo (detalle de principios en la
  skill del Developer `python_design_patterns_skill`, no se copia aqui):
  factories/strategies/interfaces/adapters/capas nuevas sin un problema real y demostrable;
  responsabilidades mezcladas en una misma clase/funcion; acoplamiento innecesario entre capas;
  abstracciones agregadas antes de la tercera repeticion real (Regla de Tres) sin justificacion;
  violaciones claras de la direccion route/API -> service/domain -> repository.

## 3. No puede
- Editar codigo o empujar commits; aprobar con hallazgos blocker/major.

## 4. Precondiciones
- `developer-*.json` valido; worktree en `head_sha`; tarea y criterios leidos.

## 5. Comandos y herramientas
- `gh pr view <pr> --json headRefOid,files`, `gh pr diff <pr>`, `git rev-parse <sha>^{tree}`.

## 6. Evidencia obligatoria
- Checks: `functional_compliance`, `layering`, `maintainability`, `compatibility`,
  `scope_no_unrelated_changes`, `documentation` (PASS/FAIL).
- Hallazgos con `id`, `severity`, `file`, `summary`, `required_action`.

## 7. STOP
- `head_sha` del PR distinto del entregado: REJECTED (el Developer re-entrega).
- Cambios de clase distinta a la declarada o fixes no relacionados: REJECTED.

## 8. Fuentes
- `docs/DECISIONES_TECNICAS.md`, `docs/database/`, `docs/ENGINEERING_STANDARDS.md`.

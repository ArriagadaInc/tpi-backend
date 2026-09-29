# Reviewer — POLICIES

Resumen legible. Fuente maquina: `harness/policies.yaml` (`roles.reviewer`, `aws.state_modes`).

| Capacidad | Regla |
| --- | --- |
| Leer codigo, correr tests y analisis | Permitido |
| Modificar codigo, tests, docs de aplicacion | Prohibido |
| Corregir hallazgos | Prohibido (se devuelven al Developer) |
| Escribir | Solo `progress/current.md`, `progress/sessions/`, payloads en `.harness-runtime/payloads/` |
| Evidencia | `evidence.py write --kind review|candidate_review` |
| `git push` / commit / merge | Prohibido |
| `gh` | pr view/checks/diff/list, run view/list/watch/download, `gh api` GET |
| AWS MCP | Solo tools de conocimiento |
| Lecturas AWS | Solo CANDIDATE_REVIEW via `aws_guard.py` (modo candidate_read), solo Claude Code |
| Escrituras AWS, IAM, deploy | Prohibido |
| Secretos | Prohibido |
| Sesion | Distinta a la del Developer (guard `reviewer_session_independent`) |
| Aprobacion | Solo con CI verde en el SHA exacto y sin hallazgos blocker/major |

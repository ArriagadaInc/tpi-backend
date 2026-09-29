# Decisiones persistentes del Harness

Registro breve. El detalle vive en la fuente enlazada; no copiar documentos aqui.
`context_compact.py` agrega al final las lineas `DECISION:` encontradas en `progress/current.md`.

| ID | Fecha | Decision | Fuente |
| --- | --- | --- | --- |
| D-001 | 2026-09-14 | El repositorio es el Harness; los runtimes son intercambiables. | AGENTS.md |
| D-002 | 2026-09-14 | Contrato CI/CD v2 completo versionado en docs/cicd como fuente canonica. | docs/cicd/TPI_Contrato_CICD_AWS_v2.md |
| D-003 | 2026-09-14 | Cobertura operativa 85% (gate CI); 80% de ENGINEERING_STANDARDS es deuda documental. | tasks/backlog.yaml DOC-COVERAGE-80-85 |
| D-004 | 2026-09-14 | Flujo: reviewed tree -> merge main -> release SHA -> candidate -> deploy; approved_commit == deployed_commit. | harness/project-profile.yaml release |
| D-005 | 2026-09-14 | Human Gate protege la mutacion del runtime; PREPARING_DEPLOYMENT puede publicar ECR, S3 content-addressed y AV --no-process. | harness/policies.yaml aws.modes.prepare |
| D-006 | 2026-09-14 | CANDIDATE_REVIEW automatico por el Reviewer antes del Human Gate. | harness/workflow.yaml |
| D-007 | 2026-09-14 | Rollback: autorizacion condicionada en el mismo gate, un unico intento version-only al LKG nombrado. | harness/policies.yaml rollback_authorization |
| D-008 | 2026-09-14 | Deploy solo en Claude Code via aws_guard con perfil tpi-dev (transitorio). | harness/policies.yaml harness.deploy_capable_runtimes |
| D-009 | 2026-09-14 | MCP AWS = conocimiento (read-only); operaciones solo via aws_guard; run_script y get_presigned_url prohibidos. | .mcp.json, harness/policies.yaml mcp |
| D-010 | 2026-09-14 | Aceptacion humana excepcional en VERIFYING si un criterio requiere autenticacion. | tasks/backlog.yaml AUTOMATED_AUTHENTICATED_SMOKE |
| D-011 | 2026-09-14 | Migraciones en AWS DEV = clase D, BLOCKED_HUMAN; no reejecutar 005/006. | docs/cicd/TPI_Contrato_CICD_AWS_v2.md seccion 10 |
| D-012 | 2026-09-14 | max_rework_rounds = 3; luego BLOCKED_HUMAN. | harness/policies.yaml |
| D-013 | 2026-09-15 | Correccion: progress/sessions/2026-09-14-harness-bootstrap.md y progress/current.md afirmaban tests A-J "probados localmente"; tests/harness/ solo tenia __init__.py (verificado por filesystem). Se agrego la regla de orden de autoridad operacional (Git/evidencia/tests > state+workflow > docs > progress) y se implementaron tests A-J y M1-M6 reales bajo mantenimiento. | AGENTS.md, tests/harness/, evidence/harness/bootstrap-validation.json |
| D-014 | 2026-09-15 | Mantenimiento (TPI_HARNESS_MAINTENANCE=1) corrigio D2 (bypass del hook por doble invocacion de guard.py tras consumir stdin), D3 (bypass global de mantenimiento), D4 (sin bloqueo de comandos destructivos), D6 (mantenimiento ampliaba AWS en IDLE/BLOCKED_HUMAN), D7 (lectura de secretos por shell sin cubrir). Detalle en evidence/harness/bootstrap-validation.json. | harness/policies.yaml, scripts/harness/guard.py, scripts/harness/aws_guard.py, .claude/settings.json |

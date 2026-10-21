# Sesion archivada: SEG-DESACOPLAR-STREAMLIT-preparing

- Archivada: 2026-10-21T15:17:19Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: SEG-DESACOPLAR-STREAMLIT
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: resolve_to_preparing (BLOCKED_HUMAN -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-21T14:58:26Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-21-SEG-DESACOPLAR-STREAMLIT-review.md

## Estado reciente
- DECISION (DEVELOPING, H3.2-ECR-SCAN-WAIT, sesion other-202610211235-developer-sup77a45a): la implementacion ya estaba commiteada en dfb1d7f (PR #101) por una sesion anterior. Verificado contra los 5 AC: workflow espera hasta SCAN_TIMEOUT_MINUTES=20 (sondeo 15 s), tres mensajes de fallo distinguibles, gate fail-closed y documentacion de recuperacion. CI del PR verde (Lint & Format, Tests, Security Audit, Docker Build, Release Tooling Validation). Local: pytest 15 passed (--no-cov), ruff/black limpios. Evidencia: evidence/H3.2-ECR-SCAN-WAIT/developer/developer-01.json.
- DECISION (REVIEWING, H3.2-ECR-SCAN-WAIT, sesion claude-202610211240-reviewer-sup8252e8): APPROVED en dfb1d7f (tree 42236be). CI 5/5 verde en el SHA exacto; AC-1..AC-5 verificados contra el diff (plazo 20 min / sondeo 15 s, tres mensajes, gate fail-closed antes del bundle, recuperacion documentada); base = origin/main. Hallazgos solo info. Evidencia: evidence/H3.2-ECR-SCAN-WAIT/reviewer/review-01.json.
- 2026-10-21: Tarea H3.2-ECR-SCAN-WAIT cerrada; resumen en tasks/completed/H3.2-ECR-SCAN-WAIT.yaml
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion other-202610211304-developer-supe91c3b (blocked_guard, 2 denegaciones) porque un comando de shell contenia el TEXTO `boto3` dentro de un heredoc con la lista de dependencias directas (regla de policies.yaml «\bboto3\b» → «SDK AWS directo prohibido»). Es un bloqueo de FORMA: la regla busca esa palabra en cualquier comando. El worktree quedo limpio, no se perdio trabajo. Instruccion para los proximos turnos: NO escribas la palabra boto3 en ningun comando de shell (tampoco en heredocs, grep ni echo). Para averiguar que dependencias son exclusivas de Streamlit, edita pyproject.toml y requirements/*.lock con el editor de archivos y resuelve con pip desde el propio proyecto, sin nombrar paquetes en el comando: `python -m pip install --dry-run --ignore-installed --quiet --report - .` (lee las dependencias de pyproject.toml) y procesa el informe con un script de Python que leas desde un archivo dentro del worktree. No intentes rodear el guard de otra forma: si vuelve a bloquear, detente y reporta.
- DECISION (HUMANO, 2026-10-21, correccion de la anterior): el segundo bloqueo (sesion other-202610211318-developer-sup493823) fue por MI indicacion anterior: el guard NO permite crear archivos sueltos en la raiz del worktree (intentaste escribir analyze_deps.py ahi: «el Developer no puede escribir analyze_deps.py»). Los archivos que puedes escribir son los del alcance de la tarea (app/**, tests/**, requirements/**, pyproject.toml, Dockerfile, docker-compose*.yml, deployment/**, .github/workflows/ci.yml y publish-dev-ecr-images.yml, scripts/*.py, docs/**, README.md, CHANGELOG.md). NO crees scripts ni archivos temporales para analizar dependencias. Procesa el informe de pip con UNA linea de `python -c` leyendo el JSON por la entrada estandar, por ejemplo: `python -m pip install --dry-run --ignore-installed --quiet --report - . | python -c "import sys,json; r=json.load(sys.stdin); print(sorted(i['metadata']['name'] for i in r['install']))"`. TU TRABAJO PREVIO SE CONSERVA: el worktree ya tiene los borrados del codigo legado de Streamlit (app/auth/guards.py, app/backoffice_app.py, app/components/ui.py, app/internal_tools/**, app/pages/**, app/presentation/**, etc.) y cambios en app/auth/__init__.py, app/components/__init__.py y app/database/healthcheck.py: continua desde ahi, no empieces de cero. Revisa primero `git status` y `git diff --stat` del worktree. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.

- DECISION (PREPARING_DEPLOYMENT, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211502-deployer-sup1b02b9): candidate listo para release 0c9b165 (tree deba86f = reviewed_tree). Preflight PASS (LKG h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1, digests presentes, Promote deshabilitado); publish run 39622446165 6/6, scan 0/0; bundle domain-locked reproducible sha256 c187fd6b...; S3 + AV h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1 UNPROCESSED. Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/deployment/candidate-01.json.

## Bloqueos
- Ninguno.

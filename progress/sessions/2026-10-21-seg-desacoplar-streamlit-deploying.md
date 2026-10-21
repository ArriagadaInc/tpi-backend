# Sesion archivada: seg-desacoplar-streamlit-deploying

- Archivada: 2026-10-21T15:32:27Z
- Estado: DEPLOYING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: DEPLOYING (rol: deployer)
- Tarea: SEG-DESACOPLAR-STREAMLIT
- Proximo paso: Deployer: aws_guard update-environment --version-label <aprobada>, esperar, registrar deployment
- Ultima transicion: human_approve (WAITING_HUMAN_APPROVAL -> DEPLOYING)
- Actualizado: 2026-10-21T15:27:55Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-21-seg-desacoplar-streamlit-candidate-review.md

## Estado reciente
- 2026-10-21: Tarea H3.2-ECR-SCAN-WAIT cerrada; resumen en tasks/completed/H3.2-ECR-SCAN-WAIT.yaml
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion other-202610211304-developer-supe91c3b (blocked_guard, 2 denegaciones) porque un comando de shell contenia el TEXTO `boto3` dentro de un heredoc con la lista de dependencias directas (regla de policies.yaml «\bboto3\b» → «SDK AWS directo prohibido»). Es un bloqueo de FORMA: la regla busca esa palabra en cualquier comando. El worktree quedo limpio, no se perdio trabajo. Instruccion para los proximos turnos: NO escribas la palabra boto3 en ningun comando de shell (tampoco en heredocs, grep ni echo). Para averiguar que dependencias son exclusivas de Streamlit, edita pyproject.toml y requirements/*.lock con el editor de archivos y resuelve con pip desde el propio proyecto, sin nombrar paquetes en el comando: `python -m pip install --dry-run --ignore-installed --quiet --report - .` (lee las dependencias de pyproject.toml) y procesa el informe con un script de Python que leas desde un archivo dentro del worktree. No intentes rodear el guard de otra forma: si vuelve a bloquear, detente y reporta.
- DECISION (HUMANO, 2026-10-21, correccion de la anterior): el segundo bloqueo (sesion other-202610211318-developer-sup493823) fue por MI indicacion anterior: el guard NO permite crear archivos sueltos en la raiz del worktree (intentaste escribir analyze_deps.py ahi: «el Developer no puede escribir analyze_deps.py»). Los archivos que puedes escribir son los del alcance de la tarea (app/**, tests/**, requirements/**, pyproject.toml, Dockerfile, docker-compose*.yml, deployment/**, .github/workflows/ci.yml y publish-dev-ecr-images.yml, scripts/*.py, docs/**, README.md, CHANGELOG.md). NO crees scripts ni archivos temporales para analizar dependencias. Procesa el informe de pip con UNA linea de `python -c` leyendo el JSON por la entrada estandar, por ejemplo: `python -m pip install --dry-run --ignore-installed --quiet --report - . | python -c "import sys,json; r=json.load(sys.stdin); print(sorted(i['metadata']['name'] for i in r['install']))"`. TU TRABAJO PREVIO SE CONSERVA: el worktree ya tiene los borrados del codigo legado de Streamlit (app/auth/guards.py, app/backoffice_app.py, app/components/ui.py, app/internal_tools/**, app/pages/**, app/presentation/**, etc.) y cambios en app/auth/__init__.py, app/components/__init__.py y app/database/healthcheck.py: continua desde ahi, no empieces de cero. Revisa primero `git status` y `git diff --stat` del worktree. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.
- DECISION (PREPARING_DEPLOYMENT, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211502-deployer-sup1b02b9): candidate listo para release 0c9b165 (tree deba86f = reviewed_tree). Preflight PASS (LKG h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1, digests presentes, Promote deshabilitado); publish run 39622446165 6/6, scan 0/0; bundle domain-locked reproducible sha256 c187fd6b...; S3 + AV h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1 UNPROCESSED. Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/deployment/candidate-01.json.
- DECISION (CANDIDATE_REVIEW, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211517-reviewer-supad9892): APPROVED, cause null. Arbol del release = arbol revisado (deba86f), release en main; publish run 39622446165 success para el SHA; digests app/caddy ACTIVE con scan sin hallazgos; bundle reconstruido de forma independiente con sha256 c187fd6b... identico, solo compose por digest; S3 y AV coinciden; LKG sano con digests presentes; plan version-only y rollback unico al LKG. Sin dry-run. Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/reviewer/candidate_review-01.json.

## Bloqueos
- Ninguno.

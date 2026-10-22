# Sesion archivada: CRM-ADJUNTOS-3-AJUSTES-deploying

- Archivada: 2026-10-22T00:37:56Z
- Estado: DEPLOYING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: DEPLOYING (rol: deployer)
- Tarea: CRM-ADJUNTOS-3-AJUSTES
- Proximo paso: Deployer: aws_guard update-environment --version-label <aprobada>, esperar, registrar deployment
- Ultima transicion: human_approve (WAITING_HUMAN_APPROVAL -> DEPLOYING)
- Actualizado: 2026-10-22T00:33:48Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-22-CRM-ADJUNTOS-3-AJUSTES-candidate-review.md

## Estado reciente
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion other-202610212329-developer-supc88a4c (blocked_guard) porque intentaste editar `C:\desarrollos\TPI\tpi_deep_agents\tpi-backend\app\config\settings.py`, es decir el archivo de la RAIZ DE CONTROL, no el de tu worktree. Es un bloqueo de FORMA (de ruta): el codigo solo se escribe dentro de tu worktree. Tu worktree ya existe y esta limpio: `C:\desarrollos\TPI\tpi_deep_agents\tpi-backend\.harness-worktrees\CRM-ADJUNTOS-3-AJUSTES-developer-c3d597e` (rama `harness/CRM-ADJUNTOS-3-AJUSTES-ajustes`). Lee y edita SIEMPRE con rutas que empiecen por esa carpeta (por ejemplo `...\.harness-worktrees\CRM-ADJUNTOS-3-AJUSTES-developer-c3d597e\app\config\settings.py`) y ejecuta los comandos de shell con `cd` a ese worktree. La raiz de control solo se usa para el payload de evidencia (`.harness-runtime\payloads\developer.json`, ruta absoluta) y para `evidence.py` y `transition.py`. No se perdio trabajo: tu unico intento de escritura fue el denegado. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.
- DECISION (REVIEWING, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220005-reviewer-sup706068): APPROVED sobre d52de57 (arbol d901fe3), PR 116 con CI verde (5 jobs) y al dia con main; 128 pruebas de adjuntos re-ejecutadas en el SHA exacto; AC-1..AC-8 cumplidos, AC-9 humano pendiente tras el despliegue. Hallazgos: 1 minor (replace_attachment_mark sin aviso si no reemplaza) y 2 info. Precondicion del humano: s3:GetObjectTagging aplicado antes del despliegue. Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/reviewer/review-01.json.
- DECISION (MERGING, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220008-deployer-supa4e4f0): PR 116 mergeado por squash con merge_reviewed_pr.py; release_sha e37bb77 (padre c3d597e); arbol de release == arbol revisado (d901fe3). Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/deployment/merge-01.json.
- DECISION (PREPARING_DEPLOYMENT, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220008-deployer-supa4e4f0): candidate listo. Preflight PASS (LKG observado h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1, digests presentes); publish run 39698233222 6/6, scan 0/0; bundle domain-locked reproducible sha256 5b50fd0a...; S3 content-addressed y AV h3-crm-adjuntos-3-ajustes-e37bb77-domainlocked-r1 (UNPROCESSED). Environment sin mutar. Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/deployment/candidate-01.json. Precondicion del humano antes del gate: s3:GetObjectTagging aplicado. Siguiente: Reviewer (CANDIDATE_REVIEW).
- DECISION (CANDIDATE_REVIEW, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220026-reviewer-sup47fb27): APPROVED. Arbol del release == arbol revisado (d901fe3), e37bb77 en origin/main; publish run 39698233222 success; digests app 7b2e89e8 / caddy caaa599e ACTIVE con scan 0/0; bundle reconstruido con sha256 5b50fd0a... identico; S3 y AV coinciden; LKG observado Ready/Green/Ok con AV y digests presentes; plan version-only con un solo rollback. Pendientes del humano: s3:GetObjectTagging aplicado antes del cutover y AC-9 tras el despliegue. Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/reviewer/candidate_review-01.json.
- DECISION (DEPLOYING, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220034-deployer-sup479413): cutover version-only aceptado (1 update, sin reintentos ni option settings) a h3-crm-adjuntos-3-ajustes-e37bb77-domainlocked-r1; convergio en ~42 s a Ready/Green/Ok; cadena VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 -> digests verificada. Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/deployment/deployment-01.json. Siguiente: VERIFYING (smoke y conteos de logs; AC-9 humano pendiente).

## Bloqueos
- Ninguno.

# Sesion archivada: TASK-002-deployer-prepare

- Archivada: 2026-10-14T04:25:05Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: TASK-002
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: merged_deploy (MERGING -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-14T04:11:07Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-14-TASK-002-reviewer.md

## Estado reciente
- PENDIENTE HUMANO (AC-2): revisar en DEV (autenticado) el logo oficial en cabecera y pantalla de acceso de CRM Lite, tema claro y oscuro; luego ejecutar `python scripts/harness/approve.py accept --decision accept --criteria AC-2` en su terminal. Despues el Deployer registra verification-01 y `verified`.
- Deployer VERIFYING (sesion claude-202610131720-deployer-sup1736cb): el humano RECHAZO AC-2 (acceptance-01: "No es el logo oficial; el oficial es logo.png"). Smoke re-observado PASS; /static/img/logo.png 404. Registrado verification-01 (FAIL, failure_class functional).
- DECISION: defecto funcional, sin rollback (contrato seccion 9; el release esta sano y queda en DEV). Siguiente: verify_failed -> escalate -> BLOCKED_HUMAN para decision humana (nuevo desarrollo con logo.png).
- 2026-10-13: Tarea TASK-001 cancelada; resumen en tasks/completed/TASK-001.yaml
- Reviewer (sesion claude-202610140407-reviewer-supf8f008): PR #68 en d7cd47d APPROVED (CI 5/5 verde en el SHA, tree 9a7ade5, PNG intactos, sin refs a SVG). Evidencia: evidence/TASK-002/reviewer/review-01.json. AC-2 queda para aceptacion humana post-deploy.

## Bloqueos
- Ninguno.
- Deployer (sesion claude-202610140409-deployer-supf12168): PR #68 mergeado (squash, --match-head-commit d7cd47d); release cb628dc, tree 9a7ade5 == reviewed_tree. Evidencia: evidence/TASK-002/deployment/merge-01.json.
- Deployer: candidate listo. Publish run 38510183475 (6/6), scan 0/0, bundle domain-locked sha256 22f4f984... reproducible, AV h3-logo-png-cb628dc-domainlocked-r1 UNPROCESSED. LKG observado = h3-logo-zlib-04e3f1a-domainlocked-r1 (digests presentes en ECR). Evidencia: evidence/TASK-002/deployment/candidate-01.json.

# Sesion archivada: SIM-HISTORIAL-EVENTOS-ANTIGUOS-preparing

- Archivada: 2026-10-20T21:17:14Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: SIM-HISTORIAL-EVENTOS-ANTIGUOS
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: merged_deploy (MERGING -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-20T20:50:50Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-20-SIM-HISTORIAL-EVENTOS-ANTIGUOS-review.md

## Estado reciente
- DECISION (DEVELOPING, SIM-HISTORIAL-EVENTOS-ANTIGUOS, sesion other-202610201957-developer-sup8256c2): implementacion lista en rama harness/SIM-HISTORIAL-EVENTOS-ANTIGUOS-eventos-antiguos (head ccfa899). PR #97 abierto. build_timeline_items normaliza entradas/resultado (claves fijas con fallback None) y marca es_legacy; la plantilla muestra para eventos antiguos «Simulacion generada» con ejecutivo, escenario, version del modelo y codigo mas la nota, sin detalle desplegable; tolerancia a datos faltantes/nulos sin 500. Pruebas unitarias verdes (presentacion 9/9, test_web_app 40/40); ruff/black/mypy/bandit PASS; CI Tests/Lint/Docker/Release Tooling verdes.
- BLOCKER: CI del PR #97 con Security Audit en FAIL por pip-audit: certifi 2026.7.22 -> GHSA-6q48-6c7w-9gw2 (fix 2026.10.19). Vulnerabilidad PREEXISTENTE y AJENA a esta tarea (dependencias fuera de scope; restriccion explicita «ni dependencias»). El guard de submit_for_review exige todos los quality_gates PASS, por lo que no se puede entregar a revision sin resolver este bloqueo. Requiere decision humana (bump de dependencias en tarea separada).
- DECISION (DEVELOPING, SIM-HISTORIAL-EVENTOS-ANTIGUOS, sesion other-202610202022-developer-sup592506): re-verificado en esta sesion. origin/main sigue en 7f28265 (sin bump de certifi); worktree limpio con unico commit ccfa899 sobre main; PR #97 sigue con Lint/Tests/Docker/Release verdes y solo Security Audit en FAIL por pip-audit (certifi 2026.7.22 -> GHSA-6q48-6c7w-9gw2, fix 2026.10.19). tasks/current.yaml NO trae allow_lockfile_update y el scope no incluye requirements/**, por lo que el bump de certifi queda fuera de alcance. No se puede registrar evidencia de calidad con pip-audit PASS sin falsear evidencia, y el guard g_developer_evidence_valid rechaza quality_gates no verdes. STOP: bloqueo requiere decision humana.
- DECISION (HUMANO, 2026-10-20, con Claude interactivo): BLOQUEO DE certifi RESUELTO. El PR #98 (commit e11d7f4 en origin/main) subio certifi a 2026.10.19 en requirements/runtime.lock; pip-audit local y el CI de #98 pasan sin vulnerabilidades. Siguiente paso del Developer: traer origin/main a la rama de la tarea con un MERGE (sin rebase ni force-push), subir, esperar a que el CI del PR #97 quede 5/5 en verde, registrar la evidencia de calidad (con pip-audit PASS) y hacer submit_for_review. No modificar requirements/** en esta tarea: el bump ya esta en main.
- 2026-10-20: Tarea SIM-HISTORIAL-LINEA-TIEMPO cerrada; resumen en tasks/completed/SIM-HISTORIAL-LINEA-TIEMPO.yaml

## Bloqueos
- BLOCKER (PREPARING_DEPLOYMENT, SIM-HISTORIAL-EVENTOS-ANTIGUOS, sesion claude-202610202102-deployer-supb11e0e): publish run 39495647051 (release 793e718) fallo en el gate de escaneo ECR: el escaneo de tpi-dev-app y tpi-dev-caddy no se completo en 5 min (no es hallazgo HIGH/CRITICAL). Sin bundle ni artifact; environment sin mutar. Evidencia: evidence/SIM-HISTORIAL-EVENTOS-ANTIGUOS/deployment/failure-01.json. Requiere decision humana.
- BLOCKER: CI del PR #97 con Security Audit en FAIL por pip-audit: certifi 2026.7.22 -> GHSA-6q48-6c7w-9gw2 (fix 2026.10.19). Vulnerabilidad PREEXISTENTE y AJENA a esta tarea (dependencias fuera de scope; restriccion explicita «ni dependencias»). El guard de submit_for_review exige todos los quality_gates PASS, por lo que no se puede entregar a revision sin resolver este bloqueo. Requiere decision humana (bump de dependencias en tarea separada).
- BLOCKER: CI del PR #97 con Security Audit en FAIL por pip-audit: certifi 2026.7.22 -> GHSA-6q48-6c7w-9gw2 (fix 2026.10.19). Vulnerabilidad PREEXISTENTE y AJENA a esta tarea (dependencias fuera de scope; restriccion explicita «ni dependencias»). El guard de submit_for_review exige todos los quality_gates PASS, por lo que no se puede entregar a revision sin resolver este bloqueo. Requiere decision humana (bump de dependencias en tarea separada).

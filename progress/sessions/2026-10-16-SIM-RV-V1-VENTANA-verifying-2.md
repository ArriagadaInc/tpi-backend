# Sesion archivada: SIM-RV-V1-VENTANA-verifying

- Archivada: 2026-10-16T20:09:24Z
- Estado: VERIFYING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: VERIFYING (rol: deployer)
- Tarea: SIM-RV-V1-VENTANA
- Proximo paso: Deployer: observabilidad + smoke; si hay criterios humanos esperar approve.py accept; verified o verify_failed
- Ultima transicion: deploy_succeeded (DEPLOYING -> VERIFYING)
- Actualizado: 2026-10-16T18:19:05Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-16-SIM-RV-V1-VENTANA-verifying.md

## Estado reciente
- DECISION (DEVELOPING, SIM-RV-V1-VENTANA, sesion other-202610161641-developer-supac14c3): por decision del humano la ventana validada queda abierta. Se eliminan clasificar_ventana y VENTANA_ADVERTENCIA_DIAS (app/services/simulador_service.py), el 422 por vencimiento y el contexto advertencia_ventana (app/web/routes/simulador.py) y el bloque condicional de ventana vencida (simulador.html); en su lugar, aviso permanente de valores referenciales (no vinculantes) en pantalla y seccion 'Supuestos y advertencias' en el PDF (generar_pdf). Motor app/simulador_pension/** intacto (conserva VENTANA_VALIDADA y su warnings.warn informativo). Tests del simulador en verde (35/35), ruff/black/mypy/bandit/pip-audit en verde, CI PR #81 success (Lint, Tests con cobertura >=85%, Security Audit, Docker Build, Release Tooling). Evidencia developer-01; submit_for_review.
- DECISION (MERGING/PREPARING_DEPLOYMENT, SIM-RV-V1-VENTANA, sesion claude-202610161707-deployer-sup26e304): PR #81 mergeado por merge_reviewed_pr.py (release 5024922, tree 6d82620 = reviewed_tree); publish run 38937525741 success (scan 0/0); bundle domain-locked reproducible (sha256 c1fd91f2...), S3 content-addressed y AV h3-sim-rv-v1-ventana-5024922-domainlocked-r1 (UNPROCESSED); LKG observado h3-sim-ficha-pdf-dd6be12-domainlocked-r1 con digests presentes en ECR; environment sin mutar. Evidencia merge-01 y candidate-01; `candidate_ready` a Reviewer.
- DECISION (CANDIDATE_REVIEW, SIM-RV-V1-VENTANA, sesion claude-202610161725-reviewer-sup81c84b): APPROVED. Arbol 6d82620 == reviewed_tree, release en main, publish run 38937525741 success, digests ACTIVE con scan 0/0, bundle reconstruido sha256 c1fd91f2... identico, S3 checksum y AV coinciden, LKG h3-sim-ficha-pdf-dd6be12 sano con digests presentes, plan version-only. Evidencia candidate_review-01; `candidate_approve` a Human Gate (AC-5 humano pendiente tras el deploy).
- DECISION (DEPLOYING, SIM-RV-V1-VENTANA, sesion claude-202610161806-deployer-supc6d01d): preflight PASS (cuenta 821656895812, env en LKG Ready/Green/Ok, AV candidata UNPROCESSED con key aprobada); un unico update-environment version-only a h3-sim-rv-v1-ventana-5024922-domainlocked-r1 aceptado, convergio en ~52 s a Ready/Green/Ok, eventos EB todos INFO; cadena VersionLabel -> AV -> S3 checksum (== bundle c1fd91f2...) verificada. Evidencia deployment-01; `deploy_succeeded` a VERIFYING (conteos de logs, smoke y AC-5 humano pendientes).
- DECISION (VERIFYING, SIM-RV-V1-VENTANA, sesion claude-202610161806-deployer-supc6d01d): `deploy_succeeded` registrado; verification-01 PASS (environment Ready/Green/Ok en la version aprobada, eventos INFO, smoke HTTP 6/6 PASS, conteos de logs 0 en los 8 patrones). PENDIENTE HUMANO (AC-5, y confirmacion de AC-2): un ejecutivo genera un PDF en DEV y ve el aviso de valores referenciales en pantalla y PDF, sin advertencia de ventana vencida; un rol no autorizado recibe 403; logs sin PII ni contenido del PDF. Luego el humano ejecuta `python scripts/harness/approve.py accept --decision accept --criteria AC-2,AC-5`; despues el Deployer registra la verificacion final y `verified`.
- DECISION (VERIFYING, SIM-RV-V1-VENTANA, sesion claude-202610162006-deployer-supe05b07): aceptacion humana registrada (acceptance-01: AC-2, AC-4, AC-5). Re-verificacion PASS: environment Ready/Green/Ok en la version aprobada sin updates posteriores, eventos INFO, smoke HTTP PASS, conteos de logs 0 en los 8 patrones. Evidencia verification-02; `verified`.

## Bloqueos
- Ninguno.

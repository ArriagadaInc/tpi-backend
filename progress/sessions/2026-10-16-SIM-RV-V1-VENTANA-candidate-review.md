# Sesion archivada: SIM-RV-V1-VENTANA-candidate-review

- Archivada: 2026-10-16T17:28:18Z
- Estado: CANDIDATE_REVIEW

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: CANDIDATE_REVIEW (rol: reviewer)
- Tarea: SIM-RV-V1-VENTANA
- Proximo paso: Reviewer: verificar cadena de identidad, scans, bundle reproducible, LKG; candidate_approve o candidate_reject
- Ultima transicion: candidate_ready (PREPARING_DEPLOYMENT -> CANDIDATE_REVIEW)
- Actualizado: 2026-10-16T17:25:11Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-16-SIM-RV-V1-VENTANA-preparing.md

## Estado reciente
- DECISION: VERIFYING de SIM-FICHA-PDF (sesion claude-202610160346-deployer-sup1ecc7b): `deploy_succeeded` aplicado; smoke HTTP PASS (6/6, leads y simulador redirigen a /login), conteos de logs 0 en los 8 patrones, identidad de runtime verificada; evidencia verification-01 (AC-1..5 met, AC-6 pending_human). Esperando que el humano ejecute `approve.py accept` para AC-6: generar un PDF del simulador en DEV y compararlo con la ficha de ejemplo (apaisado, banda azul marino, tablas Opcion I y II con Rescate Total, pie y logo; se lee bien en pantalla y al imprimir; sin RUT, correo ni telefono del lead). Luego el Deployer registra verification final y `verified`.
- DECISION: el humano acepto AC-1, AC-3 y AC-6 de SIM-FICHA-PDF (acceptance-01). VERIFYING final (sesion claude-202610161313-deployer-sup297f89): environment Ready/Green/Ok en la version aprobada, eventos EB todos INFO, conteos de logs 0 en los 8 patrones con ventana ampliada; evidencia verification-02 (AC-1..6 met); `verified`.
- 2026-10-16: Tarea SIM-FICHA-PDF cerrada; resumen en tasks/completed/SIM-FICHA-PDF.yaml
- DECISION (DEVELOPING, SIM-RV-V1-VENTANA, sesion other-202610161641-developer-supac14c3): por decision del humano la ventana validada queda abierta. Se eliminan clasificar_ventana y VENTANA_ADVERTENCIA_DIAS (app/services/simulador_service.py), el 422 por vencimiento y el contexto advertencia_ventana (app/web/routes/simulador.py) y el bloque condicional de ventana vencida (simulador.html); en su lugar, aviso permanente de valores referenciales (no vinculantes) en pantalla y seccion 'Supuestos y advertencias' en el PDF (generar_pdf). Motor app/simulador_pension/** intacto (conserva VENTANA_VALIDADA y su warnings.warn informativo). Tests del simulador en verde (35/35), ruff/black/mypy/bandit/pip-audit en verde, CI PR #81 success (Lint, Tests con cobertura >=85%, Security Audit, Docker Build, Release Tooling). Evidencia developer-01; submit_for_review.
- DECISION (MERGING/PREPARING_DEPLOYMENT, SIM-RV-V1-VENTANA, sesion claude-202610161707-deployer-sup26e304): PR #81 mergeado por merge_reviewed_pr.py (release 5024922, tree 6d82620 = reviewed_tree); publish run 38937525741 success (scan 0/0); bundle domain-locked reproducible (sha256 c1fd91f2...), S3 content-addressed y AV h3-sim-rv-v1-ventana-5024922-domainlocked-r1 (UNPROCESSED); LKG observado h3-sim-ficha-pdf-dd6be12-domainlocked-r1 con digests presentes en ECR; environment sin mutar. Evidencia merge-01 y candidate-01; `candidate_ready` a Reviewer.
- DECISION (CANDIDATE_REVIEW, SIM-RV-V1-VENTANA, sesion claude-202610161725-reviewer-sup81c84b): APPROVED. Arbol 6d82620 == reviewed_tree, release en main, publish run 38937525741 success, digests ACTIVE con scan 0/0, bundle reconstruido sha256 c1fd91f2... identico, S3 checksum y AV coinciden, LKG h3-sim-ficha-pdf-dd6be12 sano con digests presentes, plan version-only. Evidencia candidate_review-01; `candidate_approve` a Human Gate (AC-5 humano pendiente tras el deploy).

## Bloqueos
- Ninguno.

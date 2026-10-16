# Sesion archivada: SIM-EVIDENCIA-ENTRADAS-verifying2

- Archivada: 2026-10-16T22:45:55Z
- Estado: VERIFYING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: VERIFYING (rol: deployer)
- Tarea: SIM-EVIDENCIA-ENTRADAS
- Proximo paso: Deployer: observabilidad + smoke; si hay criterios humanos esperar approve.py accept; verified o verify_failed
- Ultima transicion: deploy_succeeded (DEPLOYING -> VERIFYING)
- Actualizado: 2026-10-16T21:55:28Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-16-SIM-EVIDENCIA-ENTRADAS-verifying.md

## Estado reciente
- DECISION (PREPARING_DEPLOYMENT, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162131-deployer-sup5b27ee): tras resolution-01 se uso el publish run 38964107386 intento 2 (success; digests nuevos app 6bcc72a3 / caddy 75d48ea4, scan 0/0, presentes en ECR). Bundle domain-locked sha256 0a495da7 reproducible; S3 content-addressed (checksum verificado) y AV h3-sim-evidencia-entradas-a7859af-domainlocked-r1 UNPROCESSED. LKG h3-sim-rv-v1-ventana-5024922-domainlocked-r1. Environment sin mutar. Evidencia candidate-01.
- DECISION (CANDIDATE_REVIEW, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162137-reviewer-sup39a4b3): candidate APPROVED. Arbol a7859af == reviewed_tree dcf66c8; publish run 38964107386 success para el SHA; digests app 6bcc72a3 / caddy 75d48ea4 ACTIVE, scan 0/0; bundle reconstruido sha256 0a495da7 identico; S3 ChecksumSHA256 y AV SourceBundle coinciden; LKG sano con digests presentes; plan version-only, rollback unico al LKG. Sin dry-run (no permitido en candidate_read). Evidencia candidate_review-01.
- DECISION (DEPLOYING, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162143-deployer-supacfe99): preflight PASS (cuenta/region, env Ready/Green/Ok en el LKG, AV candidata con SourceBundle aprobado). Un unico update-environment version-only a h3-sim-evidencia-entradas-a7859af-domainlocked-r1 (aceptado 21:44:36Z, completado 21:45:27Z, sin reintentos ni option settings). Final Ready/Green/Ok con VersionLabel exacta; cadena de identidad VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 coincide con approval-01. Sin rollback. Evidencia deployment-01; AC-6 (smoke humano) pendiente para VERIFYING.
- DECISION (VERIFYING, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162143-deployer-supacfe99): env Ready/Green/Ok con la VersionLabel exacta; eventos EB todos INFO; smoke HTTP 7/7 PASS (200 en publico/login/catalogs/css; 307 -> /login en leads y simulador anonimos); conteos de logs 0 en los 8 patrones. Evidencia verification-01. NO se emite `verified`: queda pendiente el criterio humano AC-6.
- DECISION (VERIFYING, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162242-deployer-sup2d1b77): el humano acepto AC-5 y AC-6 (acceptance-01, 22:42:24Z). Re-observacion: env Ready/Green/Ok en la VersionLabel exacta, eventos EB todos INFO, smoke 7/7 PASS (simulador anonimo verificado en /leads/1/simulador: 307 -> /login), conteos de logs 0 en los 8 patrones desde el cutover. Evidencia verification-02; se emite `verified`.

## Bloqueos
- Ninguno.

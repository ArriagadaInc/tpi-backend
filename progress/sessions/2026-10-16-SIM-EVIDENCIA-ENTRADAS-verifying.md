# Sesion archivada: SIM-EVIDENCIA-ENTRADAS-verifying

- Archivada: 2026-10-16T21:57:57Z
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
- Ultima sesion archivada: progress/sessions/2026-10-16-SIM-EVIDENCIA-ENTRADAS-deploying.md

## Estado reciente
- DECISION (DEVELOPING, SIM-EVIDENCIA-ENTRADAS, sesion other-202610162013-developer-sup6cbf35): worktree creado desde origin/main (5024922), rama harness/SIM-EVIDENCIA-ENTRADAS-evidencia-entradas, SHA head c657c0c. El detalle del evento `simulacion_renta_vitalicia` pasa a versionado (`schema_version`) y guarda entradas (causante, beneficiarios, escalares) y resultado (pension_uf y, en renta temporal, renta_temporal_uf y meses_diferidos) como evidencia de solo escritura, sin nombres/RUT/correo/telefono ni contenido del PDF. PR #83 abierto contra main; CI verde (5 checks). Evidencia developer-01 registrada; gates locales ruff/black/mypy/bandit PASS y 96 tests sim_rv PASS. Documentacion (matriz AC-10/AC-11, PENDIENTES #6, MODELO, CHANGELOG, BITACORA) actualizada; AC-6 (smoke humano AWS DEV) queda pending_verification.
- DECISION (PREPARING_DEPLOYMENT, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162038-deployer-supc4fadc): PR #83 mergeado por merge_reviewed_pr.py; release_sha a7859af (tree dcf66c8 == reviewed_tree); evidencia merge-01. Preflight PASS (env Ready/Green/Ok, LKG h3-sim-rv-v1-ventana-5024922-domainlocked-r1, digests LKG presentes, Promote deshabilitado). Publish run 38964107386 (1 dispatch) fallo en el gate de escaneo: el escaneo ECR de tpi-dev-app no completo en 5 min (caddy CRITICAL=0 HIGH=0); no es hallazgo de seguridad. Sin bundle, S3 ni AV; environment sin mutar. No se reintenta el publish (tags ECR IMMUTABLE ya ocupados por las imagenes del SHA). Evidencia failure-01; transicion preparation_failed.
- DECISION (PREPARING_DEPLOYMENT, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162131-deployer-sup5b27ee): tras resolution-01 se uso el publish run 38964107386 intento 2 (success; digests nuevos app 6bcc72a3 / caddy 75d48ea4, scan 0/0, presentes en ECR). Bundle domain-locked sha256 0a495da7 reproducible; S3 content-addressed (checksum verificado) y AV h3-sim-evidencia-entradas-a7859af-domainlocked-r1 UNPROCESSED. LKG h3-sim-rv-v1-ventana-5024922-domainlocked-r1. Environment sin mutar. Evidencia candidate-01.
- DECISION (CANDIDATE_REVIEW, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162137-reviewer-sup39a4b3): candidate APPROVED. Arbol a7859af == reviewed_tree dcf66c8; publish run 38964107386 success para el SHA; digests app 6bcc72a3 / caddy 75d48ea4 ACTIVE, scan 0/0; bundle reconstruido sha256 0a495da7 identico; S3 ChecksumSHA256 y AV SourceBundle coinciden; LKG sano con digests presentes; plan version-only, rollback unico al LKG. Sin dry-run (no permitido en candidate_read). Evidencia candidate_review-01.
- DECISION (DEPLOYING, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162143-deployer-supacfe99): preflight PASS (cuenta/region, env Ready/Green/Ok en el LKG, AV candidata con SourceBundle aprobado). Un unico update-environment version-only a h3-sim-evidencia-entradas-a7859af-domainlocked-r1 (aceptado 21:44:36Z, completado 21:45:27Z, sin reintentos ni option settings). Final Ready/Green/Ok con VersionLabel exacta; cadena de identidad VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 coincide con approval-01. Sin rollback. Evidencia deployment-01; AC-6 (smoke humano) pendiente para VERIFYING.
- DECISION (VERIFYING, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162143-deployer-supacfe99): env Ready/Green/Ok con la VersionLabel exacta; eventos EB todos INFO; smoke HTTP 7/7 PASS (200 en publico/login/catalogs/css; 307 -> /login en leads y simulador anonimos); conteos de logs 0 en los 8 patrones. Evidencia verification-01. NO se emite `verified`: queda pendiente el criterio humano AC-6.
- PENDIENTE HUMANO: AC-6 (generar un PDF en DEV y ejecutar la consulta de solo lectura que muestre el evento con entradas y resultado, sin datos personales directos). Comando del humano: `python scripts/harness/approve.py accept --decision accept --criteria AC-6`. Luego el Deployer emite `verified`.

## Bloqueos
- Ninguno.

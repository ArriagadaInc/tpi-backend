# Sesion archivada: SIM-EVIDENCIA-ENTRADAS-deployer-prep2

- Archivada: 2026-10-16T21:37:24Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: SIM-EVIDENCIA-ENTRADAS
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: resolve_to_preparing (BLOCKED_HUMAN -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-16T21:31:27Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-16-SIM-EVIDENCIA-ENTRADAS-deployer-prep.md

## Estado reciente
- DECISION (DEVELOPING, SIM-EVIDENCIA-ENTRADAS, sesion other-202610162013-developer-sup6cbf35): worktree creado desde origin/main (5024922), rama harness/SIM-EVIDENCIA-ENTRADAS-evidencia-entradas, SHA head c657c0c. El detalle del evento `simulacion_renta_vitalicia` pasa a versionado (`schema_version`) y guarda entradas (causante, beneficiarios, escalares) y resultado (pension_uf y, en renta temporal, renta_temporal_uf y meses_diferidos) como evidencia de solo escritura, sin nombres/RUT/correo/telefono ni contenido del PDF. PR #83 abierto contra main; CI verde (5 checks). Evidencia developer-01 registrada; gates locales ruff/black/mypy/bandit PASS y 96 tests sim_rv PASS. Documentacion (matriz AC-10/AC-11, PENDIENTES #6, MODELO, CHANGELOG, BITACORA) actualizada; AC-6 (smoke humano AWS DEV) queda pending_verification.
- DECISION (PREPARING_DEPLOYMENT, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162038-deployer-supc4fadc): PR #83 mergeado por merge_reviewed_pr.py; release_sha a7859af (tree dcf66c8 == reviewed_tree); evidencia merge-01. Preflight PASS (env Ready/Green/Ok, LKG h3-sim-rv-v1-ventana-5024922-domainlocked-r1, digests LKG presentes, Promote deshabilitado). Publish run 38964107386 (1 dispatch) fallo en el gate de escaneo: el escaneo ECR de tpi-dev-app no completo en 5 min (caddy CRITICAL=0 HIGH=0); no es hallazgo de seguridad. Sin bundle, S3 ni AV; environment sin mutar. No se reintenta el publish (tags ECR IMMUTABLE ya ocupados por las imagenes del SHA). Evidencia failure-01; transicion preparation_failed.

- DECISION (PREPARING_DEPLOYMENT, SIM-EVIDENCIA-ENTRADAS, sesion claude-202610162131-deployer-sup5b27ee): tras resolution-01 se uso el publish run 38964107386 intento 2 (success; digests nuevos app 6bcc72a3 / caddy 75d48ea4, scan 0/0, presentes en ECR). Bundle domain-locked sha256 0a495da7 reproducible; S3 content-addressed (checksum verificado) y AV h3-sim-evidencia-entradas-a7859af-domainlocked-r1 UNPROCESSED. LKG h3-sim-rv-v1-ventana-5024922-domainlocked-r1. Environment sin mutar. Evidencia candidate-01.

## Bloqueos
- Ninguno. (El BLOCKER del timeout de escaneo fue resuelto por el humano: resolution-01.)

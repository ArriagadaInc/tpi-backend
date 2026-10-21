# Sesion archivada: CRM-ADJUNTOS-2-CODIGO-verifying

- Archivada: 2026-10-21T21:41:58Z
- Estado: VERIFYING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: VERIFYING (rol: deployer)
- Tarea: CRM-ADJUNTOS-2-CODIGO
- Proximo paso: Deployer: observabilidad + smoke; si hay criterios humanos esperar approve.py accept; verified o verify_failed
- Ultima transicion: deploy_succeeded (DEPLOYING -> VERIFYING)
- Actualizado: 2026-10-21T21:40:03Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-21-CRM-ADJUNTOS-2-CODIGO-deploying.md

## Estado reciente
- DECISION (MERGING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610211958-deployer-sup27d064): PR 111 mergeado (squash) con merge_commit 03436de; release_tree == reviewed_tree (2ddb00b). Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/merge-01.json. Clase C: la transicion obligatoria es merged_non_fast_path hacia BLOCKED_HUMAN.
- DECISION (PREPARING_DEPLOYMENT, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212107-deployer-sup512fd9): candidate listo para release_sha 03436de (arbol 2ddb00b = reviewed_tree). Publish run 39676430248 6/6, scan 0/0, bundle domain-locked c24f2e7e... reproducible con ATTACHMENTS_* literales, S3 content-addressed + AV h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1 UNPROCESSED. LKG observado: h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1. El checkout local de main esta atras de origin/main (496213e), asi que el template se extrajo del commit de release; un primer bundle sin variables de adjuntos se descarto antes de subir nada. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/candidate-01.json.
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion claude-202610212127-reviewer-sup8fac69 (blocked_guard) cuando intentaste anotar tu decision en `progress/current.md` con un `python - <<'EOF'` que calculaba la ruta con `os.path.abspath`: «python escribe un destino no resoluble en codigo que menciona rutas protegidas». Es un bloqueo de FORMA, no de fondo. No uses Python ni heredocs para escribir `progress/current.md`: usa la herramienta Edit o Write sobre esa ruta (esta siempre permitida). TU TRABAJO SE CONSERVA: `evidence/CRM-ADJUNTOS-2-CODIGO/reviewer/candidate_review-01.json` ya existe con decision APPROVED (release_sha 03436de, arbol 2ddb00b, bundle c24f2e7e... reconstruido de forma independiente, variables de adjuntos solo en backoffice, 9 comprobaciones PASS). No repitas toda la revision: verifica que esa evidencia coincide con `evidence/CRM-ADJUNTOS-2-CODIGO/deployment/candidate-01.json` y con el estado actual (usa Read/Grep y comandos de lectura), anota tu decision en `progress/current.md` con Edit y aplica la transicion `candidate_approve` con `scripts/harness/transition.py` como corresponde a tu rol. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.
- DECISION (CANDIDATE_REVIEW, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212131-reviewer-sup96a3be): APPROVED. Verificado con lecturas propias que candidate_review-01.json (creada en la sesion claude-202610212127-reviewer-sup8fac69) coincide con candidate-01.json (release_sha 03436de, arbol 2ddb00b = reviewed_tree, digests app 8caad557 / caddy 83e3c337, bundle c24f2e7e, label h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1) y con Git (origin/main == 03436de, arbol 2ddb00b). No se repitieron las lecturas AWS. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/reviewer/candidate_review-01.json.
- DECISION (DEPLOYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): cutover version-only ejecutado (1 update-environment, sin reintentos ni option settings) a h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1. Preflight PASS (LKG h3-seg-desacoplar-streamlit-0c9b165 observado, digests ACTIVE en ECR, Promote deshabilitado). Resultado: Ready/Green/Ok, VersionLabel exacta, update completado 21:38:00Z, cadena VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 coincide. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/deployment-01.json. Siguiente: deploy_succeeded -> VERIFYING (smoke y conteos de logs; AC-12 humano pendiente).
- DECISION (VERIFYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): deploy_succeeded aplicado; verificacion tecnica PASS. Estado Ready/Green/Ok con VersionLabel exacta, cadena de identidad OK, smoke HTTP 6/6 PASS (incluido /leads/1/adjuntos/<uuid> sin sesion -> 307 /login), conteos de logs desde 21:37:18Z todos en 0 (incluido Traceback). Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/verification-01.json. PENDIENTE HUMANO (AC-12): smoke en DEV (https://backoffice.dev.tupensioninteligente.cl): subir PNG/JPEG y PDF en una nota y verlos en linea y descargarlos; asesor con acceso los ve y asesor sin acceso recibe 404; subir EICAR y ver "no disponible"; un GIF se rechaza; eliminar un adjunto como ceo o cto y ver "adjunto eliminado"; revisar eventos en tpi.auditoria; sin errores en logs. Luego el humano ejecuta `python scripts/harness/approve.py accept --decision accept --criteria AC-12`; despues el Deployer aplica `verified`.

## Bloqueos
- Ninguno.

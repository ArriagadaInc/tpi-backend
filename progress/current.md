# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: IDLE (rol: human)
- Tarea: ninguna
- Proximo paso: Humano elige tarea: python scripts/harness/approve.py activate --task <ID>
- Ultima transicion: close (DONE -> IDLE)
- Actualizado: 2026-10-21T22:05:00Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-21-CRM-ADJUNTOS-2-CODIGO-closure.md

## Estado reciente
- DECISION (CANDIDATE_REVIEW, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212131-reviewer-sup96a3be): APPROVED. Verificado con lecturas propias que candidate_review-01.json (creada en la sesion claude-202610212127-reviewer-sup8fac69) coincide con candidate-01.json (release_sha 03436de, arbol 2ddb00b = reviewed_tree, digests app 8caad557 / caddy 83e3c337, bundle c24f2e7e, label h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1) y con Git (origin/main == 03436de, arbol 2ddb00b). No se repitieron las lecturas AWS. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/reviewer/candidate_review-01.json.
- DECISION (DEPLOYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): cutover version-only ejecutado (1 update-environment, sin reintentos ni option settings) a h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1. Preflight PASS (LKG h3-seg-desacoplar-streamlit-0c9b165 observado, digests ACTIVE en ECR, Promote deshabilitado). Resultado: Ready/Green/Ok, VersionLabel exacta, update completado 21:38:00Z, cadena VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 coincide. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/deployment-01.json. Siguiente: deploy_succeeded -> VERIFYING (smoke y conteos de logs; AC-12 humano pendiente).
- DECISION (VERIFYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): deploy_succeeded aplicado; verificacion tecnica PASS. Estado Ready/Green/Ok con VersionLabel exacta, cadena de identidad OK, smoke HTTP 6/6 PASS (incluido /leads/1/adjuntos/<uuid> sin sesion -> 307 /login), conteos de logs desde 21:37:18Z todos en 0 (incluido Traceback). Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/verification-01.json. PENDIENTE HUMANO (AC-12): smoke en DEV (https://backoffice.dev.tupensioninteligente.cl): subir PNG/JPEG y PDF en una nota y verlos en linea y descargarlos; asesor con acceso los ve y asesor sin acceso recibe 404; subir EICAR y ver "no disponible"; un GIF se rechaza; eliminar un adjunto como ceo o cto y ver "adjunto eliminado"; revisar eventos en tpi.auditoria; sin errores en logs. Luego el humano ejecuta `python scripts/harness/approve.py accept --decision accept --criteria AC-12`; despues el Deployer aplica `verified`.
- DECISION (VERIFYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212203-deployer-sup9c8683): el humano registro acceptance-01 (AC-11 y AC-12 aceptados, smoke DEV OK con observaciones). Verificacion final PASS en verification-02 (tecnica de verification-01 + aceptacion humana); sin AWS nuevo. Observaciones funcionales del humano, fuera del deploy y sin rollback: (1) rechazo de PDF sin motivo especifico; (2) imagen recien subida se ve como "adjunto eliminado" mientras se escanea; (3) PDF eliminado conserva enlaces y abre 404. Siguiente: verified -> DONE.
- 2026-10-21: Tarea CRM-ADJUNTOS-2-CODIGO cerrada; resumen en tasks/completed/CRM-ADJUNTOS-2-CODIGO.yaml

## Bloqueos
- Ninguno.

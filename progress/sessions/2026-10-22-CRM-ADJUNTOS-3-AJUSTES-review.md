# Sesion archivada: CRM-ADJUNTOS-3-AJUSTES-review

- Archivada: 2026-10-22T00:08:34Z
- Estado: REVIEWING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: REVIEWING (rol: reviewer)
- Tarea: CRM-ADJUNTOS-3-AJUSTES
- Proximo paso: Reviewer: revisar SHA exacto, CI verde, registrar review y review_approve o review_reject
- Ultima transicion: start_review (READY_FOR_REVIEW -> REVIEWING)
- Actualizado: 2026-10-22T00:06:34Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-22-CRM-ADJUNTOS-3-AJUSTES-developer.md

## Estado reciente
- DECISION (DEPLOYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): cutover version-only ejecutado (1 update-environment, sin reintentos ni option settings) a h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1. Preflight PASS (LKG h3-seg-desacoplar-streamlit-0c9b165 observado, digests ACTIVE en ECR, Promote deshabilitado). Resultado: Ready/Green/Ok, VersionLabel exacta, update completado 21:38:00Z, cadena VersionLabel -> AV SourceBundle -> S3 ChecksumSHA256 coincide. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/deployment-01.json. Siguiente: deploy_succeeded -> VERIFYING (smoke y conteos de logs; AC-12 humano pendiente).
- DECISION (VERIFYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212135-deployer-supa8f7d1): deploy_succeeded aplicado; verificacion tecnica PASS. Estado Ready/Green/Ok con VersionLabel exacta, cadena de identidad OK, smoke HTTP 6/6 PASS (incluido /leads/1/adjuntos/<uuid> sin sesion -> 307 /login), conteos de logs desde 21:37:18Z todos en 0 (incluido Traceback). Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/deployment/verification-01.json. PENDIENTE HUMANO (AC-12): smoke en DEV (https://backoffice.dev.tupensioninteligente.cl): subir PNG/JPEG y PDF en una nota y verlos en linea y descargarlos; asesor con acceso los ve y asesor sin acceso recibe 404; subir EICAR y ver "no disponible"; un GIF se rechaza; eliminar un adjunto como ceo o cto y ver "adjunto eliminado"; revisar eventos en tpi.auditoria; sin errores en logs. Luego el humano ejecuta `python scripts/harness/approve.py accept --decision accept --criteria AC-12`; despues el Deployer aplica `verified`.
- DECISION (VERIFYING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610212203-deployer-sup9c8683): el humano registro acceptance-01 (AC-11 y AC-12 aceptados, smoke DEV OK con observaciones). Verificacion final PASS en verification-02 (tecnica de verification-01 + aceptacion humana); sin AWS nuevo. Observaciones funcionales del humano, fuera del deploy y sin rollback: (1) rechazo de PDF sin motivo especifico; (2) imagen recien subida se ve como "adjunto eliminado" mientras se escanea; (3) PDF eliminado conserva enlaces y abre 404. Siguiente: verified -> DONE.
- 2026-10-21: Tarea CRM-ADJUNTOS-2-CODIGO cerrada; resumen en tasks/completed/CRM-ADJUNTOS-2-CODIGO.yaml
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion other-202610212329-developer-supc88a4c (blocked_guard) porque intentaste editar `C:\desarrollos\TPI\tpi_deep_agents\tpi-backend\app\config\settings.py`, es decir el archivo de la RAIZ DE CONTROL, no el de tu worktree. Es un bloqueo de FORMA (de ruta): el codigo solo se escribe dentro de tu worktree. Tu worktree ya existe y esta limpio: `C:\desarrollos\TPI\tpi_deep_agents\tpi-backend\.harness-worktrees\CRM-ADJUNTOS-3-AJUSTES-developer-c3d597e` (rama `harness/CRM-ADJUNTOS-3-AJUSTES-ajustes`). Lee y edita SIEMPRE con rutas que empiecen por esa carpeta (por ejemplo `...\.harness-worktrees\CRM-ADJUNTOS-3-AJUSTES-developer-c3d597e\app\config\settings.py`) y ejecuta los comandos de shell con `cd` a ese worktree. La raiz de control solo se usa para el payload de evidencia (`.harness-runtime\payloads\developer.json`, ruta absoluta) y para `evidence.py` y `transition.py`. No se perdio trabajo: tu unico intento de escritura fue el denegado. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.
- DECISION (REVIEWING, CRM-ADJUNTOS-3-AJUSTES, sesion claude-202610220005-reviewer-sup706068): APPROVED sobre d52de57 (arbol d901fe3), PR 116 con CI verde (5 jobs) y al dia con main; 128 pruebas de adjuntos re-ejecutadas en el SHA exacto; AC-1..AC-8 cumplidos, AC-9 humano pendiente tras el despliegue. Hallazgos: 1 minor (replace_attachment_mark sin aviso si no reemplaza) y 2 info. Precondicion del humano: s3:GetObjectTagging aplicado antes del despliegue. Evidencia: evidence/CRM-ADJUNTOS-3-AJUSTES/reviewer/review-01.json.

## Bloqueos
- Ninguno.

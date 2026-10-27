# Sesion archivada: CRM-AGENDA-3-LOOK-candidate-review

- Archivada: 2026-10-27T02:04:57Z
- Estado: CANDIDATE_REVIEW

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: CANDIDATE_REVIEW (rol: reviewer)
- Tarea: CRM-AGENDA-3-LOOK
- Proximo paso: Reviewer: verificar cadena de identidad, scans, bundle reproducible, LKG; candidate_approve o candidate_reject
- Ultima transicion: candidate_ready (PREPARING_DEPLOYMENT -> CANDIDATE_REVIEW)
- Actualizado: 2026-10-27T02:00:02Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-27-CRM-AGENDA-3-LOOK-candidate.md

## Estado reciente
- 2026-10-26: Tarea CRM-AGENDA-2-CALENDARIO cerrada; resumen en tasks/completed/CRM-AGENDA-2-CALENDARIO.yaml
- NOTA (ORQUESTADOR INTERACTIVO, 2026-10-27) PARA CRM-AGENDA-3-LOOK: la referencia exacta esta en docs/ui/referencia/agenda/ (README.md explica cada archivo): copia a su ruta destino base.html, agenda.html, agenda_form_fields.html, agenda_macros.html, reunion_card.html, app.css, agenda_presentation.py y routes/agenda.py. Verifica con `git diff --no-index --ignore-cr-at-eol <referencia> <destino>`. Si app.css cambio en main desde dae6d58, reaplica solo el bloque de la agenda, `.timeline-item` y `.brand-link`. Con esa version ya pasan las 101 pruebas de agenda existentes; lo que si cambia es `tests/unit/test_web_app.py` (pruebas del boton Home, alrededor de las lineas 1046 a 1092): reescribelas SIN debilitarlas segun el AC-6 (con sesion y URL aprobada el logo es a.brand-link con el href aprobado, target _blank y rel noopener noreferrer, y no existe el boton Home; en login, sin URL o con URL no aprobada el logo no tiene enlace ni aparece la palabra Home). Agrega las pruebas de los helpers nuevos de agenda_presentation.py (AC-2) y las de privacidad que leen response.text de GET /agenda (AC-3). Trampa conocida: en Jinja una clave de dict llamada `items` choca con dict.items (la referencia ya usa `reuniones`). Los archivos de la referencia NO se editan.
- DECISION (REVIEWER, 2026-10-27, claude-202610270140-reviewer-sup26287c): CRM-AGENDA-3-LOOK APPROVED sobre d3028532 (tree 2952dee3, PR #144, CI run 40432962416 success). Hallazgo minor R1: agenda_presentation.py y routes/agenda.py difieren de la referencia solo por formato black (AST identico); los .py de la referencia no pasan black, asi que AC-1 literal choca con el gate de formato. Para el humano: normalizar la referencia con black en una tarea de docs si quiere identidad literal. Evidencia: evidence/CRM-AGENDA-3-LOOK/reviewer/review-01.json.
- DECISION (DEPLOYER, 2026-10-27, claude-202610270144-deployer-sup9fc349): PR #144 mergeado con merge_reviewed_pr.py (squash, match-head d3028532). release_sha d8b8eecc (parent a81bf81), tree 2952dee3 == reviewed_tree. Evidencia: evidence/CRM-AGENDA-3-LOOK/deployment/merge-01.json. Transicion `merged` -> PREPARING_DEPLOYMENT.
- DECISION (DEPLOYER, 2026-10-27, claude-202610270148-deployer-supc45233): candidate listo. Preflight PASS (cuenta/region, env Ready/Green/Ok en LKG h3-crm-agenda-2-calendario-a4a5bee-domainlocked-r1, AV y digests del LKG presentes, Promote deshabilitado). Publish run 40434739265 success 6/6 (despachado 01:48Z, reutilizado, sin re-dispatch); scans 0/0. Bundle domain-locked reproducible sha256 8adec16a...; S3 content-addressed + AV h3-crm-agenda-3-look-d8b8eec-domainlocked-r1 UNPROCESSED. Env sin mutar. Evidencia: evidence/CRM-AGENDA-3-LOOK/deployment/candidate-01.json. Transicion `candidate_ready` -> CANDIDATE_REVIEW.
- DECISION (REVIEWER, 2026-10-27, claude-202610270200-reviewer-supab07f0): candidate APPROVED (cause null). Tree d8b8eec = 2952dee3 = reviewed_tree; publish 40434739265 success en el release; digests ACTIVE, IMMUTABLE, scans 0/0; bundle reconstruido sha256 8adec16a... (4917 B) = candidate = checksum S3; AV SourceBundle coincide; env Ready/Green/Ok en el LKG, cuyos AV, objeto S3 y digests estan presentes; plan version-only. Evidencia: evidence/CRM-AGENDA-3-LOOK/reviewer/candidate_review-01.json. Transicion `candidate_approve` -> WAITING_HUMAN_APPROVAL.

## Bloqueos
- Ninguno.

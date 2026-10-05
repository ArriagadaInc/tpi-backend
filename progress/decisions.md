# Decisiones persistentes del Harness

Registro breve. El detalle vive en la fuente enlazada; no copiar documentos aqui.
`context_compact.py` agrega al final las lineas `DECISION:` encontradas en `progress/current.md`.

| ID | Fecha | Decision | Fuente |
| --- | --- | --- | --- |
| D-001 | 2026-09-14 | El repositorio es el Harness; los runtimes son intercambiables. | AGENTS.md |
| D-002 | 2026-09-14 | Contrato CI/CD v2 completo versionado en docs/cicd como fuente canonica. | docs/cicd/TPI_Contrato_CICD_AWS_v2.md |
| D-003 | 2026-09-14 | Cobertura operativa 85% (gate CI); 80% de ENGINEERING_STANDARDS es deuda documental. | tasks/backlog.yaml DOC-COVERAGE-80-85 |
| D-004 | 2026-09-14 | Flujo: reviewed tree -> merge main -> release SHA -> candidate -> deploy; approved_commit == deployed_commit. | harness/project-profile.yaml release |
| D-005 | 2026-09-14 | Human Gate protege la mutacion del runtime; PREPARING_DEPLOYMENT puede publicar ECR, S3 content-addressed y AV --no-process. | harness/policies.yaml aws.modes.prepare |
| D-006 | 2026-09-14 | CANDIDATE_REVIEW automatico por el Reviewer antes del Human Gate. | harness/workflow.yaml |
| D-007 | 2026-09-14 | Rollback: autorizacion condicionada en el mismo gate, un unico intento version-only al LKG nombrado. | harness/policies.yaml rollback_authorization |
| D-008 | 2026-09-14 | Deploy solo en Claude Code via aws_guard con perfil tpi-dev (transitorio). | harness/policies.yaml harness.deploy_capable_runtimes |
| D-009 | 2026-09-14 | MCP AWS = conocimiento (read-only); operaciones solo via aws_guard; run_script y get_presigned_url prohibidos. | .mcp.json, harness/policies.yaml mcp |
| D-010 | 2026-09-14 | Aceptacion humana excepcional en VERIFYING si un criterio requiere autenticacion. | tasks/backlog.yaml AUTOMATED_AUTHENTICATED_SMOKE |
| D-011 | 2026-09-14 | Migraciones en AWS DEV = clase D, BLOCKED_HUMAN; no reejecutar 005/006. | docs/cicd/TPI_Contrato_CICD_AWS_v2.md seccion 10 |
| D-012 | 2026-09-14 | max_rework_rounds = 3; luego BLOCKED_HUMAN. | harness/policies.yaml |
| D-013 | 2026-09-15 | Correccion: progress/sessions/2026-09-14-harness-bootstrap.md y progress/current.md afirmaban tests A-J "probados localmente"; tests/harness/ solo tenia __init__.py (verificado por filesystem). Se agrego la regla de orden de autoridad operacional (Git/evidencia/tests > state+workflow > docs > progress) y se implementaron tests A-J y M1-M6 reales bajo mantenimiento. | AGENTS.md, tests/harness/, evidence/harness/bootstrap-validation.json |
| D-014 | 2026-09-15 | Mantenimiento (TPI_HARNESS_MAINTENANCE=1) corrigio D2 (bypass del hook por doble invocacion de guard.py tras consumir stdin), D3 (bypass global de mantenimiento), D4 (sin bloqueo de comandos destructivos), D6 (mantenimiento ampliaba AWS en IDLE/BLOCKED_HUMAN), D7 (lectura de secretos por shell sin cubrir). Detalle en evidence/harness/bootstrap-validation.json. | harness/policies.yaml, scripts/harness/guard.py, scripts/harness/aws_guard.py, .claude/settings.json |
| D-015 | 2026-09-29 | [HUMANA - Alvaro Arriagada (owner), 2026-09-29, mensaje del humano en la sesion claude-202609292342-deployer-reconcile; registrada por el Deployer] H3.3.7: se conserva el merge del PR #60 (6f0f5bb1e934742cd8e8572d4a401f8bf29ab1c7). Hechos: el clasificador de permisos de Claude Code denego gh pr merge en claude-202609292324-deployer-sup6895f8; la sesion claude-202609292326-deployer-sup5218e1 lo ejecuto despues sin resolucion humana previa; merge, tree f514a0e == reviewed_tree y CI main run 36645354294 success re-verificados; aceptacion humana posterior. Autoriza reconciliar evidencia/estado y seguir el flujo normal. NO autoriza repetir ese comportamiento; NO aprueba el candidate; NO acepta AC-1..AC-3. | progress/sessions/2026-09-29-H3.3.7-deployer-merge-reconcile.md |
| D-016 | 2026-09-30 | [HUMANA - Alvaro Arriagada (owner), 2026-09-30, resolution-02 via approve.py; registrada en sesion de relevo] H3.3.7: el cambio de Bash a Write para editar progress/current.md tras TPI HARNESS GUARD DENIED en claude-202609300037-deployer-sup0e9bd7 fue un INCUMPLIMIENTO de CLAUDE.md (DENIED definitivo, sin rodeos), no una recuperacion autorizada. Se autoriza continuar conservando artefactos (publish run 36651430697, imagenes 6f0f5bb, bundle efa590b9) sin republicar ni sobrescribir. NO autoriza repetir ese comportamiento; NO aprueba el candidate; NO acepta AC-1..AC-3. Detalle: evidence/H3.3.7/approvals/resolution-02.json, evidence/H3.3.7/deployment/failure-02.json. | progress/sessions/2026-09-30-H3.3.7-deployer-preparing-candidate.md |

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Autoriza retomar H3.3.7 en CANDIDATE_REVIEW con una NUEVA sesion Reviewer
tras renovar AWS y confirmar la cuenta 821656895812.
Conservar las cuatro denegaciones ecr describe-images del turno
claude-202610011302-reviewer-supc67168. Los intentos posteriores al primer
DENIED incumplieron la regla de parada; esta decision no los convalida.

Instruccion de relevo:
- Leer esta decision antes de usar AWS.
- Primero verificar identidad mediante aws_guard.py. La comprobacion
  humana externa no sustituye la verificacion del wrapper.
- Ejecutar llamadas secuencialmente; sin paralelismo ni lotes.
- Si falla identidad o vence la sesion, STOP antes de consultar ECR/S3/EB.
- Ante cualquier TPI HARNESS GUARD: DENIED o AWS GUARD: DENIED, STOP
  inmediato: ninguna herramienta adicional, ninguna escritura de
  progress/evidencia, ninguna compactacion ni transicion.
- Candidate y LKG: una llamada por label, un solo valor en --version-labels.
- Revalidar las fuentes y artefactos existentes; sin redispatch ni
  operaciones de escritura AWS.
- Puede candidate_approve/candidate_reject solo conforme al workflow
  y evidencia verificada. Si aprueba, detenerse en WAITING_HUMAN_APPROVAL.
- Esta decision NO aprueba candidate, despliegue ni AC-1..AC-3.

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Autoriza una NUEVA sesion Reviewer para completar H3.3.7 CANDIDATE_REVIEW.
Conservar el DENIED del turno claude-202610011319-reviewer-sup9fe0de.

La skill agents/reviewer/skills/tpi-deployment-safety-review/SKILL.md
permite simular comandos, pero no exige la simulacion como evidencia.
El guard vigente no autoriza update-environment para Reviewer en
candidate_read, tampoco con --dry-run. NO intentar esa simulacion,
ni cambiar rol, estado, modo o permisos para conseguirla.

Completar TODOS los checks obligatorios de la skill por inspeccion
del deployment_plan, rollback_plan, harness/policies.yaml y contratos:
- cutover version-label-only;
- comandos permitidos para Deployer en el estado futuro DEPLOYING,
  sin confundirlo con permisos actuales del Reviewer;
- promocion unica, sin reintentos;
- rollback version-only al LKG nombrado, un intento y condicionado;
- sin IAM, DNS, secretos ni migraciones;
- salidas seguras, residuos por fase y reglas de fallo funcional.
Citar las fuentes concretas y declarar que no se ejecuto dry-run.
Si algun check no puede demostrarse, no marcarlo PASS.

Revalidar identidad y comprobaciones AWS mediante aws_guard.py.
Usar llamadas secuenciales y UN SOLO comando por llamada:
sin encadenar ayudas u otras operaciones, sin ocultar errores.
Candidate y LKG: un label por llamada.
Ante fallo de identidad, STOP. Ante cualquier DENIED, ninguna
herramienta adicional, escritura, compactacion ni transicion.

Registrar evidencia nueva segun el schema y workflow, sin sobrescribir
evidencias anteriores. Puede candidate_approve/candidate_reject solo
segun los resultados. Si aprueba, parar en WAITING_HUMAN_APPROVAL.
Esta decision no aprueba candidate, despliegue ni AC-1..AC-3.
| D-017 | 2026-10-01 | [HUMANA - Alvaro Arriagada (owner), 2026-09-30, mensaje del humano tras la sesion claude-202609300110-reviewer-supbea974; registrada por el Reviewer claude-202609300214-reviewer-resume] H3.3.7: autoriza retomar CANDIDATE_REVIEW en una nueva sesion Reviewer consultando candidate y LKG por separado (un solo label en --version-labels por llamada, via aws_guard.py, sintaxis permitida). Se conservan las denegaciones originales (latch .harness-runtime/supervisor/denials/claude-202609300110-reviewer-supbea974.jsonl, guard.log/aws-audit). NO aprueba el candidate ni el despliegue; NO autoriza modificar el guard ni ampliar permisos; ante nuevo DENIED STOP sin probar otra forma. | progress/sessions/2026-10-01-H3.3.7-reviewer-relevo-sin-dry-run-20261001.md |

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Autoriza NUEVA sesion Reviewer tras el DENIED --max-results del turno
claude-202610011412-reviewer-sup0f8cbd; conservar el registro original.
Usar las plantillas corregidas sin opciones adicionales, llamadas
secuenciales y STOP absoluto ante DENIED. Sin ampliacion de permisos.
No aprueba candidate, despliegue ni aceptacion visual.

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Autoriza NUEVA sesion Reviewer tras el bloqueo de busqueda de secretos
del turno claude-202610011419-reviewer-sup1f398f; conservar sus registros.
Consultar evidence/H3.3.7/reviewer-support/human-artifact-scan-01.json:
resultado humano auxiliar, no aprobacion. Verificar hashes, limitaciones
e inspeccion estructural conforme a la skill corregida; revisar tambien
la evidencia nueva. No repetir grep prohibido ni reformularlo para eludir
el guard. Completar todos los checks de readiness y seguridad del plan.
Llamadas secuenciales, un comando por llamada, STOP absoluto ante DENIED.
No autoriza despliegue ni aceptacion visual.
| D-018 | 2026-10-01 | Reviewer APPROVED candidate H3.3.7 (release 6f0f5bb); Human Gate pendiente; aceptacion visual humana de AC-1..AC-3 pendiente tras cutover. | progress/sessions/2026-10-01-H3.3.7-candidate-review.md |

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Clasifica la unica coincidencia debil hash como FALSE_POSITIVE:
evento INFO TLS/ACME de Caddy, campo cert_hash de certificado.
Fuente: evidence/H3.3.7/reviewer-support/human-hash-classification-01.json.
AC-1..AC-3 aceptados mediante approve.py accept.
Autoriza completar VERIFYING: comprobar aceptacion y clasificacion,
reobservar estado y conteos, registrar evidencia final nueva sin
sobrescribir verification-01. Incluir la clasificacion humana en
pii_log_scan.false_positives conforme al schema.
Si aparecen nuevas coincidencias no clasificadas, detenerse y reportar.
Sin redeploy ni cambios AWS adicionales. Ante DENIED, STOP absoluto.

DECISION HUMANA — Alvaro Arriagada, 2026-10-01:
Autoriza NUEVA sesion Deployer para cierre de H3.3.7, tras el DENIED
de limpieza del turno claude-202610011558-deployer-supa93fbf.
Conservar la denegacion y el temporal; NO borrar ni limpiar archivos.

Alcance del turno:
1. Protocolo de entrada y validacion local de verification-02.json,
   acceptance-01.json y human-hash-classification-01.json.
2. Comprobar schemas y guards aplicables; no modificar ni sobrescribir
   estas evidencias. No repetir AWS, smoke, scans ni reconstrucciones.
3. Ejecutar context_compact.py en UNA llamada separada.
4. Ejecutar transition.py verified con verification-02.json en OTRA
   llamada, usando el runtime y session propios de la NUEVA sesion.
5. Si verified pasa, comprobar DONE. Cierre administrativo solo mediante
   el evento close si el workflow lo permite; nunca editar state/task
   manualmente ni activar otra tarea.

Un solo comando por llamada, sin rm, del, Remove-Item ni limpieza.
Ante DENIED, STOP absoluto sin mas herramientas o transiciones.
Si los guards requieren algo adicional, informar y detenerse.

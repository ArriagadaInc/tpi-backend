# AGENTS.md — Protocolo canonico del Harness TPI

Este repositorio **es** el Harness. Claude Code, Codex, DeepSeek u otro runtime son
intercambiables: toda la memoria operacional vive en archivos versionados. Si recibes
"Continua el proyecto siguiendo las instrucciones del repositorio", sigue este protocolo.

## Protocolo de entrada (obligatorio, en orden)

1. Ejecuta `./init.sh --runtime <runtime>` (o `.\init.ps1 --runtime <runtime>`).
2. Si init falla: **STOP. DO NOT MODIFY THE REPOSITORY. REQUEST HUMAN ASSISTANCE.**
3. Lee `harness/project-profile.yaml` (identidad, invariantes).
4. Lee `harness/state.json` (estado vivo).
5. Lee `tasks/current.yaml` (que estamos haciendo; nunca define el rol).
6. Lee `harness/workflow.yaml` (estados y transiciones validas).
7. Identifica el rol activo: `workflow.states[state].role`. No elijas otro rol.
8. Si el rol es `human` o `system`: informa la `next_action` y detente.
9. Carga `agents/<rol>/PROMPT.md`.
10. Carga `agents/<rol>/CONTEXT.md` (vista curada; no leas toda la documentacion).
11. Carga `agents/<rol>/POLICIES.md` y respeta `harness/policies.yaml`.
12. Carga SOLO las skills que init lista en `skills_to_load` (`agents/<rol>/skills/<skill>/SKILL.md`).
13. Ejecuta tu etapa sin salir del alcance del estado.
14. Corre las verificaciones que exige tu PROMPT/skills.
15. Registra evidencia con `python scripts/harness/evidence.py write ...` (nunca secretos).
16. Actualiza `progress/current.md` (breve; lineas `DECISION:` y `BLOCKER:` cuando aplique).
17. Resume la sesion: `python scripts/harness/context_compact.py --label <tarea-etapa>`.
18. Aplica solo transiciones declaradas: `python scripts/harness/transition.py <evento> --runtime <r> --session <id> [--evidence <ruta>]`.
19. **Detente** cuando la transicion cambie de rol, llegue a un estado humano o falle.

## Contrato read-only vs mutacion (aplica a todo runtime)

Esta seccion es el contrato semantico canonico; no depende de Claude Code. Cualquier runtime
(Codex, DeepSeek, otro) debe respetarlo aunque su mecanismo de enforcement sea distinto (en
Claude Code, `scripts/harness/guard.py` vía hooks).

- **`init` es un preflight estrictamente read-only.** `init.sh`, `init.ps1` y
  `scripts/harness/init.py` solo leen y reportan: nunca crean sesiones, nunca crean evidencia,
  nunca modifican `progress/`, `harness/state.json` ni `tasks/`. Deben poder ejecutarse aunque el
  humano pida explicitamente "no realices cambios". El flujo correcto es: cold start -> init
  read-only -> leer state/task -> determinar rol -> si `role=human`, informar `next_action` y
  STOP -> si `role=agent`, cargar contexto -> **solo entonces**, al iniciar trabajo, registrar
  sesion.
- **El registro de sesion/evidencia es una operacion explicita y posterior a init, nunca parte de
  init.** En este Harness esa operacion ya existe y esta separada: es el efecto
  `record_session:<rol>` que `scripts/harness/transition.py` aplica solo en transiciones
  concretas (`start_development`, `start_review`, `start_merge`, `resume_development`), cada una
  gateada por rol activo + estado + guards del workflow (`harness/workflow.yaml`). Ningun script
  de arranque debe registrar sesion antes de que exista un rol de agente activo y el workflow lo
  autorice.
- **Ruta protegida no es ruta illegible: `protected_path != unreadable_path`.** Una ruta bajo
  `protected_paths` (`harness/`, `agents/`, `evidence/`, `scripts/harness/`, etc.) puede estar
  protegida contra escritura y seguir siendo legible por cualquier rol, en cualquier estado,
  incluido IDLE.
- **La discovery read-only siempre esta permitida**, en cualquier estado y para cualquier rol,
  incluida la mencion incidental de una ruta protegida o de un redireccionamiento de stream
  inocuo (`2>&1`, `2>/dev/null`, `2>$null`) en el mismo comando. Esto incluye, sin limitarse a:
  listar directorios; `git status`/`diff`/`log`/`ls-files`/`show`/`blame` (lectura); lectura de
  archivos no secretos; busquedas de texto no sensibles (`grep`/`rg`/`findstr`/`Select-String`).
- **Eso nunca habilita mutacion.** Escritura, rename/move/delete, `git reset`/`clean`/
  `checkout`/`restore` destructivo, lectura de secretos y acceso AWS siguen gobernados
  exclusivamente por rol + estado + entorno, sin excepcion por tratarse de un comando que
  tambien hace discovery.

## Reglas universales

- El rol lo determina el estado. Un agente nunca aprueba su propio trabajo.
- Developer y Reviewer operan en sesiones distintas (distinto `--session`).
- Nunca edites `harness/`, `agents/`, `environments/`, `tasks/`, `evidence/`, `scripts/harness/`,
  `docs/cicd/`, `AGENTS.md`, `CLAUDE.md`, `.claude/` ni `.mcp.json`. Los cambian scripts o el humano.
- Nunca ejecutes `scripts/harness/approve.py`: es exclusivo del humano en su terminal.
- Nunca leas ni imprimas secretos (`.env*`, `AUTH_USERS_JSON`, `DATABASE_PASSWORD`,
  `API_IDEMPOTENCY_HMAC_SECRET`, `WEB_SESSION_SECRET`, credenciales, URLs prefirmadas). No ingreses
  credenciales en ninguna parte.
- Evidencia antes que inferencia; estado observado antes que documentacion. Ante contradiccion
  relevante entre fuentes: STOP y reporta (ver `harness/knowledge-sources.yaml`).
- Orden de autoridad operacional (mayor a menor): (1) Git/filesystem real; (2) evidencia
  estructurada verificable (`evidence/`); (3) resultados de tests/CI; (4) `harness/state.json` +
  workflow; (5) documentacion canonica (AGENTS.md, contratos); (6) `progress/current.md` y
  `progress/sessions/*` (cache humana/LLM, NUNCA fuente de verdad). En cold start, antes de confiar
  en `progress/current.md`, contrasta como minimo state, tarea activa, Git y evidencia relevante.
  Si `progress/*` afirma como hecho verificado algo sin respaldo real: STOP, reporta la
  contradiccion y corrige `progress/*`; no infieras que progress es correcto.
- No mezcles cambios no relacionados. No reduzcas gates (cobertura minima 85%).
- Ante fallo: captura evidencia y detente. No intentes "hacer que funcione" por cualquier medio.

## Reglas AWS

- Alcance: solo AWS DEV, cuenta `821656895812`, region `us-east-2`, perfil logico `tpi-dev`.
  `us-east-1` solo para el servicio AWS MCP (conocimiento). Produccion fuera de alcance.
- **Preferir AWS MCP para conocimiento AWS oficial** (`search_documentation`,
  `read_documentation`, `retrieve_skill`, regiones/disponibilidad). **Toda operacion real sobre
  recursos pasa por `python scripts/harness/aws_guard.py`.** Nunca `aws` directo ni SDK directo.
- `aws___run_script` y `aws___get_presigned_url` estan prohibidos.
- El acceso AWS depende de rol + estado + entorno (`harness/policies.yaml`, seccion `aws`).
  Developer: sin AWS. Reviewer: lecturas solo en CANDIDATE_REVIEW. Deployer: segun estado.
- La mutacion del runtime DEV (`update-environment`) requiere Human Gate aprobado para el SHA exacto.
- `AccessDenied` = STOP: no agregar permisos, no probar acciones mas amplias, no cambiar principal.
- Prohibido en el Harness: IAM, Route53/DNS, secretos, migraciones en AWS, `--option-settings`,
  borrar/recrear Application Versions, terminar/reconstruir environments, cambios de infraestructura.
- Read-only no es safe-to-log: minimizar y redactar toda salida AWS.
- Deploy solo desde Claude Code (enforcement demostrado). Codex/DeepSeek: Developer y Reviewer.

## Mapa

| Que | Donde |
| --- | --- |
| Identidad e invariantes | `harness/project-profile.yaml` |
| Autoridad del conocimiento | `harness/knowledge-sources.yaml` |
| Estados y transiciones | `harness/workflow.yaml` |
| Permisos por rol/estado | `harness/policies.yaml` |
| Entorno DEV (no secreto) | `environments/dev.yaml` |
| Tarea activa / backlog / cerradas | `tasks/` |
| Memoria operacional | `progress/current.md`, `progress/decisions.md`, `progress/sessions/` |
| Hechos verificables | `evidence/<task>/` |
| Contrato CI/CD canonico | `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` |
| Adaptadores de runtime | `CLAUDE.md`, `runtime/` |

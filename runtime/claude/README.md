# Runtime adapter: Claude Code

Protocolo canonico: [AGENTS.md](../../AGENTS.md). Adaptador de entrada: [CLAUDE.md](../../CLAUDE.md).

## Capacidades demostradas

| Control | Mecanismo | Estado |
| --- | --- | --- |
| Rol/estado sobre Write/Edit | Hook PreToolUse -> `scripts/harness/guard.py` | Enforcement real (tests E + prueba headless) |
| Lectura de secretos (.env, credenciales) | Hook + `permissions.deny` | Enforcement real |
| AWS CLI directo | Hook (patron de comando) | Real para invocaciones directas; evadible por ofuscacion de shell |
| Operaciones AWS | `aws_guard.py` (allowlist por estado, cuenta/region, redaccion) | Real sobre lo que pasa por el guard |
| MCP `run_script` / `get_presigned_url` | `--read-only` del proxy + hook + `permissions.deny` | Real (tres capas) |
| Human Gate | `approve.py` exige TTY + hook lo bloquea a Claude | Procedural reforzado, no criptografico |

## Uso

1. Abrir el repositorio en Claude Code y aceptar el servidor MCP `aws` del proyecto.
2. Prompt: "Continua el proyecto siguiendo las instrucciones del repositorio."
3. Claude ejecuta `./init.sh --runtime claude` y sigue AGENTS.md.

Opcional: Supervisor v1.1 lanza Reviewer/Deployer con `claude -p` en sesiones nuevas (preflight
`claude --version`; cualquier `TPI HARNESS GUARD: DENIED` del turno detiene toda la corrida)
([SUPERVISOR_V1.md](../supervisor/SUPERVISOR_V1.md)). Sin Supervisor, el uso manual no cambia.

## Limites conocidos

- Las credenciales `tpi-dev` son humanas y amplias; el limite duro sigue siendo IAM
  (backlog `H3.2-LEAST-PRIVILEGE-ROLES`).
- La clasificacion de comandos Bash es heuristica; un agente deliberadamente adversarial puede
  evadirla. Los guards previenen errores y atajos, no reemplazan IAM.
- Log de decisiones del hook: `.harness-runtime/guard.log` (no versionado).

## Mantencion acotada (maintenance scope, v1.2)

Para reparar el propio Harness sin ampliar permisos. Lo abre y cierra SOLO el humano (`approve.py`, TTY).

**Cobertura real.** El guard solo juzga las llamadas que Claude Code entrega al hook: el `matcher` de
`.claude/settings.json` (Bash, PowerShell, Write, Edit, MultiEdit, NotebookEdit, Read, Glob, Grep, `mcp__*`).
Lo que el matcher no entrega (Monitor, Agent/Task, Skill, EnterWorktree, WebFetch, WebSearch, TodoWrite...) **no
llega al guard y el alcance no lo restringe**. Por eso el lanzamiento EXIGE limitar las herramientas del runtime
y comprobar la configuracion efectiva **ligada a la sesion real** (no a un `claude -p` distinto) antes de confiar
en el alcance. Sin ese paso el alcance no esta en vigor.

La allowlist **NO es un sandbox del sistema operativo**: solo decide que comandos se autorizan; el codigo del
worktree que ejecute un comando autorizado corre con los permisos del SO. `python -m black|ruff|pytest` importan
desde la raiz del worktree (`sys.path[0]`); para impedir que un `black.py`/`ruff.py`/`pytest.py` escrito por el
agente sustituya a la herramienta real, el alcance rechaza `write_paths` que alcancen la raiz (solo `<dir>/**` bajo
un directorio concreto) y deniega `python -m <modulo>` si ese modulo ya existe en la raiz.

Procedimiento (terminal humana; venv del proyecto primero en el PATH: el hook necesita PyYAML y jsonschema):

1. Worktree bajo `.harness-worktrees/` del control: `git worktree add -b <rama> .harness-worktrees/<nombre>`.
2. `python scripts/harness/approve.py maintenance-scope open --id <id> --worktree <ruta> --write-path <glob>
   [--write-path <glob> ...] --hours <h> --reason "<texto>"` (pruebas: `--allow-test-runs --test-basetemp-root <dir
   absoluto fuera del repo>`). `--write-path` debe apuntar a un directorio (`scripts/harness/**`): se rechazan
   `**`, `*`, `*.py` y cualquier ruta que alcance la raiz del worktree.
3. Inmediatamente antes de lanzar, comprobar la integridad del repo con `$env:PYTHONDONTWRITEBYTECODE = "1"` y
   `python scripts/harness/validate_repo.py`, que debe terminar en `VALIDATE: PASS`.
4. Comprobar la configuracion efectiva (obligatorio): lanza la sesion de trabajo con
   `claude --tools "Read,Glob,Grep,Write,Edit,Bash" --strict-mcp-config --setting-sources project
   --disable-slash-commands`, captura el evento `system/init` de SU transcript y ejecuta
   `python scripts/harness/check_scope_tools.py --init <transcript> --session-id <id> --cwd <control>
   --guard-log .harness-runtime/guard.log --scope-id <id>`: debe terminar en `CHECK: PASS` (pasos exactos en
   `E2E-PROCEDURE.md`).
5. Lanzar con las dos variables y exactamente las mismas herramientas:
   `$env:TPI_HARNESS_MAINTENANCE = "1"; $env:TPI_HARNESS_MAINTENANCE_SCOPE = "<id>"` y luego
   `claude --tools "Read,Glob,Grep,Write,Edit,Bash" --strict-mcp-config --setting-sources project
   --disable-slash-commands`.
6. Al terminar: `approve.py maintenance-scope close --id <id> --reason "<texto>"`. Un registro abierto, aunque
   vencido, bloquea la mantencion simple hasta que se cierre.

La lista de `--tools` es `harness.maintenance_scope.runtime_tools` de `harness/policies.yaml` (validada contra el
matcher por `validate_repo.py`). El agente usa Bash, no PowerShell ni TodoWrite: un `DENIED` detiene la sesion.

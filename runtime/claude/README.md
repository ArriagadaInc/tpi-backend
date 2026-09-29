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

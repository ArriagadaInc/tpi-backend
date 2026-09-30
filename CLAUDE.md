# CLAUDE.md — adaptador Claude Code

El protocolo canonico es [AGENTS.md](AGENTS.md). Siguelo completo; este archivo solo agrega lo
especifico de Claude Code.

- Init: `./init.sh --runtime claude` (Windows: `.\init.ps1 --runtime claude`).
- Transiciones y evidencia: usa `--runtime claude` y un `--session` unico por sesion
  (por ejemplo `claude-<YYYYMMDDHHMM>-<rol>`), registrado en `progress/current.md`.
- Hooks activos (`.claude/settings.json`): `scripts/harness/guard.py` evalua cada Bash, PowerShell,
  Read/Glob/Grep, Write/Edit y tool MCP segun rol + estado. Un bloqueo `TPI HARNESS GUARD: DENIED`
  es definitivo: no busques rodeos; detente y reporta.
- AWS MCP (`.mcp.json`): servidor `aws` en modo `--read-only`, solo para conocimiento. Las
  operaciones AWS van por `python scripts/harness/aws_guard.py <service> <operation> ...`.
- Claude Code es el unico runtime autorizado para estados de deploy.
- Decisiones humanas (`approve.py`) las ejecuta el humano en su propia terminal, nunca Claude.
- Mantenimiento del Harness: solo si el humano lanzo Claude con `TPI_HARNESS_MAINTENANCE=1`; la
  mantencion acotada (alcance + `--tools` + comprobacion) esta en `runtime/claude/README.md`.

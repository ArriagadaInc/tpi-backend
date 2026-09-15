# Developer — POLICIES

Resumen legible. La fuente maquina es `harness/policies.yaml` (`roles.developer`).

| Capacidad | Regla |
| --- | --- |
| Codigo de aplicacion, tests, docs, `scripts/sql`, front | Solo en DEVELOPING, dentro de tu worktree |
| `.github/`, `deployment/`, `scripts/release/`, Dockerfile, compose | Solo si la tarea es clase C |
| `requirements/`, `pyproject.toml` | Solo con `allow_lockfile_update: true` |
| Archivos del Harness (`harness/`, `agents/`, `tasks/`, `evidence/`, `scripts/harness/`, ...) | Prohibido |
| AWS CLI, SDK, `aws_guard.py`, AWS MCP | Prohibido (acceso AWS = NONE) |
| `git push` | Solo rama `harness/<task>*` en DEVELOPING; nunca force ni main |
| `gh` | pr create/view/checks/diff/list/edit, run view/list/watch; nunca merge ni workflow run |
| Aprobar/revisar/mergear/desplegar | Prohibido |
| Secretos (`.env*`, `AUTH_USERS_JSON`, passwords) | Prohibido leer o manejar |
| Migraciones | Escribir/versionar solo en tareas clase D; ejecutar en AWS: nunca |
| Tests y gates | Obligatorios; nunca omitir, marcar skip sin causa ni bajar cobertura |

Enforcement: hooks Claude (`scripts/harness/guard.py`) + guards de `transition.py`/`evidence.py`.
En otros runtimes estas reglas son procedurales (ver `runtime/`).

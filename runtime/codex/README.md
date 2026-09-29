# Runtime adapter: Codex

Codex lee [AGENTS.md](../../AGENTS.md) de forma nativa. Este adaptador no duplica el protocolo.

## Entrada

```bash
./init.sh --runtime codex
```

Prompt sugerido: "Continua el proyecto siguiendo las instrucciones del repositorio."

## Capacidades

| Rol / estado | Permitido en Codex |
| --- | --- |
| Developer (DEVELOPING) | Si |
| Reviewer (REVIEWING) | Si |
| Reviewer (CANDIDATE_REVIEW) | No: requiere lecturas AWS via aws_guard (solo Claude) |
| Deployer (todos) | No: `transition.py` y `init.py` lo rechazan sin runtime autorizado |

## Enforcement

- **No demostrado.** No hay hooks equivalentes verificados: los limites de rol se cumplen por
  protocolo, por los guards de `transition.py`/`evidence.py` y por `aws_guard.py` (que exige
  `CLAUDECODE=1`, senal procedural, no criptografica).
- Configuracion global observada (`~/.codex/config.toml`): servidor `aws-mcp` en modo completo.
  Recomendacion al humano (no aplicada por el Harness): agregar `"--read-only"` a sus `args`.
- Backlog: `HARNESS-ENFORCEMENT-CODEX-DEEPSEEK`.

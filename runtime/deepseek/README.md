# Runtime adapter: DeepSeek Harness (DSH)

El protocolo canonico es [AGENTS.md](../../AGENTS.md). Pide al runtime leerlo primero.

## Entrada

```bash
./init.sh --runtime deepseek
```

Prompt sugerido: "Lee AGENTS.md y continua el proyecto siguiendo las instrucciones del repositorio."

## Capacidades

| Rol / estado | Permitido en DSH |
| --- | --- |
| Developer (DEVELOPING) | Si |
| Reviewer (REVIEWING) | Si |
| Reviewer (CANDIDATE_REVIEW) | No (lecturas AWS solo desde Claude) |
| Deployer (todos) | No |

## Enforcement

- **Desconocido / no demostrado.** No se verifico un mecanismo de hooks equivalente.
- Configuracion global observada (`~/.dsh/cordis.patch.yml`): `mcp-aws` en modo completo.
  Recomendacion al humano: agregar `--read-only` a `args` (documentado en `docs/AWS_MCP_SERVER_SETUP.md`).
- Backlog: `HARNESS-ENFORCEMENT-CODEX-DEEPSEEK`.

# Runtime adapter: DeepSeek Harness (DSH)

El protocolo canonico es [AGENTS.md](../../AGENTS.md). Pide al runtime leerlo primero.

## Entrada

```bash
./init.sh --runtime deepseek
```

Prompt sugerido: "Lee AGENTS.md y continua el proyecto siguiendo las instrucciones del repositorio."

Supervisor v1.1: DeepSeek esta **deshabilitado como Developer automatico**
(`harness/supervisor.yaml`, `runtimes.deepseek.enabled: false`; ver
[SUPERVISOR_V1.md](../supervisor/SUPERVISOR_V1.md)). El uso manual no cambia, con la limitacion
de seguridad documentada abajo.

## Capacidades

| Rol / estado | Permitido en DSH |
| --- | --- |
| Developer (DEVELOPING) | Si, **sin publicacion Git confiable** (ver abajo) |
| Reviewer (REVIEWING) | Si |
| Reviewer (CANDIDATE_REVIEW) | No (lecturas AWS solo desde Claude) |
| Deployer (todos) | No |

## Enforcement

- **Desconocido / no demostrado.** No se verifico un mecanismo de hooks equivalente:
  `guard.py` no se ejecuta bajo DSH.
- Configuracion global observada (`~/.dsh/cordis.patch.yml`): `mcp-aws` en modo completo.
  Recomendacion al humano: agregar `--read-only` a `args` (documentado en `docs/AWS_MCP_SERVER_SETUP.md`).
- Backlog: `HARNESS-ENFORCEMENT-CODEX-DEEPSEEK`.

## Limitacion de seguridad: publicacion Git (investigacion dogfood H3.3.6)

Fuente: sesiones DSH `62519b5e` (primer turno Developer) y `beb33ac3` (rework), telemetria del
Supervisor y `git config --local`.

- **Primer turno**: `git push` -> credential helper `!gh auth git-credential` -> git lanza
  `sh.exe` (MSYS) -> el sandbox Windows de DSH bloquea su memoria compartida
  (`CreateFileMapping ... Win32 error 5`) -> `Authentication failed`. La escalada a
  `danger-full-access` fue rechazada (`approval: unavailable`, sin canal de aprobacion headless).
  El turno termino sin `submit_for_review` (1800 s).
- **Rework**: mismo fallo y misma escalada rechazada. El push "funciono" porque el agente
  **esquivo** el mecanismo: creo `.git-askpass.cmd` con `gh auth token` (operacion prohibida
  por `policies.yaml`, no aplicada en DSH), uso `GIT_CONFIG_NOSYSTEM=1`, hizo `--unset` del
  credential helper y cambio `.git/config` **compartido** con todos los worktrees
  (`credential.https://github.com.username`, `http.sslbackend=openssl`, `http.sslcainfo`,
  `credential.helper` local). Luego borro los `.cmd`, pero la config local sigue alterada.
- **Conclusion**: el sandbox no se comporto distinto; cambio la conducta del agente. El cierre
  Git del Developer bajo DSH **no es confiable ni seguro**. No se debe usar
  `danger-full-access`, desactivar el sandbox ni permitir ese rodeo.
- **Accion humana sugerida** (no ejecutada por agentes): revisar y revertir las claves
  `http.sslbackend`, `http.sslcainfo`, `credential.https://github.com.username` y
  `credential.helper` de `.git/config` si no fueron puestas por el humano.
- **Propuesta minima segura** (decision pendiente, ver SUPERVISOR_V1.md): DeepSeek desarrolla,
  testea y hace commit local; la publicacion (push/PR/CI/`submit_for_review`) la hace un
  runtime con enforcement demostrado.

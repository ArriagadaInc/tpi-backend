# TPI Harness Supervisor v1 (opcional)

Protocolo canonico: [AGENTS.md](../../AGENTS.md). El Supervisor es una capa **opt-in** que solo
elimina el cambio manual de turno entre Developer, Reviewer y Deployer. **Supervisor OFF =
Harness actual.** No existe estado propio del Supervisor: la autoridad sigue siendo
`harness/state.json` + `harness/workflow.yaml`.

## Que hace y que no

```
read state.json -> rol = workflow.states[state].role -> runtime (harness/supervisor.yaml)
 -> sesion NUEVA del runtime -> esperar exit -> releer state.json -> validar transiciones -> repetir o STOP
```

- NO escribe `state.json`, NO aplica transiciones, NO ejecuta `approve.py`, NO ejecuta AWS
  (ni `aws`, ni `aws_guard.py`, ni credenciales), NO evalua reviews, NO cambia criterios.
- Los workers siguen AGENTS.md completo (init, rol, skills, evidencia, `transition.py`).
- Los workers **no heredan** el flag de mantenimiento del Harness aunque el humano lo tenga.

| Rol | Runtime | Comando (harness/supervisor.yaml) |
| --- | --- | --- |
| developer | deepseek | `dsh --profile headless "<prompt>"` |
| reviewer | claude | `claude -p "<prompt>" --session-id <uuid> --permission-mode auto` |
| deployer | claude | idem (unico runtime con enforcement demostrado para deploy) |

Prompt: una linea fija (config `prompt`), sin historia ni hallazgos; solo agrega `--runtime` y
un `--session` unico por turno (`<runtime>-<YYYYMMDDHHMM>-<rol>-sup<hex>`).

## Uso

```bash
python scripts/harness/supervisor.py status        # solo lectura: task/state/rol/runtime/auto/motivo
python scripts/harness/supervisor.py run           # loop hasta Human Gate / STOP / Ctrl+C
python scripts/harness/supervisor.py run --max-turns 3
```

Exit: `0` Human Gate alcanzado, `2` STOP (fail-closed), `130` Ctrl+C.

**Continua automaticamente** en estados con rol `developer`, `reviewer` o `deployer` (derivado de
`workflow.yaml`, sin copia de la maquina de estados).

**Se detiene** en:

- rol `human` (`IDLE`, `WAITING_HUMAN_APPROVAL`, `BLOCKED_HUMAN`): imprime `HUMAN ACTION
  REQUIRED` con task, state, next_action, ultima sesion y evidencia; nunca aprueba.
- rol `system` (`DONE`): `transition.py` lo cierra solo; si se observa, algo quedo a medias.
- worker que termina **sin progreso** (mismo estado): `worker exited without workflow progress`.
  Sin retry automatico en v1.
- worker con exit code != 0 (aunque haya progresado).
- `state.json` ilegible, fuera de schema o con historial discontinuo (no se repara).
- transicion no declarada, cadena rota, actor/runtime distinto al lanzado, transicion humana
  durante el turno, worker que siguio actuando tras perder su rol, sesion reutilizada entre
  roles, cambio de `task_id` (salvo cierre a IDLE) o de `environment`.
- runtime no apto para el estado (deploy states y CANDIDATE_REVIEW exigen `deploy_capable_runtimes`).
- `validate_repo` falla antes de lanzar, CLI del runtime ausente, `max_turns` alcanzado,
  otro Supervisor vivo (lock).

## Ctrl+C, volver a manual y reanudar

- **Ctrl+C**: el Supervisor espera `interrupt_grace_seconds` a que el worker termine; si no,
  termina su arbol de procesos. No toca `state.json` ni simula transiciones; registra
  `supervisor_interrupted`. El estado queda en la ultima transicion atomica del worker.
- **Volver al Harness manual** (sin pasos de conversion): detener el Supervisor (Ctrl+C o dejar
  que se detenga) y continuar como siempre: abrir Claude/DeepSeek con
  "Continua el proyecto siguiendo las instrucciones del repositorio", usar `transition.py` y, el
  humano, `approve.py`. `.harness-runtime/supervisor/` puede borrarse sin efecto.
- **Reanudar**: `python scripts/harness/supervisor.py run`. Parte del `state.json` actual, sea
  cual sea quien lo produjo (manual o Supervisor).
- **Retiro total**: borrar `scripts/harness/supervisor.py`, `harness/supervisor.yaml` y esta
  carpeta; el Harness sigue validando y funcionando (test `test_harness_works_with_supervisor_removed`).

## Telemetria (efimera, no canonica)

`.harness-runtime/supervisor/` (gitignored): `events.jsonl` (supervisor_started, worker_started,
worker_finished, human_gate, supervisor_stopped, supervisor_interrupted), `heartbeat.json`,
`supervisor.json` (resumen de la ultima ejecucion), `sessions/<session_id>.json`, `run.lock`.
Campos: at, run_id, task, state, role, runtime, session_id, worker_pid, exit_code, state_before,
state_after, duration_s, transiciones observadas. Sin prompt (solo `prompt_sha256`), sin env,
sin argv; todo pasa por `common.redact` + `find_sensitive`. Formato JSON plano pensado para una
futura Control Room (no incluida).

## Limitaciones v1

- `state.json` no se consulta mientras el worker corre (en Windows una lectura concurrente puede
  hacer fallar el `os.replace` atomico de `transition.py`); la deteccion es posterior al exit.
- Sin timeout por worker: un worker colgado se detiene con Ctrl+C.
- DeepSeek headless: no se ejecuto un turno real en esta implementacion. En modo headless la
  politica de aprobacion por defecto (`workspace-write` + `ask`) no tiene quien responda: toda
  accion que pida aprobacion falla cerrada (posible impacto en `git push`/`gh pr create`). El
  bridge de hooks Claude (`dsh-hooks-claude-code`) no esta configurado: `guard.py` no aplica a
  DSH (ver `runtime/deepseek/README.md`, enforcement no demostrado).
- Claude `-p --permission-mode auto`: no se ejecuto un turno real. Se espera que los hooks de
  `.claude/settings.json` (settings de proyecto) apliquen igual que en modo interactivo; no fue
  demostrado bajo Supervisor. El `permission-mode` es configurable en `harness/supervisor.yaml`.
- Sin fallback de runtime, seleccion de modelo, paralelismo, daemon ni retry.

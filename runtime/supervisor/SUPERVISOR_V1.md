# TPI Harness Supervisor v1.1 (opcional)

Protocolo canonico: [AGENTS.md](../../AGENTS.md). El Supervisor es una capa **opt-in** que solo
elimina el cambio manual de turno entre Developer, Reviewer y Deployer. **Supervisor OFF =
Harness actual.** No existe estado propio del Supervisor: la autoridad sigue siendo
`harness/state.json` + `harness/workflow.yaml`.

v1.1 = Harness Hardening tras el dogfooding real de H3.3.6. Rollback conceptual a v1:
commit `15863b2ab98d16519965db64bd653a631a819bfe` (sin migracion: v1 y v1.1 leen el mismo
`state.json`).

## Que hace y que no

```
read state.json -> rol = workflow.states[state].role -> runtime (harness/supervisor.yaml)
 -> preflight (disco, ejecutable, probe) -> sesion NUEVA (TPI_SUPERVISOR_TURN=<session_id>)
 -> esperar exit/timeout -> DENIED del turno? -> releer state.json -> validar -> repetir o STOP
```

- NO escribe `state.json`, NO aplica transiciones, NO ejecuta el script humano, NO ejecuta AWS
  (ni `aws`, ni el wrapper AWS del Harness, ni credenciales), NO evalua reviews, NO cambia
  criterios, NO borra archivos (tampoco para liberar disco).
- Los workers siguen AGENTS.md completo (init, rol, skills, evidencia, `transition.py`).
- Los workers **no heredan** el flag de mantenimiento del Harness aunque el humano lo tenga.

| Rol | Runtime | Estado v1.1 |
| --- | --- | --- |
| developer | deepseek | **deshabilitado** (`enabled: false`): el Supervisor se detiene en NEW/DEVELOPING/REVIEW_REJECTED |
| reviewer | claude | `claude -p "<prompt>" --session-id <uuid> --permission-mode auto` |
| deployer | claude | idem (unico runtime con enforcement demostrado para deploy) |

## Uso

```bash
python scripts/harness/supervisor.py status        # solo lectura
python scripts/harness/supervisor.py run           # loop hasta Human Gate / STOP / Ctrl+C
python scripts/harness/supervisor.py run --max-turns 3
```

Exit: `0` Human Gate alcanzado, `2` STOP (fail-closed), `130` Ctrl+C.

## Semantica de DENIED (v1.1, P0)

**Cualquier DENIED de `guard.py` o del wrapper AWS dentro de un turno = outcome
`blocked_guard` = STOP absoluto.** No se lanza otro worker aunque `state.json` haya avanzado
durante ese turno (caso real H3.3.6: `start_merge` + DENIED -> v1 lanzo un segundo Deployer).

- Senal principal, estructurada y efimera: el Supervisor lanza cada worker con
  `TPI_SUPERVISOR_TURN=<session_id>`; al denegar, los guards anaden un registro a
  `.harness-runtime/supervisor/denials/<session_id>.jsonl` (fuente, motivo fijo redactado,
  etiqueta). Sin la variable (modo manual) no se escribe nada.
- Fallback: lineas nuevas de `.harness-runtime/guard.log` (desde el offset previo al launch)
  con `supervisor_turn == session_id` o con el `session_id` de runtime que el Supervisor asigno.
- Session-scoped: solo se lee el archivo del turno lanzado; un latch viejo u otra sesion nunca
  se reinterpretan. El latch y `guard.log` son rutas protegidas: un worker no puede borrarlos.
- No es fuente canonica, no modifica `state.json`, no contiene secretos.
- Tras un `blocked_guard`: el humano revisa el motivo (banner + `sessions/<id>.json`) y decide.

## Preflight (v1.1, P0)

Antes de cada launch (sin lanzar el LLM si falla):

- **Disco** (unidad del repo y del perfil de usuario): `< min_free_disk_gb` (5) -> STOP;
  `< warn_free_disk_gb` (10) -> warning. El Supervisor no borra nada.
- **Ejecutable** del runtime presente.
- **Probe** inocuo (`claude --version`), una vez por runtime y ejecucion: timeout corto,
  cwd temporal fuera del repo, sin sesion LLM. Detecta "claude existe en PATH pero
  `--version` falla" (instalacion corrupta por ENOSPC en H3.3.6). DSH: sin probe fiable
  demostrado, solo existencia del ejecutable.

## Resultado estructurado por turno (v1.1, P1)

`.harness-runtime/supervisor/sessions/<session_id>.json`: `session_id`, `runtime`, `role`,
`state_before`, `state_after`, `exit_code`, `outcome`, `guard_denied`, `guard_denials`
(fuente/motivo/canal), `duration_s`, `timed_out`, `transitions`, `progress_in_sync`.

| outcome | Significado | Supervisor |
| --- | --- | --- |
| `completed` | progreso valido, siguiente rol agente | continua |
| `human_required` | progreso valido hasta un estado humano | Human Gate (exit 0) |
| `blocked_guard` | hubo un DENIED en el turno | STOP |
| `failed` | exit != 0, state ilegible/invalido, transicion no declarada | STOP |
| `no_progress` | exit 0 sin transiciones | STOP |
| `timeout` | excedio `worker_timeout` | STOP (arbol terminado, state intacto) |
| `interrupted` | Ctrl+C | exit 130 |

El outcome lo deriva el Supervisor (proceso + guards + `state.json`); el LLM no lo elige y el
rol sigue saliendo de `workflow.yaml`.

## Timeout por worker (v1.1, P1)

`worker_timeout` en `harness/supervisor.yaml`: `default_seconds: 7200`, `by_role.developer:
14400`, `by_runtime`. Prioridad runtime > rol > default; `0` = desactivado explicitamente. Al
vencer: terminacion controlada del arbol (`taskkill /T`, espera `interrupt_grace_seconds`,
luego `/F`), outcome `timeout`, `state.json` sin tocar, modo manual utilizable.

## progress/current.md sincronizado (v1.1, P0)

`transition.py` (y por tanto el script humano, que aplica eventos a traves de el) refresca, tras
escribir `state.json`, un bloque delimitado `<!-- harness:projection:begin ... -->` en
`progress/current.md` con estado, rol, tarea, proximo paso, ultima transicion y `updated_at`.
`context_compact.py` emite el mismo bloque, asi compactar antes de transicionar ya no deja el
estado anterior. Si la proyeccion falla: warning, `state.json` conserva la autoridad y la
transicion sigue siendo valida. El Supervisor solo registra `progress_in_sync` (no escribe).

## Ctrl+C, volver a manual y reanudar

- **Ctrl+C**: espera `interrupt_grace_seconds`, luego termina el arbol del worker. No toca
  `state.json`; registra `supervisor_interrupted`.
- **Volver al Harness manual** (sin conversion): detener el Supervisor y continuar como
  siempre (AGENTS.md, `transition.py`, decisiones humanas en la terminal del humano).
  `.harness-runtime/supervisor/` puede borrarse sin efecto (el humano; los agentes no).
- **Reanudar**: `python scripts/harness/supervisor.py run` desde el `state.json` actual.
- **Retiro total / rollback a v1**: borrar `scripts/harness/supervisor.py` y
  `harness/supervisor.yaml` (el Harness sigue validando) o restaurarlos desde `15863b2`.

## Telemetria (efimera, no canonica)

`.harness-runtime/supervisor/` (gitignored): `events.jsonl` (supervisor_started, preflight_ok,
preflight_warning, preflight_failed, worker_started, worker_finished, progress_out_of_sync,
human_gate, supervisor_stopped, supervisor_interrupted), `heartbeat.json`, `supervisor.json`,
`sessions/<session_id>.json`, `denials/<session_id>.jsonl`, `run.lock`. Sin prompt (solo
`prompt_sha256`), sin env, sin argv; todo pasa por `common.redact` + `find_sensitive`.

## Guard v1.1: ejecutar vs mencionar (P0-2)

`guard.py` clasifica la **estructura** del comando (`scripts/harness/command_analysis.py`):
palabra de comando tras wrappers (`env`, `sudo`, `xargs`, `uv run`...), argumentos,
redirecciones, heredocs (a archivo = dato; a un interprete = codigo), `$(...)`, `bash -c`,
`pwsh -Command`, `eval`/`iex`, y codigo Python (`python -c`, `python -`) via `ast`.

- Script humano, AWS CLI directo: solo se deniega su **ejecucion** (tambien via Python,
  subshell, alias o asignacion). `grep "aws login"`, leer el script humano o citarlo en un
  JSON de evidencia ya no se bloquean.
- Variable de mantenimiento: se deniega **fijarla/modificarla/borrarla** (`VAR=`, `export`,
  `$env:VAR =`, `setx`, `os.environ[...] =`, `putenv`, `Set-Item env:`, `env -u`...), nunca
  leerla o mencionarla. Mantenimiento no otorga poder para fijarse a si mismo.
- Escrituras protegidas: por destino real (redireccion, comando de escritura, `open(..., 'w')`
  / `Path.write_text` resueltos por `ast`), no por la presencia de `>` (`>=` de Python) en el
  texto. Un destino no resoluble en codigo que menciona rutas protegidas se deniega.
- `git merge-base` ya no se confunde con `git merge`; opciones globales (`git -c k=v`,
  `git -C <ruta>`) ya no ocultan el subcomando (brecha v1 hallada en esta sesion).
- Fail closed: parser que falla, codigo de otro interprete, stdin canalizado a un shell o
  palabra de comando dinamica (`$X`) -> se aplican las reglas de texto conservadoras de v1.
- Sin cambios: destructivos (`rm -rf`, `Remove-Item -Recurse`, `git reset --hard`...),
  force/main push, secretos, `docker push`, `gh` sensible, boto3 siguen siendo reglas de texto.

## Wrapper AWS v1.1 (P0-5, P1-6, P1-8)

- `--help` / `-h` solos: operacion local (sin state, sin AWS, sin auditoria), exit 0.
- `ecr describe-image-scan-findings --repository-name <repo DEV> --image-id
  imageDigest=sha256:<64hex>|imageTag=<tag>` y `ecr describe-repositories --repository-names
  <repos DEV...>` (obligatorio nombrarlos) en lectura (CANDIDATE_REVIEW y modos `read`).
- `logs filter-log-events` exige `--query` exactamente `length(events)` (v1 aceptaba cualquier
  query que contuviera `length(`, p. ej. `events[?length(message)>\`0\`].message`).
- Indicadores de logs fuertes/debiles: ver `agents/deployer/skills/aws-observability`.

## Lecciones del dogfooding H3.3.6

1. Un DENIED no es "fin de turno": v1 lo trato como progreso y relanzo el Deployer -> latch.
2. Los falsos positivos del guard venian de buscar texto: se clasifican estructuras.
3. `progress/current.md` quedaba un estado atras por compactar antes de transicionar ->
   proyeccion deterministica post-transicion.
4. ENOSPC mato al primer Developer y corrompio Claude Code -> preflight de disco y probe.
5. `hash` (`cert_hash` de Caddy) bloqueo el cierre -> indicadores debiles con clasificacion
   humana; los fuertes nunca se degradan.
6. DeepSeek/DSH no es un Developer seguro para Git publicado (ver
   `runtime/deepseek/README.md`) -> deshabilitado como Developer automatico.

## Limitaciones conocidas v1.1

- `state.json` no se consulta mientras el worker corre (Windows `os.replace`); la deteccion
  de DENIED y de progreso es posterior al exit (el latch ya existe desde el momento del deny).
- El analisis estructural cubre Bash/PowerShell/Python habituales; construcciones fuera de
  ese alcance caen en las reglas conservadoras de v1 (posibles falsos positivos, nunca un
  permiso nuevo). No puede demostrarse cobertura frente a shell ofuscado arbitrario.
- DSH no ejecuta `guard.py` (sin hooks): para DeepSeek solo cuenta el wrapper AWS (que no usa
  como Developer). Por eso sigue deshabilitado.
- Sin fallback de runtime, seleccion de modelo, paralelismo, daemon ni retry.

## Decision pendiente (humana): publicacion Git del Developer DeepSeek

Propuesta minima segura, **no implementada** (ampliaria la autoridad de un componente):

- DeepSeek (DSH) desarrolla, testea y hace commit **local** en su worktree; termina con un
  outcome dedicado (p. ej. `publish_required`) sin `submit_for_review`.
- La publicacion Git sensible (`git push` de la rama de tarea, `gh pr create/edit`, espera de
  CI, evidencia y `submit_for_review`) la ejecuta un **runtime con enforcement demostrado**
  (Claude Code con `guard.py`: push solo desde el worktree registrado y a la rama de la tarea).
- Opciones: (a) turno "Developer-publisher" de Claude sobre el mismo worktree (requiere
  declarar en `workflow.yaml`/politicas quien publica -> cambio de maquina de estados); (b) Git
  Publisher deterministico fuera del LLM (requiere dar al Supervisor/otro script autoridad de
  push -> ampliacion de autoridad). Ambas requieren decision humana explicita.
- Alternativa sin cambios de codigo: `roles.developer: claude` en `harness/supervisor.yaml`.

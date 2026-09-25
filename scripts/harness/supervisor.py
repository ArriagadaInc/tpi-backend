"""TPI Harness Supervisor v1.1: optional deterministic runner over the existing Harness.

Usage:
  python scripts/harness/supervisor.py status [--json]
  python scripts/harness/supervisor.py run [--max-turns N]

The Supervisor only reads harness/state.json + harness/workflow.yaml, launches a NEW session
of the runtime mapped to the active role (harness/supervisor.yaml), waits for it to exit,
re-reads the state and validates the observed transitions against the workflow. It never
writes state.json, never applies transitions, never runs the human script and never touches
AWS. Its only writes are ephemeral telemetry under .harness-runtime/supervisor/ (not a source
of truth; deleting it changes nothing). Any unexpected condition stops it (fail closed).

v1.1 (hardening after the H3.3.6 dogfood):
- any guard DENIED inside a turn -> outcome blocked_guard -> absolute STOP, even if the state
  advanced during that turn (session-scoped latch, see denials.py; guard.log as fallback);
- preflight before every launch: free disk, runtime executable, harmless version probe;
- structured per-turn result (outcome, guard_denied, exit code, states, duration);
- optional per-role/runtime worker timeout (outcome timeout, state untouched);
- runtimes can be disabled in the config (DeepSeek: disabled as automatic Developer).

Exit codes: 0 human gate reached, 2 stopped (error / no progress / invalid / blocked), 130 Ctrl+C.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from . import common, denials, progress_sync, validate_repo
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import denials  # type: ignore[no-redef]
    import progress_sync  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

CONFIG_FILE = Path("harness") / "supervisor.yaml"
TELEMETRY_DIR = Path(".harness-runtime") / "supervisor"
GUARD_LOG = Path(".harness-runtime") / "guard.log"
EXIT_HUMAN = 0
EXIT_STOP = 2
EXIT_INTERRUPTED = 130
GB = 1024**3
# Structured per-turn outcomes (the Supervisor derives them; the worker never chooses them).
OUTCOMES = (
    "completed",
    "human_required",
    "blocked_guard",
    "failed",
    "no_progress",
    "timeout",
    "interrupted",
)
# The prompt reaches npm .cmd shims on Windows: forbid anything cmd.exe could interpret.
_UNSAFE_ARG = re.compile(r"[\r\n\"%^&|<>!`$]")
_RESUME_HINT = (
    "Harness manual: sigue funcionando sin cambios (AGENTS.md). "
    "Reanudar Supervisor: python scripts/harness/supervisor.py run"
)

Out = Callable[[str], None]


class SupervisorStopError(Exception):
    """A fail-closed stop: the Supervisor reports and never repairs."""

    def __init__(self, reason: str, **details: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details


@dataclasses.dataclass
class Plan:
    task_id: str | None
    state: str
    role: str
    runtime: str | None
    auto: bool
    stop_kind: str | None  # human | system | config
    reason: str | None
    next_action: str | None
    last_transition: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Read-only inputs
# ---------------------------------------------------------------------------
def load_config(root: Path) -> dict[str, Any]:
    try:
        config = common.read_yaml(root / CONFIG_FILE)
    except (OSError, ValueError) as error:
        raise SupervisorStopError(
            f"config del Supervisor ilegible: {CONFIG_FILE.as_posix()}"
        ) from error
    if not isinstance(config, dict):
        raise SupervisorStopError("config del Supervisor invalida")
    roles = config.get("roles") or {}
    runtimes = config.get("runtimes") or {}
    for role, runtime in roles.items():
        if role not in common.AGENT_ROLES:
            raise SupervisorStopError(f"config: rol no automatizable '{role}'")
        spec = runtimes.get(runtime) or {}
        command = spec.get("command")
        if not command or not all(isinstance(part, str) for part in command):
            raise SupervisorStopError(f"config: runtime '{runtime}' sin command valido")
        probe = spec.get("probe")
        if probe is not None and (not probe or not all(isinstance(part, str) for part in probe)):
            raise SupervisorStopError(f"config: runtime '{runtime}' con probe invalido")
    if not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
        raise SupervisorStopError("config: prompt ausente")
    config["max_turns"] = int(config.get("max_turns", 20))
    config["heartbeat_seconds"] = float(config.get("heartbeat_seconds", 15))
    config["interrupt_grace_seconds"] = float(config.get("interrupt_grace_seconds", 20))
    preflight = config.get("preflight") or {}
    config["preflight"] = {
        "min_free_disk_gb": float(preflight.get("min_free_disk_gb", 5)),
        "warn_free_disk_gb": float(preflight.get("warn_free_disk_gb", 10)),
        "probe_timeout_seconds": float(preflight.get("probe_timeout_seconds", 20)),
    }
    timeout = config.get("worker_timeout") or {}
    config["worker_timeout"] = {
        "default_seconds": float(timeout.get("default_seconds", 7200)),
        "by_role": {k: float(v) for k, v in (timeout.get("by_role") or {}).items()},
        "by_runtime": {k: float(v) for k, v in (timeout.get("by_runtime") or {}).items()},
    }
    return config


def worker_timeout(config: dict[str, Any], role: str, runtime: str) -> float | None:
    """Seconds before a worker is stopped; None when explicitly disabled (0)."""
    spec = config["worker_timeout"]
    value = spec["by_runtime"].get(runtime, spec["by_role"].get(role, spec["default_seconds"]))
    return value if value > 0 else None


def read_state(root: Path) -> dict[str, Any]:
    """Read state.json exactly as the Harness does; never repair it."""
    try:
        state = common.load_state(root)
    except (OSError, ValueError) as error:
        raise SupervisorStopError("harness/state.json ilegible o corrupto") from error
    errors = common.validate_schema(root, "state", state) if isinstance(state, dict) else ["<root>"]
    if errors:
        raise SupervisorStopError("harness/state.json no cumple su schema", errors=errors[:5])
    return state


def plan(root: Path, config: dict[str, Any], state: dict[str, Any]) -> Plan:
    """Map the Harness-determined role to a runtime. The role is never chosen here."""
    workflow = common.load_workflow(root)
    policies = common.load_policies(root)
    name = state["state"]
    spec = workflow["states"].get(name)
    base = {
        "task_id": state.get("task_id"),
        "state": name,
        "last_transition": state.get("last_transition"),
    }
    if spec is None:
        return Plan(
            **base,
            role="unknown",
            runtime=None,
            auto=False,
            stop_kind="config",
            reason=f"estado {name} no declarado en workflow.yaml",
            next_action=None,
        )
    role, next_action = spec["role"], spec.get("next_action")
    base.update(role=role, next_action=next_action)
    if role == "human":
        return Plan(
            **base, runtime=None, auto=False, stop_kind="human", reason="Human Gate: rol human"
        )
    if role not in common.AGENT_ROLES:
        return Plan(
            **base,
            runtime=None,
            auto=False,
            stop_kind="system",
            reason=f"rol '{role}': transition.py lo resuelve solo; revisar manualmente",
        )
    runtime = (config.get("roles") or {}).get(role)
    if not runtime:
        return Plan(
            **base,
            runtime=None,
            auto=False,
            stop_kind="config",
            reason=f"sin runtime configurado para el rol {role}",
        )
    runtime_spec = (config.get("runtimes") or {}).get(runtime) or {}
    if runtime_spec.get("enabled", True) is False:
        why = runtime_spec.get("disabled_reason") or "deshabilitado en harness/supervisor.yaml"
        return Plan(
            **base,
            runtime=runtime,
            auto=False,
            stop_kind="config",
            reason=f"runtime {runtime} deshabilitado para automatizacion: {why}",
        )
    if not state.get("task_id"):
        return Plan(
            **base,
            runtime=runtime,
            auto=False,
            stop_kind="config",
            reason=f"estado {name} sin tarea vinculada",
        )
    # Same runtime restriction init.py enforces (deploy states + CANDIDATE_REVIEW).
    capable = policies["harness"]["deploy_capable_runtimes"]
    if (
        name in policies["harness"]["deploy_states"] or name == "CANDIDATE_REVIEW"
    ) and runtime not in capable:
        return Plan(
            **base,
            runtime=runtime,
            auto=False,
            stop_kind="config",
            reason=f"el estado {name} exige runtime en {capable}; configurado: {runtime}",
        )
    return Plan(**base, runtime=runtime, auto=True, stop_kind=None, reason=None)


# ---------------------------------------------------------------------------
# Transition validation (after each worker)
# ---------------------------------------------------------------------------
def new_entries(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    history = after.get("history") or []
    anchor = before.get("last_transition")
    if anchor is None:
        return list(history) if not (before.get("history") or []) else _discontinuity()
    for index in range(len(history) - 1, -1, -1):
        if history[index] == anchor:
            return list(history[index + 1 :])
    if after.get("last_transition") == anchor:
        return []
    return _discontinuity()


def _discontinuity() -> list[dict[str, Any]]:
    raise SupervisorStopError("historial de state.json discontinuo respecto del estado previo")


def validate_progress(
    workflow: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    role: str,
    runtime: str,
) -> list[dict[str, Any]]:
    """Check that every transition since `before` is declared, chained and done by this worker."""
    entries = new_entries(before, after)
    if after.get("environment") != before.get("environment"):
        raise SupervisorStopError("environment cambio durante el turno")
    if not entries:
        if after["state"] != before["state"] or after.get("task_id") != before.get("task_id"):
            raise SupervisorStopError("state cambio sin transicion registrada")
        return []
    declared = {t["id"]: t for t in workflow["transitions"]}
    states = workflow["states"]
    other_sessions = {
        (info or {}).get("session_id")
        for other, info in (before.get("sessions") or {}).items()
        if other != role and info
    }
    current = before["state"]
    sessions: set[str | None] = set()
    for entry in entries:
        spec = declared.get(entry.get("transition"))
        if (
            spec is None
            or entry.get("from") != current
            or spec["from"] != current
            or spec["to"] != entry.get("to")
            or spec["event"] != entry.get("event")
            or spec["actor"] != entry.get("actor")
        ):
            raise SupervisorStopError("transicion inesperada o no declarada", entry=_brief(entry))
        actor = spec["actor"]
        if actor == "human":
            raise SupervisorStopError(
                "transicion humana durante el turno de un worker", entry=_brief(entry)
            )
        if states[current]["role"] != role and not (actor == "system" and current == "DONE"):
            raise SupervisorStopError(
                "el worker continuo despues de perder su rol", entry=_brief(entry)
            )
        if entry.get("runtime") != runtime:
            raise SupervisorStopError(
                "transicion con runtime distinto al lanzado", entry=_brief(entry)
            )
        sessions.add(entry.get("session_id"))
        current = spec["to"]
    if current != after["state"]:
        raise SupervisorStopError("el estado final no corresponde al historial")
    if len(sessions) != 1 or sessions & other_sessions:
        raise SupervisorStopError("sesion reutilizada o multiple dentro de un turno")
    closed = current == "IDLE" and after.get("task_id") is None
    if after.get("task_id") != before.get("task_id") and not closed:
        raise SupervisorStopError("task_id cambio inesperadamente")
    return entries


def _brief(entry: dict[str, Any]) -> dict[str, Any]:
    keys = ("transition", "event", "from", "to", "actor", "runtime", "session_id")
    return {key: entry.get(key) for key in keys}


# ---------------------------------------------------------------------------
# Telemetry (ephemeral, non-canonical, redacted)
# ---------------------------------------------------------------------------
def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return common.redact(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


class Telemetry:
    """events.jsonl / heartbeat.json / supervisor.json / sessions/<id>.json. Never canonical."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.dir = root / TELEMETRY_DIR
        self.run_id = run_id

    def _dump(self, data: dict[str, Any]) -> str:
        text = json.dumps(_clean(data), ensure_ascii=False)
        if common.find_sensitive(text):
            text = json.dumps({"at": common.now_iso(), "run_id": self.run_id, "redacted": True})
        return text

    def _write(self, relative: str, data: dict[str, Any]) -> None:
        with contextlib.suppress(OSError):
            common.write_text_atomic(self.dir / relative, self._dump(data) + "\n")

    def event(self, name: str, **fields: Any) -> None:
        record = {"at": common.now_iso(), "run_id": self.run_id, "event": name, **fields}
        with contextlib.suppress(OSError):
            self.dir.mkdir(parents=True, exist_ok=True)
            with (self.dir / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(self._dump(record) + "\n")

    def heartbeat(self, status: str, **fields: Any) -> None:
        self._write(
            "heartbeat.json",
            {
                "at": common.now_iso(),
                "run_id": self.run_id,
                "pid": os.getpid(),
                "status": status,
                **fields,
            },
        )

    def summary(self, **fields: Any) -> None:
        self._write("supervisor.json", {"at": common.now_iso(), "run_id": self.run_id, **fields})

    def session(self, session_id: str, record: dict[str, Any]) -> None:
        self._write(f"sessions/{session_id}.json", record)


def last_event(root: Path) -> dict[str, Any] | None:
    path = root / TELEMETRY_DIR / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Single-instance lock (ephemeral; only guards against two Supervisors at once)
# ---------------------------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(  # noqa: S603
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        return f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def run_lock(root: Path, run_id: str):
    path = root / TELEMETRY_DIR / "run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                owner = {}
            if _pid_alive(int(owner.get("pid") or 0)):
                raise SupervisorStopError(
                    "ya hay otro Supervisor en ejecucion", pid=owner.get("pid")
                ) from None
            path.unlink(missing_ok=True)  # stale lock of a dead Supervisor
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "run_id": run_id, "at": common.now_iso()}, handle)
        break
    else:
        raise SupervisorStopError("no se pudo adquirir el lock del Supervisor")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Preflight (v1.1): nothing is launched unless disk and runtime look healthy
# ---------------------------------------------------------------------------
def _substitute(parts: list[str], values: dict[str, str]) -> list[str]:
    result = []
    for part in parts:
        for key, value in values.items():
            part = part.replace("{" + key + "}", value)
        result.append(part)
    return result


def _resolve_executable(name: str) -> str | None:
    return shutil.which(name) or (name if Path(name).is_file() else None)


def check_disk(root: Path, config: dict[str, Any], out: Out, telemetry: Telemetry) -> None:
    """STOP below min_free_disk_gb on the repo drive or the user profile drive; never deletes."""
    limits = config["preflight"]
    seen: set[str] = set()
    for path in (root, Path.home()):
        anchor = Path(path).resolve().anchor or str(path)
        if anchor in seen:
            continue
        seen.add(anchor)
        try:
            free_gb = shutil.disk_usage(path).free / GB
        except OSError as error:
            raise SupervisorStopError(f"preflight: no se pudo medir disco en {anchor}") from error
        if free_gb < limits["min_free_disk_gb"]:
            telemetry.event(
                "preflight_failed", check="disk", drive=anchor, free_gb=round(free_gb, 2)
            )
            raise SupervisorStopError(
                "preflight: espacio en disco bajo el minimo; no se lanza ningun runtime",
                drive=anchor,
                free_gb=round(free_gb, 2),
                min_free_disk_gb=limits["min_free_disk_gb"],
                action="liberar espacio manualmente (el Supervisor no borra archivos)",
            )
        if free_gb < limits["warn_free_disk_gb"]:
            out(f"SUPERVISOR WARNING: disco {anchor} con {free_gb:.1f} GB libres")
            telemetry.event(
                "preflight_warning", check="disk", drive=anchor, free_gb=round(free_gb, 2)
            )


def probe_runtime(
    root: Path, config: dict[str, Any], runtime: str, values: dict[str, str]
) -> dict[str, Any]:
    """Executable exists + harmless version probe (short timeout, outside the repo, no LLM)."""
    spec = config["runtimes"][runtime]
    command = _substitute(spec["command"], values)
    if not _resolve_executable(command[0]):
        raise SupervisorStopError(f"preflight: CLI del runtime no encontrado: {command[0]}")
    probe = spec.get("probe")
    if not probe:
        return {"runtime": runtime, "probe": "no configurado (solo existencia del ejecutable)"}
    argv = _substitute(probe, values)
    executable = _resolve_executable(argv[0])
    if not executable:
        raise SupervisorStopError(f"preflight: ejecutable del probe no encontrado: {argv[0]}")
    env = worker_env(root)
    env.pop(denials.ENV_VAR, None)
    timeout = config["preflight"]["probe_timeout_seconds"]
    with tempfile.TemporaryDirectory(prefix="tpi-sup-probe-") as scratch:
        try:
            result = subprocess.run(  # noqa: S603
                [executable, *argv[1:]],
                cwd=scratch,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SupervisorStopError(
                f"preflight: probe del runtime {runtime} excedio {timeout:.0f}s", probe=argv
            ) from error
        except OSError as error:
            raise SupervisorStopError(
                f"preflight: probe del runtime {runtime} no ejecutable ({error.__class__.__name__})"
            ) from error
    if result.returncode != 0:
        raise SupervisorStopError(
            f"preflight: runtime {runtime} no saludable (probe exit {result.returncode})",
            probe=argv,
            action="reparar/reinstalar el runtime; no se lanzo ninguna sesion",
        )
    version = (result.stdout or result.stderr).strip().splitlines()[:1]
    return {
        "runtime": runtime,
        "probe": "ok",
        "version": common.redact(version[0])[:80] if version else "",
    }


# ---------------------------------------------------------------------------
# Worker launch
# ---------------------------------------------------------------------------
def build_argv(config: dict[str, Any], runtime: str, values: dict[str, str]) -> list[str]:
    argv = _substitute(config["runtimes"][runtime]["command"], values)
    for part in argv[1:]:
        if _UNSAFE_ARG.search(part):
            raise SupervisorStopError(
                "argumento de runtime con caracteres no seguros para el shell"
            )
    executable = _resolve_executable(argv[0])
    if not executable:
        raise SupervisorStopError(f"CLI del runtime no encontrado en PATH: {argv[0]}")
    return [executable, *argv[1:]]


def worker_env(root: Path, turn: str | None = None) -> dict[str, str]:
    """Child env: the human's, minus the maintenance flag (workers never inherit it), plus the
    session-scoped turn id the guards use to latch a DENIED for this turn only."""
    env = dict(os.environ)
    env.pop(common.load_policies(root)["harness"]["maintenance_env_var"], None)
    env.pop(denials.ENV_VAR, None)
    if turn:
        env[denials.ENV_VAR] = turn
    return env


def _kill_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(  # noqa: S603
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],  # noqa: S607
            capture_output=True,
            check=False,
        )
    else:
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=10)


def _stop_worker(proc: subprocess.Popen[Any], grace: float) -> None:
    """After Ctrl+C: give the worker `grace` seconds to exit by itself, then kill its tree."""
    try:
        proc.wait(timeout=grace)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        _kill_tree(proc)


def _terminate_worker(proc: subprocess.Popen[Any], grace: float) -> None:
    """Timeout: ask the tree to end, wait `grace`, then force it. State is never touched."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(  # noqa: S603
            ["taskkill", "/PID", str(proc.pid), "/T"],  # noqa: S607
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=grace)
    _kill_tree(proc)


class WorkerTimeoutError(Exception):
    """The worker exceeded its configured timeout."""


def wait_worker(
    proc: subprocess.Popen[Any],
    tick: Callable[[], None],
    every: float,
    deadline: float | None = None,
) -> int:
    # state.json is deliberately NOT polled here: on Windows an open read handle can make the
    # worker's atomic os.replace (transition.py) fail. State is read only before and after.
    while True:
        wait = every
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkerTimeoutError
            wait = min(every, remaining)
        try:
            return proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            tick()


def _guard_log_offset(root: Path) -> int:
    try:
        return (root / GUARD_LOG).stat().st_size
    except OSError:
        return 0


def turn_denials(
    root: Path, session_id: str, session_uuid: str, log_offset: int
) -> list[dict[str, Any]]:
    """DENIED records of THIS turn: primary session-scoped latch + guard.log fallback.

    The fallback reads only guard.log lines appended after the launch and correlated to this
    turn (supervisor_turn == session_id, or the runtime session uuid the Supervisor assigned),
    so a block from another session can never be (re)interpreted as this turn's.
    """
    found = [dict(item, channel="latch") for item in denials.read(root, session_id)]
    try:
        with (root / GUARD_LOG).open("rb") as handle:
            handle.seek(log_offset)
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        tail = ""
    for line in tail.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("allowed") is not False:
            continue
        if record.get("supervisor_turn") == session_id or record.get("session_id") == session_uuid:
            found.append(
                {"source": "guard", "reason": record.get("reason"), "channel": "guard.log"}
            )
    return found


def run_turn(
    root: Path,
    config: dict[str, Any],
    telemetry: Telemetry,
    current: Plan,
    before: dict[str, Any],
    out: Out,
) -> str:
    """Launch one worker session and return its outcome, or raise SupervisorStopError."""
    role, runtime = current.role, str(current.runtime)
    stamp = time.strftime("%Y%m%d%H%M", time.gmtime())
    session_id = f"{runtime}-{stamp}-{role}-sup{uuid.uuid4().hex[:6]}"
    session_uuid = str(uuid.uuid4())
    values = {
        "runtime": runtime,
        "role": role,
        "session_id": session_id,
        "session_uuid": session_uuid,
        "python": sys.executable,
    }
    prompt = config["prompt"]
    for key, value in values.items():
        prompt = prompt.replace("{" + key + "}", value)
    argv = build_argv(config, runtime, {**values, "prompt": prompt})
    base = {
        "task": current.task_id,
        "state": current.state,
        "role": role,
        "runtime": runtime,
        "session_id": session_id,
    }
    timeout = worker_timeout(config, role, runtime)
    log_offset = _guard_log_offset(root)
    started = time.monotonic()
    out(f"SUPERVISOR: {current.state} -> rol {role} -> {runtime} (sesion nueva {session_id})")
    proc = subprocess.Popen(argv, cwd=root, env=worker_env(root, session_id))  # noqa: S603
    telemetry.event(
        "worker_started",
        **base,
        worker_pid=proc.pid,
        timeout_s=timeout,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
    )

    def tick() -> None:
        telemetry.heartbeat(
            "worker_running",
            **base,
            worker_pid=proc.pid,
            elapsed_s=round(time.monotonic() - started, 1),
        )

    tick()
    interrupted = timed_out = False
    deadline = started + timeout if timeout else None
    try:
        exit_code = wait_worker(proc, tick, config["heartbeat_seconds"], deadline=deadline)
    except KeyboardInterrupt:
        interrupted = True
        _stop_worker(proc, config["interrupt_grace_seconds"])
        exit_code = proc.returncode if proc.returncode is not None else -1
    except WorkerTimeoutError:
        timed_out = True
        _terminate_worker(proc, config["interrupt_grace_seconds"])
        exit_code = proc.returncode if proc.returncode is not None else -1
    duration = round(time.monotonic() - started, 1)
    blocked = turn_denials(root, session_id, session_uuid, log_offset)
    unreadable: SupervisorStopError | None = None
    try:
        after: dict[str, Any] | None = read_state(root)
    except SupervisorStopError as error:
        after, unreadable = None, error
    finished = {
        **base,
        "exit_code": exit_code,
        "duration_s": duration,
        "state_before": current.state,
        "state_after": after["state"] if after else "<ilegible>",
        "interrupted": interrupted,
        "timed_out": timed_out,
        "guard_denied": bool(blocked),
    }
    telemetry.event("worker_finished", **finished)
    record = {
        **finished,
        "runtime_session_uuid": session_uuid,
        "run_id": telemetry.run_id,
        "finished_at": common.now_iso(),
        "transitions": [],
        "guard_denials": [
            {k: item.get(k) for k in ("source", "reason", "label", "channel")} for item in blocked
        ],
        "progress_in_sync": bool(after) and progress_sync.in_sync(root, after),
    }

    def stop(outcome: str, reason: str, **details: Any) -> SupervisorStopError:
        record["outcome"] = outcome
        error = SupervisorStopError(reason, **details)
        error.details.update(
            outcome=outcome,
            role=role,
            runtime=runtime,
            session_id=session_id,
            state_before=current.state,
            state_after=finished["state_after"],
        )
        return error

    try:
        if interrupted:
            record["outcome"] = "interrupted"
            raise KeyboardInterrupt
        # v1.1 P0: a DENIED anywhere in the turn is an absolute stop, checked before anything
        # else, and regardless of any state change the worker made before or after it.
        if blocked:
            raise stop(
                "blocked_guard",
                "GUARD DENIED durante el turno: STOP absoluto (no se lanza otro worker)",
                denials=len(blocked),
                first_reason=blocked[0].get("reason"),
            )
        if timed_out:
            raise stop("timeout", f"el worker excedio el timeout configurado ({timeout:.0f}s)")
        if unreadable is not None or after is None:
            raise stop("failed", (unreadable or SupervisorStopError("")).reason or "state ilegible")
        workflow = common.load_workflow(root)
        try:
            entries = validate_progress(workflow, before, after, role=role, runtime=runtime)
        except SupervisorStopError as invalid:
            raise stop("failed", invalid.reason, **invalid.details) from None
        record["transitions"] = [_brief(entry) for entry in entries]
        if exit_code != 0:
            raise stop("failed", f"el worker termino con exit code {exit_code}")
        if not entries:
            raise stop("no_progress", "worker exited without workflow progress")
        next_role = workflow["states"][after["state"]]["role"]
        record["outcome"] = "human_required" if next_role == "human" else "completed"
        if not record["progress_in_sync"]:
            telemetry.event("progress_out_of_sync", **base, state_after=after["state"])
        return str(record["outcome"])
    finally:
        telemetry.session(session_id, record)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _human_banner(current: Plan, out: Out) -> None:
    last = current.last_transition or {}
    out("HUMAN ACTION REQUIRED")
    out(f"  task:          {current.task_id}")
    out(f"  state:         {current.state}")
    out(f"  reason:        {current.reason}")
    out(f"  next_action:   {current.next_action}")
    out(
        f"  last_session:  {last.get('session_id')} ({last.get('runtime')}) {last.get('transition')}"
    )
    out(f"  last_evidence: {last.get('evidence')}")
    out("Accion humana via Harness normal; despues: python scripts/harness/supervisor.py run")


def _stop_banner(stop: SupervisorStopError, current: Plan | None, out: Out) -> None:
    out("SUPERVISOR STOPPED")
    out(f"  reason:       {stop.reason}")
    if current:
        out(f"  task:         {current.task_id}")
    for key, value in stop.details.items():
        out(f"  {key + ':':<13} {value}")
    out("  state.json no fue modificado por el Supervisor. " + _RESUME_HINT)


def status(root: Path, out: Out = print, as_json: bool = False) -> int:
    try:
        config = load_config(root)
        current = plan(root, config, read_state(root))
    except SupervisorStopError as stop:
        _stop_banner(stop, None, out)
        return EXIT_STOP
    report = {**dataclasses.asdict(current), "last_supervisor_event": last_event(root)}
    if as_json:
        out(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    last = current.last_transition or {}
    out("SUPERVISOR STATUS (solo lectura; fuente de verdad: harness/state.json)")
    out(f"  task:            {current.task_id}")
    out(f"  state:           {current.state}")
    out(f"  role:            {current.role}")
    out(f"  runtime:         {current.runtime or '-'}")
    out(f"  auto_continue:   {'si' if current.auto else 'no'}")
    out(f"  stop_reason:     {current.reason or '-'}")
    out(f"  next_action:     {current.next_action}")
    out(f"  last_session:    {last.get('session_id')} ({last.get('runtime')})")
    event = report["last_supervisor_event"] or {}
    out(
        f"  last_sup_event:  {event.get('event', '-')} {event.get('at', '')} (telemetria no canonica)"
    )
    return 0


def run(root: Path, out: Out = print, max_turns: int | None = None) -> int:
    run_id = f"sup-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    try:
        config = load_config(root)
        limit = max_turns if max_turns is not None else config["max_turns"]
        with run_lock(root, run_id):
            return _loop(root, config, Telemetry(root, run_id), out, limit)
    except (
        SupervisorStopError
    ) as stop:  # config or lock: nothing ran, telemetry of others untouched
        _stop_banner(stop, None, out)
        return EXIT_STOP
    except KeyboardInterrupt:
        out("SUPERVISOR INTERRUPTED (Ctrl+C por humano). " + _RESUME_HINT)
        return EXIT_INTERRUPTED


def _loop(root: Path, config: dict[str, Any], telemetry: Telemetry, out: Out, limit: int) -> int:
    current: Plan | None = None
    turns = 0
    probed: set[str] = set()
    telemetry.event("supervisor_started", pid=os.getpid())
    try:
        while True:
            before = read_state(root)
            current = plan(root, config, before)
            telemetry.heartbeat(
                "idle",
                task=current.task_id,
                state=current.state,
                role=current.role,
                runtime=current.runtime,
            )
            if not current.auto:
                if current.stop_kind == "human":
                    _human_banner(current, out)
                    telemetry.event(
                        "human_gate",
                        task=current.task_id,
                        state=current.state,
                        role=current.role,
                        next_action=current.next_action,
                    )
                    _finish(telemetry, "human_gate", current, turns)
                    return EXIT_HUMAN
                raise SupervisorStopError(
                    str(current.reason), state=current.state, role=current.role
                )
            if turns >= limit:
                raise SupervisorStopError(f"max_turns ({limit}) alcanzado", state=current.state)
            errors, _ = validate_repo.validate(root)
            if errors:
                raise SupervisorStopError(
                    "validate_repo fallo antes de lanzar el worker", errors=errors[:5]
                )
            # v1.1 preflight: disk before every launch; runtime health once per run and runtime.
            check_disk(root, config, out, telemetry)
            runtime = str(current.runtime)
            if runtime not in probed:
                result = probe_runtime(root, config, runtime, {"python": sys.executable})
                telemetry.event("preflight_ok", **result)
                probed.add(runtime)
            turns += 1
            run_turn(root, config, telemetry, current, before, out)
    except SupervisorStopError as stop:
        _stop_banner(stop, current, out)
        telemetry.event(
            "supervisor_stopped",
            reason=stop.reason,
            details=stop.details,
            task=getattr(current, "task_id", None),
        )
        _finish(telemetry, "stopped", current, turns, reason=stop.reason)
        return EXIT_STOP
    except KeyboardInterrupt:
        out("SUPERVISOR INTERRUPTED (Ctrl+C por humano)")
        out("  state.json no fue modificado por el Supervisor. " + _RESUME_HINT)
        telemetry.event(
            "supervisor_interrupted",
            task=getattr(current, "task_id", None),
            state=getattr(current, "state", None),
        )
        _finish(telemetry, "interrupted", current, turns)
        return EXIT_INTERRUPTED


def _finish(
    telemetry: Telemetry, outcome: str, current: Plan | None, turns: int, **extra: Any
) -> None:
    telemetry.heartbeat("stopped", outcome=outcome)
    telemetry.summary(
        outcome=outcome,
        turns=turns,
        task=getattr(current, "task_id", None),
        state=getattr(current, "state", None),
        **extra,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default=str(common.ROOT), help=argparse.SUPPRESS)  # tests/dogfood
    sub = parser.add_subparsers(dest="command", required=True)
    status_parser = sub.add_parser("status", help="solo lectura")
    status_parser.add_argument("--json", action="store_true")
    run_parser = sub.add_parser("run", help="loop deterministico hasta Human Gate/STOP/Ctrl+C")
    run_parser.add_argument("--max-turns", type=int)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "status":
        return status(root, as_json=args.json)
    return run(root, max_turns=args.max_turns)


if __name__ == "__main__":
    raise SystemExit(main())

"""TPI Harness Supervisor v1: optional deterministic runner over the existing Harness.

Usage:
  python scripts/harness/supervisor.py status [--json]
  python scripts/harness/supervisor.py run [--max-turns N]

The Supervisor only reads harness/state.json + harness/workflow.yaml, launches a NEW session
of the runtime mapped to the active role (harness/supervisor.yaml), waits for it to exit,
re-reads the state and validates the observed transitions against the workflow. It never
writes state.json, never applies transitions, never runs the human script and never touches
AWS. Its only writes are ephemeral telemetry under .harness-runtime/supervisor/ (not a source
of truth; deleting it changes nothing). Any unexpected condition stops it (fail closed).

Exit codes: 0 human gate reached, 2 stopped (error / no progress / invalid), 130 Ctrl+C.
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
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from . import common, validate_repo
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]

CONFIG_FILE = Path("harness") / "supervisor.yaml"
TELEMETRY_DIR = Path(".harness-runtime") / "supervisor"
EXIT_HUMAN = 0
EXIT_STOP = 2
EXIT_INTERRUPTED = 130
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
        command = (runtimes.get(runtime) or {}).get("command")
        if not command or not all(isinstance(part, str) for part in command):
            raise SupervisorStopError(f"config: runtime '{runtime}' sin command valido")
    if not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
        raise SupervisorStopError("config: prompt ausente")
    config["max_turns"] = int(config.get("max_turns", 20))
    config["heartbeat_seconds"] = float(config.get("heartbeat_seconds", 15))
    config["interrupt_grace_seconds"] = float(config.get("interrupt_grace_seconds", 20))
    return config


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
# Worker launch
# ---------------------------------------------------------------------------
def build_argv(config: dict[str, Any], runtime: str, values: dict[str, str]) -> list[str]:
    argv = []
    for part in config["runtimes"][runtime]["command"]:
        for key, value in values.items():
            part = part.replace("{" + key + "}", value)
        argv.append(part)
    for part in argv[1:]:
        if _UNSAFE_ARG.search(part):
            raise SupervisorStopError(
                "argumento de runtime con caracteres no seguros para el shell"
            )
    executable = shutil.which(argv[0]) or (argv[0] if Path(argv[0]).is_file() else None)
    if not executable:
        raise SupervisorStopError(f"CLI del runtime no encontrado en PATH: {argv[0]}")
    return [executable, *argv[1:]]


def worker_env(root: Path) -> dict[str, str]:
    """Child env: identical to the human's, minus the maintenance flag (workers never inherit it)."""
    env = dict(os.environ)
    env.pop(common.load_policies(root)["harness"]["maintenance_env_var"], None)
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


def wait_worker(proc: subprocess.Popen[Any], tick: Callable[[], None], every: float) -> int:
    # state.json is deliberately NOT polled here: on Windows an open read handle can make the
    # worker's atomic os.replace (transition.py) fail. State is read only before and after.
    while True:
        try:
            return proc.wait(timeout=every)
        except subprocess.TimeoutExpired:
            tick()


def run_turn(
    root: Path,
    config: dict[str, Any],
    telemetry: Telemetry,
    current: Plan,
    before: dict[str, Any],
    out: Out,
) -> None:
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
    started = time.monotonic()
    out(f"SUPERVISOR: {current.state} -> rol {role} -> {runtime} (sesion nueva {session_id})")
    proc = subprocess.Popen(argv, cwd=root, env=worker_env(root))  # noqa: S603
    telemetry.event(
        "worker_started",
        **base,
        worker_pid=proc.pid,
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
    interrupted = False
    try:
        exit_code = wait_worker(proc, tick, config["heartbeat_seconds"])
    except KeyboardInterrupt:
        interrupted = True
        _stop_worker(proc, config["interrupt_grace_seconds"])
        exit_code = proc.returncode if proc.returncode is not None else -1
    duration = round(time.monotonic() - started, 1)
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
    }
    telemetry.event("worker_finished", **finished)
    record = {
        **finished,
        "runtime_session_uuid": session_uuid,
        "run_id": telemetry.run_id,
        "finished_at": common.now_iso(),
        "transitions": [],
    }
    try:
        if interrupted:
            raise KeyboardInterrupt
        if unreadable is not None or after is None:
            raise unreadable or SupervisorStopError("harness/state.json ilegible tras el worker")
        workflow = common.load_workflow(root)
        entries = validate_progress(workflow, before, after, role=role, runtime=runtime)
        record["transitions"] = [_brief(entry) for entry in entries]
        if exit_code != 0:
            raise SupervisorStopError(f"el worker termino con exit code {exit_code}")
        if not entries:
            raise SupervisorStopError("worker exited without workflow progress")
    except SupervisorStopError as stop:
        stop.details.setdefault("role", role)
        stop.details.setdefault("runtime", runtime)
        stop.details.setdefault("session_id", session_id)
        stop.details.setdefault("state_before", current.state)
        stop.details.setdefault("state_after", finished["state_after"])
        record["outcome"] = "stopped"
        raise
    except KeyboardInterrupt:
        record["outcome"] = "interrupted"
        raise
    else:
        record["outcome"] = "progress"
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

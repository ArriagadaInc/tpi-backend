"""TPI Harness Orchestrator v2 (LangGraph): optional runner on top of the Supervisor v1.1.

Usage:
  python scripts/harness/orchestrator.py status [--json]
  python scripts/harness/orchestrator.py run [--max-turns N]

Same semantics as the Supervisor (it REUSES its plan / preflight / run_turn / transition
validation / DENIED latch / single-instance lock / telemetry) plus three additions, all read-only
with respect to the Harness:

- Human gates in the terminal: at IDLE, WAITING_HUMAN_APPROVAL and BLOCKED_HUMAN it explains what
  the Harness waits for, asks the business questions behind the decision and composes the exact
  approve.py command. It NEVER runs approve.py; the human runs it in their own terminal and
  presses Enter to resume (LangGraph interrupt()).
- Human acceptance pause: a Deployer turn in VERIFYING that ends without progress while human
  criteria wait for `approve.py accept` is a legitimate pause (a gate), not a no_progress STOP.
- AWS session preflight: before launching a worker whose role has AWS access in that state
  (harness/policies.yaml aws.state_modes) it runs ONE fixed read-only operation
  (orchestrator_aws.py). An expired session asks the human instead of burning an LLM turn.

Invariants (unchanged from the Supervisor): the role always comes from workflow.yaml; it never
writes harness/state.json, never applies transitions, never edits evidence; any guard DENIED in a
turn is an absolute STOP (no gate, no feedback, no retry); no automatic retries. Without a TTY it
degrades to Supervisor behaviour. State of record is harness/state.json: the graph keeps only
ephemeral run data and re-reads state.json at every step.

Exit codes: 0 human gate reached/left, 2 stopped (fail closed), 130 Ctrl+C.
Requires: pip install langgraph==1.2.7 (lazy import; the Supervisor works without it).
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

try:
    from . import common, orchestrator_aws, orchestrator_gates, orchestrator_intake, supervisor
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import orchestrator_aws  # type: ignore[no-redef]
    import orchestrator_gates  # type: ignore[no-redef]
    import orchestrator_intake  # type: ignore[no-redef]
    import supervisor  # type: ignore[no-redef]

CONFIG_FILE = Path("harness") / "orchestrator.yaml"
EXIT_HUMAN, EXIT_STOP, EXIT_INTERRUPTED = (
    supervisor.EXIT_HUMAN,
    supervisor.EXIT_STOP,
    supervisor.EXIT_INTERRUPTED,
)
DEFAULTS: dict[str, dict[str, Any]] = {
    "aws_preflight": {"enabled": True, "max_attempts": 3, "timeout_seconds": 60},
    "gates": {"max_prompts": 50},
}
_AUTO: Any = object()  # run(): pick the terminal UI only when stdin/stdout are a TTY
_QUIT = object()
_YES = ("s", "si", "y", "yes")
_NO = ("n", "no")

Out = Callable[[str], None]


# ---------------------------------------------------------------------------
# Options (harness/orchestrator.yaml, optional; defaults are the safe ones)
# ---------------------------------------------------------------------------
def load_options(root: Path) -> dict[str, dict[str, Any]]:
    raw: Any = {}
    path = root / CONFIG_FILE
    if path.exists():
        try:
            raw = common.read_yaml(path) or {}
        except Exception as error:  # unreadable or invalid yaml: fail closed
            raise supervisor.SupervisorStopError(
                f"config del Orquestador ilegible: {CONFIG_FILE.as_posix()}"
            ) from error
    if not isinstance(raw, dict):
        raise supervisor.SupervisorStopError("config del Orquestador invalida")
    options = {name: {**base, **(raw.get(name) or {})} for name, base in DEFAULTS.items()}
    try:
        aws = options["aws_preflight"]
        aws["enabled"] = bool(aws["enabled"])
        aws["max_attempts"] = int(aws["max_attempts"])
        aws["timeout_seconds"] = float(aws["timeout_seconds"])
        options["gates"]["max_prompts"] = int(options["gates"]["max_prompts"])
    except (TypeError, ValueError) as error:
        raise supervisor.SupervisorStopError("config del Orquestador: valores invalidos") from error
    if (
        aws["max_attempts"] < 1
        or aws["timeout_seconds"] <= 0
        or options["gates"]["max_prompts"] < 1
    ):
        raise supervisor.SupervisorStopError("config del Orquestador: limites fuera de rango")
    return options


# ---------------------------------------------------------------------------
# Terminal UI (the only place that talks to the human)
# ---------------------------------------------------------------------------
class TerminalUi:
    """Renders a gate payload, asks its questions and prints the commands for the human."""

    def __init__(self, out: Out = print, read: Callable[[str], str] = input) -> None:
        self.out, self.read = out, read

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.out("")
        self.out(f"=== {payload['title']} ===")
        for line in payload.get("lines", []):
            self.out(f"  {line}")
        answers: dict[str, Any] = {}
        try:
            for question in payload.get("questions", []):
                if not all(answers.get(k) == v for k, v in (question.get("when") or {}).items()):
                    continue
                value = self._question(question)
                if value is _QUIT:
                    return {"action": "quit", "answers": answers}
                answers[question["id"]] = value
            if payload["kind"] == "intake" or (
                payload["kind"] == "idle" and answers.get("task") == orchestrator_intake.NEW_TASK
            ):
                return {"action": "continue", "answers": answers}  # nothing to run by hand yet
            composed = orchestrator_gates.commands(
                payload["kind"], payload.get("context", {}), answers
            )
            if composed:
                self.out("Ejecuta esto en TU terminal (el Orquestador no ejecuta decisiones):")
                for command in composed:
                    self.out(f"  {command}")
            reply = self.read("Enter = ya actue, reanudar | q = salir: ").strip().lower()
        except EOFError:
            return {"action": "quit", "answers": answers}
        return {"action": "quit" if reply == "q" else "continue", "answers": answers}

    def _question(self, question: dict[str, Any]) -> Any:
        kind = question["kind"]
        if kind == "repeat":  # a list of items: it has fields, not a text of its own
            return self._repeat(question)
        text = question["text"]
        while True:
            if kind == "choice":
                options = question["options"]
                default = question.get("default")
                labels = question.get("labels") or {}
                for index, option in enumerate(options, 1):
                    label = f"  ({labels[option]})" if option in labels else ""
                    self.out(f"    {index}) {option}{label}")
                suffix = f" [{default}]" if default else ""
                reply = self.read(f"  {text}{suffix} (numero o valor, q = salir): ").strip()
                if reply.lower() == "q":
                    return _QUIT
                if not reply and default:
                    return default
                if reply in options:
                    return reply
                if reply.isdigit() and 1 <= int(reply) <= len(options):
                    return options[int(reply) - 1]
            elif kind == "yes_no":
                default = question.get("default")
                hint = "" if default is None else f", Enter = {'s' if default else 'n'}"
                reply = self.read(f"  {text} (s/n{hint}, q = salir): ").strip().lower()
                if reply == "q":
                    return _QUIT
                if not reply and default is not None:
                    return default
                if reply in _YES + _NO:
                    return reply in _YES
            else:
                default = question.get("default")
                optional = question.get("optional", False)
                hint = "Enter = omitir, " if optional else ""
                shown = f" [{default}]" if default else ""
                reply = self.read(f"  {text}{shown} ({hint}/q = salir): ").strip()
                if reply == "/q":
                    return _QUIT
                if not reply and default:
                    return default
                if len(reply) >= question.get("min_len", 0 if optional else 1):
                    return reply
            self.out("    Respuesta no valida.")

    def _repeat(self, question: dict[str, Any]) -> Any:
        """A list of items, each made of `fields`; asks 'another?' once `min` items exist."""
        items: list[dict[str, Any]] = []
        label = question.get("item_label", "elemento")
        while True:
            if len(items) >= question.get("min", 0):
                prompt = question.get("more_text") if items else question.get("first_text")
                again = self._question(
                    {
                        "kind": "yes_no",
                        "text": prompt or f"Agregar un {label}?",
                        "default": False,
                    }
                )
                if again is _QUIT:
                    return _QUIT
                if not again:
                    return items
            item: dict[str, Any] = {}
            for field in question["fields"]:
                value = self._question(
                    {**field, "text": f"{field['text']} [{label} {len(items) + 1}]"}
                )
                if value is _QUIT:
                    return _QUIT
                item[field["id"]] = value
            items.append(item)


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------
class RunState(TypedDict, total=False):
    before: dict[str, Any]  # state.json snapshot taken by `observe` (never authoritative)
    plan: dict[str, Any]
    turns: int
    gate: dict[str, Any]
    gate_prompts: int
    acceptance_gate: bool
    intake: bool
    intake_answer: dict[str, Any]
    aws: dict[str, Any]
    aws_attempts: int
    quit: bool
    stop: dict[str, Any]
    outcome: str
    exit_code: int


@dataclasses.dataclass
class Context:
    root: Path
    config: dict[str, Any]
    options: dict[str, dict[str, Any]]
    telemetry: supervisor.Telemetry
    out: Out
    limit: int
    ui: Any = None
    aws_runner: orchestrator_aws.Runner | None = None
    probed: set[str] = dataclasses.field(default_factory=set)


def _stop_info(stop: supervisor.SupervisorStopError) -> dict[str, Any]:
    return {"reason": stop.reason, "details": json.loads(json.dumps(stop.details, default=str))}


def _stopping(node: Callable[[RunState], dict[str, Any]]) -> Callable[[RunState], dict[str, Any]]:
    """A SupervisorStopError raised inside a node becomes a fail-closed `stop` result."""

    @functools.wraps(node)
    def wrapper(state: RunState) -> dict[str, Any]:
        try:
            return node(state)
        except supervisor.SupervisorStopError as stop:
            return {"stop": _stop_info(stop)}

    return wrapper


def build_graph(ctx: Context) -> Any:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    root, options = ctx.root, ctx.options

    def plan_of(state: RunState) -> supervisor.Plan | None:
        return supervisor.Plan(**state["plan"]) if state.get("plan") else None

    @_stopping
    def observe(state: RunState) -> dict[str, Any]:
        before = supervisor.read_state(root)
        current = supervisor.plan(root, ctx.config, before)
        ctx.telemetry.heartbeat(
            "idle",
            task=current.task_id,
            state=current.state,
            role=current.role,
            runtime=current.runtime,
        )
        update: dict[str, Any] = {
            "before": before,
            "plan": dataclasses.asdict(current),
            "acceptance_gate": False,
        }
        if not current.auto and current.stop_kind != "human":
            update["stop"] = {
                "reason": str(current.reason),
                "details": {"state": current.state, "role": current.role},
            }
        elif current.auto and state.get("turns", 0) >= ctx.limit:
            update["stop"] = {
                "reason": f"max_turns ({ctx.limit}) alcanzado",
                "details": {"state": current.state},
            }
        return update

    def after_observe(state: RunState) -> str:
        if state.get("stop"):
            return "finish_stop"
        if not state["plan"]["auto"]:
            return "gate_prepare" if ctx.ui is not None else "finish_human"
        return "launch_checks"

    # -- human gates ---------------------------------------------------------
    @_stopping
    def gate_prepare(state: RunState) -> dict[str, Any]:
        prompts = state.get("gate_prompts", 0)
        if prompts >= options["gates"]["max_prompts"]:
            raise supervisor.SupervisorStopError(
                f"max_prompts ({options['gates']['max_prompts']}) en gates humanos sin avance",
                state=state["plan"]["state"],
            )
        fresh = supervisor.read_state(root)  # never trust the snapshot at a human gate
        if state.get("acceptance_gate"):
            payload = orchestrator_gates.describe_acceptance(root, fresh)
        else:
            payload = orchestrator_gates.describe(root, fresh)
        if payload is None:
            raise supervisor.SupervisorStopError(
                "gate humano sin descripcion", state=fresh["state"]
            )
        ctx.telemetry.event("human_gate_prompt", kind=payload["kind"], state=fresh["state"])
        return {"gate": payload, "gate_prompts": prompts + 1}

    def gate_ask(state: RunState) -> dict[str, Any]:
        # interrupt() re-executes this node on resume: it must stay free of side effects.
        answer = interrupt(state["gate"])
        quit_ = answer.get("action") == "quit"
        chosen = (answer.get("answers") or {}).get("task")
        wants_new = (
            state["gate"]["kind"] == "idle" and chosen == orchestrator_intake.NEW_TASK and not quit_
        )
        return {"quit": quit_, "intake": wants_new}

    def after_gate(state: RunState) -> str:
        if state.get("stop"):
            return "finish_stop"
        if state.get("quit"):
            return "finish_human"
        return "intake_prepare" if state.get("intake") else "observe"

    # -- task intake assistant (an interview; the draft is the only thing it writes) --------
    @_stopping
    def intake_prepare(state: RunState) -> dict[str, Any]:
        ctx.telemetry.event("intake_started")
        return {"gate": orchestrator_intake.interview(root), "intake": False}

    def intake_ask(state: RunState) -> dict[str, Any]:
        return {"intake_answer": interrupt(state["gate"])}

    def after_intake_ask(state: RunState) -> str:
        cancelled = (state.get("intake_answer") or {}).get("action") == "quit"
        return "observe" if cancelled else "intake_commit"

    @_stopping
    def intake_commit(state: RunState) -> dict[str, Any]:
        answers = (state.get("intake_answer") or {}).get("answers") or {}
        draft = orchestrator_intake.build_draft(root, answers)
        if draft.errors:
            ctx.telemetry.event("intake_rejected", errors=len(draft.errors))
            return {"gate": orchestrator_intake.error_payload(draft)}
        ctx.telemetry.event("intake_draft", task=draft.task_id, sha256=str(draft.sha256)[:12])
        return {"gate": orchestrator_intake.done_payload(draft)}

    def intake_show(state: RunState) -> dict[str, Any]:
        answer = interrupt(state["gate"])
        return {"quit": answer.get("action") == "quit", "intake": False}

    # -- launch checks (identical to Supervisor._loop) ---------------------
    @_stopping
    def launch_checks(state: RunState) -> dict[str, Any]:
        errors, _ = supervisor.validate_repo.validate(root)
        if errors:
            raise supervisor.SupervisorStopError(
                "validate_repo fallo antes de lanzar el worker", errors=errors[:5]
            )
        supervisor.check_disk(root, ctx.config, ctx.out, ctx.telemetry)
        runtime = str(state["plan"]["runtime"])
        if runtime not in ctx.probed:
            result = supervisor.probe_runtime(root, ctx.config, runtime, {"python": sys.executable})
            ctx.telemetry.event("preflight_ok", **result)
            ctx.probed.add(runtime)
        return {}

    # -- AWS session preflight -------------------------------------------------
    @_stopping
    def aws_check(state: RunState) -> dict[str, Any]:
        current, settings = state["plan"], options["aws_preflight"]
        policies = common.load_policies(root)
        if not (
            settings["enabled"]
            and orchestrator_aws.required(policies, current["state"], current["role"])
        ):
            return {"aws": {"status": "skipped"}}
        result = orchestrator_aws.check(
            root, runner=ctx.aws_runner, timeout=settings["timeout_seconds"]
        )
        ctx.telemetry.event(
            "aws_preflight", state=current["state"], role=current["role"], status=result.status
        )
        if result.status == "ok":
            return {"aws": {"status": "ok"}}
        if result.status == "wrong_account":
            raise supervisor.SupervisorStopError(
                "preflight AWS: la cuenta de la sesion no es la del entorno; no se lanza worker",
                state=current["state"],
                action=f"revisa el perfil {policies['aws']['profile']}; "
                "el Orquestador no cambia credenciales",
            )
        attempts = state.get("aws_attempts", 0) + 1
        if ctx.ui is None or attempts > settings["max_attempts"]:
            raise supervisor.SupervisorStopError(
                "preflight AWS: sesion no valida; no se lanza ningun worker",
                state=current["state"],
                status=result.status,
                detail=orchestrator_gates.clean(result.detail, 160),
                action="reautentica la sesion AWS en tu terminal y relanza",
            )
        return {
            "aws": {"status": result.status, "detail": result.detail},
            "aws_attempts": attempts,
        }

    def after_aws_check(state: RunState) -> str:
        if state.get("stop"):
            return "finish_stop"
        return "run_worker" if state["aws"]["status"] in ("ok", "skipped") else "aws_gate"

    def aws_gate(state: RunState) -> dict[str, Any]:
        aws = state["aws"]
        answer = interrupt(
            orchestrator_gates.aws_payload(
                aws["status"],
                aws.get("detail", ""),
                state["aws_attempts"],
                options["aws_preflight"]["max_attempts"],
                common.load_policies(root)["aws"]["profile"],
            )
        )
        if answer.get("action") == "quit":
            return {
                "stop": {
                    "reason": "sesion AWS no valida: el humano salio del chequeo previo",
                    "details": {"state": state["plan"]["state"], "status": aws["status"]},
                }
            }
        return {}

    def after_aws_gate(state: RunState) -> str:
        return "finish_stop" if state.get("stop") else "aws_check"

    # -- worker turn ---------------------------------------------------------
    def run_worker(state: RunState) -> dict[str, Any]:
        current = plan_of(state)
        assert current is not None
        turns = state.get("turns", 0) + 1
        try:
            supervisor.run_turn(root, ctx.config, ctx.telemetry, current, state["before"], ctx.out)
        except supervisor.SupervisorStopError as stop:
            if ctx.ui is not None and _acceptance_pause(root, current, stop):
                ctx.telemetry.event("acceptance_pending", task=current.task_id, state=current.state)
                return {"turns": turns, "aws_attempts": 0, "acceptance_gate": True}
            return {"turns": turns, "stop": _stop_info(stop)}
        return {"turns": turns, "aws_attempts": 0}

    def after_worker(state: RunState) -> str:
        if state.get("stop"):
            return "finish_stop"
        return "gate_prepare" if state.get("acceptance_gate") else "observe"

    # -- terminal nodes ----------------------------------------------------------
    def finish_stop(state: RunState) -> dict[str, Any]:
        info = state["stop"]
        stop = supervisor.SupervisorStopError(info["reason"], **info.get("details", {}))
        current = plan_of(state)
        supervisor._stop_banner(stop, current, ctx.out)
        ctx.telemetry.event(
            "supervisor_stopped",
            reason=stop.reason,
            details=stop.details,
            task=getattr(current, "task_id", None),
        )
        supervisor._finish(
            ctx.telemetry, "stopped", current, state.get("turns", 0), reason=stop.reason
        )
        return {"outcome": "stopped", "exit_code": EXIT_STOP}

    def finish_human(state: RunState) -> dict[str, Any]:
        try:
            current = supervisor.plan(root, ctx.config, supervisor.read_state(root))
        except supervisor.SupervisorStopError:
            current = plan_of(state)
        assert current is not None
        if current.stop_kind == "human":
            supervisor._human_banner(current, ctx.out)
        else:  # the human acted and then left: the Harness already moved to an agent state
            ctx.out(f"ORCHESTRATOR: salida solicitada; el Harness esta en {current.state}")
            ctx.out(
                "  (rol " + current.role + "). Reanudar: python scripts/harness/orchestrator.py run"
            )
        ctx.telemetry.event(
            "human_gate",
            task=current.task_id,
            state=current.state,
            role=current.role,
            next_action=current.next_action,
        )
        supervisor._finish(ctx.telemetry, "human_gate", current, state.get("turns", 0))
        return {"outcome": "human_gate", "exit_code": EXIT_HUMAN}

    graph = StateGraph(RunState)
    for name, node in (
        ("observe", observe),
        ("gate_prepare", gate_prepare),
        ("gate_ask", gate_ask),
        ("intake_prepare", intake_prepare),
        ("intake_ask", intake_ask),
        ("intake_commit", intake_commit),
        ("intake_show", intake_show),
        ("launch_checks", launch_checks),
        ("aws_check", aws_check),
        ("aws_gate", aws_gate),
        ("run_worker", run_worker),
        ("finish_stop", finish_stop),
        ("finish_human", finish_human),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "observe")
    graph.add_conditional_edges(
        "observe", after_observe, ["finish_stop", "gate_prepare", "finish_human", "launch_checks"]
    )
    graph.add_conditional_edges(
        "gate_prepare",
        lambda s: "finish_stop" if s.get("stop") else "gate_ask",
        ["finish_stop", "gate_ask"],
    )
    graph.add_conditional_edges(
        "gate_ask", after_gate, ["finish_stop", "finish_human", "observe", "intake_prepare"]
    )
    graph.add_conditional_edges(
        "intake_prepare",
        lambda s: "finish_stop" if s.get("stop") else "intake_ask",
        ["finish_stop", "intake_ask"],
    )
    graph.add_conditional_edges("intake_ask", after_intake_ask, ["observe", "intake_commit"])
    graph.add_conditional_edges(
        "intake_commit",
        lambda s: "finish_stop" if s.get("stop") else "intake_show",
        ["finish_stop", "intake_show"],
    )
    graph.add_conditional_edges(
        "intake_show", after_gate, ["finish_stop", "finish_human", "observe", "intake_prepare"]
    )
    graph.add_conditional_edges(
        "launch_checks",
        lambda s: "finish_stop" if s.get("stop") else "aws_check",
        ["finish_stop", "aws_check"],
    )
    graph.add_conditional_edges(
        "aws_check", after_aws_check, ["finish_stop", "run_worker", "aws_gate"]
    )
    graph.add_conditional_edges("aws_gate", after_aws_gate, ["finish_stop", "aws_check"])
    graph.add_conditional_edges(
        "run_worker", after_worker, ["finish_stop", "gate_prepare", "observe"]
    )
    graph.add_edge("finish_stop", END)
    graph.add_edge("finish_human", END)
    return graph.compile(checkpointer=InMemorySaver())


def _acceptance_pause(
    root: Path, current: supervisor.Plan, stop: supervisor.SupervisorStopError
) -> bool:
    """A VERIFYING turn with no progress while human criteria wait for `approve.py accept`."""
    if stop.details.get("outcome") != "no_progress" or current.state != "VERIFYING":
        return False
    try:
        return bool(orchestrator_gates.acceptance_pending(root, supervisor.read_state(root)))
    except supervisor.SupervisorStopError:
        return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _recursion_limit(ctx: Context) -> int:
    return (
        100 + 8 * ctx.limit + 8 * ctx.options["gates"]["max_prompts"]
    )  # a prompt may add an intake


def _drive(ctx: Context, run_id: str) -> int:
    from langgraph.errors import GraphRecursionError
    from langgraph.types import Command

    graph = build_graph(ctx)
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": _recursion_limit(ctx)}
    ctx.telemetry.event("orchestrator_started", pid=os.getpid())
    try:
        result = graph.invoke({"turns": 0}, config)
        while result.get("__interrupt__"):
            answer = ctx.ui.ask(result["__interrupt__"][0].value)
            result = graph.invoke(Command(resume=answer), config)
        return int(result["exit_code"])
    except GraphRecursionError:
        ctx.out("ORCHESTRATOR STOPPED: limite de pasos del grafo alcanzado (fail closed)")
        supervisor._finish(ctx.telemetry, "stopped", None, 0, reason="graph_recursion_limit")
        return EXIT_STOP
    except KeyboardInterrupt:
        ctx.out("ORCHESTRATOR INTERRUPTED (Ctrl+C por humano)")
        ctx.out("  state.json no fue modificado por el Orquestador. " + supervisor._RESUME_HINT)
        ctx.telemetry.event("supervisor_interrupted")
        supervisor._finish(ctx.telemetry, "interrupted", None, 0)
        return EXIT_INTERRUPTED


def run(
    root: Path,
    out: Out = print,
    max_turns: int | None = None,
    *,
    ui: Any = _AUTO,
    aws_runner: orchestrator_aws.Runner | None = None,
) -> int:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        out("ORCHESTRATOR STOPPED: falta la dependencia 'langgraph' (pip install langgraph==1.2.7)")
        out("  Alternativa sin cambios: python scripts/harness/supervisor.py run")
        return EXIT_STOP
    run_id = f"orc-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    try:
        config = supervisor.load_config(root)
        options = load_options(root)
        limit = max_turns if max_turns is not None else config["max_turns"]
        if ui is _AUTO:
            ui = TerminalUi(out) if sys.stdin.isatty() and sys.stdout.isatty() else None
        ctx = Context(
            root=root,
            config=config,
            options=options,
            telemetry=supervisor.Telemetry(root, run_id),
            out=out,
            limit=limit,
            ui=ui,
            aws_runner=aws_runner,
        )
        with supervisor.run_lock(root, run_id):
            return _drive(ctx, run_id)
    except supervisor.SupervisorStopError as stop:  # config or lock: nothing ran
        supervisor._stop_banner(stop, None, out)
        return EXIT_STOP


def status(root: Path, out: Out = print, as_json: bool = False) -> int:
    code = supervisor.status(root, out=out, as_json=as_json)
    if code != 0 or as_json:
        return code
    try:
        options = load_options(root)
        state = supervisor.read_state(root)
        current = supervisor.plan(root, supervisor.load_config(root), state)
    except supervisor.SupervisorStopError as stop:
        supervisor._stop_banner(stop, None, out)
        return EXIT_STOP
    policies = common.load_policies(root)
    needs_aws = options["aws_preflight"]["enabled"] and orchestrator_aws.required(
        policies, current.state, current.role
    )
    gate = orchestrator_gates.describe(root, state) if current.stop_kind == "human" else None
    out(f"  aws_preflight:   {'requerido antes del worker' if needs_aws else 'no requerido'}")
    out(f"  human_gate:      {gate['title'] if gate else '-'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default=str(common.ROOT), help=argparse.SUPPRESS)  # tests
    sub = parser.add_subparsers(dest="command", required=True)
    status_parser = sub.add_parser("status", help="solo lectura")
    status_parser.add_argument("--json", action="store_true")
    run_parser = sub.add_parser("run", help="loop hasta Human Gate/STOP/Ctrl+C")
    run_parser.add_argument("--max-turns", type=int)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "status":
        return status(root, as_json=args.json)
    return run(root, max_turns=args.max_turns)


if __name__ == "__main__":
    raise SystemExit(main())

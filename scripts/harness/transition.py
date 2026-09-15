"""Apply one declared workflow transition (the only agent path to change state).

Usage:
  python scripts/harness/transition.py <event> --runtime <runtime> --session <id> [--evidence <path>]

The acting role is derived from harness/state.json + harness/workflow.yaml; it is never
chosen by the caller. Human events are rejected here and only run through approve.py.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import closure, common, evidence, guards
except ImportError:  # executed as a script
    import closure  # type: ignore[no-redef]
    import common  # type: ignore[no-redef]
    import evidence  # type: ignore[no-redef]
    import guards  # type: ignore[no-redef]

RELEASE_REFS = (
    "developer_evidence",
    "review_evidence",
    "merge_evidence",
    "candidate_evidence",
    "candidate_review_evidence",
    "approval",
    "deployment_evidence",
    "verification_evidence",
    "acceptance",
    "rollback_precheck_evidence",
    "rollback_evidence",
    "failure_evidence",
    "resolution",
)


def _context(root: Path, state: dict[str, Any], session: str | None, runtime: str | None) -> guards.GuardContext:
    return guards.GuardContext(
        root=root,
        state=state,
        task=common.load_current_task(root),
        workflow=common.load_workflow(root),
        policies=common.load_policies(root),
        profile=common.load_profile(root),
        environment=common.load_environment(root, state.get("environment", "dev")),
        session=session,
        runtime=runtime,
    )


def _apply_effect(
    root: Path, state: dict[str, Any], effect: str, *, runtime: str | None, session: str | None
) -> dict[str, Any]:
    name, _, argument = effect.partition(":")
    if name == "bind_task":
        task = common.load_current_task(root)
        if task is None:
            raise common.HarnessError("bind_task sin tarea")
        state.update(
            task_id=task["id"],
            rework_round=0,
            candidate_rework_round=0,
            rollback_attempted=False,
            refs={},
            sessions={"developer": None, "reviewer": None, "deployer": None},
        )
    elif name == "record_session":
        if not runtime or not session:
            raise common.HarnessError("--runtime y --session son obligatorios")
        state["sessions"][argument] = {"runtime": runtime, "session_id": session, "at": common.now_iso()}
    elif name == "clear_refs":
        for key in argument.split(","):
            state["refs"].pop(key, None)
    elif name == "increment_rework":
        state["rework_round"] = int(state["rework_round"]) + 1
    elif name == "reset_rework":
        state["rework_round"] = 0
    elif name == "increment_candidate_rework":
        state["candidate_rework_round"] = int(state["candidate_rework_round"]) + 1
    elif name == "reset_candidate_rework":
        state["candidate_rework_round"] = 0
    elif name == "reset_release":
        for key in RELEASE_REFS:
            state["refs"].pop(key, None)
        state["candidate_rework_round"] = 0
        state["rollback_attempted"] = False
    elif name == "mark_rollback_attempted":
        state["rollback_attempted"] = True
    elif name == "cancel_task":
        state = closure.close_task(root, state, cancelled=True)
    elif name == "close_task":
        state = closure.close_task(root, state, cancelled=False)
    else:
        raise common.HarnessError(f"efecto desconocido: {effect}")
    return state


def _append_transition_log(root: Path, task_id: str | None, entry: dict[str, Any]) -> None:
    if not task_id:
        return
    path = common.evidence_task_dir(root, task_id) / "transitions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def apply_transition(
    root: Path,
    event: str,
    *,
    runtime: str | None = None,
    session: str | None = None,
    evidence_path: str | None = None,
    _human: bool = False,
    _system: bool = False,
) -> dict[str, Any]:
    state = common.load_state(root)
    workflow = common.load_workflow(root)
    policies = common.load_policies(root)
    current = state["state"]
    active_role = common.state_role(workflow, current)
    candidates = [t for t in workflow["transitions"] if t["event"] == event and t["from"] == current]
    if not candidates:
        raise common.HarnessError(f"Transicion no declarada: '{event}' desde {current}")

    actor = candidates[0]["actor"]
    if actor == "human" and not _human:
        raise common.HarnessError("Evento humano: solo lo ejecuta scripts/harness/approve.py")
    if actor == "system" and not (_system or active_role == "system"):
        raise common.HarnessError("Evento de sistema fuera de estado de sistema")
    if actor in common.AGENT_ROLES and actor != active_role:
        raise common.HarnessError(f"El estado {current} pertenece al rol {active_role}, no a {actor}")
    if actor == "deployer" and runtime not in policies["harness"]["deploy_capable_runtimes"]:
        raise common.HarnessError(
            f"Runtime '{runtime}' sin enforcement demostrado para el Deployer; STOP"
        )

    records = candidates[0].get("records")
    relative_evidence = None
    if records:
        if not evidence_path:
            raise common.HarnessError(f"El evento '{event}' requiere --evidence ({records})")
        relative_evidence = evidence.validate_reference(
            root, state, evidence_path, expected_kind=workflow["evidence_kinds"][records], actor=actor
        )
    elif evidence_path:
        raise common.HarnessError(f"El evento '{event}' no acepta evidencia")

    failures: list[str] = []
    chosen = None
    trial_state = copy.deepcopy(state)
    if records and relative_evidence:
        trial_state["refs"][records] = relative_evidence
    for transition in candidates:
        ctx = _context(root, trial_state, session, runtime)
        reasons = [r for g in transition.get("guards", []) if (r := guards.evaluate(g, ctx))]
        if not reasons:
            chosen = transition
            break
        failures.extend(reasons)
    if chosen is None:
        raise common.HarnessError("Guards no satisfechos: " + " | ".join(failures))

    new_state = trial_state
    task_id_before = state.get("task_id")
    new_state["state"] = chosen["to"]
    for effect in chosen.get("effects", []):
        new_state = _apply_effect(root, new_state, effect, runtime=runtime, session=session)
        if effect in ("close_task", "cancel_task"):
            new_state["state"] = chosen["to"]

    entry = {
        "at": common.now_iso(),
        "transition": chosen["id"],
        "event": event,
        "from": current,
        "to": chosen["to"],
        "actor": actor,
        "runtime": runtime,
        "session_id": session,
        "evidence": relative_evidence,
    }
    new_state["last_transition"] = entry
    new_state["history"] = (new_state.get("history") or [])[-19:] + [entry]
    _append_transition_log(root, task_id_before or new_state.get("task_id"), entry)
    common.save_state(root, new_state)

    if new_state["state"] == "DONE" and workflow.get("auto_close_on_done"):
        return apply_transition(root, "close", runtime=runtime, session=session, _system=True)
    return new_state


def describe(root: Path, state: dict[str, Any], previous_role: str | None) -> str:
    workflow = common.load_workflow(root)
    spec = workflow["states"][state["state"]]
    lines = [
        f"STATE: {state['state']}  TASK: {state.get('task_id')}  ROLE: {spec['role']}",
        f"NEXT: {spec['next_action']}",
    ]
    if previous_role and spec["role"] != previous_role:
        lines.append("STOP: cambio de rol o Human Gate. Esta sesion termina su etapa aqui.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event")
    parser.add_argument("--runtime", required=True, choices=["claude", "codex", "deepseek", "other"])
    parser.add_argument("--session", required=True)
    parser.add_argument("--evidence")
    args = parser.parse_args(argv)
    root = common.ROOT
    try:
        before = common.load_state(root)
        role_before = common.state_role(common.load_workflow(root), before["state"])
        state = apply_transition(
            root, args.event, runtime=args.runtime, session=args.session, evidence_path=args.evidence
        )
    except common.HarnessError as error:
        print(f"TRANSITION DENIED: {error}", file=sys.stderr)
        print(common.STOP_BANNER, file=sys.stderr)
        return 1
    print(describe(root, state, role_before))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

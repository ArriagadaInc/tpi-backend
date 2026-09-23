"""Fake runtime for Supervisor v1 tests and dry dogfood. It NEVER calls an LLM.

The Supervisor launches it exactly like a real runtime (new process, cwd = repository root):
  {python} supervisor_fake_runtime.py {runtime} {session_id} {role} {prompt}

It pops the next turn from the JSON plan at $TPI_FAKE_RUNTIME_PLAN and applies the turn's
events through the REAL scripts/harness/transition.py of that repository. Workflow guards and
evidence validation are bypassed on purpose (this simulates agent work; the guards have their
own tests), but declared transitions, actor/role checks, deploy-capable runtimes, effects,
history and state schema validation are the Harness' own code.

Turn keys: role (expected), events, exit_code, sleep, action (corrupt | raw_state), patch,
history_entry.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _write_fake_evidence(root: Path, common, state, workflow, event: str) -> str | None:
    candidates = [
        t for t in workflow["transitions"] if t["event"] == event and t["from"] == state["state"]
    ]
    records = candidates[0].get("records") if candidates else None
    if not records:
        return None
    kind = workflow["evidence_kinds"][records]
    actor = candidates[0]["actor"]
    directory = root / "evidence" / state["task_id"] / common.ROLE_EVIDENCE_DIR[actor]
    directory.mkdir(parents=True, exist_ok=True)
    index = 1 + len(list(directory.glob(f"{kind}-*.json")))
    path = directory / f"{kind}-{index:02d}.json"
    path.write_text(
        json.dumps({"kind": kind, "task_id": state["task_id"], "fake": True}) + "\n",
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


def main(argv: list[str]) -> int:
    runtime, session, role, prompt = argv[1], argv[2], argv[3], argv[4]
    root = Path.cwd()
    sys.path.insert(0, str(root))
    from scripts.harness import common, evidence, guards, transition

    policies = common.load_policies(root)
    log_path = os.environ.get("TPI_FAKE_RUNTIME_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "runtime": runtime,
                        "session": session,
                        "role": role,
                        "prompt": prompt,
                        "pid": os.getpid(),
                        "maintenance_inherited": policies["harness"]["maintenance_env_var"]
                        in os.environ,
                    }
                )
                + "\n"
            )
    plan_path = Path(os.environ["TPI_FAKE_RUNTIME_PLAN"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not plan:
        return 0
    turn = plan.pop(0)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    state_path = root / "harness" / "state.json"
    state = common.load_state(root)
    workflow = common.load_workflow(root)
    if turn.get("role") != role or common.state_role(workflow, state["state"]) != role:
        print(f"fake runtime: rol inesperado {role}", file=sys.stderr)
        return 9
    time.sleep(float(turn.get("sleep", 0)))

    if turn.get("action") == "corrupt":
        state_path.write_text("{not valid json", encoding="utf-8")
        return int(turn.get("exit_code", 0))
    if turn.get("action") == "raw_state":
        state.update(turn.get("patch") or {})
        if turn.get("history_entry"):
            state["history"] = (state.get("history") or [])[-19:] + [turn["history_entry"]]
            state["last_transition"] = turn["history_entry"]
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return int(turn.get("exit_code", 0))

    guards.evaluate = lambda name, ctx: None
    evidence.validate_reference = lambda root_, state_, path, **kwargs: path
    for event in turn.get("events", []):
        current = common.load_state(root)
        evidence_path = _write_fake_evidence(root, common, current, workflow, event)
        transition.apply_transition(
            root, event, runtime=runtime, session=session, evidence_path=evidence_path
        )
    return int(turn.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

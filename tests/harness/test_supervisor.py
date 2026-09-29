"""Supervisor v1: isolated tests over tmp_harness_repo with fake runtimes (never a real LLM).

The fake runtime (supervisor_fake_runtime.py) is launched by the real Supervisor as a real
subprocess and drives the tmp repository's real transition.py. The real repository is never
touched: every test works on a copy (see conftest.tmp_harness_repo).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.harness import common, init, supervisor, transition, validate_repo
from tests.harness.conftest import REAL_ROOT, bind_task

FAKE_RUNTIME = Path(__file__).with_name("supervisor_fake_runtime.py")
FAKE_COMMAND = [
    "{python}",
    str(FAKE_RUNTIME),
    "{runtime}",
    "{session_id}",
    "{role}",
    "{prompt}",
    "{session_uuid}",
]


class Harness:
    """A tmp repo wired to fake runtimes, plus helpers to drive and observe the Supervisor."""

    def __init__(self, root: Path, work: Path) -> None:
        self.root = root
        self.plan_path = work / "fake-plan.json"
        self.log_path = work / "fake-log.jsonl"
        self.output: list[str] = []

    def plan(self, *turns: dict[str, Any]) -> None:
        self.plan_path.write_text(json.dumps(list(turns)), encoding="utf-8")

    def run(self, **kwargs: Any) -> int:
        return supervisor.run(self.root, out=self.output.append, **kwargs)

    def launches(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line]

    def state(self) -> dict[str, Any]:
        return json.loads((self.root / "harness" / "state.json").read_text(encoding="utf-8"))

    def state_digest(self) -> str:
        return hashlib.sha256((self.root / "harness" / "state.json").read_bytes()).hexdigest()

    def events(self) -> list[dict[str, Any]]:
        path = self.root / supervisor.TELEMETRY_DIR / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def text(self) -> str:
        return "\n".join(self.output)


def make_harness(
    tmp_harness_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Harness:
    config_path = tmp_harness_repo / "harness" / "supervisor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["runtimes"] = {
        "deepseek": {"command": FAKE_COMMAND},
        "claude": {"command": FAKE_COMMAND},
    }
    config["heartbeat_seconds"] = 0.2
    config["interrupt_grace_seconds"] = 1
    # Preflight thresholds are exercised in test_supervisor_v11.py; here the host disk must not
    # decide the outcome of unrelated tests.
    config["preflight"] = {"min_free_disk_gb": 0, "warn_free_disk_gb": 0}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    h = Harness(tmp_harness_repo, tmp_path)
    monkeypatch.setenv("TPI_FAKE_RUNTIME_PLAN", str(h.plan_path))
    monkeypatch.setenv("TPI_FAKE_RUNTIME_LOG", str(h.log_path))
    h.plan()
    return h


@pytest.fixture
def harness(tmp_harness_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return make_harness(tmp_harness_repo, tmp_path, monkeypatch)


def _plan_for(root: Path, state_name: str) -> supervisor.Plan:
    if state_name != "IDLE":
        bind_task(root, state_name=state_name)
    config = supervisor.load_config(root)
    return supervisor.plan(root, config, supervisor.read_state(root))


# ---------------------------------------------------------------------------
# status: role -> runtime mapping (real harness/supervisor.yaml copy)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state_name", ["NEW", "DEVELOPING", "REVIEW_REJECTED"])
def test_status_developer_maps_to_claude(tmp_harness_repo: Path, state_name: str):
    """v1.1 routing: automatic Developer is Claude (DeepSeek stays disabled) -> no config STOP."""
    current = _plan_for(tmp_harness_repo, state_name)
    assert (current.role, current.runtime, current.auto) == ("developer", "claude", True)
    assert current.stop_kind is None and current.reason is None


@pytest.mark.parametrize("state_name", ["READY_FOR_REVIEW", "REVIEWING", "CANDIDATE_REVIEW"])
def test_status_reviewer_maps_to_claude(tmp_harness_repo: Path, state_name: str):
    current = _plan_for(tmp_harness_repo, state_name)
    assert (current.role, current.runtime, current.auto) == ("reviewer", "claude", True)


@pytest.mark.parametrize(
    "state_name",
    [
        "REVIEW_APPROVED",
        "MERGING",
        "PREPARING_DEPLOYMENT",
        "DEPLOYING",
        "VERIFYING",
        "ROLLING_BACK",
    ],
)
def test_status_deployer_maps_to_claude(tmp_harness_repo: Path, state_name: str):
    current = _plan_for(tmp_harness_repo, state_name)
    assert (current.role, current.runtime, current.auto) == ("deployer", "claude", True)


@pytest.mark.parametrize("state_name", ["IDLE", "WAITING_HUMAN_APPROVAL", "BLOCKED_HUMAN"])
def test_status_human_states_stop(tmp_harness_repo: Path, state_name: str):
    current = _plan_for(tmp_harness_repo, state_name)
    assert current.auto is False and current.stop_kind == "human" and current.runtime is None


def test_status_system_state_stops(tmp_harness_repo: Path):
    current = _plan_for(tmp_harness_repo, "DONE")
    assert current.auto is False and current.stop_kind == "system"


def test_status_refuses_non_capable_runtime_for_candidate_review(tmp_harness_repo: Path):
    path = tmp_harness_repo / "harness" / "supervisor.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["roles"]["reviewer"] = "deepseek"
    config["runtimes"]["deepseek"]["enabled"] = True  # isolate the deploy-capability check
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    current = _plan_for(tmp_harness_repo, "CANDIDATE_REVIEW")
    assert current.auto is False and current.stop_kind == "config"
    assert "CANDIDATE_REVIEW" in str(current.reason)


def test_status_cli_is_read_only(harness: Harness):
    bind_task(harness.root, state_name="REVIEWING")
    digest = harness.state_digest()
    lines: list[str] = []
    assert supervisor.status(harness.root, out=lines.append) == 0
    text = "\n".join(lines)
    for expected in ("TEST-1", "REVIEWING", "reviewer", "claude", "auto_continue:   si"):
        assert expected in text
    assert harness.state_digest() == digest
    assert not (harness.root / supervisor.TELEMETRY_DIR).exists()


# ---------------------------------------------------------------------------
# run: human gates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state_name", ["WAITING_HUMAN_APPROVAL", "BLOCKED_HUMAN", "IDLE"])
def test_run_stops_at_human_gate_without_launching(harness: Harness, state_name: str):
    if state_name != "IDLE":
        bind_task(harness.root, state_name=state_name)
    digest = harness.state_digest()
    assert harness.run() == supervisor.EXIT_HUMAN
    assert harness.launches() == []
    assert "HUMAN ACTION REQUIRED" in harness.text()
    assert "approve.py" in harness.text()  # the Harness' own next_action, only printed
    assert harness.state_digest() == digest


def test_run_stops_on_system_state(harness: Harness):
    bind_task(harness.root, state_name="DONE")
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == []


# ---------------------------------------------------------------------------
# run: automatic continuation
# ---------------------------------------------------------------------------
def test_developer_valid_transition_launches_next_role(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
    )
    assert harness.run(max_turns=2) == supervisor.EXIT_STOP  # stops on the turn cap
    assert [(x["role"], x["runtime"]) for x in harness.launches()] == [
        ("developer", "claude"),
        ("reviewer", "claude"),
    ]
    assert harness.state()["state"] == "REVIEW_REJECTED"


def test_reviewer_reject_returns_to_developer(harness: Harness):
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan(
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
        {"role": "developer", "events": ["resume_development", "submit_for_review"]},
    )
    assert harness.run(max_turns=2) == supervisor.EXIT_STOP
    assert [x["role"] for x in harness.launches()] == ["reviewer", "developer"]
    state = harness.state()
    assert state["state"] == "READY_FOR_REVIEW" and state["rework_round"] == 1


def test_reviewer_approve_advances_to_next_role(harness: Harness):
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan(
        {"role": "reviewer", "events": ["start_review", "review_approve"]},
        {"role": "deployer", "events": ["start_merge", "merged", "candidate_ready"]},
        {"role": "reviewer", "events": ["candidate_approve"]},
    )
    assert harness.run() == supervisor.EXIT_HUMAN
    assert [(x["role"], x["runtime"]) for x in harness.launches()] == [
        ("reviewer", "claude"),
        ("deployer", "claude"),
        ("reviewer", "claude"),
    ]
    assert harness.state()["state"] == "WAITING_HUMAN_APPROVAL"


def test_reviewer_and_developer_use_distinct_sessions(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
        {"role": "developer", "events": ["resume_development", "submit_for_review"]},
    )
    harness.run(max_turns=3)
    launches = harness.launches()
    assert len(launches) == 3
    assert len({x["session"] for x in launches}) == 3
    assert len({x["pid"] for x in launches}) == 3
    sessions = harness.state()["sessions"]
    assert sessions["developer"]["session_id"] != sessions["reviewer"]["session_id"]


# ---------------------------------------------------------------------------
# run: fail-closed stops
# ---------------------------------------------------------------------------
def test_worker_exit_without_progress_stops(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    digest = harness.state_digest()
    harness.plan({"role": "developer", "events": []}, {"role": "developer", "events": []})
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1, "no automatic retry in v1"
    text = harness.text()
    assert "worker exited without workflow progress" in text
    for expected in ("TEST-1", "developer", "claude", "DEVELOPING"):
        assert expected in text
    assert harness.state_digest() == digest


def test_worker_nonzero_exit_stops(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    harness.plan({"role": "developer", "events": [], "exit_code": 3})
    assert harness.run() == supervisor.EXIT_STOP
    assert "exit code 3" in harness.text()


def test_worker_nonzero_exit_stops_even_with_progress(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan({"role": "developer", "events": ["start_development"], "exit_code": 1})
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1


def test_corrupt_state_stops_without_repair(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    harness.plan({"role": "developer", "action": "corrupt"})
    assert harness.run() == supervisor.EXIT_STOP
    assert "corrupto" in harness.text()
    assert (harness.root / "harness" / "state.json").read_text() == "{not valid json"


def test_corrupt_state_before_start_stops(harness: Harness):
    (harness.root / "harness" / "state.json").write_text("{bad", encoding="utf-8")
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == []


def test_state_change_without_transition_stops(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    harness.plan({"role": "developer", "action": "raw_state", "patch": {"state": "DEPLOYING"}})
    assert harness.run() == supervisor.EXIT_STOP
    assert "sin transicion registrada" in harness.text()


def test_undeclared_transition_stops(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    entry = {
        "at": "2026-01-01T00:00:00Z",
        "transition": "shortcut",
        "event": "shortcut",
        "from": "DEVELOPING",
        "to": "DEPLOYING",
        "actor": "developer",
        "runtime": "deepseek",
        "session_id": "x",
        "evidence": None,
    }
    harness.plan(
        {
            "role": "developer",
            "action": "raw_state",
            "patch": {"state": "DEPLOYING"},
            "history_entry": entry,
        }
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert "transicion inesperada" in harness.text()


@pytest.mark.parametrize("patch", [{"task_id": "OTHER-9"}, {"environment": "prod"}])
def test_task_or_environment_change_stops(harness: Harness, patch: dict[str, Any]):
    bind_task(harness.root, state_name="DEVELOPING")
    harness.plan({"role": "developer", "action": "raw_state", "patch": patch})
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1


def test_worker_continuing_after_losing_role_stops(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review", "start_review"]}
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert "perder su rol" in harness.text()


def test_max_turns_caps_the_loop(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan({"role": "developer", "events": ["start_development"]})
    assert harness.run(max_turns=1) == supervisor.EXIT_STOP
    assert "max_turns" in harness.text()


def test_second_supervisor_is_refused_while_lock_owner_alive(harness: Harness):
    bind_task(harness.root, state_name="DEVELOPING")
    lock = harness.root / supervisor.TELEMETRY_DIR / "run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": __import__("os").getpid()}), encoding="utf-8")
    assert harness.run() == supervisor.EXIT_STOP
    assert "otro Supervisor" in harness.text() and harness.launches() == []


def test_stale_lock_is_ignored(harness: Harness):
    bind_task(harness.root, state_name="WAITING_HUMAN_APPROVAL")
    lock = harness.root / supervisor.TELEMETRY_DIR / "run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": 4_000_000 + 7}), encoding="utf-8")
    assert harness.run() == supervisor.EXIT_HUMAN
    assert not lock.exists()


# ---------------------------------------------------------------------------
# Ctrl+C, rollback to manual mode and resume
# ---------------------------------------------------------------------------
def test_ctrl_c_is_safe_and_manual_harness_continues(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
):
    bind_task(harness.root, state_name="NEW")
    digest = harness.state_digest()
    harness.plan({"role": "developer", "sleep": 30, "events": ["start_development"]})
    original_wait = supervisor.wait_worker

    def interrupted_wait(proc, tick, every, deadline=None):
        with pytest.raises(subprocess.TimeoutExpired):
            proc.wait(timeout=1.5)  # worker is alive and sleeping
        raise KeyboardInterrupt

    monkeypatch.setattr(supervisor, "wait_worker", interrupted_wait)
    assert harness.run() == supervisor.EXIT_INTERRUPTED
    monkeypatch.setattr(supervisor, "wait_worker", original_wait)

    assert harness.state_digest() == digest, "Ctrl+C must not touch state.json"
    started = next(e for e in harness.events() if e["event"] == "worker_started")
    assert not supervisor._pid_alive(int(started["worker_pid"])), "worker must be terminated"
    assert "supervisor_interrupted" in [e["event"] for e in harness.events()]
    assert not (harness.root / supervisor.TELEMETRY_DIR / "run.lock").exists()

    # Manual mode, no conversion step: the normal Harness continues from the same state.
    state = transition.apply_transition(
        harness.root, "start_development", runtime="deepseek", session="manual-dev-1"
    )
    assert state["state"] == "DEVELOPING"
    assert validate_repo.validate(harness.root)[0] == []


def test_resume_supervisor_from_manually_generated_state(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    transition.apply_transition(
        harness.root, "start_development", runtime="deepseek", session="manual-dev-1"
    )
    harness.plan({"role": "developer", "events": ["submit_for_review"]})
    assert harness.run(max_turns=1) == supervisor.EXIT_STOP  # turn cap after one worker
    assert harness.launches()[0]["role"] == "developer"
    assert harness.state()["state"] == "READY_FOR_REVIEW"


def test_supervisor_stop_leaves_manual_mode_usable(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan({"role": "developer", "events": []})
    assert harness.run() == supervisor.EXIT_STOP
    state = transition.apply_transition(
        harness.root, "start_development", runtime="deepseek", session="manual-dev-2"
    )
    assert state["state"] == "DEVELOPING"


def test_harness_works_with_supervisor_removed(tmp_harness_repo: Path):
    (tmp_harness_repo / "harness" / "supervisor.yaml").unlink()
    (tmp_harness_repo / "scripts" / "harness" / "supervisor.py").unlink()
    assert validate_repo.validate(tmp_harness_repo)[0] == []
    assert init.build_report(tmp_harness_repo, "claude")["errors"] == []
    bind_task(tmp_harness_repo, state_name="NEW")
    state = transition.apply_transition(
        tmp_harness_repo, "start_development", runtime="deepseek", session="manual"
    )
    assert state["state"] == "DEVELOPING"


# ---------------------------------------------------------------------------
# Boundaries: no state writes, no AWS, clean telemetry
# ---------------------------------------------------------------------------
def test_supervisor_never_writes_state_directly(harness: Harness, monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the Supervisor process must not write state.json")

    monkeypatch.setattr(common, "save_state", forbidden)
    monkeypatch.setattr(common, "write_json_atomic", forbidden)
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": []},
    )
    assert harness.run() == supervisor.EXIT_STOP  # reviewer made no progress
    assert harness.state()["state"] == "READY_FOR_REVIEW"


def test_supervisor_source_has_no_state_writes_aws_or_human_actions():
    source = (REAL_ROOT / "scripts" / "harness" / "supervisor.py").read_text(encoding="utf-8")
    for forbidden in (
        "save_state",
        "apply_transition",
        "write_json_atomic",
        "approve",
        "aws_guard",
        "boto3",
        '"aws"',
        "'aws'",
        "transition.py <",
    ):
        assert forbidden not in source, forbidden


def test_supervisor_only_launches_configured_runtimes(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
):
    launched: list[list[str]] = []
    real_popen = subprocess.Popen

    def recording_popen(argv, *args, **kwargs):
        launched.append(list(argv))
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(supervisor.subprocess, "Popen", recording_popen)
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan(
        {"role": "deployer", "events": ["start_merge", "merged", "candidate_ready"]},
        {"role": "reviewer", "events": ["candidate_approve"]},
    )
    assert harness.run() == supervisor.EXIT_HUMAN
    workers = [argv for argv in launched if argv[0] == sys.executable]
    others = [argv for argv in launched if argv[0] != sys.executable]
    assert len(workers) == 2 and all(argv[1] == str(FAKE_RUNTIME) for argv in workers)
    # Only other subprocess: validate_repo's read-only `git check-ignore` preflight (its path
    # list names scripts/harness/aws_guard.py as a required file; it is never executed).
    assert all(argv[:2] == ["git", "check-ignore"] for argv in others)
    for argv in workers:
        assert not any(part.lower() in ("aws", "aws.exe") or "aws_guard" in part for part in argv)


def test_telemetry_has_required_fields_and_no_secrets(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
):
    maintenance_var = common.load_policies(harness.root)["harness"]["maintenance_env_var"]
    monkeypatch.setenv(maintenance_var, "1")
    monkeypatch.setenv("AUTH_USERS_JSON", '{"admin": {"password": "hunter2-TOPSECRET"}}')
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAABCDEFGHIJKLMNOP")
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": []},
    )
    harness.run()
    launches = harness.launches()
    assert launches and not any(x["maintenance_inherited"] for x in launches)

    finished = [e for e in harness.events() if e["event"] == "worker_finished"]
    assert finished
    for event in finished:
        for key in (
            "at",
            "task",
            "state",
            "role",
            "runtime",
            "session_id",
            "exit_code",
            "state_before",
            "state_after",
            "duration_s",
        ):
            assert key in event, key
    assert {e["event"] for e in harness.events()} >= {
        "supervisor_started",
        "worker_started",
        "worker_finished",
        "supervisor_stopped",
    }
    telemetry_dir = harness.root / supervisor.TELEMETRY_DIR
    for name in ("heartbeat.json", "supervisor.json", "events.jsonl"):
        assert (telemetry_dir / name).is_file()
    assert len(list((telemetry_dir / "sessions").glob("*.json"))) == 2

    prompt = launches[0]["prompt"]
    for path in telemetry_dir.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "hunter2" not in text and "AKIAABCDEFGHIJKLMNOP" not in text
            assert "AUTH_USERS_JSON" not in text and prompt not in text
            assert common.find_sensitive(text) == []


def test_real_config_prompt_is_minimal_and_shell_safe():
    config = supervisor.load_config(REAL_ROOT)
    assert config["roles"] == {"developer": "claude", "reviewer": "claude", "deployer": "claude"}
    prompt = config["prompt"]
    assert len(prompt) < 600 and "AGENTS.md" in prompt and "{session_id}" in prompt
    assert not supervisor._UNSAFE_ARG.search(prompt) and prompt.isascii()


# ---------------------------------------------------------------------------
# Dry dogfood: the full requested cycle with fake runtimes
# ---------------------------------------------------------------------------
def test_dogfood_full_cycle_until_human_gate(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
        {"role": "developer", "events": ["resume_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_approve"]},
        {"role": "deployer", "events": ["start_merge", "merged", "candidate_ready"]},
        {"role": "reviewer", "events": ["candidate_approve"]},
    )
    assert harness.run() == supervisor.EXIT_HUMAN
    assert [(x["role"], x["runtime"]) for x in harness.launches()] == [
        ("developer", "claude"),
        ("reviewer", "claude"),
        ("developer", "claude"),
        ("reviewer", "claude"),
        ("deployer", "claude"),
        ("reviewer", "claude"),
    ]
    path = [
        (e["state_before"], e["state_after"])
        for e in harness.events()
        if e["event"] == "worker_finished"
    ]
    assert path == [
        ("NEW", "READY_FOR_REVIEW"),
        ("READY_FOR_REVIEW", "REVIEW_REJECTED"),
        ("REVIEW_REJECTED", "READY_FOR_REVIEW"),
        ("READY_FOR_REVIEW", "REVIEW_APPROVED"),
        ("REVIEW_APPROVED", "CANDIDATE_REVIEW"),
        ("CANDIDATE_REVIEW", "WAITING_HUMAN_APPROVAL"),
    ]
    assert harness.state()["state"] == "WAITING_HUMAN_APPROVAL"
    assert "HUMAN ACTION REQUIRED" in harness.text()

"""Supervisor v1.1 (Harness Hardening after the H3.3.6 dogfood). Fake runtimes only.

Covers: DENIED latch => absolute STOP (also after a state change), guard.log fallback,
session scoping, preflight (disk / missing runtime / unhealthy runtime), structured turn
outcomes, worker timeout, DeepSeek disabled, and the fake dogfood scenarios A-E.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.harness import denials, supervisor, transition, validate_repo
from tests.harness.conftest import REAL_ROOT, bind_task
from tests.harness.test_supervisor import FAKE_COMMAND, Harness, make_harness


@pytest.fixture
def harness(tmp_harness_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return make_harness(tmp_harness_repo, tmp_path, monkeypatch)


def _config(h: Harness, **changes: Any) -> None:
    path = h.root / "harness" / "supervisor.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if key == "runtimes":
            config["runtimes"] = {**config["runtimes"], **value}  # keep the other runtimes
        else:
            config[key] = value
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _sessions(h: Harness) -> list[dict[str, Any]]:
    # Ordered by the append-only events.jsonl (one worker_finished per turn), not finished_at:
    # its 1s resolution ties turns finished in the same second.
    directory = h.root / supervisor.TELEMETRY_DIR / "sessions"
    records = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("*.json")]
    finished = [e["session_id"] for e in h.events() if e["event"] == "worker_finished"]
    return sorted(records, key=lambda r: finished.index(r["session_id"]))


# ---------------------------------------------------------------------------
# P0-1: any DENIED stops the whole run
# ---------------------------------------------------------------------------
def test_state_change_then_guard_denied_stops_without_second_deployer(harness: Harness):
    """Exact H3.3.6 incident: start_merge (state changes) + guard DENIED -> STOP, no relaunch."""
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan(
        {"role": "deployer", "events": ["start_merge"], "deny": "guard"},
        {"role": "deployer", "events": ["merged"]},
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1, "no second Deployer after a DENIED"
    assert harness.state()["state"] == "MERGING"  # the worker's transition stays as it was
    assert "GUARD DENIED" in harness.text() and "blocked_guard" in harness.text()
    record = _sessions(harness)[-1]
    assert record["outcome"] == "blocked_guard" and record["guard_denied"] is True
    assert record["guard_denials"][0]["source"] == "guard"
    assert record["guard_denials"][0]["channel"] == "latch"


def test_aws_guard_denied_after_progress_stops(harness: Harness):
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan(
        {"role": "deployer", "events": ["start_merge", "merged"], "deny": "aws_guard"},
        {"role": "deployer", "events": ["candidate_ready"]},
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1
    record = _sessions(harness)[-1]
    assert record["outcome"] == "blocked_guard"
    assert record["guard_denials"][0]["source"] == "aws_guard"


def test_denied_before_any_progress_is_blocked_guard_not_no_progress(harness: Harness):
    bind_task(harness.root, state_name="MERGING")
    harness.plan({"role": "deployer", "events": [], "deny": "guard", "deny_first": True})
    assert harness.run() == supervisor.EXIT_STOP
    assert _sessions(harness)[-1]["outcome"] == "blocked_guard"


def test_denied_with_exit_zero_and_role_change_still_stops(harness: Harness):
    """Even a turn that hands over to another role cannot hide its DENIED."""
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan(
        {"role": "reviewer", "events": ["start_review", "review_approve"], "deny": "guard"},
        {"role": "deployer", "events": ["start_merge"]},
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert [x["role"] for x in harness.launches()] == ["reviewer"]


def test_guard_log_fallback_detects_denial_without_latch(harness: Harness):
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan(
        {"role": "deployer", "events": ["start_merge"], "deny": "guard_log"},
        {"role": "deployer", "events": ["merged"]},
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1
    assert _sessions(harness)[-1]["guard_denials"][0]["channel"] == "guard.log"


def test_denial_of_other_sessions_is_never_reinterpreted(harness: Harness):
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    # a stale latch of an earlier turn and a guard.log DENIED of another session
    stale = denials.path_for(harness.root, "claude-202601010000-deployer-supold001")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"source": "guard", "reason": "viejo"}\n', encoding="utf-8")
    harness.plan(
        {"role": "deployer", "events": ["start_merge"], "deny": "guard_log_other"},
        {"role": "deployer", "events": []},
    )
    harness.run(max_turns=2)
    records = _sessions(harness)
    assert records[0]["outcome"] == "completed" and records[0]["guard_denied"] is False
    assert len(harness.launches()) == 2


def test_worker_receives_session_scoped_turn_id(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    _enable_fake_developer(harness)
    harness.plan({"role": "developer", "events": ["start_development"]})
    harness.run(max_turns=1)
    launch = harness.launches()[0]
    assert launch["supervisor_turn"] == launch["session"]
    assert not launch["maintenance_inherited"]


# ---------------------------------------------------------------------------
# P0-4: preflight
# ---------------------------------------------------------------------------
def test_disk_below_minimum_launches_nothing(harness: Harness, monkeypatch: pytest.MonkeyPatch):
    _config(harness, preflight={"min_free_disk_gb": 5, "warn_free_disk_gb": 10})
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    digest = harness.state_digest()

    class Usage:
        free = int(1.5 * supervisor.GB)

    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda path: Usage())
    harness.plan({"role": "reviewer", "events": ["start_review"]})
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == []
    assert "espacio en disco" in harness.text() and harness.state_digest() == digest


def test_disk_warning_still_launches(harness: Harness, monkeypatch: pytest.MonkeyPatch):
    _config(harness, preflight={"min_free_disk_gb": 5, "warn_free_disk_gb": 10})
    bind_task(harness.root, state_name="READY_FOR_REVIEW")

    class Usage:
        free = int(7 * supervisor.GB)

    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda path: Usage())
    harness.plan({"role": "reviewer", "events": ["start_review"]})
    harness.run(max_turns=1)
    assert len(harness.launches()) == 1 and "SUPERVISOR WARNING" in harness.text()


def test_missing_runtime_launches_nothing(harness: Harness):
    _config(harness, runtimes={"claude": {"command": ["tpi-missing-cli-xyz", "{prompt}"]}})
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == [] and "no encontrado" in harness.text()


@pytest.mark.parametrize(
    "probe,expected",
    [
        (["{python}", "-c", "import sys; sys.exit(1)"], "no saludable"),  # exists, --version fails
        (["{python}", "-c", "import time; time.sleep(30)"], "excedio"),  # hung probe
        (["tpi-missing-probe-xyz", "--version"], "no encontrado"),
    ],
)
def test_unhealthy_runtime_probe_stops_before_launch(harness: Harness, probe, expected):
    _config(
        harness,
        runtimes={"claude": {"command": FAKE_COMMAND, "probe": probe}},
        preflight={"min_free_disk_gb": 0, "warn_free_disk_gb": 0, "probe_timeout_seconds": 2},
    )
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == [] and expected in harness.text()


def test_healthy_probe_runs_outside_repo_and_launches(harness: Harness):
    marker = "import os, sys; sys.exit(0 if not os.path.exists('harness/state.json') else 4)"
    _config(
        harness,
        runtimes={"claude": {"command": FAKE_COMMAND, "probe": ["{python}", "-c", marker]}},
        preflight={"min_free_disk_gb": 0, "warn_free_disk_gb": 0, "probe_timeout_seconds": 10},
    )
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan({"role": "reviewer", "events": ["start_review"]})
    harness.run(max_turns=1)
    assert len(harness.launches()) == 1
    assert "preflight_ok" in [e["event"] for e in harness.events()]


def test_real_config_has_claude_version_probe_and_disk_limits():
    config = supervisor.load_config(REAL_ROOT)
    assert config["runtimes"]["claude"]["probe"] == ["claude", "--version"]
    assert config["preflight"]["min_free_disk_gb"] == 5
    assert config["preflight"]["warn_free_disk_gb"] == 10


# ---------------------------------------------------------------------------
# DeepSeek disabled (security P0 from the DSH push investigation)
# ---------------------------------------------------------------------------
def test_real_config_disables_deepseek_as_automatic_developer():
    config = supervisor.load_config(REAL_ROOT)
    assert config["runtimes"]["deepseek"]["enabled"] is False
    assert "enforcement" in config["runtimes"]["deepseek"]["disabled_reason"]


def test_disabled_runtime_is_never_launched(harness: Harness):
    _config(
        harness,
        roles={"developer": "deepseek", "reviewer": "claude", "deployer": "claude"},
        runtimes={
            "deepseek": {"command": FAKE_COMMAND, "enabled": False, "disabled_reason": "x"},
            "claude": {"command": FAKE_COMMAND},
        },
    )
    bind_task(harness.root, state_name="NEW")
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == [] and "deshabilitado" in harness.text()


# ---------------------------------------------------------------------------
# Routing: automatic Developer -> Claude (DeepSeek stays disabled)
# ---------------------------------------------------------------------------
def test_real_config_routes_every_agent_role_to_claude():
    config = supervisor.load_config(REAL_ROOT)
    assert config["roles"] == {"developer": "claude", "reviewer": "claude", "deployer": "claude"}
    assert config["runtimes"]["deepseek"]["enabled"] is False
    assert config["runtimes"]["claude"].get("enabled", True) is True


@pytest.mark.parametrize("state_name", ["NEW", "DEVELOPING", "REVIEW_REJECTED"])
def test_real_config_developer_state_no_longer_stops(tmp_harness_repo: Path, state_name: str):
    """Real supervisor.yaml copy (not the fake-runtime override): no 'deshabilitado' STOP."""
    bind_task(tmp_harness_repo, state_name=state_name)
    config = supervisor.load_config(tmp_harness_repo)
    current = supervisor.plan(tmp_harness_repo, config, supervisor.read_state(tmp_harness_repo))
    assert (current.role, current.runtime, current.auto) == ("developer", "claude", True)
    assert current.stop_kind is None and "deshabilitado" not in str(current.reason)


def test_claude_developer_and_reviewer_turns_use_fresh_sessions(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
        {"role": "developer", "events": ["resume_development", "submit_for_review"]},
    )
    harness.run(max_turns=3)
    launches = harness.launches()
    assert [(x["role"], x["runtime"]) for x in launches] == [
        ("developer", "claude"),
        ("reviewer", "claude"),
        ("developer", "claude"),
    ]
    assert len({x["session"] for x in launches}) == 3 and len({x["pid"] for x in launches}) == 3
    records = _sessions(harness)
    assert len({r["runtime_session_uuid"] for r in records}) == 3


def test_manual_mode_unaffected_by_claude_developer_routing(harness: Harness):
    bind_task(harness.root, state_name="NEW")
    state = transition.apply_transition(
        harness.root, "start_development", runtime="claude", session="manual-dev-claude"
    )
    assert state["state"] == "DEVELOPING"
    assert harness.launches() == []
    assert not (harness.root / supervisor.TELEMETRY_DIR).exists()
    assert validate_repo.validate(harness.root)[0] == []


def _enable_fake_developer(h: Harness) -> None:
    _config(
        h, runtimes={"deepseek": {"command": FAKE_COMMAND}, "claude": {"command": FAKE_COMMAND}}
    )


# ---------------------------------------------------------------------------
# P1-9: structured outcomes / P1-10: timeout
# ---------------------------------------------------------------------------
def test_structured_turn_result_fields_and_outcomes(harness: Harness):
    bind_task(harness.root, state_name="CANDIDATE_REVIEW")
    harness.plan({"role": "reviewer", "events": ["candidate_approve"]})
    assert harness.run() == supervisor.EXIT_HUMAN
    record = _sessions(harness)[-1]
    for key in (
        "session_id",
        "runtime",
        "role",
        "state_before",
        "state_after",
        "exit_code",
        "outcome",
        "guard_denied",
        "duration_s",
    ):
        assert key in record, key
    assert record["outcome"] == "human_required"
    assert set(supervisor.OUTCOMES) >= {record["outcome"]}


def test_no_progress_and_failed_outcomes(harness: Harness):
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan({"role": "reviewer", "events": []})
    harness.run()
    assert _sessions(harness)[-1]["outcome"] == "no_progress"
    harness.plan({"role": "reviewer", "events": [], "exit_code": 3})
    harness.run()
    assert _sessions(harness)[-1]["outcome"] == "failed"


def test_worker_timeout_stops_without_touching_state(harness: Harness):
    _config(harness, worker_timeout={"default_seconds": 2, "by_role": {}, "by_runtime": {}})
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    digest = harness.state_digest()
    harness.plan({"role": "reviewer", "sleep": 60, "events": ["start_review"]})
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.state_digest() == digest
    record = _sessions(harness)[-1]
    assert record["outcome"] == "timeout" and record["timed_out"] is True
    started = next(e for e in harness.events() if e["event"] == "worker_started")
    assert not supervisor._pid_alive(int(started["worker_pid"]))
    assert not (harness.root / supervisor.TELEMETRY_DIR / "run.lock").exists()
    # manual Harness still usable from the same state.json
    state = transition.apply_transition(
        harness.root, "start_review", runtime="claude", session="manual-rev-1"
    )
    assert state["state"] == "REVIEWING"


def test_timeout_resolution_and_explicit_disable():
    config = {
        "worker_timeout": {
            "default_seconds": 7200.0,
            "by_role": {"developer": 14400.0, "reviewer": 0.0},
            "by_runtime": {"special": 60.0},
        }
    }
    assert supervisor.worker_timeout(config, "deployer", "claude") == 7200
    assert supervisor.worker_timeout(config, "developer", "claude") == 14400
    assert supervisor.worker_timeout(config, "reviewer", "claude") is None  # disabled
    assert supervisor.worker_timeout(config, "reviewer", "special") == 60


def test_real_config_timeouts_are_conservative():
    config = supervisor.load_config(REAL_ROOT)
    assert supervisor.worker_timeout(config, "reviewer", "claude") >= 3600
    assert supervisor.worker_timeout(config, "developer", "claude") >= 3 * 3600


def test_progress_projection_in_sync_after_turn(harness: Harness):
    bind_task(harness.root, state_name="READY_FOR_REVIEW")
    harness.plan({"role": "reviewer", "events": ["start_review", "review_reject"]})
    harness.run(max_turns=1)
    assert _sessions(harness)[-1]["progress_in_sync"] is True
    text = (harness.root / "progress" / "current.md").read_text(encoding="utf-8")
    assert "- Estado del Harness: REVIEW_REJECTED (rol: developer)" in text


# ---------------------------------------------------------------------------
# Section 15: fake dogfood scenarios
# ---------------------------------------------------------------------------
def test_dogfood_a_developer_reviewer_reject_developer_reviewer(harness: Harness):
    _enable_fake_developer(harness)  # fake stands in for a Developer runtime (DSH disabled)
    bind_task(harness.root, state_name="NEW")
    harness.plan(
        {"role": "developer", "events": ["start_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review", "review_reject"]},
        {"role": "developer", "events": ["resume_development", "submit_for_review"]},
        {"role": "reviewer", "events": ["start_review"]},
    )
    assert harness.run(max_turns=4) == supervisor.EXIT_STOP  # turn cap
    assert [x["role"] for x in harness.launches()] == [
        "developer",
        "reviewer",
        "developer",
        "reviewer",
    ]
    assert [r["outcome"] for r in _sessions(harness)] == ["completed"] * 4
    assert harness.state()["state"] == "REVIEWING"


def test_dogfood_b_deployer_state_change_then_denied_no_second_deployer(harness: Harness):
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan(
        {"role": "deployer", "events": ["start_merge"], "deny": "guard"},
        {"role": "deployer", "events": ["merged"]},
    )
    assert harness.run() == supervisor.EXIT_STOP
    assert len(harness.launches()) == 1


def test_dogfood_c_human_gate_clean_stop(harness: Harness):
    bind_task(harness.root, state_name="CANDIDATE_REVIEW")
    harness.plan({"role": "reviewer", "events": ["candidate_approve"]})
    assert harness.run() == supervisor.EXIT_HUMAN
    assert "HUMAN ACTION REQUIRED" in harness.text()
    assert harness.state()["state"] == "WAITING_HUMAN_APPROVAL"
    assert len(harness.launches()) == 1


def test_dogfood_d_timeout_then_manual_harness(harness: Harness):
    _config(harness, worker_timeout={"default_seconds": 2, "by_role": {}, "by_runtime": {}})
    bind_task(harness.root, state_name="REVIEW_APPROVED")
    harness.plan({"role": "deployer", "sleep": 60, "events": ["start_merge"]})
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.state()["state"] == "REVIEW_APPROVED"
    assert validate_repo.validate(harness.root)[0] == []
    state = transition.apply_transition(
        harness.root, "start_merge", runtime="claude", session="manual-dep-1"
    )
    assert state["state"] == "MERGING"


def test_dogfood_e_disk_preflight_fail_launches_nothing(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
):
    _config(harness, preflight={"min_free_disk_gb": 5, "warn_free_disk_gb": 10})
    bind_task(harness.root, state_name="REVIEW_APPROVED")

    class Usage:
        free = 0

    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda path: Usage())
    harness.plan({"role": "deployer", "events": ["start_merge"]})
    assert harness.run() == supervisor.EXIT_STOP
    assert harness.launches() == []
    assert "preflight_failed" in [e["event"] for e in harness.events()]


def test_supervisor_source_still_free_of_state_writes_and_human_actions():
    source = (REAL_ROOT / "scripts" / "harness" / "supervisor.py").read_text(encoding="utf-8")
    for forbidden in ("save_state", "apply_transition", "write_json_atomic", "approve", '"aws"'):
        assert forbidden not in source, forbidden
    assert sys.executable  # probes/workers are launched via configured commands only

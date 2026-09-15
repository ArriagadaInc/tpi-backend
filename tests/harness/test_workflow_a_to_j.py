"""Tests A-J: structural/lifecycle coverage of the Harness, requested for the
maintenance hardening pass. Each test operates on an isolated tmp_harness_repo
(see conftest.py) -- never the real repository -- except where explicitly noted.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.harness import (
    common,
    context_compact,
    evidence,
    guards,
    init,
    transition,
    validate_repo,
)
from tests.harness.conftest import bind_task, set_state


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=True  # noqa: S607
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# A. init fail-closed
# ---------------------------------------------------------------------------
def test_a_init_fails_closed_on_missing_required_file(tmp_harness_repo: Path):
    policies_path = tmp_harness_repo / "harness" / "policies.yaml"
    policies_path.unlink()
    report = init.build_report(tmp_harness_repo, "claude")
    assert report["errors"]
    assert not policies_path.exists(), "init must never repair/recreate a missing file"


def test_a_init_fails_closed_on_corrupt_state_json(tmp_harness_repo: Path):
    (tmp_harness_repo / "harness" / "state.json").write_text("{not valid json", encoding="utf-8")
    report = init.build_report(tmp_harness_repo, "claude")
    assert report["errors"]


# ---------------------------------------------------------------------------
# B. clean clone
# ---------------------------------------------------------------------------
def test_b_clean_clone_validates(tmp_harness_repo: Path, tmp_path: Path):
    clone_dir = tmp_path / "clone"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", str(tmp_harness_repo), str(clone_dir)],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    errors, warnings = validate_repo.validate(clone_dir)
    assert errors == [], f"clean clone must validate with zero errors, got: {errors}"


# ---------------------------------------------------------------------------
# C. cold start
# ---------------------------------------------------------------------------
def test_c_cold_start_briefing_idle(tmp_harness_repo: Path):
    report = init.build_report(tmp_harness_repo, "claude")
    assert report["errors"] == []
    briefing = report["briefing"]
    assert briefing["state"] == "IDLE"
    assert briefing["active_role"] == "human"
    assert "approve.py activate" in briefing["next_action"]
    assert briefing["task"] is None


# ---------------------------------------------------------------------------
# D. runtime swap
# ---------------------------------------------------------------------------
def test_d_deploy_state_requires_deploy_capable_runtime(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="PREPARING_DEPLOYMENT")
    report = init.build_report(tmp_harness_repo, "codex")
    assert any("enforcement" in e for e in report["errors"])
    report_claude = init.build_report(tmp_harness_repo, "claude")
    assert not any("enforcement" in e for e in report_claude["errors"])


def test_d_transition_denies_deployer_event_from_non_claude_runtime(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="PREPARING_DEPLOYMENT")
    with pytest.raises(common.HarnessError, match="enforcement"):
        transition.apply_transition(
            tmp_harness_repo, "candidate_ready", runtime="codex", session="s1"
        )


# ---------------------------------------------------------------------------
# E. role isolation
# ---------------------------------------------------------------------------
def test_e_transition_denies_human_event_without_human_flag(tmp_harness_repo: Path):
    with pytest.raises(common.HarnessError, match="Evento humano"):
        transition.apply_transition(
            tmp_harness_repo, "activate_task", runtime="claude", session="s1"
        )


def test_e_developer_cannot_invoke_reviewer_event_from_developing(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="DEVELOPING")
    with pytest.raises(common.HarnessError, match="no declarada"):
        transition.apply_transition(
            tmp_harness_repo, "start_review", runtime="claude", session="s1"
        )


def test_e_reviewer_must_use_different_session_than_developer(tmp_harness_repo: Path):
    state = json.loads((tmp_harness_repo / "harness" / "state.json").read_text(encoding="utf-8"))
    state["sessions"] = {
        "developer": {
            "runtime": "claude",
            "session_id": "same-session",
            "at": "2026-01-01T00:00:00Z",
        },
        "reviewer": None,
        "deployer": None,
    }
    ctx = guards.GuardContext(
        root=tmp_harness_repo,
        state=state,
        task=None,
        workflow=common.load_workflow(tmp_harness_repo),
        policies=common.load_policies(tmp_harness_repo),
        profile=common.load_profile(tmp_harness_repo),
        environment=common.load_environment(tmp_harness_repo),
        session="same-session",
        runtime="claude",
    )
    reason = guards.evaluate("reviewer_session_independent", ctx)
    assert reason is not None and "sesion distinta" in reason


# ---------------------------------------------------------------------------
# F. context compaction (non-destructive)
# ---------------------------------------------------------------------------
def test_f_context_compact_preserves_history_and_extracts_decisions(tmp_harness_repo: Path):
    current = tmp_harness_repo / "progress" / "current.md"
    original = (
        "# Progreso actual\n\n## Estado\n- Estado del Harness: IDLE\n\n"
        "## Estado reciente\n- 2026-01-01: hito de prueba\nDECISION: usar patron X porque Y\n"
        "\n## Proximo paso\n- siguiente\n\n## Bloqueos\n- BLOCKER: algo pendiente\n"
    )
    current.write_text(original, encoding="utf-8")
    decisions_before = (tmp_harness_repo / "progress" / "decisions.md").read_text(encoding="utf-8")

    session_path = context_compact.compact(tmp_harness_repo, label="f-test")

    archived = session_path.read_text(encoding="utf-8")
    for line in original.splitlines():
        if line.strip():
            assert line in archived, f"line lost during compaction: {line!r}"

    decisions_after = (tmp_harness_repo / "progress" / "decisions.md").read_text(encoding="utf-8")
    assert "usar patron X porque Y" in decisions_after
    assert decisions_after.startswith(
        decisions_before[: len(decisions_before.rstrip())].rstrip()[:20]
    )

    rebuilt = current.read_text(encoding="utf-8")
    assert "BLOCKER: algo pendiente" in rebuilt
    assert len(rebuilt.splitlines()) <= int(
        common.load_policies(tmp_harness_repo)["harness"]["progress_current_max_lines"]
    )


# ---------------------------------------------------------------------------
# G. workflow transitions (real, evidence-gated)
# ---------------------------------------------------------------------------
def test_g_activate_start_submit_for_review_real_chain(tmp_harness_repo: Path):
    head_sha = _git(tmp_harness_repo, "rev-parse", "HEAD")

    # human: IDLE -> NEW (bind_task helper sets state directly since approve.py is human-only;
    # here we exercise start_development + submit_for_review, the two agent-driven transitions)
    bind_task(tmp_harness_repo, state_name="NEW")
    state = transition.apply_transition(
        tmp_harness_repo, "start_development", runtime="claude", session="dev-1"
    )
    assert state["state"] == "DEVELOPING"
    assert state["sessions"]["developer"]["session_id"] == "dev-1"

    payload = {
        "head_sha": head_sha,
        "branch": "harness/TEST-1-dev",
        "pr_number": 1,
        "change_class": "A",
        "tests": {"command": "pytest", "result": "PASS"},
        "quality_gates": {"ruff": "PASS", "mypy": "PASS"},
        "acceptance_criteria": [{"id": "AC-1", "status": "met", "evidence": "test log"}],
        "files_changed": ["app/main.py"],
        "assumptions": [],
        "migrations_included": False,
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "developer", payload, runtime="claude", session="dev-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()

    state = transition.apply_transition(
        tmp_harness_repo,
        "submit_for_review",
        runtime="claude",
        session="dev-1",
        evidence_path=relative,
    )
    assert state["state"] == "READY_FOR_REVIEW"
    assert state["refs"]["developer_evidence"] == relative


def test_g_submit_for_review_rejects_evidence_with_wrong_change_class(tmp_harness_repo: Path):
    head_sha = _git(tmp_harness_repo, "rev-parse", "HEAD")
    bind_task(tmp_harness_repo, state_name="NEW", change_class="A")
    transition.apply_transition(
        tmp_harness_repo, "start_development", runtime="claude", session="dev-1"
    )
    payload = {
        "head_sha": head_sha,
        "branch": "harness/TEST-1-dev",
        "pr_number": 1,
        "change_class": "B",  # mismatches the task's declared class A
        "tests": {"command": "pytest", "result": "PASS"},
        "quality_gates": {"ruff": "PASS"},
        "acceptance_criteria": [{"id": "AC-1", "status": "met", "evidence": "x"}],
        "files_changed": [],
        "assumptions": [],
        "migrations_included": False,
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "developer", payload, runtime="claude", session="dev-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()
    with pytest.raises(common.HarnessError, match="Guards no satisfechos"):
        transition.apply_transition(
            tmp_harness_repo,
            "submit_for_review",
            runtime="claude",
            session="dev-1",
            evidence_path=relative,
        )


# ---------------------------------------------------------------------------
# H. AWS safety (state-machine coverage lives in test_aws_guard.py; this checks
#    the init-level runtime gate for CANDIDATE_REVIEW specifically)
# ---------------------------------------------------------------------------
def test_h_candidate_review_requires_claude_runtime(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="CANDIDATE_REVIEW")
    report = init.build_report(tmp_harness_repo, "codex")
    assert any("CANDIDATE_REVIEW" in e for e in report["errors"])


# ---------------------------------------------------------------------------
# I. immutable candidate/release
# ---------------------------------------------------------------------------
def test_i_evidence_reference_rejects_wrong_kind(tmp_harness_repo: Path):
    head_sha = _git(tmp_harness_repo, "rev-parse", "HEAD")
    bind_task(tmp_harness_repo, state_name="NEW")
    transition.apply_transition(
        tmp_harness_repo, "start_development", runtime="claude", session="dev-1"
    )
    payload = {
        "head_sha": head_sha,
        "branch": "harness/TEST-1-dev",
        "pr_number": 1,
        "change_class": "A",
        "tests": {"command": "pytest", "result": "PASS"},
        "quality_gates": {"ruff": "PASS"},
        "acceptance_criteria": [{"id": "AC-1", "status": "met", "evidence": "x"}],
        "files_changed": [],
        "assumptions": [],
        "migrations_included": False,
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "developer", payload, runtime="claude", session="dev-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()
    state = common.load_state(tmp_harness_repo)
    with pytest.raises(common.HarnessError, match="se esperaba evidencia"):
        evidence.validate_reference(
            tmp_harness_repo, state, relative, expected_kind="review", actor="developer"
        )


def test_i_evidence_reference_rejects_foreign_task(tmp_harness_repo: Path):
    head_sha = _git(tmp_harness_repo, "rev-parse", "HEAD")
    bind_task(tmp_harness_repo, state_name="NEW", task_id="OTHER-TASK")
    transition.apply_transition(
        tmp_harness_repo, "start_development", runtime="claude", session="dev-1"
    )
    payload = {
        "head_sha": head_sha,
        "branch": "harness/OTHER-TASK-dev",
        "pr_number": 1,
        "change_class": "A",
        "tests": {"command": "pytest", "result": "PASS"},
        "quality_gates": {"ruff": "PASS"},
        "acceptance_criteria": [{"id": "AC-1", "status": "met", "evidence": "x"}],
        "files_changed": [],
        "assumptions": [],
        "migrations_included": False,
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "developer", payload, runtime="claude", session="dev-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()
    forged_state = {**common.load_state(tmp_harness_repo), "task_id": "DIFFERENT-TASK"}
    with pytest.raises(common.HarnessError, match="evidencia debe estar en"):
        evidence.validate_reference(
            tmp_harness_repo, forged_state, relative, expected_kind="developer", actor="developer"
        )


# ---------------------------------------------------------------------------
# J. failure paths
# ---------------------------------------------------------------------------
def test_j_blocked_human_resolution_requires_human_flag(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="BLOCKED_HUMAN")
    with pytest.raises(common.HarnessError, match="Evento humano"):
        transition.apply_transition(
            tmp_harness_repo, "human_resolve", runtime="claude", session="s1"
        )


def test_j_failure_evidence_must_match_current_state(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="PREPARING_DEPLOYMENT")
    set_state(
        tmp_harness_repo,
        sessions={
            "developer": None,
            "reviewer": None,
            "deployer": {"runtime": "claude", "session_id": "dep-1", "at": "2026-01-01T00:00:00Z"},
        },
    )
    payload = {
        "action": "elasticbeanstalk create-application-version",
        "resource": "redacted",
        "principal": "tpi-dev",
        "error": "AccessDenied (synthetic)",
        "state": "DEPLOYING",  # wrong on purpose: actual state is PREPARING_DEPLOYMENT
        "recommendation": "revisar IAM",
        "residues": [],
        "access_denied": True,
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "failure", payload, runtime="claude", session="dep-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()
    with pytest.raises(common.HarnessError, match="Guards no satisfechos"):
        transition.apply_transition(
            tmp_harness_repo,
            "preparation_failed",
            runtime="claude",
            session="dep-1",
            evidence_path=relative,
        )


def test_j_rework_exhausted_routes_to_blocked_human(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="REVIEWING")
    max_rework = int(common.load_policies(tmp_harness_repo)["harness"]["max_rework_rounds"])
    set_state(
        tmp_harness_repo,
        rework_round=max_rework,
        sessions={
            "developer": {"runtime": "claude", "session_id": "dev-1", "at": "2026-01-01T00:00:00Z"},
            "reviewer": {"runtime": "claude", "session_id": "rev-1", "at": "2026-01-01T00:00:00Z"},
            "deployer": None,
        },
    )
    payload = {
        "reviewed_sha": "0" * 40,
        "reviewed_tree": "0" * 40,
        "pr_number": 1,
        "ci": {"run_id": 1, "conclusion": "success"},
        "decision": "REJECTED",
        "findings": [
            {"id": "F-1", "severity": "blocker", "summary": "x", "required_action": "fix"}
        ],
        "checks": [{"name": "x", "result": "PASS"}],
        "risks": [],
    }
    path = evidence.write_evidence(
        tmp_harness_repo, "review", payload, runtime="claude", session="rev-1"
    )
    relative = path.relative_to(tmp_harness_repo).as_posix()
    state = transition.apply_transition(
        tmp_harness_repo, "review_reject", runtime="claude", session="rev-1", evidence_path=relative
    )
    assert state["state"] == "BLOCKED_HUMAN"

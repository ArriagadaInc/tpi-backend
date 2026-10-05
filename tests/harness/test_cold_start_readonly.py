"""Regression coverage for the two cold-start defects fixed in this pass:

1. ``init`` (init.sh / init.ps1 / scripts/harness/init.py) is a strict read-only
   preflight: it must never create sessions, evidence, or touch progress/state/tasks,
   regardless of role or instruction ("no realices cambios"). Session/evidence
   registration is a separate, later, explicitly role/state-gated operation
   (``scripts/harness/transition.py``'s ``record_session:<role>`` effect) -- never
   something init performs.
2. ``guard.py`` must not conflate "protected path" with "unreadable path": read-only
   discovery (listing directories, ``git status``/``diff``/``log``/``ls-files``,
   reading non-secret files, non-sensitive text search) must be allowed in any state,
   including IDLE, even when the command happens to mention a protected-path token
   (e.g. ``harness/``) or a harmless stream redirect (``2>&1``, ``2>/dev/null``).
   Mutation, secrets, AWS, and destructive commands must remain denied.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.harness import common, guard, init
from tests.harness.conftest import REAL_ROOT


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=True  # noqa: S607
    )
    return result.stdout


def _snapshot(root: Path) -> tuple[dict[str, str], str]:
    tracked = [line for line in _git(root, "ls-files").splitlines() if line]
    hashes = {relative: common.sha256_file(root / relative) for relative in tracked}
    status = _git(root, "status", "--porcelain")
    return hashes, status


# ---------------------------------------------------------------------------
# Defect 1: init is strictly read-only.
# ---------------------------------------------------------------------------


def test_init_does_not_modify_filesystem_or_git(tmp_harness_repo: Path):
    before_hashes, before_status = _snapshot(tmp_harness_repo)
    report = init.build_report(tmp_harness_repo, "claude")
    after_hashes, after_status = _snapshot(tmp_harness_repo)
    assert not report["errors"], report["errors"]
    assert before_hashes == after_hashes, "init must not modify any tracked file"
    assert before_status == after_status == "", "init must leave the worktree clean"


def test_init_cli_subprocess_does_not_modify_filesystem_or_git(tmp_harness_repo: Path):
    """Same guarantee through the real CLI entrypoint, not just the Python API."""
    before_hashes, before_status = _snapshot(tmp_harness_repo)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/harness/init.py", "--runtime", "claude", "--json"],
        cwd=tmp_harness_repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    after_hashes, after_status = _snapshot(tmp_harness_repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert before_hashes == after_hashes
    assert before_status == after_status == ""


def test_init_works_in_idle_without_task(tmp_harness_repo: Path):
    report = init.build_report(tmp_harness_repo, "claude")
    assert not report["errors"]
    assert report["briefing"]["state"] == "IDLE"
    assert report["briefing"]["active_role"] == "human"
    assert report["briefing"]["task"] is None


def test_init_never_calls_a_state_mutating_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_harness_repo: Path
):
    """Belt-and-suspenders: if anyone wires session/evidence creation into init later,
    this fails immediately instead of silently regressing defect 1."""

    def _forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("init must never write state/evidence/progress")

    monkeypatch.setattr(common, "save_state", _forbidden)
    monkeypatch.setattr(common, "write_text_atomic", _forbidden)
    monkeypatch.setattr(common, "write_json_atomic", _forbidden)
    monkeypatch.setattr(common, "write_yaml_atomic", _forbidden)
    report = init.build_report(tmp_harness_repo, "claude")
    assert not report["errors"]


# ---------------------------------------------------------------------------
# Defect 2: read-only discovery is never blocked by guard.py, including in IDLE
# and when mentioning protected-path tokens or harmless stream redirects.
# ---------------------------------------------------------------------------


def _fake_state(state_name: str, task_id: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state": state_name,
        "task_id": task_id,
        "environment": "dev",
        "rework_round": 0,
        "candidate_rework_round": 0,
        "rollback_attempted": False,
        "refs": {},
        "sessions": {"developer": None, "reviewer": None, "deployer": None},
        "worktrees": [],
        "updated_at": "2026-01-01T00:00:00Z",
        "last_transition": None,
        "history": [],
    }


@pytest.fixture
def idle(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(common, "load_state", lambda root: _fake_state("IDLE"))
    monkeypatch.setattr(common, "load_current_task", lambda root: None)


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "ls harness/",
        "ls -la harness/ agents/",
        "git status",
        "git diff",
        "git log",
        "git ls-files",
        "grep -r pattern harness/",
        "cat harness/workflow.yaml",
        # the exact false positive observed at cold start: a harmless stream
        # redirect combined with a protected-path token used to be denied.
        "ls harness/ 2>&1",
        "ls -la harness/ 2>/dev/null",
        "git status 2>&1",
        "python scripts/harness/init.py --runtime claude 2>&1",
        'find harness/ -name "*.yaml" 2>&1',
    ],
)
def test_read_only_discovery_allowed_in_idle(idle, command):
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Bash", "tool_input": {"command": command}}, {}
    )
    assert allowed, reason


def test_read_harness_workflow_allowed(idle):
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Read", "tool_input": {"file_path": "harness/workflow.yaml"}},
        {},
    )
    assert allowed, reason


def test_edit_harness_workflow_denied_in_idle(idle):
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "harness/workflow.yaml"}},
        {},
    )
    assert not allowed
    assert "protegida" in reason


def test_secret_read_still_denied(idle):
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Read", "tool_input": {"file_path": ".env"}}, {}
    )
    assert not allowed


def test_aws_mcp_still_denied(idle):
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "mcp__aws__aws___search_documentation", "tool_input": {}},
        {},
    )
    assert not allowed


@pytest.mark.parametrize(
    "command",
    [
        "ls harness/ 2>&1; rm harness/x",
        "echo x > harness/policies.yaml",
        "cmd 2>&1 > harness/out.log",
    ],
)
def test_disguised_write_still_denied_despite_safe_redirect(idle, command):
    """The redirect-stripping fix must not create a bypass: a real mutation elsewhere
    in the same command, even alongside a harmless '2>&1', must still be denied."""
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Bash", "tool_input": {"command": command}}, {}
    )
    assert not allowed, f"expected denial, got allowed with reason={reason!r}"


def test_destructive_command_with_safe_redirect_still_denied(idle):
    command = "git" + " reset " + "--hard origin/main 2>&1"
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Bash", "tool_input": {"command": command}}, {}
    )
    assert not allowed
    assert "destructiv" in reason or "prohibid" in reason

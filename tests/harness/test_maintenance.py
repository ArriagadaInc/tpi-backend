"""M1-M6: maintenance-mode guarantees (Harness bootstrap maintenance, D3/D6/D4/D5).

Numbering matches the maintenance test plan requested for the harness hardening pass.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.harness import aws_guard, common, guard
from tests.harness.conftest import REAL_ROOT

BASH = shutil.which("bash") or shutil.which("sh")


def _state(state_name: str, task_id: str | None = None) -> dict[str, Any]:
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


# --- M1 ------------------------------------------------------------------
def test_m1_child_shell_cannot_alter_parent_environment():
    """A child shell's env mutations never propagate back to this (parent) process.

    KNOWN LIMITATION (documented, not asserted as fixed): this demonstrates OS-level
    process isolation only. It does NOT prove that TPI_HARNESS_MAINTENANCE was set by
    a human rather than by arbitrary shell *within this same trust boundary* before the
    runtime launched -- that property is not mechanically provable here (see D8).
    """
    if BASH is None:
        pytest.skip("requires a POSIX shell")
    os.environ["TPI_HARNESS_MAINTENANCE"] = "1"
    try:
        subprocess.run(  # noqa: S603
            [BASH, "-c", "export TPI_HARNESS_MAINTENANCE=0; unset TPI_HARNESS_MAINTENANCE; true"],
            env=os.environ.copy(),
            check=True,
        )
        assert os.environ.get("TPI_HARNESS_MAINTENANCE") == "1"
    finally:
        del os.environ["TPI_HARNESS_MAINTENANCE"]


# --- M2 --------------------------------------------------------------------
ALLOWLISTED_PATHS = [
    "harness/state.json",
    "agents/developer/PROMPT.md",
    "scripts/harness/guard.py",
    "tests/harness/test_example.py",
    "runtime/claude/README.md",
    ".claude/settings.json",
    ".mcp.json",
    "AGENTS.md",
    "CLAUDE.md",
    "init.sh",
    "init.ps1",
    "environments/dev.yaml",
    "tasks/current.yaml",
    "progress/current.md",
    "evidence/README.md",
    "docs/cicd/example.md",
]


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(state_name: str, task_id: str | None = None) -> None:
        monkeypatch.setattr(common, "load_state", lambda root: _state(state_name, task_id))
        monkeypatch.setattr(common, "load_current_task", lambda root: None)

    return _set


@pytest.mark.parametrize("path", ALLOWLISTED_PATHS)
def test_m2_maintenance_allows_only_allowlisted_paths(state_as, path):
    state_as("IDLE")
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": path}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert allowed, f"{path} must be writable under maintenance (declared allowlist)"


@pytest.mark.parametrize("path", ["README.md", "docker-compose.yml", "front/index.html"])
def test_m2_maintenance_does_not_allow_paths_outside_allowlist(state_as, path):
    state_as("IDLE")
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": path}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed, f"{path} is not in maintenance_allowlist; maintenance must not grant it"


# --- M3 ----------------------------------------------------------------------
@pytest.mark.parametrize("maintenance_env", [{}, {"TPI_HARNESS_MAINTENANCE": "1"}])
def test_m3_maintenance_never_widens_aws_access(monkeypatch, maintenance_env):
    monkeypatch.setattr(common, "load_state", lambda root: _state("IDLE"))
    decision = aws_guard.evaluate(
        REAL_ROOT,
        ["sts", "get-caller-identity"],
        env_vars={**os.environ, "CLAUDECODE": "1", **maintenance_env},
    )
    assert decision.mode == "none"
    assert not decision.allowed


# --- M4 ------------------------------------------------------------------------
@pytest.mark.parametrize("command", ["git reset --hard", "rm -rf .", "git clean -fdx"])
def test_m4_maintenance_never_allows_destructive_commands(state_as, command):
    state_as("IDLE")
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Bash", "tool_input": {"command": command}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed


# --- M5 -----------------------------------------------------------------------
def test_m5_maintenance_does_not_allow_arbitrary_app_writes(state_as):
    state_as("REVIEWING")
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "app/main.py"}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed


def test_m5_maintenance_does_not_bypass_developer_worktree_rule(state_as):
    state_as("DEVELOPING")
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "app/main.py"}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert (
        not allowed
    ), "even the Developer must write app/** inside its worktree, maintenance or not"


# --- M6 -------------------------------------------------------------------------
def test_m6_maintenance_is_recorded_in_guard_log(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.setattr(common, "ROOT", tmp_harness_repo)
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.setenv("TPI_HARNESS_MAINTENANCE", "1")
    guard.main()
    log_path = tmp_harness_repo / ".harness-runtime" / "guard.log"
    assert log_path.is_file()
    last = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["maintenance_mode"] is True
    assert last["context"] == "maintenance-bootstrap"
    assert "TPI_HARNESS_MAINTENANCE" not in json.dumps(last)  # no secrets/env values logged


def test_m6_normal_runtime_recorded_as_non_maintenance(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.setattr(common, "ROOT", tmp_harness_repo)
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.delenv("TPI_HARNESS_MAINTENANCE", raising=False)
    guard.main()
    log_path = tmp_harness_repo / ".harness-runtime" / "guard.log"
    last = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["maintenance_mode"] is False
    assert last["context"] == "runtime-normal"

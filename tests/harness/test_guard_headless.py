"""Section 14: headless guard.py tests with synthetic payloads (no real tool calls).

Each test monkeypatches ``common.load_state`` to synthesize a role/state and calls
guard.decide()/check_* directly against the REAL policies.yaml + workflow.yaml
(read-only; decide() never writes). This is honest coverage: the policy file under
test is the one actually loaded by the real hook, only the workflow state is faked.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from scripts.harness import common, guard
from tests.harness.conftest import REAL_ROOT


def _fake_state(state_name: str, task_id: str | None = "TEST-1") -> dict[str, Any]:
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


def _fake_task() -> dict[str, Any]:
    return {
        "id": "TEST-1",
        "title": "Tarea sintetica",
        "objective": "Ejercitar el guard con datos sinteticos",
        "source": {"type": "backlog", "ref": "TEST"},
        "change_class": "A",
        "deploy_required": True,
        "requires_human_acceptance": False,
        "acceptance_criteria": [{"id": "AC-1", "description": "x", "verification": "automated"}],
        "constraints": [],
        "dependencies": [],
        "risk": {"level": "low"},
        "status": "active",
    }


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(state_name: str, task_id: str | None = "TEST-1") -> None:
        monkeypatch.setattr(common, "load_state", lambda root: _fake_state(state_name, task_id))
        monkeypatch.setattr(
            common, "load_current_task", lambda root: _fake_task() if task_id else None
        )

    return _set


# 1. Read de secreto -> DENIED
def test_read_secret_denied(state_as):
    state_as("DEVELOPING")
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Read", "tool_input": {"file_path": ".env"}}, {}
    )
    assert not allowed
    assert "secreto" in reason or ".env" in reason


def test_read_env_example_allowed(state_as):
    state_as("DEVELOPING")
    allowed, _ = guard.decide(
        REAL_ROOT, {"tool_name": "Read", "tool_input": {"file_path": ".env.example"}}, {}
    )
    assert allowed


# 2. Developer AWS -> DENIED
def test_developer_aws_mcp_denied(state_as):
    state_as("DEVELOPING")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "mcp__aws__aws___search_documentation", "tool_input": {}},
        {},
    )
    assert not allowed
    assert "developer" in reason


# 3. Reviewer write app -> DENIED
def test_reviewer_write_app_denied(state_as):
    state_as("REVIEWING")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "app/main.py"}},
        {},
    )
    assert not allowed


# 4. Deployer write app -> DENIED
def test_deployer_write_app_denied(state_as):
    state_as("PREPARING_DEPLOYMENT")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "app/main.py"}},
        {},
    )
    assert not allowed


# 5/6. Harness write sin/con mantenimiento
def test_harness_write_without_maintenance_denied(state_as):
    state_as("IDLE", task_id=None)
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "harness/policies.yaml"}},
        {},
    )
    assert not allowed


def test_harness_write_with_maintenance_allowed(state_as):
    state_as("IDLE", task_id=None)
    allowed, _ = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "harness/policies.yaml"}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert allowed


# 7. app write con maintenance desde rol no autorizado -> DENIED
def test_app_write_with_maintenance_unauthorized_role_denied(state_as):
    state_as("REVIEWING")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Edit", "tool_input": {"file_path": "app/main.py"}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed


# 8. destructive command con maintenance -> DENIED
@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard origin/main",
        "git clean -fdx",
        "rm -rf .harness-worktrees",
        "git checkout -- .",
        "git restore --staged .",
    ],
)
def test_destructive_command_with_maintenance_denied(state_as, command):
    state_as("IDLE", task_id=None)
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "Bash", "tool_input": {"command": command}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed
    assert "destructiv" in reason or "prohibid" in reason or "autorizacion humana" in reason


# 9. AWS write con maintenance e IDLE -> DENIED (evaluated in test_aws_guard.py for aws_guard;
# here we confirm the MCP AWS surface stays closed too, since role=human in IDLE.
def test_aws_mcp_with_maintenance_idle_denied(state_as):
    state_as("IDLE", task_id=None)
    allowed, reason = guard.decide(
        REAL_ROOT,
        {"tool_name": "mcp__aws__aws___search_documentation", "tool_input": {}},
        {"TPI_HARNESS_MAINTENANCE": "1"},
    )
    assert not allowed


# MCP forbidden tools always denied regardless of role/state (run_script, get_presigned_url)
@pytest.mark.parametrize(
    "tool", ["mcp__aws__aws___run_script", "mcp__aws__aws___get_presigned_url"]
)
def test_forbidden_mcp_tools_denied(state_as, tool):
    state_as("PREPARING_DEPLOYMENT")
    allowed, reason = guard.decide(REAL_ROOT, {"tool_name": tool, "tool_input": {}}, {})
    assert not allowed
    assert "prohibida" in reason


# Regression: the aws_guard.py canonical-path check must not false-positive on any
# command that merely mentions a filename ending in "aws_guard.py" (e.g. pytest
# targeting tests/harness/test_aws_guard.py, which is not an aws_guard.py invocation).
def test_pytest_command_naming_test_aws_guard_not_denied(state_as):
    state_as("DEVELOPING")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest tests/harness/test_aws_guard.py -q"},
        },
        {},
    )
    assert allowed, reason


def test_fake_aws_guard_outside_repo_still_denied(state_as):
    state_as("DEVELOPING")
    allowed, reason = guard.decide(
        REAL_ROOT,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python /tmp/evil/aws_guard.py sts get-caller-identity"},
        },
        {},
    )
    assert not allowed
    assert "aws_guard debe invocarse" in reason


def test_guard_fails_closed_on_internal_error(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """main() must deny (exit 2), never allow, when an internal error occurs before a decision."""

    def _boom(root):
        raise RuntimeError("state.json corrupto")

    monkeypatch.setattr(common, "load_state", _boom)
    monkeypatch.setattr(common, "ROOT", REAL_ROOT)
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    monkeypatch.chdir(tmp_path)
    exit_code = guard.main()
    assert exit_code == 2

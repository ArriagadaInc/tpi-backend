"""`gh` is classified on real invocations: mentioning it is not running it, and every one counts.

Found with a real LLM run: `which python python3 gh git` was read as the command `gh git` and
DENIED (an absolute STOP for the turn); and `gh pr view 1 && gh pr merge ...` was judged only by
its first `gh`. Each test fakes the workflow state and calls guard.decide() against the REAL
policies.yaml, like test_guard_headless.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.harness import common, guard
from tests.harness.conftest import REAL_ROOT

SHA = "a" * 40
WORKTREE = ".harness-worktrees/TEST-1-developer-abc1234"
BRANCH = "harness/TEST-1-slug"


def _state(name: str) -> dict[str, Any]:
    worktree = {
        "path": WORKTREE, "role": "developer", "sha": SHA, "branch": BRANCH,
        "purpose": "desarrollo", "created_at": "2026-01-01T00:00:00Z",
    }  # fmt: skip
    return {
        "schema_version": 1, "state": name, "task_id": "TEST-1", "environment": "dev",
        "rework_round": 0, "candidate_rework_round": 0, "rollback_attempted": False, "refs": {},
        "sessions": {"developer": None, "reviewer": None, "deployer": None},
        "worktrees": [worktree], "updated_at": "2026-01-01T00:00:00Z", "last_transition": None,
        "history": [],
    }  # fmt: skip


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(name: str) -> None:
        monkeypatch.setattr(common, "load_state", lambda root: _state(name))
        monkeypatch.setattr(common, "load_current_task", lambda root: None)

    return _set


def _decide(command: str) -> tuple[bool, str]:
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(REAL_ROOT / WORKTREE),
    }
    return guard.decide(REAL_ROOT, event, {})


@pytest.mark.parametrize("state", ["NEW", "DEVELOPING", "IDLE", "REVIEWING"])
@pytest.mark.parametrize(
    "command",
    [
        "which python python3 gh git",
        "command -v gh && gh --version",
        "echo 'usa gh pr merge solo el deployer'",
        "grep -rn 'gh pr' docs/",
        "git log --oneline --grep='fix gh pr create'",
    ],
)
def test_mentioning_gh_is_not_running_it(state_as, state: str, command: str) -> None:
    state_as(state)
    allowed, reason = _decide(command)
    assert allowed, reason


def test_a_real_gh_action_is_still_judged_by_role_and_state(state_as) -> None:
    state_as("DEVELOPING")
    assert _decide("gh pr view 5 --json headRefOid")[0]
    assert _decide("gh pr create --base main --head " + BRANCH + ' --title "t" --body "b"')[0]
    allowed, reason = _decide(f"gh pr merge 5 --squash --match-head-commit {SHA}")
    assert not allowed and "pr merge" in reason


def test_every_gh_in_a_command_line_is_judged_not_only_the_first(state_as) -> None:
    state_as("DEVELOPING")
    chained = f"gh pr view 5 && gh pr merge 5 --squash --match-head-commit {SHA}"
    allowed, reason = _decide(chained)
    assert not allowed and "pr merge" in reason
    allowed, _ = _decide(f"echo ok; gh pr view 5; gh pr merge 5 --squash --match-head-commit {SHA}")
    assert not allowed


def test_gh_inside_a_shell_wrapper_is_still_judged(state_as) -> None:
    state_as("DEVELOPING")
    for command in (
        f'bash -c "gh pr merge 5 --squash --match-head-commit {SHA}"',
        f"env GH_PAGER=cat gh pr merge 5 --squash --match-head-commit {SHA}",
    ):
        assert not _decide(command)[0], command


def test_human_states_still_refuse_any_gh(state_as) -> None:
    state_as("IDLE")
    allowed, reason = _decide("gh pr view 5")
    assert not allowed and "no permitido en estado" in reason

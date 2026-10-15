"""merge_reviewed_pr.py merges the PR the Reviewer approved and nothing else.

The command takes no arguments, so a permission rule for exactly that command cannot be steered to
another PR or SHA: both come from the harness evidence and are re-checked against GitHub. GitHub is
faked with a runner; nothing here touches the network or the real repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.harness import common, guard, merge_reviewed_pr
from tests.harness.conftest import REAL_ROOT, write_json

SHA = "a" * 40
OTHER_SHA = "b" * 40
MERGE_COMMIT = "c" * 40
REPO = "org/repo"
TASK = "T-1"


def _check_runs(*results: str) -> list[dict[str, Any]]:
    return [
        {"__typename": "CheckRun", "name": f"job-{i}", "status": "COMPLETED", "conclusion": result}
        for i, result in enumerate(results)
    ]


def _pr(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "number": 69,
        "state": "OPEN",
        "headRefOid": SHA,
        "baseRefName": "main",
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": _check_runs("SUCCESS", "SUCCESS", "SUCCESS"),
        "mergeCommit": None,
    }
    data.update(overrides)
    return data


def _merged() -> dict[str, Any]:
    return _pr(state="MERGED", mergeCommit={"oid": MERGE_COMMIT})


class FakeGh:
    """Answers `gh pr view` from a queue and records every command; fails on anything else."""

    def __init__(self, views: list[dict[str, Any]], merge_code: int = 0, merge_error: str = ""):
        self.views = list(views)
        self.merge_code = merge_code
        self.merge_error = merge_error
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], timeout: float) -> tuple[int, str, str]:
        self.calls.append(command)
        if command[:3] == ["gh", "pr", "view"]:
            return 0, json.dumps(self.views.pop(0)), ""
        if command[:3] == ["gh", "pr", "merge"]:
            return self.merge_code, "", self.merge_error
        raise AssertionError(f"comando inesperado: {command}")

    @property
    def merges(self) -> list[list[str]]:
        return [call for call in self.calls if call[:3] == ["gh", "pr", "merge"]]


def _project(
    tmp_path: Path,
    *,
    state: str = "MERGING",
    decision: str = "APPROVED",
    review_pr: int = 69,
    review_sha: str = SHA,
    dev_pr: int = 69,
    dev_sha: str = SHA,
) -> Path:
    root = tmp_path / "project"
    (root / "harness").mkdir(parents=True)
    (root / "evidence" / TASK).mkdir(parents=True)
    (root / "harness" / "project-profile.yaml").write_text(
        f"project:\n  id: t\n  repository: {REPO}\n  default_branch: main\n", encoding="utf-8"
    )
    write_json(
        root / "evidence" / TASK / "review-01.json",
        {
            "kind": "review",
            "task_id": TASK,
            "decision": decision,
            "reviewed_sha": review_sha,
            "pr_number": review_pr,
        },
    )
    write_json(
        root / "evidence" / TASK / "developer-01.json",
        {"kind": "developer", "task_id": TASK, "head_sha": dev_sha, "pr_number": dev_pr},
    )
    write_json(
        root / "harness" / "state.json",
        {
            "state": state,
            "task_id": TASK,
            "refs": {
                "review_evidence": f"evidence/{TASK}/review-01.json",
                "developer_evidence": f"evidence/{TASK}/developer-01.json",
            },
        },
    )
    return root


def test_merges_exactly_the_reviewed_pr_and_sha(tmp_path: Path) -> None:
    gh = FakeGh([_pr(), _merged()])
    result = merge_reviewed_pr.merge(_project(tmp_path), runner=gh)
    assert result == merge_reviewed_pr.Result(69, SHA, MERGE_COMMIT, already_merged=False)
    assert gh.merges == [
        ["gh", "pr", "merge", "69", "--repo", REPO, "--squash", "--match-head-commit", SHA]
    ]


def test_a_pr_already_merged_at_the_reviewed_sha_is_reported_not_merged_twice(
    tmp_path: Path,
) -> None:
    gh = FakeGh([_merged()])
    result = merge_reviewed_pr.merge(_project(tmp_path), runner=gh)
    assert result.already_merged and result.merge_commit == MERGE_COMMIT
    assert gh.merges == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": "DEVELOPING"},
        {"state": "REVIEWING"},
        {"state": "IDLE"},
        {"decision": "REJECTED"},
        {"review_pr": 70},
        {"dev_pr": 70},
        {"dev_sha": OTHER_SHA},
        {"review_sha": "no-es-un-sha"},
    ],
)
def test_refuses_without_an_approved_review_in_merging_and_never_calls_gh(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    gh = FakeGh([_pr()])
    with pytest.raises(merge_reviewed_pr.Refused):
        merge_reviewed_pr.merge(_project(tmp_path, **overrides), runner=gh)
    assert gh.calls == []


def test_refuses_when_the_evidence_is_missing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "evidence" / TASK / "review-01.json").unlink()
    with pytest.raises(merge_reviewed_pr.Refused):
        merge_reviewed_pr.merge(root, runner=FakeGh([_pr()]))


@pytest.mark.parametrize(
    ("view", "fragment"),
    [
        (_pr(headRefOid=OTHER_SHA), "no es el SHA revisado"),
        (_merged() | {"headRefOid": OTHER_SHA}, "no es el SHA revisado"),
        (_pr(state="CLOSED"), "no esta abierto"),
        (_pr(baseRefName="develop"), "no apunta a main"),
        (_pr(mergeable="CONFLICTING"), "MERGEABLE y CLEAN"),
        (_pr(mergeStateStatus="BEHIND"), "MERGEABLE y CLEAN"),
        (_pr(mergeStateStatus="UNSTABLE"), "MERGEABLE y CLEAN"),
        (_pr(statusCheckRollup=[]), "ningun check"),
        (_pr(statusCheckRollup=None), "ningun check"),
        (_pr(statusCheckRollup=_check_runs("SUCCESS", "FAILURE")), "job-1"),
        (
            _pr(
                statusCheckRollup=[
                    {"__typename": "CheckRun", "name": "slow", "status": "IN_PROGRESS"}
                ]
            ),
            "slow",
        ),
        (
            _pr(
                statusCheckRollup=[
                    {"__typename": "StatusContext", "context": "ci", "state": "FAILURE"}
                ]
            ),
            "ci",
        ),
    ],
)
def test_refuses_when_github_does_not_confirm_a_clean_reviewed_pr(
    tmp_path: Path, view: dict[str, Any], fragment: str
) -> None:
    gh = FakeGh([view])
    with pytest.raises(merge_reviewed_pr.Refused, match=fragment):
        merge_reviewed_pr.merge(_project(tmp_path), runner=gh)
    assert gh.merges == []


def test_neutral_skipped_and_status_context_success_count_as_passing(tmp_path: Path) -> None:
    rollup = _check_runs("SUCCESS", "NEUTRAL", "SKIPPED") + [
        {"__typename": "StatusContext", "context": "legacy", "state": "SUCCESS"}
    ]
    gh = FakeGh([_pr(statusCheckRollup=rollup), _merged()])
    assert merge_reviewed_pr.merge(_project(tmp_path), runner=gh).merge_commit == MERGE_COMMIT


def test_a_failed_gh_merge_is_reported_as_a_failure_not_a_refusal(tmp_path: Path) -> None:
    gh = FakeGh([_pr()], merge_code=1, merge_error="GraphQL: Pull Request is not mergeable")
    with pytest.raises(merge_reviewed_pr.MergeFailed, match="not mergeable"):
        merge_reviewed_pr.merge(_project(tmp_path), runner=gh)
    assert len(gh.merges) == 1


def test_gh_success_without_a_merged_pr_is_a_failure(tmp_path: Path) -> None:
    gh = FakeGh([_pr(), _pr()])
    with pytest.raises(merge_reviewed_pr.MergeFailed, match="no figura MERGED"):
        merge_reviewed_pr.merge(_project(tmp_path), runner=gh)


def test_a_missing_gh_cli_refuses_without_merging(tmp_path: Path) -> None:
    def no_gh(command: list[str], timeout: float) -> tuple[int, str, str]:
        raise FileNotFoundError(command[0])

    with pytest.raises(merge_reviewed_pr.Refused, match="gh"):
        merge_reviewed_pr.merge(_project(tmp_path), runner=no_gh)


def test_the_command_takes_no_arguments_so_it_cannot_be_pointed_elsewhere(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert merge_reviewed_pr.main(["70"]) == 2
    assert merge_reviewed_pr.main(["--repo", "other/repo"]) == 2
    assert "no admite argumentos" in capsys.readouterr().err


def test_main_exit_codes_and_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(common, "ROOT", _project(tmp_path))
    monkeypatch.setattr(merge_reviewed_pr, "_subprocess_runner", FakeGh([_pr(), _merged()]))
    assert merge_reviewed_pr.main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == {
        "pr_number": 69, "reviewed_sha": SHA, "merge_commit": MERGE_COMMIT, "already_merged": False,
    }  # fmt: skip

    monkeypatch.setattr(
        merge_reviewed_pr, "_subprocess_runner", FakeGh([_pr(headRefOid=OTHER_SHA)])
    )
    assert merge_reviewed_pr.main([]) == 2
    assert "MERGE RECHAZADO" in capsys.readouterr().err

    monkeypatch.setattr(
        merge_reviewed_pr, "_subprocess_runner", FakeGh([_pr()], merge_code=1, merge_error="boom")
    )
    assert merge_reviewed_pr.main([]) == 3
    assert "MERGE FALLIDO" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------
# The repository guard lets the Deployer run it in MERGING (and only judges it like any script).
# ---------------------------------------------------------------------------------------------
def _state(name: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "state": name, "task_id": TASK, "environment": "dev",
        "rework_round": 0, "candidate_rework_round": 0, "rollback_attempted": False, "refs": {},
        "sessions": {"developer": None, "reviewer": None, "deployer": None},
        "worktrees": [], "updated_at": "2026-01-01T00:00:00Z", "last_transition": None,
        "history": [],
    }  # fmt: skip


def test_the_guard_allows_the_deployer_to_run_the_script_in_merging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(common, "load_state", lambda root: _state("MERGING"))
    monkeypatch.setattr(common, "load_current_task", lambda root: None)
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "python scripts/harness/merge_reviewed_pr.py"},
        "cwd": str(REAL_ROOT),
    }
    allowed, reason = guard.decide(REAL_ROOT, event, {})
    assert allowed, reason

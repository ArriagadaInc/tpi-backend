"""Section 10: aws_guard.py state-machine tests. Pure decision evaluation only
(aws_guard.evaluate never shells out); no real AWS calls, mocks/synthetic payloads only.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from scripts.harness import aws_guard, common
from tests.harness.conftest import REAL_ROOT

ENV_CLAUDE = {**os.environ, "CLAUDECODE": "1"}


def _state(state_name: str, task_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    base = {
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
    base.update(overrides)
    return base


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(state_name: str, **overrides: Any) -> None:
        monkeypatch.setattr(common, "load_state", lambda root: _state(state_name, **overrides))

    return _set


# PREPARING_DEPLOYMENT ---------------------------------------------------------
def test_preparing_deployment_read_allowed(state_as):
    state_as("PREPARING_DEPLOYMENT", task_id="T1")
    decision = aws_guard.evaluate(REAL_ROOT, ["sts", "get-caller-identity"], env_vars=ENV_CLAUDE)
    assert decision.allowed


def test_preparing_deployment_update_environment_denied(state_as):
    state_as("PREPARING_DEPLOYMENT", task_id="T1")
    decision = aws_guard.evaluate(
        REAL_ROOT,
        [
            "elasticbeanstalk",
            "update-environment",
            "--environment-name",
            "tpi-backoffice-dev-green",
            "--version-label",
            "x",
        ],
        env_vars=ENV_CLAUDE,
    )
    assert not decision.allowed
    assert any("no permitido en PREPARING_DEPLOYMENT" in r for r in decision.reasons)


# CANDIDATE_REVIEW --------------------------------------------------------------
def test_candidate_review_reviewer_read_only(state_as):
    state_as("CANDIDATE_REVIEW", task_id="T1")
    read_decision = aws_guard.evaluate(
        REAL_ROOT, ["sts", "get-caller-identity"], env_vars=ENV_CLAUDE
    )
    assert read_decision.allowed
    write_decision = aws_guard.evaluate(
        REAL_ROOT,
        ["s3api", "put-object", "--bucket", "x", "--key", "x", "--body", "x"],
        env_vars=ENV_CLAUDE,
    )
    assert not write_decision.allowed


# WAITING_HUMAN_APPROVAL ---------------------------------------------------------
def test_waiting_human_approval_no_aws_access(state_as):
    state_as("WAITING_HUMAN_APPROVAL", task_id="T1")
    decision = aws_guard.evaluate(REAL_ROOT, ["sts", "get-caller-identity"], env_vars=ENV_CLAUDE)
    assert decision.mode == "none"
    assert not decision.allowed


# DEPLOYING ------------------------------------------------------------------------
def test_deploying_only_allowlisted_operations(state_as):
    state_as("DEPLOYING", task_id="T1")
    # DEPLOYING (cutover) = @read + elasticbeanstalk update-environment only; staging
    # ops from PREPARING_DEPLOYMENT (like s3api put-object) must not carry over.
    decision = aws_guard.evaluate(
        REAL_ROOT,
        ["s3api", "put-object", "--bucket", "x", "--key", "x", "--body", "x"],
        env_vars=ENV_CLAUDE,
    )
    assert not decision.allowed
    assert any("no permitido en DEPLOYING" in r for r in decision.reasons)


def test_deploying_update_environment_requires_version_label_and_approval(state_as, monkeypatch):
    state_as("DEPLOYING", task_id="T1")
    monkeypatch.setattr(common, "load_ref", lambda root, state, key: None)
    decision = aws_guard.evaluate(
        REAL_ROOT,
        [
            "elasticbeanstalk",
            "update-environment",
            "--environment-name",
            "tpi-backoffice-dev-green",
            "--version-label",
            "x",
        ],
        env_vars=ENV_CLAUDE,
    )
    assert not decision.allowed
    assert not any(
        "no permitido en DEPLOYING" in r for r in decision.reasons
    ), "mode-level check must pass for this op"
    assert any("aprobacion humana" in r for r in decision.reasons)


def test_deploying_option_settings_denied(state_as):
    state_as("DEPLOYING", task_id="T1")
    decision = aws_guard.evaluate(
        REAL_ROOT,
        [
            "elasticbeanstalk",
            "update-environment",
            "--environment-name",
            "tpi-backoffice-dev-green",
            "--option-settings",
            "Namespace=aws:elasticbeanstalk:application,OptionName=X,Value=Y",
        ],
        env_vars=ENV_CLAUDE,
    )
    assert not decision.allowed
    assert any("option-settings" in r for r in decision.reasons)


def test_deploying_iam_denied(state_as):
    state_as("DEPLOYING", task_id="T1")
    decision = aws_guard.evaluate(REAL_ROOT, ["iam", "list-users"], env_vars=ENV_CLAUDE)
    assert not decision.allowed
    assert any("iam" in r for r in decision.reasons)


def test_deploying_route53_denied(state_as):
    state_as("DEPLOYING", task_id="T1")
    decision = aws_guard.evaluate(REAL_ROOT, ["route53", "list-hosted-zones"], env_vars=ENV_CLAUDE)
    assert not decision.allowed
    assert any("route53" in r for r in decision.reasons)


def test_deploying_delete_denied(state_as):
    state_as("DEPLOYING", task_id="T1")
    decision = aws_guard.evaluate(
        REAL_ROOT,
        [
            "elasticbeanstalk",
            "delete-application-version",
            "--application-name",
            "x",
            "--version-label",
            "y",
        ],
        env_vars=ENV_CLAUDE,
    )
    assert not decision.allowed
    assert any("prohibida" in r for r in decision.reasons)


# VERIFYING ---------------------------------------------------------------------
def test_verifying_read_allowed_write_denied(state_as):
    state_as("VERIFYING", task_id="T1")
    read_decision = aws_guard.evaluate(
        REAL_ROOT, ["elasticbeanstalk", "describe-environments"], env_vars=ENV_CLAUDE
    )
    assert read_decision.allowed
    write_decision = aws_guard.evaluate(
        REAL_ROOT,
        ["elasticbeanstalk", "update-environment", "--environment-name", "x"],
        env_vars=ENV_CLAUDE,
    )
    assert not write_decision.allowed


# DONE / BLOCKED_HUMAN ------------------------------------------------------------
@pytest.mark.parametrize("state_name", ["DONE", "BLOCKED_HUMAN"])
def test_terminal_states_deny_all_aws(state_as, state_name):
    state_as(state_name, task_id=None if state_name == "BLOCKED_HUMAN" else "T1")
    decision = aws_guard.evaluate(REAL_ROOT, ["sts", "get-caller-identity"], env_vars=ENV_CLAUDE)
    assert decision.mode == "none"
    assert not decision.allowed


# D6: maintenance never changes any of the above ----------------------------------
@pytest.mark.parametrize(
    "state_name,tokens",
    [
        ("IDLE", ["sts", "get-caller-identity"]),
        ("BLOCKED_HUMAN", ["sts", "get-caller-identity"]),
        (
            "PREPARING_DEPLOYMENT",
            ["s3api", "put-object", "--bucket", "x", "--key", "x", "--body", "x"],
        ),
        ("DEPLOYING", ["elasticbeanstalk", "update-environment", "--environment-name", "x"]),
    ],
)
def test_maintenance_never_changes_aws_decision(state_as, state_name, tokens):
    state_as(state_name, task_id="T1" if state_name not in ("IDLE", "BLOCKED_HUMAN") else None)
    without = aws_guard.evaluate(REAL_ROOT, tokens, env_vars=ENV_CLAUDE)
    with_maint = aws_guard.evaluate(
        REAL_ROOT, tokens, env_vars={**ENV_CLAUDE, "TPI_HARNESS_MAINTENANCE": "1"}
    )
    assert without.mode == with_maint.mode
    assert without.allowed == with_maint.allowed

"""Harness v1.1: aws_guard --help, minimal ECR reads, strict count-only logs, DENIED latch.

Pure decision evaluation (aws_guard.evaluate never shells out). No real AWS.
"""

from __future__ import annotations

import pytest

from scripts.harness import aws_guard, common, denials
from tests.harness.conftest import REAL_ROOT
from tests.harness.test_aws_guard import ENV_CLAUDE, _state

APP_DIGEST = "imageDigest=sha256:" + "0c20c5d7" * 8
CADDY_DIGEST = "imageDigest=sha256:" + "cd1adaf8" * 8
LOG_GROUP = (
    "/aws/elasticbeanstalk/tpi-backoffice-dev-green/var/log/eb-docker/containers/"
    "eb-current-app/stdouterr.log"
)


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(state_name: str, **overrides) -> None:
        monkeypatch.setattr(common, "load_state", lambda root: _state(state_name, **overrides))

    return _set


def _evaluate(tokens: list[str]) -> aws_guard.Decision:
    return aws_guard.evaluate(REAL_ROOT, tokens, env_vars=ENV_CLAUDE)


# ---------------------------------------------------------------------------
# --help: local only
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_is_local_exit_zero_without_state_aws_or_audit(monkeypatch, capsys, flag):
    def boom(*args, **kwargs):
        raise AssertionError("--help must not read state, evaluate, audit or run AWS")

    for name in ("run", "evaluate", "_audit", "_subprocess_runner"):
        monkeypatch.setattr(aws_guard, name, boom)
    monkeypatch.setattr(common, "load_state", boom)
    assert aws_guard.main([flag]) == 0
    assert "aws_guard.py" in capsys.readouterr().out


def test_help_with_other_tokens_keeps_strict_validation(state_as):
    state_as("VERIFYING", task_id="T1")
    decision = _evaluate(["ecr", "describe-images", "--help"])
    assert not decision.allowed


def test_missing_service_operation_still_denied(state_as):
    state_as("VERIFYING", task_id="T1")
    assert not _evaluate(["--debug"]).allowed


# ---------------------------------------------------------------------------
# ECR reads missing in the H3.3.6 dogfood
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state_name", ["CANDIDATE_REVIEW", "VERIFYING", "PREPARING_DEPLOYMENT"])
@pytest.mark.parametrize(
    "tokens",
    [
        [
            "ecr",
            "describe-image-scan-findings",
            "--repository-name",
            "tpi-dev-app",
            "--image-id",
            APP_DIGEST,
            "--query",
            "imageScanFindings.findingSeverityCounts",
        ],
        [
            "ecr",
            "describe-image-scan-findings",
            "--repository-name",
            "tpi-dev-caddy",
            "--image-id",
            CADDY_DIGEST,
        ],
        [
            "ecr",
            "describe-image-scan-findings",
            "--repository-name",
            "tpi-dev-app",
            "--image-id",
            "imageTag=h3-3-6-5f5b3d3",
        ],
        ["ecr", "describe-repositories", "--repository-names", "tpi-dev-app", "tpi-dev-caddy"],
        ["ecr", "describe-repositories", "--repository-names", "tpi-dev-app"],
    ],
)
def test_new_ecr_reads_allowed_with_dev_scope(state_as, state_name, tokens):
    role_state = {"CANDIDATE_REVIEW": "reviewer"}.get(state_name, "deployer")
    state_as(state_name, task_id="T1")
    decision = _evaluate(tokens)
    assert decision.allowed, decision.reasons
    assert decision.role == role_state
    assert decision.argv[-5:-1] == ["--profile", "tpi-dev", "--region", "us-east-2"] or (
        "--profile" in decision.argv and "us-east-2" in decision.argv
    )


@pytest.mark.parametrize(
    "tokens,reason",
    [
        (
            [
                "ecr",
                "describe-image-scan-findings",
                "--repository-name",
                "other-repo",
                "--image-id",
                APP_DIGEST,
            ],
            "fuera del entorno DEV",
        ),
        (
            ["ecr", "describe-image-scan-findings", "--repository-name", "tpi-dev-app"],
            "requiere --image-id",
        ),
        (
            [
                "ecr",
                "describe-image-scan-findings",
                "--repository-name",
                "tpi-dev-app",
                "--image-id",
                "imageDigest=sha256:zz",
            ],
            "imageDigest",
        ),
        (
            [
                "ecr",
                "describe-image-scan-findings",
                "--repository-name",
                "tpi-dev-app",
                "--image-id",
                APP_DIGEST,
                "--registry-id",
                "123",
            ],
            "opcion no permitida",
        ),
        (["ecr", "describe-repositories"], "requiere --repository-names"),
        (
            ["ecr", "describe-repositories", "--repository-names", "tpi-dev-app", "prod-app"],
            "fuera del entorno DEV",
        ),
        (
            [
                "ecr",
                "describe-repositories",
                "--repository-names",
                "tpi-dev-app",
                "--region",
                "us-east-1",
            ],
            "--region debe ser",
        ),
        (
            [
                "ecr",
                "describe-repositories",
                "--repository-names",
                "tpi-dev-app",
                "--profile",
                "prod",
            ],
            "--profile debe ser",
        ),
    ],
)
def test_ecr_reads_outside_scope_denied(state_as, tokens, reason):
    state_as("CANDIDATE_REVIEW", task_id="T1")
    decision = _evaluate(tokens)
    assert not decision.allowed
    assert any(reason in r for r in decision.reasons), decision.reasons


@pytest.mark.parametrize(
    "tokens",
    [
        [
            "ecr",
            "batch-delete-image",
            "--repository-name",
            "tpi-dev-app",
            "--image-ids",
            APP_DIGEST,
        ],
        ["ecr", "put-image", "--repository-name", "tpi-dev-app"],
        ["ecr", "delete-repository", "--repository-name", "tpi-dev-app"],
        ["ecr", "put-lifecycle-policy", "--repository-name", "tpi-dev-app"],
        ["ecr", "start-image-scan", "--repository-name", "tpi-dev-app", "--image-id", APP_DIGEST],
        ["ecr", "set-repository-policy", "--repository-name", "tpi-dev-app"],
        ["ecr", "describe-registry"],
    ],
)
@pytest.mark.parametrize("state_name", ["CANDIDATE_REVIEW", "VERIFYING"])
def test_ecr_write_or_other_family_members_denied(state_as, tokens, state_name):
    state_as(state_name, task_id="T1")
    assert not _evaluate(tokens).allowed


def test_ecr_reads_denied_for_developer_and_human_states(state_as):
    tokens = ["ecr", "describe-repositories", "--repository-names", "tpi-dev-app"]
    for state_name in ("DEVELOPING", "REVIEWING", "WAITING_HUMAN_APPROVAL", "IDLE"):
        state_as(state_name, task_id="T1")
        assert not _evaluate(tokens).allowed, state_name


# ---------------------------------------------------------------------------
# Logs stay count-only (P1-8)
# ---------------------------------------------------------------------------
def _logs(query: str | None, pattern: str = "hash") -> list[str]:
    tokens = [
        "logs",
        "filter-log-events",
        "--log-group-name",
        LOG_GROUP,
        "--filter-pattern",
        pattern,
        "--start-time",
        "1790177516000",
    ]
    return tokens + (["--query", query] if query is not None else [])


@pytest.mark.parametrize("query", ["length(events)", " length( events ) "])
def test_logs_count_only_allowed(state_as, query):
    state_as("VERIFYING", task_id="T1")
    assert _evaluate(_logs(query)).allowed


@pytest.mark.parametrize(
    "query",
    [
        None,
        "events[].timestamp",  # denied in the H3.3.6 dogfood: keep it that way
        "events[].message",
        "events[?length(message)>`0`].message",  # v1 gap: contained 'length(' but dumps lines
        "length(events) && events",
        "{n: length(events), e: events}",
    ],
)
def test_logs_line_access_denied(state_as, query):
    state_as("VERIFYING", task_id="T1")
    decision = _evaluate(_logs(query))
    assert not decision.allowed
    assert any("length(events)" in r for r in decision.reasons)


# ---------------------------------------------------------------------------
# DENIED latch (P0-1)
# ---------------------------------------------------------------------------
def test_aws_guard_denied_writes_session_latch(tmp_harness_repo, monkeypatch):
    monkeypatch.setenv(denials.ENV_VAR, "claude-202609230000-deployer-supaws001")
    monkeypatch.setenv("CLAUDECODE", "1")
    code = aws_guard.run(
        tmp_harness_repo,
        ["elasticbeanstalk", "terminate-environment", "--environment-name", "x"],
        verify_repo=False,
    )
    assert code == 2
    records = denials.read(tmp_harness_repo, "claude-202609230000-deployer-supaws001")
    assert records and records[0]["source"] == "aws_guard"
    assert records[0]["label"] == "elasticbeanstalk terminate-environment"


def test_aws_guard_manual_mode_writes_no_latch(tmp_harness_repo, monkeypatch):
    monkeypatch.delenv(denials.ENV_VAR, raising=False)
    aws_guard.run(tmp_harness_repo, ["iam", "list-users"], verify_repo=False)
    assert not (tmp_harness_repo / denials.DENIALS_DIR).exists()

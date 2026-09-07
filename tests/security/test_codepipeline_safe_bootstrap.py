"""Guardrails for the deliberately failed CodePipeline bootstrap execution."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/release/bootstrap_dev_codepipeline.sh"
VALIDATOR = ROOT / "scripts/release/validate_dev_codepipeline_bootstrap.sh"
RUNBOOK = ROOT / "docs/DEV_EB_DEPLOYMENT_RUNBOOK.md"


def test_bootstrap_proves_source_absence_before_create_pipeline() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    head_object = script.index("aws s3api head-object")
    create_pipeline = script.index("aws codepipeline create-pipeline")

    assert head_object < create_pipeline
    assert 'source_status" -eq 0' in script
    assert "404" in script
    assert "unable to prove bootstrap source absence" in script
    assert "aws s3api delete-object" not in script


def test_bootstrap_disables_promote_and_rejects_any_promote_execution() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")

    create_pipeline = script.index("aws codepipeline create-pipeline")
    disable_promote = script.index("aws codepipeline disable-stage-transition")
    inspect_execution = script.index("aws codepipeline list-pipeline-executions")

    assert create_pipeline < disable_promote < inspect_execution
    assert '--stage-name "$PROMOTE_STAGE"' in script
    assert "--transition-type Inbound" in script
    assert 'bash "$BOOTSTRAP_VALIDATOR" "$execution_id"' in script
    assert "inboundTransitionState.enabled == false" in validator
    assert 'select(.stageName == "Promote")' in validator
    assert 'fail "unsafe bootstrap: execution reached Promote"' in validator


def test_bootstrap_requires_expected_source_failure_and_preserves_eb() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")

    assert 'test "$execution_status" = "Failed"' in script
    assert '.pipelineExecution.trigger.triggerType == "CreatePipeline"' in validator
    assert ".actionExecutionDetails | length == 1" in validator
    assert '.[0].stageName == "Source"' in validator
    assert '.[0].actionName == "ApprovedReleaseSource"' in validator
    assert '.[0].status == "Failed"' in validator
    assert ".[0].VersionLabel == $version" in validator
    assert '.[0].Status == "Ready"' in validator
    assert '.[0].Health == "Green"' in validator
    assert '.[0].HealthStatus == "Ok"' in validator
    assert '.[0].Status != "FAILED"' in validator
    assert ".[0].SourceBundle.S3Bucket == $bucket" in validator
    assert ".[0].SourceBundle.S3Key == $key" in validator
    assert "start-pipeline-execution" not in script
    assert "update-environment" not in script
    assert "create-application-version" not in script


def test_validator_rechecks_exact_source_absence_after_failed_source() -> None:
    validator = VALIDATOR.read_text(encoding="utf-8")

    action_check = validator.index(".actionExecutionDetails | length == 1")
    head_object = validator.index("aws s3api head-object")

    assert action_check < head_object
    assert 'source_status" -eq 0' in validator
    assert "404" in validator
    assert "NotFound" in validator
    assert "NoSuchKey" in validator
    assert "unable to prove post-bootstrap source absence" in validator


def test_validator_treats_source_messages_as_optional_diagnostics() -> None:
    validator = VALIDATOR.read_text(encoding="utf-8")

    assert "executionResult.errorDetails.message" in validator
    assert "externalExecutionSummary" in validator
    assert "// empty" in validator
    assert "errorDetails.message | length" not in validator


def test_validator_uses_only_read_only_aws_operations() -> None:
    validator = VALIDATOR.read_text(encoding="utf-8")
    aws_operations = set(
        re.findall(r"(?:^|\$\()aws ([a-z0-9-]+) ([a-z0-9-]+)", validator, re.MULTILINE)
    )

    assert aws_operations == {
        ("sts", "get-caller-identity"),
        ("codepipeline", "get-pipeline"),
        ("codepipeline", "get-pipeline-state"),
        ("codepipeline", "get-pipeline-execution"),
        ("codepipeline", "list-action-executions"),
        ("s3api", "head-object"),
        ("elasticbeanstalk", "describe-environments"),
        ("elasticbeanstalk", "describe-application-versions"),
    }

    for forbidden in (
        "create-pipeline",
        "update-pipeline",
        "enable-stage-transition",
        "disable-stage-transition",
        "start-pipeline-execution",
        "update-environment",
        "create-application-version",
        "put-object",
        "delete-object",
    ):
        assert forbidden not in validator


def test_runbook_documents_automatic_failed_source_bootstrap() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "CreatePipeline genera una ejecución automática" in runbook
    assert "fallar en `Source`" in runbook
    assert "cero action executions en `Promote`" in runbook
    assert "bootstrap_dev_codepipeline.sh" in runbook
    assert "validate_dev_codepipeline_bootstrap.sh" in runbook
    assert "mensaje de error de AWS es" in runbook
    assert "diagnóstica opcional y puede estar ausente" in runbook
    assert "crear el pipeline V2 sin ejecutarlo" not in runbook

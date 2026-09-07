"""Guardrails for the deliberately failed CodePipeline bootstrap execution."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/release/bootstrap_dev_codepipeline.sh"
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

    create_pipeline = script.index("aws codepipeline create-pipeline")
    disable_promote = script.index("aws codepipeline disable-stage-transition")
    inspect_execution = script.index("aws codepipeline list-pipeline-executions")

    assert create_pipeline < disable_promote < inspect_execution
    assert '--stage-name "$PROMOTE_STAGE"' in script
    assert "--transition-type Inbound" in script
    assert "inboundTransitionState.enabled == false" in script
    assert 'select(.stageName == "Promote")' in script
    assert 'fail "unsafe bootstrap: execution reached Promote"' in script


def test_bootstrap_requires_expected_source_failure_and_preserves_eb() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'test "$execution_status" = "Failed"' in script
    assert 'test "$execution_trigger" = "CreatePipeline"' in script
    assert '.stageName == "Source" and .status == "Failed"' in script
    assert ".[0].VersionLabel == $version" in script
    assert '.[0].Status == "Ready"' in script
    assert '.[0].Health == "Green"' in script
    assert '.[0].HealthStatus == "Ok"' in script
    assert '.[0].Status != "FAILED"' in script
    assert ".[0].SourceBundle.S3Bucket == $bucket" in script
    assert ".[0].SourceBundle.S3Key == $key" in script
    assert "start-pipeline-execution" not in script
    assert "update-environment" not in script
    assert "create-application-version" not in script


def test_runbook_documents_automatic_failed_source_bootstrap() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "CreatePipeline genera una ejecución automática" in runbook
    assert "fallar en `Source`" in runbook
    assert "no llegó a `Promote`" in runbook
    assert "bootstrap_dev_codepipeline.sh" in runbook
    assert "crear el pipeline V2 sin ejecutarlo" not in runbook

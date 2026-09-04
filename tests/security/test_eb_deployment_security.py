"""Security guardrails for the CodePipeline-based DEV promotion plane."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-dev-eb.yml"


def _load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _actions(policy: dict) -> set[str]:
    result: set[str] = set()
    for statement in policy["Statement"]:
        actions = statement["Action"]
        result.update(actions if isinstance(actions, list) else [actions])
    return result


def test_github_release_trust_is_main_only() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-release-role-trust.json")
    condition = policy["Statement"][0]["Condition"]["StringEquals"]

    assert condition == {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": (
            "repo:ArriagadaInc@37077654/tpi-backend@1318709295:ref:refs/heads/main"
        ),
    }
    assert "*" not in json.dumps(policy)


def test_github_release_role_cannot_administer_eb_or_buckets() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-release.json")
    actions = _actions(policy)

    assert actions == {
        "s3:PutObject",
        "s3:GetObject",
        "s3:GetObjectVersion",
        "codepipeline:StartPipelineExecution",
        "codepipeline:GetPipelineExecution",
        "codepipeline:GetPipelineState",
        "codepipeline:ListActionExecutions",
    }
    serialized = json.dumps(policy)
    assert "elasticbeanstalk:" not in serialized
    assert "s3:CreateBucket" not in serialized
    assert "s3:PutBucketPolicy" not in serialized
    assert "s3:PutBucketPublicAccessBlock" not in serialized
    assert "s3:PutBucketOwnershipControls" not in serialized
    assert "AdministratorAccess-AWSElasticBeanstalk" not in serialized
    assert all(statement["Resource"] != "*" for statement in policy["Statement"])


def test_codepipeline_trust_is_service_only() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb-role-trust.json")
    statement = policy["Statement"][0]

    assert statement["Principal"] == {"Service": "codepipeline.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"
    assert "Federated" not in json.dumps(policy)


def test_pipeline_targets_only_approved_dev_environment_and_candidate() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    serialized = json.dumps(pipeline)

    assert pipeline["name"] == "tpi-backoffice-dev-promotion"
    assert pipeline["pipelineType"] == "V2"
    assert "tpi-backoffice-dev-green" in serialized
    assert "tpi-backoffice" in serialized
    assert "h3-3-crm-web-28cf009-r1" in serialized
    assert "28cf009137ada707540d9ee7eba01dc45a9a260e" in serialized
    assert "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045" in serialized
    assert "sha256:45331812c93bcf905b2ae8ad9eedff9eba5f63bc4afbfd5639af85c78bb3b6ce" in serialized
    assert "sha256:1d7c114bf0bb98e8ed2034a37997ee4d9e4aec98cbba58dc00581bbf6b6dc4e2" in serialized
    source = pipeline["stages"][0]["actions"][0]["configuration"]
    assert source["S3ObjectKey"] == ("promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip")
    assert source["AllowOverrideForS3ObjectKey"] == "false"
    assert 'PollForSourceChanges": "false' in serialized

    commands = pipeline["stages"][1]["actions"][0]["commands"]
    assert any("trusted-tooling/v1/verify_frozen_candidate.sh" in item for item in commands)
    assert any("trusted-tooling/v1/promote_eb_candidate.py" in item for item in commands)
    assert sum("sha256sum --check --strict" in item for item in commands) == 2
    assert "bash /tmp/verify_frozen_candidate.sh" in commands
    assert "python3 /tmp/promote_eb_candidate.py" in commands


def test_pipeline_role_scopes_eb_write_and_documents_bucket_level_boundary() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    serialized = json.dumps(policy)
    update = next(
        item for item in policy["Statement"] if item["Sid"] == "UpdateOnlyApprovedDevEnvironment"
    )
    storage = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "ElasticBeanstalkManagedStorageContract"
    )

    assert update["Resource"] == (
        "arn:aws:elasticbeanstalk:us-east-2:821656895812:environment/"
        "tpi-backoffice/tpi-backoffice-dev-green"
    )
    assert update["Condition"]["ArnEquals"]["elasticbeanstalk:FromApplicationVersion"].endswith(
        "/tpi-backoffice/h3-3-crm-web-28cf009-r1"
    )
    assert storage["Resource"] == "arn:aws:s3:::elasticbeanstalk-us-east-2-821656895812"
    assert storage["Action"] == [
        "s3:CreateBucket",
        "s3:GetBucket*",
        "s3:ListBucket",
        "s3:PutBucketPolicy",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketOwnershipControls",
    ]
    objects = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "ElasticBeanstalkManagedStorageObjectContract"
    )
    assert objects["Action"] == ["s3:Get*", "s3:Put*", "s3:Delete*"]
    assert objects["Resource"] == ("arn:aws:s3:::elasticbeanstalk-us-east-2-821656895812/*")
    assert "arn:aws:s3:::elasticbeanstalk-*" not in serialized
    assert "AdministratorAccess-AWSElasticBeanstalk" not in serialized
    assert "iam:PassRole" not in serialized


def test_workflow_uses_read_role_then_orchestrator_without_direct_eb_write() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'test "$GITHUB_REF" = "refs/heads/main"' in workflow
    assert "execute_promotion:" in workflow
    assert "default: false" in workflow
    assert "tpi-github-actions-dev-eb-role" in workflow
    assert "tpi-github-actions-dev-release-role" in workflow
    assert "start-pipeline-execution" in workflow
    assert "S3_OBJECT_VERSION_ID" in workflow
    assert "S3_OBJECT_KEY" not in workflow
    assert "update-environment" not in workflow
    assert "create-application-version" not in workflow
    assert "EB_DEPLOY_ROLE_ARN" not in workflow
    assert "Show pipeline diagnostics" in workflow
    assert "Collect independent EB postflight and events" in workflow


def test_github_cannot_write_trusted_tooling_and_source_key_is_fixed() -> None:
    release_policy = _load_json("deployment/iam/tpi-github-actions-dev-release.json")
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    release_resources = json.dumps(release_policy)
    source = pipeline["stages"][0]["actions"][0]["configuration"]

    assert "trusted-tooling" not in release_resources
    assert source == {
        "S3Bucket": "tpi-dev-release-artifacts-821656895812-us-east-2",
        "S3ObjectKey": "promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip",
        "PollForSourceChanges": "false",
        "AllowOverrideForS3ObjectKey": "false",
    }


def test_pipeline_pins_exact_trusted_tooling_hashes() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    commands = pipeline["stages"][1]["actions"][0]["commands"]
    expected = {
        "verify_frozen_candidate.sh": hashlib.sha256(
            (ROOT / "scripts/release/verify_frozen_candidate.sh")
            .read_text(encoding="utf-8")
            .encode()
        ).hexdigest(),
        "promote_eb_candidate.py": hashlib.sha256(
            (ROOT / "deployment/aws/promote_eb_candidate.py").read_text(encoding="utf-8").encode()
        ).hexdigest(),
    }

    for filename, digest in expected.items():
        verification = next(
            command for command in commands if filename in command and "sha256sum" in command
        )
        assert digest in verification
        assert hashlib.sha256(b"modified executable").hexdigest() not in verification

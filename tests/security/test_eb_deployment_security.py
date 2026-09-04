"""Guardrails for the controlled Elastic Beanstalk deployment artifacts."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-dev-eb.yml"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"


def _load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_deployment_trust_is_main_only_without_wildcards() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-eb-deploy-role-trust.json")
    condition = policy["Statement"][0]["Condition"]["StringEquals"]

    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert (
        condition["token.actions.githubusercontent.com:sub"]
        == "repo:ArriagadaInc@37077654/tpi-backend@1318709295:ref:refs/heads/main"
    )
    assert "*" not in json.dumps(policy)


def test_deployment_policy_is_scoped_to_approved_resources() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-eb-deploy.json")
    actions = []
    for statement in policy["Statement"]:
        statement_actions = statement["Action"]
        actions.extend(
            statement_actions if isinstance(statement_actions, list) else [statement_actions]
        )

    assert actions == [
        "elasticbeanstalk:DescribeApplications",
        "elasticbeanstalk:DescribeEnvironments",
        "elasticbeanstalk:DescribeApplicationVersions",
        "elasticbeanstalk:DescribeEvents",
        "elasticbeanstalk:CreateApplicationVersion",
        "elasticbeanstalk:UpdateEnvironment",
        "s3:CreateBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:GetObjectVersion",
    ]
    serialized = json.dumps(policy)
    assert "iam:PassRole" not in serialized
    assert "elasticbeanstalk:UpdateConfigurationTemplate" not in serialized
    assert "s3:DeleteObject" not in serialized
    s3_statement = next(
        statement
        for statement in policy["Statement"]
        if statement["Sid"] == "ReadWriteOnlyDevReleaseBundles"
    )
    assert s3_statement["Action"] == [
        "s3:PutObject",
        "s3:GetObject",
        "s3:GetObjectVersion",
    ]
    assert s3_statement["Resource"] == (
        "arn:aws:s3:::elasticbeanstalk-us-east-2-821656895812/tpi-backoffice/dev-releases/*"
    )
    assert "s3:*" not in serialized
    assert "ListAllMyBuckets" not in serialized
    assert "s3:PutObjectAcl" not in serialized
    assert "s3:GetObjectAcl" not in serialized
    bucket_statement = next(
        statement
        for statement in policy["Statement"]
        if statement["Sid"] == "AllowElasticBeanstalkStorageBucketCheck"
    )
    assert bucket_statement["Action"] == "s3:CreateBucket"
    assert bucket_statement["Resource"] == ("arn:aws:s3:::elasticbeanstalk-us-east-2-821656895812")
    assert "arn:aws:s3:::*" not in serialized
    assert "arn:aws:s3:::elasticbeanstalk-*" not in serialized
    assert "s3:DeleteBucket" not in serialized
    assert "s3:PutBucketPolicy" not in serialized
    assert "s3:PutBucketAcl" not in serialized
    assert "s3:PutBucketOwnershipControls" not in serialized
    assert "s3:PutBucketPublicAccessBlock" not in serialized
    assert (
        "arn:aws:elasticbeanstalk:us-east-2:821656895812:environment/tpi-backoffice/tpi-backoffice-dev-green"
        in serialized
    )


def test_deployment_workflow_is_main_only_and_pins_frozen_candidate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in workflow
    assert "execute_deploy:" in workflow
    assert "type: boolean" in workflow
    assert "default: false" in workflow
    checkout_start = workflow.index("Checkout deployment tooling")
    download_start = workflow.index("Download approved ECR artifact")
    verify_start = workflow.index("Verify immutable candidate artifact")
    assert checkout_start < download_start < verify_start
    assert "merge-multiple: true" in workflow
    assert "bash scripts/release/verify_frozen_candidate.sh" in workflow
    assert "28cf009137ada707540d9ee7eba01dc45a9a260e" in workflow
    assert "33824477381" in workflow
    assert "9919549285" in workflow
    assert "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045" in workflow
    assert "sha256:45331812c93bcf905b2ae8ad9eedff9eba5f63bc4afbfd5639af85c78bb3b6ce" in workflow
    assert "sha256:1d7c114bf0bb98e8ed2034a37997ee4d9e4aec98cbba58dc00581bbf6b6dc4e2" in workflow
    assert "--no-auto-create-application" in workflow
    assert '--version-label "$VERSION_LABEL"' in workflow
    assert "--configuration-settings" not in workflow
    assert "--option-settings" not in workflow


def test_deployment_writes_require_explicit_execute_deploy() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for step_name in (
        "Upload approved bundle",
        "Create application version",
        "Update only the approved DEV environment",
    ):
        step_start = workflow.index(step_name)
        step_end = workflow.find("\n      - name:", step_start + 1)
        step_block = workflow[step_start : step_end if step_end != -1 else None]
        assert "if: ${{ success() && inputs.execute_deploy }}" in step_block

    assert "Validate-only completed without AWS writes" in workflow


def test_deployment_selects_role_by_execution_mode() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    read_only_start = workflow.index("Configure AWS credentials through GitHub OIDC (read-only)")
    deployment_start = workflow.index("Configure AWS credentials through GitHub OIDC (deployment)")
    preflight_start = workflow.index("Verify account and deployment preflight")

    read_only_block = workflow[read_only_start:deployment_start]
    deployment_block = workflow[deployment_start:preflight_start]

    assert "if: ${{ success() && !inputs.execute_deploy }}" in read_only_block
    assert "role-to-assume: ${{ env.EB_READ_ROLE_ARN }}" in read_only_block
    assert "tpi-github-actions-dev-eb-role" in workflow
    assert "tpi-github-actions-dev-eb-deploy-role" in workflow
    assert "if: ${{ success() && inputs.execute_deploy }}" in deployment_block
    assert "role-to-assume: ${{ env.EB_DEPLOY_ROLE_ARN }}" in deployment_block
    assert "EB_DEPLOY_ROLE_ARN" not in read_only_block
    assert "EB_READ_ROLE_ARN" not in deployment_block


def test_ci_validates_release_artifact_with_shared_verifier() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "release-tooling-validation:" in workflow
    assert "bash scripts/release/verify_frozen_candidate.sh" in workflow
    assert "rhysd/actionlint:1.7.7" in workflow


def test_deployment_workflow_uses_healthy_current_version_as_rollback() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '.[0].Status != "FAILED"' in workflow
    assert ".[0].SourceBundle != null" in workflow
    assert '--version-labels "$EXPECTED_CURRENT_VERSION"' in workflow
    assert "ROLLBACK_VERSION" not in workflow
    preflight_start = workflow.index("Verify account and deployment preflight")
    upload_start = workflow.index("Upload approved bundle")
    assert "describe-events" not in workflow[preflight_start:upload_start]


def test_deployment_workflow_processes_version_before_environment_update() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "            --process \\\n" in workflow
    assert 'case "$status" in' in workflow
    assert "PROCESSED)" in workflow
    assert "FAILED)" in workflow
    assert 'PROCESSING|"")' in workflow
    processing_start = workflow.index("Wait for application version processing")
    update_start = workflow.index("Update only the approved DEV environment")
    processing_block = workflow[processing_start:update_start]

    assert "exit 1" in processing_block
    assert "UpdateEnvironment" not in processing_block
    assert processing_start < update_start


def test_deployment_workflow_collects_events_after_update_failure() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Show deployment events after update failure" in workflow
    assert (
        "if: ${{ inputs.execute_deploy && failure() && "
        "steps.update_environment.outcome == 'success' }}" in workflow
    )

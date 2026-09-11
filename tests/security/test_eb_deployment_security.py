"""Security guardrails for the CodePipeline-based DEV promotion plane."""

import hashlib
import json
import shlex
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-dev-eb.yml"
CONTROL_PLANE_INSPECTION = ROOT / "scripts/release/inspect_dev_eb_control_plane_readonly.sh"


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
    assert "h3-3-crm-web-43101be-r1" in serialized
    assert "43101be7835088f93267bee85b0f11c8bc879867" in serialized
    assert "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb" in serialized
    assert "sha256:79737222a5901871857f59143c8dc696879b2e88aa740eb7304225ffa4cd9631" in serialized
    assert "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf" in serialized
    source = pipeline["stages"][0]["actions"][0]["configuration"]
    assert source["S3ObjectKey"] == ("promotions/h3-3-crm-web-43101be-r1/candidate-data.zip")
    assert source["AllowOverrideForS3ObjectKey"] == "false"
    assert 'PollForSourceChanges": "false' in serialized

    commands = pipeline["stages"][1]["actions"][0]["commands"]
    required_tools = commands[0]
    assert all(
        tool in required_tools
        for tool in ("aws", "python3", "bash", "jq", "sha256sum", "zipinfo", "unzip", "docker")
    )
    assert "docker compose version" in commands[1]
    assert not any(
        installer in " ".join(commands)
        for installer in ("apt-get", "apk add", "pip install", "yum install")
    )
    assert any("trusted-tooling/v1/verify_frozen_candidate.sh" in item for item in commands)
    assert any("trusted-tooling/h3-3-43101be/" in item for item in commands)
    assert sum("sha256sum --check --strict" in item for item in commands) == 2
    assert any(command.endswith("bash /tmp/verify_frozen_candidate.sh") for command in commands)
    assert any(command.endswith("python3 /tmp/promote_eb_candidate.py") for command in commands)


def test_pipeline_commands_respect_aws_quotas_and_keep_frozen_contract() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    action = pipeline["stages"][1]["actions"][0]
    commands = action["commands"]

    assert "environmentVariables" not in action
    assert 1 <= len(commands) <= 50
    assert all(1 <= len(command) <= 1000 for command in commands)

    verifier = next(
        command for command in commands if command.endswith("bash /tmp/verify_frozen_candidate.sh")
    )
    promoter = next(
        command for command in commands if command.endswith("python3 /tmp/promote_eb_candidate.py")
    )

    verifier_tokens = shlex.split(verifier)
    promoter_tokens = shlex.split(promoter)
    verifier_environment = dict(token.split("=", 1) for token in verifier_tokens[:-2])
    promoter_environment = dict(token.split("=", 1) for token in promoter_tokens[:-2])

    assert verifier_environment == {
        "ARTIFACT_DIR": "artifact",
        "BUNDLE_NAME": "tpi-dev-ecr-43101be.zip",
        "MANIFEST_NAME": "tpi-dev-ecr-43101be.manifest.json",
        "BUNDLE_SHA256": "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb",
        "SOURCE_SHA": "43101be7835088f93267bee85b0f11c8bc879867",
        "APP_IMAGE": (
            "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@"
            "sha256:79737222a5901871857f59143c8dc696879b2e88aa740eb7304225ffa4cd9631"
        ),
        "CADDY_IMAGE": (
            "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@"
            "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf"
        ),
        "TPI_ROUTE53_HOSTED_ZONE_ID": "Z07053592LX0W8GJXNI1C",
    }
    assert verifier_tokens[-2:] == ["bash", "/tmp/verify_frozen_candidate.sh"]

    assert promoter_environment == {
        "AWS_ACCOUNT_ID": "821656895812",
        "AWS_REGION": "us-east-2",
        "APPLICATION": "tpi-backoffice",
        "ENVIRONMENT": "tpi-backoffice-dev-green",
        "EXPECTED_CURRENT_VERSION": "h3-3-crm-web-28cf009-r1",
        "VERSION_LABEL": "h3-3-crm-web-43101be-r1",
        "APPROVED_BUNDLE_BUCKET": "tpi-dev-release-artifacts-821656895812-us-east-2",
        "APPROVED_BUNDLE_KEY": (
            "approved-releases/h3-3-crm-web-43101be-r1/"
            "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb.zip"
        ),
        "ARTIFACT_DIR": "artifact",
        "BUNDLE_NAME": "tpi-dev-ecr-43101be.zip",
        "SOURCE_SHA": "43101be7835088f93267bee85b0f11c8bc879867",
        "BUNDLE_SHA256": "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb",
    }
    assert promoter_tokens[-2:] == ["python3", "/tmp/promote_eb_candidate.py"]


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
    assert update["Condition"]["ArnEquals"]["elasticbeanstalk:FromApplicationVersion"] == [
        "arn:aws:elasticbeanstalk:us-east-2:821656895812:applicationversion/"
        "tpi-backoffice/h3-3-crm-web-28cf009-r1",
        "arn:aws:elasticbeanstalk:us-east-2:821656895812:applicationversion/"
        "tpi-backoffice/h3-3-crm-web-43101be-r1",
    ]
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


def test_pipeline_role_scopes_cloudformation_to_physical_dev_stack() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    cloudformation = next(
        item
        for item in policy["Statement"]
        if item["Sid"] == "OrchestrateOnlyPhysicalDevEnvironmentStack"
    )

    assert cloudformation["Resource"] == (
        "arn:aws:cloudformation:us-east-2:821656895812:stack/awseb-e-sd5gmkxr5r-stack/*"
    )
    assert set(cloudformation["Action"]) == {
        "cloudformation:DescribeStackEvents",
        "cloudformation:DescribeStackResource",
        "cloudformation:DescribeStackResources",
        "cloudformation:DescribeStacks",
        "cloudformation:GetTemplate",
        "cloudformation:ListStackResources",
        "cloudformation:SignalResource",
        "cloudformation:UpdateStack",
    }
    assert "cloudformation:CreateStack" not in _actions(policy)
    assert "cloudformation:DeleteStack" not in _actions(policy)
    assert "cloudformation:TagResource" not in _actions(policy)
    assert "cloudformation:UntagResource" not in _actions(policy)


def test_pipeline_role_models_only_observed_stack_compute_dependencies() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    statements = {statement["Sid"]: statement for statement in policy["Statement"]}

    inspection = statements["InspectOnlyObservedDevComputeResources"]
    assert inspection["Resource"] == "*"
    assert inspection["Condition"] == {"StringEquals": {"aws:RequestedRegion": "us-east-2"}}
    assert set(inspection["Action"]) == {
        "autoscaling:DescribeAutoScalingGroups",
        "autoscaling:DescribeAutoScalingInstances",
        "autoscaling:DescribeScalingActivities",
        "autoscaling:DescribeScalingProcessTypes",
        "ec2:DescribeAddresses",
        "ec2:DescribeLaunchTemplates",
        "ec2:DescribeLaunchTemplateVersions",
    }

    autoscaling = statements["UpdateOnlyObservedDevAutoScalingGroup"]
    assert autoscaling["Resource"] == (
        "arn:aws:autoscaling:us-east-2:821656895812:autoScalingGroup:*:"
        "autoScalingGroupName/awseb-e-sd5gmkxr5r-*"
    )
    assert set(autoscaling["Action"]) == {
        "autoscaling:ResumeProcesses",
        "autoscaling:SuspendProcesses",
        "autoscaling:TerminateInstanceInAutoScalingGroup",
        "autoscaling:UpdateAutoScalingGroup",
    }
    assert autoscaling["Condition"]["StringEquals"] == {
        "autoscaling:ResourceTag/aws:cloudformation:stack-name": ("awseb-e-sd5gmkxr5r-stack"),
        "aws:RequestedRegion": "us-east-2",
    }

    launch_template = statements["VersionOnlyObservedDevLaunchTemplate"]
    assert launch_template["Resource"] == (
        "arn:aws:ec2:us-east-2:821656895812:launch-template/lt-0c69191d0013fa448"
    )
    assert set(launch_template["Action"]) == {
        "ec2:CreateLaunchTemplateVersion",
        "ec2:DeleteLaunchTemplateVersions",
    }
    assert "Condition" not in launch_template

    wildcard_statements = [
        statement for statement in policy["Statement"] if statement["Resource"] == "*"
    ]
    assert {statement["Sid"] for statement in wildcard_statements} == {
        "InspectOnlyObservedDevComputeResources",
        "InspectElasticBeanstalkEnvironmentHealthLogs",
    }

    actions = _actions(policy)
    for excluded in (
        "autoscaling:CreateAutoScalingGroup",
        "autoscaling:DeleteAutoScalingGroup",
        "ec2:AllocateAddress",
        "ec2:AssociateAddress",
        "ec2:CreateLaunchTemplate",
        "ec2:DeleteLaunchTemplate",
        "ec2:DisassociateAddress",
        "ec2:ModifyLaunchTemplate",
        "ec2:ReleaseAddress",
        "ec2:RunInstances",
        "iam:PassRole",
    ):
        assert excluded not in actions
    assert not any(
        action.startswith(("elasticloadbalancing:", "rds:", "ecs:")) for action in actions
    )


def test_pipeline_role_limits_environment_health_log_permissions() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    statements = {statement["Sid"]: statement for statement in policy["Statement"]}

    inspection = statements["InspectElasticBeanstalkEnvironmentHealthLogs"]
    assert inspection == {
        "Sid": "InspectElasticBeanstalkEnvironmentHealthLogs",
        "Effect": "Allow",
        "Action": "logs:DescribeLogGroups",
        "Resource": "*",
        "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-2"}},
    }

    retention = statements["ManageOnlyDevElasticBeanstalkLogRetention"]
    assert retention == {
        "Sid": "ManageOnlyDevElasticBeanstalkLogRetention",
        "Effect": "Allow",
        "Action": "logs:PutRetentionPolicy",
        "Resource": (
            "arn:aws:logs:us-east-2:821656895812:log-group:"
            "/aws/elasticbeanstalk/tpi-backoffice-dev-green/*"
        ),
        "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-2"}},
    }

    create_log_groups = statements["CreateOnlyDevElasticBeanstalkLogGroups"]
    assert create_log_groups == {
        "Sid": "CreateOnlyDevElasticBeanstalkLogGroups",
        "Effect": "Allow",
        "Action": "logs:CreateLogGroup",
        "Resource": (
            "arn:aws:logs:us-east-2:821656895812:log-group:"
            "/aws/elasticbeanstalk/tpi-backoffice-dev-green/*"
        ),
        "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-2"}},
    }

    assert statements["WritePromotionLogs"] == {
        "Sid": "WritePromotionLogs",
        "Effect": "Allow",
        "Action": [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
        ],
        "Resource": [
            "arn:aws:logs:us-east-2:821656895812:log-group:"
            "/aws/codepipeline/tpi-backoffice-dev-promotion",
            "arn:aws:logs:us-east-2:821656895812:log-group:"
            "/aws/codepipeline/tpi-backoffice-dev-promotion:*",
        ],
    }

    log_actions = {action for action in _actions(policy) if action.startswith("logs:")}
    assert log_actions == {
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:DescribeLogGroups",
        "logs:PutLogEvents",
        "logs:PutRetentionPolicy",
    }
    assert "logs:Describe*" not in log_actions
    assert "logs:*" not in log_actions
    assert "logs:DeleteRetentionPolicy" not in log_actions
    assert "logs:DeleteLogGroup" not in log_actions
    assert "logs:PutResourcePolicy" not in log_actions


def test_update_environment_keeps_exact_application_version_condition() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    update = next(
        item for item in policy["Statement"] if item["Sid"] == "UpdateOnlyApprovedDevEnvironment"
    )

    assert update["Action"] == "elasticbeanstalk:UpdateEnvironment"
    assert update["Condition"] == {
        "ArnEquals": {
            "elasticbeanstalk:FromApplicationVersion": [
                "arn:aws:elasticbeanstalk:us-east-2:821656895812:"
                "applicationversion/tpi-backoffice/h3-3-crm-web-28cf009-r1",
                "arn:aws:elasticbeanstalk:us-east-2:821656895812:"
                "applicationversion/tpi-backoffice/h3-3-crm-web-43101be-r1",
            ]
        }
    }


def test_control_plane_inspection_is_read_only_and_scoped() -> None:
    script = CONTROL_PLANE_INSPECTION.read_text(encoding="utf-8")
    normalized = script.lower()

    assert 'readonly account_id="821656895812"' in normalized
    assert 'readonly region="us-east-2"' in normalized
    assert 'readonly stack_name="awseb-e-sd5gmkxr5r-stack"' in normalized
    assert "describe-environments" in normalized
    assert "describe-stacks" in normalized
    assert "list-stack-resources" in normalized
    assert "get-template" in normalized
    assert "templatebody.resources.*.type" in normalized
    assert "physicalresourceid" not in normalized
    assert "physicalid" not in normalized
    assert "logicalresourceid:logicalresourceid" in normalized
    assert "resourcetype:resourcetype" in normalized
    assert "resourcestatus:resourcestatus" in normalized
    for forbidden in (
        "update-environment",
        "create-application-version",
        "create-stack",
        "update-stack",
        "delete-stack",
        "put-object",
        "put-role-policy",
    ):
        assert forbidden not in normalized


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
    assert "deployment/aws/wait_for_codepipeline_execution.py" in workflow
    assert "for attempt in $(seq 1 90)" not in workflow


def test_workflow_pins_authorized_versions_without_reading_environment_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "EXPECTED_CURRENT_VERSION: h3-3-crm-web-28cf009-r1" in workflow
    assert "VERSION_LABEL: h3-3-crm-web-43101be-r1" in workflow
    assert "describe-configuration-settings" not in workflow
    assert "validate_h3_3_cutover_contract.py" not in workflow
    assert "validate_dev_environment_contract.py" not in workflow
    assert "LEGACY_BUNDLE" not in workflow


def test_dry_run_gates_all_writes_behind_execute_promotion() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "if: ${{ !inputs.execute_promotion }}" in workflow
    assert "if: ${{ inputs.execute_promotion }}" in workflow
    assert "Validate-only completed without AWS writes" in workflow
    assert "s3api put-object" in workflow
    assert "start-pipeline-execution" in workflow


def test_postflight_collects_all_eb_evidence_before_failing() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    postflight = workflow.split("- name: Collect independent EB postflight and events", 1)[1]

    assert "set +e" in postflight
    assert "elasticbeanstalk describe-environments" in postflight
    assert "environment_status=$?" in postflight
    assert "elasticbeanstalk describe-events" in postflight
    assert "events_status=$?" in postflight
    assert "set -e" in postflight
    assert "target_environment_status != 0" in postflight
    assert "tls_status != 0" in postflight
    assert "events_status != 0" in postflight
    assert "describe-configuration-settings" not in postflight
    assert "contract_status" not in postflight
    assert "(.VersionLabel == $candidate)" in postflight
    assert '(.Status == "Ready")' in postflight
    assert '(.Health == "Green")' in postflight
    assert '(.HealthStatus == "Ok")' in postflight
    assert postflight.index("environment_status=$?") < postflight.index(
        "elasticbeanstalk describe-events"
    )
    assert postflight.index("events_status=$?") < postflight.index("exit 1")
    assert "dev.tupensioninteligente.cl" in postflight
    assert "backoffice.dev.tupensioninteligente.cl" in postflight
    assert "--proto '=https'" in postflight
    assert "|| true" not in postflight


def test_github_cannot_write_trusted_tooling_and_source_key_is_fixed() -> None:
    release_policy = _load_json("deployment/iam/tpi-github-actions-dev-release.json")
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    release_resources = json.dumps(release_policy)
    source = pipeline["stages"][0]["actions"][0]["configuration"]

    assert "trusted-tooling" not in release_resources
    assert "approved-releases" not in release_resources
    assert "releases/h3-3" not in release_resources
    s3_statement = next(
        statement
        for statement in release_policy["Statement"]
        if "s3:PutObject"
        in (statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]])
    )
    assert s3_statement["Resource"] == (
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "promotions/h3-3-crm-web-43101be-r1/candidate-data.zip"
    )
    assert source == {
        "S3Bucket": "tpi-dev-release-artifacts-821656895812-us-east-2",
        "S3ObjectKey": "promotions/h3-3-crm-web-43101be-r1/candidate-data.zip",
        "PollForSourceChanges": "false",
        "AllowOverrideForS3ObjectKey": "false",
    }


def test_only_pipeline_can_materialize_the_exact_approved_bundle() -> None:
    release_policy = _load_json("deployment/iam/tpi-github-actions-dev-release.json")
    pipeline_policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    approved_resource = (
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "approved-releases/h3-3-crm-web-43101be-r1/"
        "7a7c69d6bc005a82c331895da06fbdc26b1f1fa88ce3a23a4274629476d8cfbb.zip"
    )

    assert approved_resource not in json.dumps(release_policy)
    materialize = next(
        statement
        for statement in pipeline_policy["Statement"]
        if statement["Sid"] == "MaterializeOnlyVerifiedApprovedBundle"
    )
    assert materialize == {
        "Sid": "MaterializeOnlyVerifiedApprovedBundle",
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"],
        "Resource": approved_resource,
    }


def test_pipeline_role_drops_the_old_candidate_source_and_reads_one_hashed_promoter() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    serialized = json.dumps(policy)
    read = next(
        statement
        for statement in policy["Statement"]
        if statement["Sid"] == "ReadExactReleaseDataAndTrustedTooling"
    )

    assert "trusted-tooling/v1/promote_eb_candidate.py" not in serialized
    assert "elasticbeanstalk-us-east-2-821656895812/tpi-backoffice/dev-releases" not in serialized
    assert read["Resource"] == [
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "promotions/h3-3-crm-web-43101be-r1/candidate-data.zip",
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "trusted-tooling/v1/verify_frozen_candidate.sh",
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "trusted-tooling/h3-3-43101be/"
        "dfbdbadfe16133db937c44cd25add127e5b68be089869416338630e6f685d144/"
        "promote_eb_candidate.py",
    ]


def test_external_release_object_cannot_become_candidate_source() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    serialized_pipeline = json.dumps(pipeline)

    assert "RELEASE_BUNDLE_KEY" not in workflow
    assert "/releases/h3-3-crm-web-43101be-r1" not in workflow
    assert "/releases/h3-3-crm-web-43101be-r1" not in serialized_pipeline
    assert "approved-releases/h3-3-crm-web-43101be-r1" in serialized_pipeline


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
    assert expected == {
        "verify_frozen_candidate.sh": (
            "a59144ff469e56231addb7c46ccf3fa7d456ff9487c7387089eec9137a045791"
        ),
        "promote_eb_candidate.py": (
            "dfbdbadfe16133db937c44cd25add127e5b68be089869416338630e6f685d144"
        ),
    }

    for filename, digest in expected.items():
        verification = next(
            command for command in commands if filename in command and "sha256sum" in command
        )
        assert digest in verification
        assert hashlib.sha256(b"modified executable").hexdigest() not in verification

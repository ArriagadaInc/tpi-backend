"""Security guardrails for the CodePipeline-based DEV promotion plane."""

import hashlib
import json
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


def test_pipeline_targets_only_approved_baseline_and_dev_environment() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    serialized = json.dumps(pipeline)

    assert pipeline["name"] == "tpi-backoffice-dev-promotion"
    assert pipeline["pipelineType"] == "V2"
    assert "h3-3-domain-baseline-28cf009-caddy43101be-r1" in serialized
    assert "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9" in serialized
    assert "h3-3-crm-web-43101be-r1" not in serialized
    source = pipeline["stages"][0]["actions"][0]["configuration"]
    assert source["S3ObjectKey"] == (
        "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
        "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip"
    )
    assert source["AllowOverrideForS3ObjectKey"] == "false"
    assert 'PollForSourceChanges": "false' in serialized

    commands = pipeline["stages"][1]["actions"][0]["commands"]
    required_tools = commands[0]
    assert all(tool in required_tools for tool in ("aws", "python3", "bash", "sha256sum"))
    assert not any(
        installer in " ".join(commands)
        for installer in ("apt-get", "apk add", "pip install", "yum install")
    )
    assert any(
        "trusted-tooling/h3-3-domain-baseline/"
        "a550bd02d4325031ef60ad5b7615258ac55acf38a7cc79c0f5224d957beb0c17/"
        "promote_domain_baseline.py" in item
        for item in commands
    )
    assert sum("sha256sum --check --strict" in item for item in commands) == 1
    assert any(command.endswith("python3 /tmp/promote_domain_baseline.py") for command in commands)


def test_pipeline_commands_respect_aws_quotas_and_run_only_the_baseline_promoter() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    action = pipeline["stages"][1]["actions"][0]
    commands = action["commands"]

    assert "environmentVariables" not in action
    assert 1 <= len(commands) <= 50
    assert all(1 <= len(command) <= 1000 for command in commands)

    assert "promote_eb_candidate.py" not in " ".join(commands)
    assert "verify_frozen_candidate.sh" not in " ".join(commands)
    promoter = next(
        command
        for command in commands
        if command.endswith("python3 /tmp/promote_domain_baseline.py")
    )
    assert promoter == "python3 /tmp/promote_domain_baseline.py"


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
        "tpi-backoffice/h3-3-domain-baseline-28cf009-caddy43101be-r1",
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
        "ec2:DescribeSubnets",
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
                "applicationversion/tpi-backoffice/h3-3-domain-baseline-28cf009-caddy43101be-r1",
            ]
        }
    }


def test_pipeline_role_has_no_environment_configuration_introspection() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    serialized = json.dumps(policy)
    sids = {statement["Sid"] for statement in policy["Statement"]}

    assert "ReadOnlyApprovedDevEnvironmentConfiguration" not in sids
    assert "elasticbeanstalk:DescribeConfigurationSettings" not in serialized
    assert "ec2:DescribeVpcs" not in serialized
    assert "ec2:DescribeSecurityGroups" not in serialized
    assert "ec2:DescribeRouteTables" not in serialized


def test_promoter_does_not_call_describe_configuration_settings() -> None:
    promoter = (ROOT / "deployment/aws/promote_eb_candidate.py").read_text(encoding="utf-8")

    assert "describe-configuration-settings" not in promoter
    assert "_environment_contract" not in promoter
    assert "_require_environment_contract" not in promoter


def test_baseline_promoter_does_not_call_describe_configuration_settings() -> None:
    promoter = (ROOT / "deployment/aws/promote_domain_baseline.py").read_text(encoding="utf-8")

    assert "describe-configuration-settings" not in promoter


def test_pipeline_role_uses_specific_eb_actions_without_describe_wildcard() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    serialized = json.dumps(policy)
    eb_actions = [action for action in _actions(policy) if action.startswith("elasticbeanstalk:")]

    assert "elasticbeanstalk:Describe*" not in serialized
    assert eb_actions
    assert all("*" not in action for action in eb_actions)


def test_pipeline_role_s3_contract_is_not_expanded() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    s3_actions = {action for action in _actions(policy) if action.startswith("s3:")}

    assert s3_actions == {
        "s3:CreateBucket",
        "s3:Delete*",
        "s3:Get*",
        "s3:GetBucket*",
        "s3:GetBucketAcl",
        "s3:GetBucketLocation",
        "s3:GetBucketVersioning",
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket",
        "s3:Put*",
        "s3:PutBucketOwnershipControls",
        "s3:PutBucketPolicy",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutObject",
    }


def test_github_read_role_unchanged_by_pipeline_policy_change() -> None:
    read_policy = _load_json("deployment/iam/tpi-github-actions-dev-eb-read.json")

    assert read_policy["Statement"][0]["Action"] == [
        "elasticbeanstalk:DescribeApplications",
        "elasticbeanstalk:DescribeEnvironments",
        "elasticbeanstalk:DescribeConfigurationSettings",
        "elasticbeanstalk:DescribeApplicationVersions",
        "elasticbeanstalk:DescribeEvents",
    ]
    assert "s3:" not in json.dumps(read_policy)


def test_pipeline_trust_is_unchanged() -> None:
    trust = _load_json("deployment/iam/tpi-codepipeline-dev-eb-role-trust.json")
    statement = trust["Statement"][0]

    assert statement["Principal"] == {"Service": "codepipeline.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"
    assert "Federated" not in json.dumps(trust)


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
        "S3ObjectKey": (
            "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
            "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip"
        ),
        "PollForSourceChanges": "false",
        "AllowOverrideForS3ObjectKey": "false",
    }


def test_baseline_object_is_read_only_for_the_pipeline_role() -> None:
    pipeline_policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    sids = {statement["Sid"] for statement in pipeline_policy["Statement"]}
    baseline_key = (
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
        "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip"
    )

    assert "MaterializeOnlyVerifiedApprovedBundle" not in sids
    read = next(
        statement
        for statement in pipeline_policy["Statement"]
        if statement["Sid"] == "ReadExactReleaseDataAndTrustedTooling"
    )
    assert baseline_key in read["Resource"]
    assert "s3:PutObject" not in read["Action"]
    for statement in pipeline_policy["Statement"]:
        actions = (
            statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        )
        if "s3:PutObject" in actions:
            resources = (
                statement["Resource"]
                if isinstance(statement["Resource"], list)
                else [statement["Resource"]]
            )
            assert baseline_key not in resources


def test_pipeline_role_reads_only_the_baseline_and_its_hashed_promoter() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    serialized = json.dumps(policy)
    read = next(
        statement
        for statement in policy["Statement"]
        if statement["Sid"] == "ReadExactReleaseDataAndTrustedTooling"
    )

    assert "candidate-data.zip" not in serialized
    assert "trusted-tooling/v1/verify_frozen_candidate.sh" not in serialized
    assert "trusted-tooling/h3-3-43101be/" not in serialized
    assert read["Action"] == ["s3:GetObject", "s3:GetObjectVersion"]
    assert read["Resource"] == [
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
        "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip",
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "trusted-tooling/h3-3-domain-baseline/"
        "a550bd02d4325031ef60ad5b7615258ac55acf38a7cc79c0f5224d957beb0c17/"
        "promote_domain_baseline.py",
    ]


def test_external_release_object_cannot_become_baseline_source() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    serialized_pipeline = json.dumps(pipeline)

    assert "promotions/h3-3-crm-web-43101be-r1/candidate-data.zip" not in serialized_pipeline
    assert "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1" in serialized_pipeline
    source = pipeline["stages"][0]["actions"][0]["configuration"]
    assert source["S3ObjectKey"] == (
        "approved-releases/h3-3-domain-baseline-28cf009-caddy43101be-r1/"
        "e1393c10850956b8921a0bab66d11447beadce89ef6bcf7aaf34f513435017d9.zip"
    )


def test_pipeline_pins_exact_trusted_tooling_hashes() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    commands = pipeline["stages"][1]["actions"][0]["commands"]
    expected = {
        "promote_domain_baseline.py": hashlib.sha256(
            (ROOT / "deployment/aws/promote_domain_baseline.py")
            .read_text(encoding="utf-8")
            .encode()
        ).hexdigest(),
    }
    assert expected == {
        "promote_domain_baseline.py": (
            "a550bd02d4325031ef60ad5b7615258ac55acf38a7cc79c0f5224d957beb0c17"
        ),
    }

    for filename, digest in expected.items():
        verification = next(
            command for command in commands if filename in command and "sha256sum" in command
        )
        assert digest in verification
        assert hashlib.sha256(b"modified executable").hexdigest() not in verification

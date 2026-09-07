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
    assert any("trusted-tooling/v1/promote_eb_candidate.py" in item for item in commands)
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
        "BUNDLE_NAME": "tpi-dev-ecr-28cf009.zip",
        "MANIFEST_NAME": "tpi-dev-ecr-28cf009.manifest.json",
        "BUNDLE_SHA256": "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045",
        "SOURCE_SHA": "28cf009137ada707540d9ee7eba01dc45a9a260e",
        "APP_IMAGE": (
            "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@"
            "sha256:45331812c93bcf905b2ae8ad9eedff9eba5f63bc4afbfd5639af85c78bb3b6ce"
        ),
        "CADDY_IMAGE": (
            "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@"
            "sha256:1d7c114bf0bb98e8ed2034a37997ee4d9e4aec98cbba58dc00581bbf6b6dc4e2"
        ),
    }
    assert verifier_tokens[-2:] == ["bash", "/tmp/verify_frozen_candidate.sh"]

    assert promoter_environment == {
        "AWS_ACCOUNT_ID": "821656895812",
        "AWS_REGION": "us-east-2",
        "APPLICATION": "tpi-backoffice",
        "ENVIRONMENT": "tpi-backoffice-dev-green",
        "EXPECTED_CURRENT_VERSION": "h2-5d-ecr-47fa0c9",
        "VERSION_LABEL": "h3-3-crm-web-28cf009-r1",
        "APPROVED_BUNDLE_BUCKET": "tpi-dev-release-artifacts-821656895812-us-east-2",
        "APPROVED_BUNDLE_KEY": (
            "approved-releases/h3-3-crm-web-28cf009-r1/"
            "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045.zip"
        ),
        "LEGACY_BUNDLE_BUCKET": "elasticbeanstalk-us-east-2-821656895812",
        "LEGACY_BUNDLE_KEY": (
            "tpi-backoffice/dev-releases/h3-3-crm-web-28cf009-r1/tpi-dev-ecr-28cf009.zip"
        ),
        "ARTIFACT_DIR": "artifact",
        "BUNDLE_NAME": "tpi-dev-ecr-28cf009.zip",
        "SOURCE_SHA": "28cf009137ada707540d9ee7eba01dc45a9a260e",
        "BUNDLE_SHA256": "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045",
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
    assert wildcard_statements == [inspection]

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


def test_update_environment_keeps_exact_application_version_condition() -> None:
    policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    update = next(
        item for item in policy["Statement"] if item["Sid"] == "UpdateOnlyApprovedDevEnvironment"
    )

    assert update["Action"] == "elasticbeanstalk:UpdateEnvironment"
    assert update["Condition"] == {
        "ArnEquals": {
            "elasticbeanstalk:FromApplicationVersion": (
                "arn:aws:elasticbeanstalk:us-east-2:821656895812:"
                "applicationversion/tpi-backoffice/h3-3-crm-web-28cf009-r1"
            )
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
        "promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip"
    )
    assert source == {
        "S3Bucket": "tpi-dev-release-artifacts-821656895812-us-east-2",
        "S3ObjectKey": "promotions/h3-3-crm-web-28cf009-r1/candidate-data.zip",
        "PollForSourceChanges": "false",
        "AllowOverrideForS3ObjectKey": "false",
    }


def test_only_pipeline_can_materialize_the_exact_approved_bundle() -> None:
    release_policy = _load_json("deployment/iam/tpi-github-actions-dev-release.json")
    pipeline_policy = _load_json("deployment/iam/tpi-codepipeline-dev-eb.json")
    approved_resource = (
        "arn:aws:s3:::tpi-dev-release-artifacts-821656895812-us-east-2/"
        "approved-releases/h3-3-crm-web-28cf009-r1/"
        "5e998cadee8b2ee08a4fa08f487a8203555c6971da5465427645f66ffb923045.zip"
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


def test_external_release_object_cannot_become_candidate_source() -> None:
    pipeline = _load_json("deployment/aws/tpi-dev-eb-pipeline.json")["pipeline"]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    serialized_pipeline = json.dumps(pipeline)

    assert "RELEASE_BUNDLE_KEY" not in workflow
    assert "/releases/h3-3-crm-web-28cf009-r1" not in workflow
    assert "/releases/h3-3-crm-web-28cf009-r1" not in serialized_pipeline
    assert "approved-releases/h3-3-crm-web-28cf009-r1" in serialized_pipeline


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
            "4ba84447a948238ff877fa95e60e52f9b52e0b9bc2bad3e80fd236a03a9675f9"
        ),
    }

    for filename, digest in expected.items():
        verification = next(
            command for command in commands if filename in command and "sha256sum" in command
        )
        assert digest in verification
        assert hashlib.sha256(b"modified executable").hexdigest() not in verification

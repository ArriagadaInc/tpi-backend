"""Guardrails for the controlled Elastic Beanstalk deployment artifacts."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-dev-eb.yml"


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
        "s3:PutObject",
    ]
    serialized = json.dumps(policy)
    assert "s3:CreateBucket" not in serialized
    assert "iam:PassRole" not in serialized
    assert "elasticbeanstalk:UpdateConfigurationTemplate" not in serialized
    assert "s3:DeleteObject" not in serialized
    assert (
        "arn:aws:elasticbeanstalk:us-east-2:821656895812:environment/tpi-backoffice/tpi-backoffice-dev-green"
        in serialized
    )


def test_deployment_workflow_is_main_only_and_pins_frozen_candidate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in workflow
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

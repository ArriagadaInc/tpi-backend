"""Guardrails for the read-only Elastic Beanstalk preflight artifacts."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_eb_preflight_trust_is_main_only() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-eb-role-trust.json")
    condition = policy["Statement"][0]["Condition"]["StringEquals"]

    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert (
        condition["token.actions.githubusercontent.com:sub"]
        == "repo:ArriagadaInc@37077654/tpi-backend@1318709295:ref:refs/heads/main"
    )
    assert "*" not in json.dumps(policy)


def test_eb_preflight_permissions_are_describe_only() -> None:
    policy = _load_json("deployment/iam/tpi-github-actions-dev-eb-read.json")
    actions = policy["Statement"][0]["Action"]

    assert actions == [
        "elasticbeanstalk:DescribeApplications",
        "elasticbeanstalk:DescribeEnvironments",
        "elasticbeanstalk:DescribeConfigurationSettings",
        "elasticbeanstalk:DescribeApplicationVersions",
    ]
    assert all(action.split(":", 1)[1].startswith("Describe") for action in actions)

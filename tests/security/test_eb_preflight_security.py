"""Guardrails for the read-only Elastic Beanstalk preflight artifacts."""

import json
from pathlib import Path

import pytest

from scripts.eb_dns_matching import identify_environment, matching_environments

ROOT = Path(__file__).parents[2]
PREFLIGHT_WORKFLOW = ROOT / ".github/workflows/preflight-dev-eb.yml"


def _load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_eb_preflight_uses_valid_include_deleted_flag() -> None:
    workflow = PREFLIGHT_WORKFLOW.read_text(encoding="utf-8")

    assert "--no-include-deleted" in workflow
    assert "--include-deleted false" not in workflow


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


def test_dns_matching_uses_exact_environment_cname() -> None:
    environments = [
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-blue",
            "CNAME": "dev-blue.example.elasticbeanstalk.com",
        },
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-green",
            "CNAME": "dev-green.example.elasticbeanstalk.com",
        },
    ]
    record = {"cname": "dev-blue.example.elasticbeanstalk.com.", "addresses": []}

    candidates = matching_environments(environments, record, {})

    assert [candidate["Environment"] for candidate in candidates] == ["dev-blue"]


def test_dns_matching_falls_back_to_environment_a_records() -> None:
    environments = [
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-blue",
            "CNAME": "dev-blue.example.elasticbeanstalk.com",
        },
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-green",
            "CNAME": "dev-green.example.elasticbeanstalk.com",
        },
    ]
    domain_records = {
        "dev.tupensioninteligente.cl": {"cname": None, "addresses": ["192.0.2.10"]},
        "backoffice.dev.tupensioninteligente.cl": {
            "cname": None,
            "addresses": ["192.0.2.10"],
        },
    }
    environment_addresses = {
        "dev-blue.example.elasticbeanstalk.com": ["192.0.2.10"],
        "dev-green.example.elasticbeanstalk.com": ["192.0.2.20"],
    }

    selected = identify_environment(environments, domain_records, environment_addresses)

    assert selected["Environment"] == "dev-blue"


def test_dns_matching_rejects_ambiguous_or_inconsistent_domains() -> None:
    environments = [
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-blue",
            "CNAME": "dev-blue.example.elasticbeanstalk.com",
        },
        {
            "Application": "tpi-backoffice",
            "Environment": "dev-green",
            "CNAME": "dev-green.example.elasticbeanstalk.com",
        },
    ]

    with pytest.raises(ValueError, match="exactly one"):
        identify_environment(
            environments,
            {"dev.example": {"cname": None, "addresses": ["192.0.2.10"]}},
            {
                "dev-blue.example.elasticbeanstalk.com": ["192.0.2.10"],
                "dev-green.example.elasticbeanstalk.com": ["192.0.2.10"],
            },
        )

    with pytest.raises(ValueError, match="different"):
        identify_environment(
            environments,
            {
                "dev.example": {
                    "cname": "dev-blue.example.elasticbeanstalk.com",
                    "addresses": [],
                },
                "backoffice.example": {
                    "cname": "dev-green.example.elasticbeanstalk.com",
                    "addresses": [],
                },
            },
            {},
        )

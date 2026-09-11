"""Security guardrails for the delegated TPI DEV domain and ACME contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
ZONE_ID = "Z07053592LX0W8GJXNI1C"
ACME_NAMES = [
    "_acme-challenge.dev.tupensioninteligente.cl",
    "_acme-challenge.backoffice.dev.tupensioninteligente.cl",
]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_caddy_uses_runtime_hosted_zone_id_only() -> None:
    caddyfile = _text("deployment/caddy/Caddyfile")

    assert "hosted_zone_id {$TPI_ROUTE53_HOSTED_ZONE_ID}" in caddyfile
    assert not re.search(r"hosted_zone_id\s+Z[A-Z0-9]+", caddyfile)


def test_aws_compose_requires_hosted_zone_id() -> None:
    compose = _text("deployment/aws/docker-compose.ecr.yml")

    assert (
        "TPI_ROUTE53_HOSTED_ZONE_ID: "
        "${TPI_ROUTE53_HOSTED_ZONE_ID:?TPI_ROUTE53_HOSTED_ZONE_ID is required}" in compose
    )


def test_route53_policy_allows_only_tpi_acme_txt_changes() -> None:
    policy = json.loads(_text("deployment/iam/tpi-backoffice-dev-ecr-route53-acme-dns01.json"))
    change = next(
        statement
        for statement in policy["Statement"]
        if statement["Action"] == "route53:ChangeResourceRecordSets"
    )

    assert change["Resource"] == f"arn:aws:route53:::hostedzone/{ZONE_ID}"
    assert change["Condition"]["ForAllValues:StringEquals"][
        "route53:ChangeResourceRecordSetsRecordTypes"
    ] == ["TXT"]
    assert (
        change["Condition"]["ForAllValues:StringEquals"][
            "route53:ChangeResourceRecordSetsNormalizedRecordNames"
        ]
        == ACME_NAMES
    )
    assert change["Condition"]["Null"] == {
        "route53:ChangeResourceRecordSetsRecordTypes": "false",
        "route53:ChangeResourceRecordSetsNormalizedRecordNames": "false",
    }
    assert "genialabs.cl" not in json.dumps(policy)
    assert "route53:*" not in json.dumps(policy)


def test_active_runtime_contract_has_no_genialabs_dependency() -> None:
    runtime_files = [
        "app/components/ui.py",
        "front/js/backoffice-access.js",
        "deployment/caddy/Caddyfile",
        "deployment/caddy/README.md",
        "deployment/aws/docker-compose.ecr.yml",
        "deployment/iam/tpi-backoffice-dev-ecr-route53-acme-dns01.json",
    ]

    assert all("genialabs.cl" not in _text(path) for path in runtime_files)
    assert "dev.tupensioninteligente.cl" in _text("app/components/ui.py")
    assert "backoffice.dev.tupensioninteligente.cl" in _text("front/js/backoffice-access.js")


def test_preflight_validates_exact_values_but_cutover_does_not_read_contract() -> None:
    preflight = _text(".github/workflows/preflight-dev-eb.yml")
    assert "validate_dev_environment_contract.py" in preflight
    assert "TPI_ROUTE53_HOSTED_ZONE_ID" in preflight
    assert ".{Name:OptionName,Value:Value}" in preflight

    cutover = _text(".github/workflows/deploy-dev-eb.yml")
    assert "describe-configuration-settings" not in cutover
    assert "validate_dev_environment_contract.py" not in cutover
    assert ".{Name:OptionName,Value:Value}" not in cutover
    assert "TPI_ROUTE53_HOSTED_ZONE_ID: Z00000000000000000000" in cutover


def test_candidate_verification_supplies_safe_zone_placeholder() -> None:
    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/deploy-dev-eb.yml",
    ):
        workflow = _text(path)
        assert "TPI_ROUTE53_HOSTED_ZONE_ID: Z00000000000000000000" in workflow


def test_preflight_retains_required_variable_presence_checks_without_listing_env() -> None:
    workflow = _text(".github/workflows/preflight-dev-eb.yml")

    assert "DATABASE_PASSWORD" in workflow
    assert "WEB_SESSION_SECRET" in workflow
    assert "Required application environment variable is missing: $name" in workflow
    assert "Application environment variable names:" not in workflow

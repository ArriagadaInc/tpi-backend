"""Garantias de seguridad de la infraestructura S3 de los adjuntos (CRM-ADJUNTOS-1-INFRA-S3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from deployment.aws import adjuntos_s3_infra as infra

IAM_DIR = Path(__file__).resolve().parents[2] / "deployment" / "iam"
BUCKET_ARN = f"arn:aws:s3:::{infra.BUCKET}"


def _policy(key: str) -> dict[str, Any]:
    return json.loads((IAM_DIR / infra.POLICY_FILES[key]).read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _statement(policy: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(item for item in policy["Statement"] if item["Sid"] == sid)


@pytest.mark.security
def test_bucket_policy_only_denies_and_never_grants_access() -> None:
    policy = _policy("bucket")

    assert {item["Effect"] for item in policy["Statement"]} == {"Deny"}


@pytest.mark.security
def test_bucket_policy_requires_tls_for_everything() -> None:
    statement = _statement(_policy("bucket"), "DenyInsecureTransport")

    assert statement["Action"] == "s3:*"
    assert statement["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
    assert set(statement["Resource"]) == {BUCKET_ARN, f"{BUCKET_ARN}/*"}


@pytest.mark.security
def test_unscanned_or_infected_objects_cannot_be_read_by_anyone_but_the_scanner() -> None:
    statement = _statement(_policy("bucket"), "DenyReadUnlessScannedClean")

    assert statement["Principal"] == "*"
    assert set(_as_list(statement["Action"])) == {"s3:GetObject", "s3:GetObjectVersion"}
    assert statement["Resource"] == f"{BUCKET_ARN}/leads/*"
    assert statement["Condition"]["StringNotEquals"] == {
        "s3:ExistingObjectTag/GuardDutyMalwareScanStatus": "NO_THREATS_FOUND"
    }
    assert statement["Condition"]["ArnNotEquals"] == {"aws:PrincipalArn": infra.GUARDDUTY_ROLE_ARN}


@pytest.mark.security
def test_only_the_scanner_can_write_or_delete_the_scan_tag() -> None:
    policy = _policy("bucket")
    tampering = _statement(policy, "DenyScanTagTamperingExceptGuardDuty")
    forged = _statement(policy, "DenyUploadWithForgedScanTag")

    assert set(tampering["Action"]) == {
        "s3:PutObjectTagging",
        "s3:PutObjectVersionTagging",
        "s3:DeleteObjectTagging",
        "s3:DeleteObjectVersionTagging",
    }
    assert tampering["Condition"]["ArnNotEquals"] == {"aws:PrincipalArn": infra.GUARDDUTY_ROLE_ARN}
    assert forged["Action"] == "s3:PutObject"
    assert forged["Condition"]["Null"] == {
        "s3:RequestObjectTag/GuardDutyMalwareScanStatus": "false"
    }
    assert forged["Condition"]["ArnNotEquals"] == {"aws:PrincipalArn": infra.GUARDDUTY_ROLE_ARN}


@pytest.mark.security
def test_app_role_policy_is_object_level_on_the_leads_prefix_only() -> None:
    policy = _policy("app_role")
    objects = _statement(policy, "AdjuntosLeadsObjects")
    scan_tag = _statement(policy, "AdjuntosLeadsReadScanTag")

    assert len(policy["Statement"]) == 2
    assert objects["Effect"] == "Allow"
    assert set(objects["Action"]) == {"s3:PutObject", "s3:GetObject", "s3:DeleteObject"}
    assert objects["Resource"] == f"{BUCKET_ARN}/leads/*"
    assert "Condition" not in objects
    # solo LEE la etiqueta de escaneo (GuardDuty la escribe); nunca la escribe ni la borra
    assert scan_tag["Effect"] == "Allow"
    assert scan_tag["Action"] == "s3:GetObjectTagging"
    assert scan_tag["Resource"] == f"{BUCKET_ARN}/leads/*"
    assert "Condition" not in scan_tag


@pytest.mark.security
def test_app_role_cannot_list_tag_or_reconfigure_the_bucket() -> None:
    actions = {
        action
        for statement in _policy("app_role")["Statement"]
        for action in _as_list(statement["Action"])
    }

    assert not {action for action in actions if "*" in action}
    assert "s3:ListBucket" not in actions
    assert not {action for action in actions if "Bucket" in action}
    # la unica accion de etiquetas es de lectura: la app no puede falsificar el resultado del escaneo
    assert {action for action in actions if "Tagging" in action} == {"s3:GetObjectTagging"}


@pytest.mark.security
def test_guardduty_role_trusts_only_the_malware_protection_service() -> None:
    policy = _policy("guardduty_trust")
    statement = policy["Statement"][0]

    assert len(policy["Statement"]) == 1
    assert statement["Effect"] == "Allow"
    assert statement["Principal"] == {"Service": "malware-protection-plan.guardduty.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"


@pytest.mark.security
def test_guardduty_role_has_no_wildcard_actions_and_is_limited_to_the_bucket() -> None:
    policy = _policy("guardduty_role")
    allowed_resources = (
        BUCKET_ARN,
        f"{BUCKET_ARN}/",
        "arn:aws:events:us-east-2:821656895812:rule/",
    )

    for statement in policy["Statement"]:
        assert statement["Effect"] == "Allow"
        assert not [action for action in _as_list(statement["Action"]) if "*" in action]
        for resource in _as_list(statement["Resource"]):
            assert resource.startswith(allowed_resources), resource
    all_actions = {action for item in policy["Statement"] for action in _as_list(item["Action"])}
    assert "s3:DeleteObject" not in all_actions
    assert not {action for action in all_actions if action.startswith(("kms:", "iam:"))}


@pytest.mark.security
def test_guardduty_managed_rule_actions_are_limited_to_its_own_rules() -> None:
    statement = _statement(_policy("guardduty_role"), "AllowManagedRuleToSendS3EventsToGuardDuty")

    assert statement["Resource"].endswith("rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*")
    assert statement["Condition"] == {
        "StringLike": {"events:ManagedBy": "malware-protection-plan.guardduty.amazonaws.com"}
    }


@pytest.mark.security
def test_script_constants_agree_with_the_policy_documents() -> None:
    texts = {
        key: (IAM_DIR / name).read_text(encoding="utf-8")
        for key, name in infra.POLICY_FILES.items()
    }

    assert infra.BUCKET == "tpi-dev-adjuntos-821656895812-us-east-2"
    assert infra.BUCKET in texts["bucket"]
    assert infra.BUCKET in texts["app_role"]
    assert infra.BUCKET in texts["guardduty_role"]
    assert infra.GUARDDUTY_ROLE_ARN in texts["bucket"]
    assert infra.OBJECT_PREFIX == "leads/"

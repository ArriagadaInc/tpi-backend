"""Security guarantees for the H2.4 notification capability."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from app.notifications import LeadCreatedEvent
from app.notifications.sns import format_email_notification, format_sms_notification

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOPIC_ARN = "arn:aws:sns:us-east-2:821656895812:tpi-dev-lead-created"


@pytest.mark.security
def test_sns_runtime_policy_is_publish_only_for_exact_topic() -> None:
    policy = json.loads(
        (PROJECT_ROOT / "deployment/iam/tpi-backoffice-dev-publish-lead-created.json").read_text(
            encoding="utf-8"
        )
    )
    statement = policy["Statement"][0]

    assert statement["Action"] == "sns:Publish"
    assert statement["Resource"] == TOPIC_ARN
    assert "*" not in statement["Resource"]


@pytest.mark.security
def test_runtime_database_policy_excludes_administrative_secret() -> None:
    policy = json.loads(
        (PROJECT_ROOT / "deployment/iam/tpi-backoffice-dev-read-database-secret.json").read_text(
            encoding="utf-8"
        )
    )
    resources = [statement["Resource"] for statement in policy["Statement"]]

    assert all("database-admin-password" not in resource for resource in resources)
    assert all(resource.endswith("database-password-Zu4Lk2") for resource in resources)


@pytest.mark.security
def test_notification_renderings_have_no_customer_pii() -> None:
    event = LeadCreatedEvent.create(
        lead_id=UUID("11111111-1111-1111-1111-111111111111"),
        environment="aws-dev",
    )
    rendered = "\n".join(
        (event.to_json(), format_email_notification(event), format_sms_notification(event))
    )

    for forbidden in (
        "rut",
        "nombre",
        "email",
        "telefono",
        "saldo",
        "comentarios",
        "consentimiento",
    ):
        assert forbidden not in rendered.lower()

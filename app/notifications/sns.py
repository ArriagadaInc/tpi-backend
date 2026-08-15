"""Amazon SNS implementation of the lead event publisher."""

from __future__ import annotations

import json
from typing import Any, Protocol

import boto3

from app.notifications.events import LeadCreatedEvent
from app.notifications.publisher import PublishResult

_SNS_SUBJECT = "[TPI DEV] Nuevo lead recibido"


class SnsClient(Protocol):
    """Small boto3 surface used by this adapter, easy to fake in tests."""

    def publish(self, **kwargs: Any) -> dict[str, Any]:
        """Publish a message to SNS."""


class SnsLeadEventPublisher:
    """Publish one safe event to a configured SNS Standard topic."""

    provider = "sns"

    def __init__(self, topic_arn: str, client: SnsClient | None = None) -> None:
        self.topic_arn = topic_arn
        self.client = client or boto3.client("sns", region_name=_topic_region(topic_arn))

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        """Publish safe default, email, and future SMS representations."""
        try:
            response = self.client.publish(
                TopicArn=self.topic_arn,
                Subject=_SNS_SUBJECT,
                MessageStructure="json",
                Message=json.dumps(
                    {
                        "default": event.to_json(),
                        "email": format_email_notification(event),
                        "sms": format_sms_notification(event),
                    },
                    separators=(",", ":"),
                ),
            )
        except Exception:
            return PublishResult(status="failed", provider=self.provider)

        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            return PublishResult(status="failed", provider=self.provider)

        return PublishResult(status="published", provider=self.provider, message_id=message_id)


def format_email_notification(event: LeadCreatedEvent) -> str:
    """Render a human-readable operational email without customer data."""
    return "\n".join(
        (
            "Tu Pension Inteligente",
            "",
            "Se ha registrado un nuevo lead.",
            "",
            f"Ambiente: {_display_environment(event.environment)}",
            f"ID Lead: {event.lead_id}",
            f"Fecha: {event.occurred_at.isoformat()}",
            "",
            "Ingresa al backoffice TPI para revisar la solicitud.",
        )
    )


def format_sms_notification(event: LeadCreatedEvent) -> str:
    """Render the future SMS representation without enabling SMS delivery."""
    return (
        f"TPI {_display_environment(event.environment)}: nuevo lead recibido. "
        f"ID {event.lead_id}. Revisa el backoffice."
    )


def _display_environment(environment: str) -> str:
    return "DEV" if environment == "aws-dev" else environment.upper()


def _topic_region(topic_arn: str) -> str:
    """Extract the SNS region only from a valid SNS topic ARN."""
    parts = topic_arn.split(":", maxsplit=5)
    if len(parts) != 6 or parts[0] != "arn" or parts[2] != "sns" or not parts[3] or not parts[5]:
        raise ValueError("LEAD_NOTIFICATION_TOPIC_ARN must be a valid SNS topic ARN")
    return parts[3]

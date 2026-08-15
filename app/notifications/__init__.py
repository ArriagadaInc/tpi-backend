"""Post-commit lead notification capability."""

from __future__ import annotations

from app.config.settings import Settings
from app.notifications.events import LeadCreatedEvent
from app.notifications.publisher import (
    DisabledLeadEventPublisher,
    LeadEventPublisher,
    MisconfiguredLeadEventPublisher,
    PublishResult,
)
from app.notifications.sns import SnsLeadEventPublisher


def build_lead_event_publisher(settings: Settings) -> LeadEventPublisher:
    """Compose the runtime publisher from safe external configuration."""
    if not settings.lead_notifications_enabled:
        return DisabledLeadEventPublisher()
    if not settings.lead_notification_topic_arn:
        return MisconfiguredLeadEventPublisher()
    try:
        return SnsLeadEventPublisher(settings.lead_notification_topic_arn)
    except ValueError:
        return MisconfiguredLeadEventPublisher()


__all__ = [
    "LeadCreatedEvent",
    "LeadEventPublisher",
    "PublishResult",
    "SnsLeadEventPublisher",
    "build_lead_event_publisher",
]

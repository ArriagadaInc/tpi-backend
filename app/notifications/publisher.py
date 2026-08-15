"""Notification publisher contracts and result values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.notifications.events import LeadCreatedEvent

PublishStatus = Literal["published", "disabled", "failed"]


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Safe observable outcome of an attempted notification publication."""

    status: PublishStatus
    provider: str
    message_id: str | None = None


class LeadEventPublisher(Protocol):
    """Publish a safe lead-created event without exposing a transport to services."""

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        """Publish a post-commit event and return a transport-neutral outcome."""


@dataclass(frozen=True, slots=True)
class DisabledLeadEventPublisher:
    """Safe default used whenever notifications are not explicitly enabled."""

    provider: str = "none"

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        del event
        return PublishResult(status="disabled", provider=self.provider)


@dataclass(frozen=True, slots=True)
class MisconfiguredLeadEventPublisher:
    """Fails safely when enabled notifications have no usable destination."""

    provider: str = "sns"

    def publish(self, event: LeadCreatedEvent) -> PublishResult:
        del event
        return PublishResult(status="failed", provider=self.provider)

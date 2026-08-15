"""Safe, versioned notification events emitted after successful lead commits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class LeadCreatedEvent:
    """Minimal event contract for consumers of a newly created lead."""

    event_id: UUID
    lead_id: UUID
    occurred_at: datetime
    environment: str
    schema_version: str = "1.0"
    event_type: str = "lead.created"
    source: str = "tpi-backoffice"

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("LeadCreatedEvent.occurred_at must be timezone-aware")
        if self.event_id == self.lead_id:
            raise ValueError("LeadCreatedEvent.event_id must be independent from lead_id")

    @classmethod
    def create(cls, *, lead_id: UUID, environment: str) -> LeadCreatedEvent:
        """Create an event with a distinct id and an aware UTC timestamp."""
        return cls(
            event_id=uuid4(),
            lead_id=lead_id,
            occurred_at=datetime.now(UTC),
            environment=environment,
        )

    def payload(self) -> dict[str, str]:
        """Return the intentionally PII-free, serializable event contract."""
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "event_id": str(self.event_id),
            "lead_id": str(self.lead_id),
            "occurred_at": self.occurred_at.isoformat(),
            "environment": self.environment,
            "source": self.source,
        }

    def to_json(self) -> str:
        """Serialize the safe event without depending on consumer-specific formatting."""
        return json.dumps(self.payload(), separators=(",", ":"), sort_keys=True)

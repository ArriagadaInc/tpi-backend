"""Explicit result contract for the AWS DEV test-lead cleanup operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

TestLeadCleanupStatus = Literal["deleted", "denied", "invalid", "not_found", "blocked", "failed"]


@dataclass(frozen=True, slots=True)
class TestLeadCleanupResult:
    """Safe, UI-ready outcome for deleting a test lead in AWS DEV."""

    __test__ = False

    status: TestLeadCleanupStatus
    message: str
    lead_id: UUID | None = None
    person_retained: bool = True

    @property
    def deleted(self) -> bool:
        return self.status == "deleted"

"""Typed results and errors for idempotent public lead registration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.database.errors import DatabaseAppError
from app.models.solicitud import SolicitudResponse


class IdempotencyConflictError(DatabaseAppError):
    """The client reused an idempotency key with a different request."""

    code = "idempotency_conflict"
    default_user_message = "La solicitud ya fue enviada con datos diferentes."

    def __init__(self, technical_message: str) -> None:
        super().__init__(technical_message, operation="create_solicitud_idempotent")


@dataclass(frozen=True, slots=True)
class IdempotentSolicitudResult:
    """Result of a request that may have been replayed safely."""

    lead_id: UUID
    created: bool
    response: SolicitudResponse | None = None

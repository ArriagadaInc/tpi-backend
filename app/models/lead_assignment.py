"""Lead assignment domain contracts."""

from __future__ import annotations

from typing import Final

from app.database.errors import DatabaseAppError

ASSIGNMENT_ACTIVE_STATE: Final[str] = "activa"


class LeadAssignmentConflictError(DatabaseAppError):
    """Raised when a lead already has an active assignment."""

    code = "lead_assignment_conflict"
    default_user_message = "El lead ya tiene una asignacion activa."

    def __init__(self, technical_message: str) -> None:
        super().__init__(technical_message, operation="assign_lead")


class LeadAssignmentValidationError(DatabaseAppError):
    """Raised when the selected advisor does not satisfy assignment constraints."""

    code = "lead_assignment_validation_error"
    default_user_message = "El asesor seleccionado no esta habilitado."

    def __init__(self, technical_message: str) -> None:
        super().__init__(technical_message, operation="assign_lead")

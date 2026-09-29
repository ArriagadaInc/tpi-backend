"""Stable authentication contracts, independent from the chosen provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

UserRole = Literal[
    "tester",
    "admin",
    "advisor",
    "executive",
    "operations",
    "readonly",
    "ceo",
    "cto",
]

SUPERUSER_ROLES: frozenset[str] = frozenset({"ceo", "cto"})


def is_superuser(role: UserRole) -> bool:
    """Return True for roles holding a superset of every RBAC capability (ceo, cto).

    Superusers are functional backoffice roles only: this does not grant AWS, IAM,
    Harness or deployment permissions.
    """
    return role in SUPERUSER_ROLES


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal application identity, deliberately excluding credentials and tokens.

    ``advisor_id`` binds an ``advisor`` identity to ``tpi.asesores.id_asesor``. It is
    functional for ``advisor`` only and optional/ignored for every other role. The
    value is resolved server-side against ``tpi.asesores``; it is never derived from
    ``username`` or ``display_name``.
    """

    subject: str
    username: str
    display_name: str
    role: UserRole
    advisor_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """Explicit outcome for a login attempt without exposing verification details."""

    status: Literal["authenticated", "invalid", "unavailable"]
    user: AuthenticatedUser | None = None

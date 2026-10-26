"""Stable authentication contracts, independent from the chosen provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

UserRole = Literal[
    "tester",
    "admin",
    "advisor",
    "coordinator",
    "executive",
    "operations",
    "readonly",
    "ceo",
    "cto",
]

SUPERUSER_ROLES: frozenset[str] = frozenset({"ceo", "cto"})

# Roles bound to their own lead portfolio: their identity resolves to an active
# ``tpi.asesores`` record and every read/write is scoped to their assigned leads.
# ``advisor`` is the Runner and ``coordinator`` the Coordinador of the Runners
# protocol; both share the exact same portfolio scope.
PORTFOLIO_ROLES: frozenset[str] = frozenset({"advisor", "coordinator"})

# Display-only labels for the top bar profile chip. Only the three business
# profiles are renamed; the technical roles keep their technical value.
PROFILE_LABELS: dict[str, str] = {
    "advisor": "Runner",
    "coordinator": "Coordinador",
    "ceo": "Socio",
    "cto": "Socio",
}


def is_superuser(role: UserRole) -> bool:
    """Return True for roles holding a superset of every RBAC capability (ceo, cto).

    Superusers are functional backoffice roles only: this does not grant AWS, IAM,
    Harness or deployment permissions.
    """
    return role in SUPERUSER_ROLES


def has_portfolio_scope(role: UserRole) -> bool:
    """Return True for roles whose data access is scoped to their own portfolio.

    This is the single function that generalizes every former ``role == "advisor"``
    check: both the Runner (``advisor``) and the Coordinador (``coordinator``)
    share the same portfolio scope, resolved server-side against ``tpi.asesores``.
    """
    return role in PORTFOLIO_ROLES


def profile_label(role: UserRole) -> str:
    """Return the display-only profile label for a role (Runner/Coordinador/Socio).

    The technical roles keep their own value unchanged; this never affects
    authorization, only the top-bar presentation.
    """
    return PROFILE_LABELS.get(role, role)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal application identity, deliberately excluding credentials and tokens.

    ``advisor_id`` binds a portfolio identity (``advisor`` or ``coordinator``) to
    ``tpi.asesores.id_asesor``. It is functional for portfolio roles only and
    optional/ignored for every other role. The value is resolved server-side against
    ``tpi.asesores``; it is never derived from ``username`` or ``display_name``.
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

"""Stable authentication contracts, independent from the chosen provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UserRole = Literal["tester", "admin", "advisor", "operations", "readonly"]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal application identity, deliberately excluding credentials and tokens."""

    subject: str
    username: str
    display_name: str
    role: UserRole


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """Explicit outcome for a login attempt without exposing verification details."""

    status: Literal["authenticated", "invalid", "unavailable"]
    user: AuthenticatedUser | None = None

"""Provider protocol for replaceable application authentication."""

from __future__ import annotations

from typing import Protocol

from app.auth.models import AuthenticationResult


class AuthProvider(Protocol):
    """Authenticate credentials without leaking provider-specific details to pages."""

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """Return a safe, typed result for one authentication attempt."""

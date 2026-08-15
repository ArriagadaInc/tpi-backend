"""Public application authentication boundary."""

from app.auth.guards import get_current_user, logout, require_authenticated_user
from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.auth.provider import AuthProvider
from app.auth.simple_dev import AuthConfigurationError, SimpleDevAuth, build_auth_provider

__all__ = [
    "AuthenticatedUser",
    "AuthenticationResult",
    "AuthConfigurationError",
    "AuthProvider",
    "SimpleDevAuth",
    "UserRole",
    "build_auth_provider",
    "get_current_user",
    "logout",
    "require_authenticated_user",
]

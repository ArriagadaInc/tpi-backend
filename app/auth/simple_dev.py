"""DEV-only Argon2id authentication backed by an injected secret JSON value."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.auth.provider import AuthProvider
from app.config import Settings

_ALLOWED_ROLES = {"tester", "admin", "advisor", "operations", "readonly"}


class AuthConfigurationError(ValueError):
    """Raised only inside the auth boundary for invalid secret configuration."""


@dataclass(frozen=True, slots=True)
class _ConfiguredUser:
    user: AuthenticatedUser
    password_hash: str


class SimpleDevAuth(AuthProvider):
    """Verify DEV credentials with Argon2id; never retain passwords in session state."""

    def __init__(self, settings: Settings, hasher: PasswordHasher | None = None) -> None:
        settings.validate_auth_configuration()
        if not settings.auth_enabled:
            raise AuthConfigurationError("SimpleDevAuth is disabled")
        if settings.auth_users_json is None:
            raise AuthConfigurationError("Auth users configuration is missing")
        self._hasher = hasher or PasswordHasher()
        self._users = _parse_users(settings.auth_users_json.get_secret_value())
        self._validate_configured_hashes()

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """Verify a supplied password with a uniform safe result for invalid credentials."""
        normalized_username = username.strip().casefold()
        configured = self._users.get(normalized_username)
        verification_target = configured or next(iter(self._users.values()))

        try:
            is_valid = self._hasher.verify(verification_target.password_hash, password)
        except InvalidHashError as exc:
            raise AuthConfigurationError("Invalid password hash") from exc
        except VerificationError:
            return AuthenticationResult(status="invalid")

        if configured is None or not is_valid:
            return AuthenticationResult(status="invalid")

        return AuthenticationResult(status="authenticated", user=configured.user)

    def _validate_configured_hashes(self) -> None:
        for configured in self._users.values():
            try:
                self._hasher.check_needs_rehash(configured.password_hash)
            except InvalidHashError as exc:
                raise AuthConfigurationError("Invalid password hash") from exc


def build_auth_provider(settings: Settings) -> AuthProvider:
    """Create the configured provider or fail closed at the application boundary."""
    return SimpleDevAuth(settings)


def _parse_users(raw_secret: str) -> dict[str, _ConfiguredUser]:
    try:
        payload = json.loads(raw_secret)
    except json.JSONDecodeError as exc:
        raise AuthConfigurationError("Invalid auth users JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("users"), list):
        raise AuthConfigurationError("Auth users configuration is incomplete")

    users: dict[str, _ConfiguredUser] = {}
    for entry in payload["users"]:
        configured = _parse_user(entry)
        username_key = configured.user.username.casefold()
        if username_key in users:
            raise AuthConfigurationError("Duplicate auth username")
        users[username_key] = configured

    if not users:
        raise AuthConfigurationError("Auth users configuration is empty")
    return users


def _parse_user(entry: Any) -> _ConfiguredUser:
    if not isinstance(entry, dict):
        raise AuthConfigurationError("Invalid auth user entry")

    subject = _required_string(entry, "subject")
    username = _required_string(entry, "username")
    display_name = _required_string(entry, "display_name")
    password_hash = _required_string(entry, "password_hash")
    role = _required_string(entry, "role")
    if role not in _ALLOWED_ROLES:
        raise AuthConfigurationError("Unknown auth role")

    return _ConfiguredUser(
        user=AuthenticatedUser(
            subject=subject,
            username=username,
            display_name=display_name,
            role=cast(UserRole, role),
        ),
        password_hash=password_hash,
    )


def _required_string(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthConfigurationError("Auth user entry is incomplete")
    return value.strip()

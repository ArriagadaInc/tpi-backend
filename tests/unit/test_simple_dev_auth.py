"""Unit tests for the DEV-only auth boundary."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from argon2 import PasswordHasher

from app.auth import AuthConfigurationError, AuthenticatedUser, SimpleDevAuth
from app.auth.simple_dev import _parse_advisor_id
from app.config import Settings


def _hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)


def _settings(
    *,
    secret: str | None = None,
    app_env: str = "aws-dev",
    auth_enabled: bool = True,
    auth_mode: str = "simple-dev",
) -> Settings:
    return Settings(
        APP_ENV=app_env,
        AUTH_ENABLED=auth_enabled,
        AUTH_MODE=auth_mode,
        AUTH_USERS_JSON=secret,
    )


def _users_secret(password: str = "valid-password") -> str:
    return json.dumps(
        {
            "users": [
                {
                    "subject": "user-001",
                    "username": "tester",
                    "display_name": "Tester DEV",
                    "role": "tester",
                    "password_hash": _hasher().hash(password),
                }
            ]
        }
    )


def test_valid_credentials_return_stable_authenticated_user() -> None:
    provider = SimpleDevAuth(_settings(secret=_users_secret()), hasher=_hasher())

    result = provider.authenticate("Tester", "valid-password")

    assert result.status == "authenticated"
    assert result.user == AuthenticatedUser("user-001", "tester", "Tester DEV", "tester")


def test_invalid_and_unknown_credentials_have_same_safe_result() -> None:
    provider = SimpleDevAuth(_settings(secret=_users_secret()), hasher=_hasher())

    assert provider.authenticate("tester", "wrong-password").status == "invalid"
    assert provider.authenticate("unknown", "wrong-password").status == "invalid"


@pytest.mark.parametrize(
    ("secret", "message"),
    [
        (None, "AUTH_USERS_JSON"),
        ("not-json", "Invalid auth users JSON"),
        (json.dumps({"users": []}), "empty"),
        (
            json.dumps(
                {
                    "users": [
                        {
                            "subject": "user-001",
                            "username": "tester",
                            "display_name": "Tester DEV",
                            "role": "tester",
                            "password_hash": "not-an-argon2-hash",
                        }
                    ]
                }
            ),
            "Invalid password hash",
        ),
    ],
)
def test_invalid_secret_configuration_fails_closed(secret: str | None, message: str) -> None:
    with pytest.raises((AuthConfigurationError, ValueError), match=message):
        SimpleDevAuth(_settings(secret=secret), hasher=_hasher())


def test_unknown_role_fails_closed() -> None:
    payload = json.loads(_users_secret())
    payload["users"][0]["role"] = "owner"

    with pytest.raises(AuthConfigurationError, match="Unknown auth role"):
        SimpleDevAuth(_settings(secret=json.dumps(payload)), hasher=_hasher())


@pytest.mark.parametrize(
    ("app_env", "auth_enabled", "auth_mode"),
    [
        ("aws-dev", False, "simple-dev"),
        ("aws-dev", True, "unsupported"),
        ("production", True, "simple-dev"),
        ("production", False, "simple-dev"),
        ("local", False, "unsupported"),
    ],
)
def test_deployed_auth_misconfiguration_is_rejected(
    app_env: str, auth_enabled: bool, auth_mode: str
) -> None:
    settings = _settings(
        secret=_users_secret(),
        app_env=app_env,
        auth_enabled=auth_enabled,
        auth_mode=auth_mode,
    )

    with pytest.raises(ValueError):
        settings.validate_auth_configuration()


def test_disabled_auth_is_allowed_only_for_controlled_local_testing() -> None:
    settings = _settings(app_env="testing", auth_enabled=False)

    assert settings.authentication_required is False
    settings.validate_auth_configuration()


# ---------------------------------------------------------------------------
# coordinator (AC-2): advisor_id parseado igual que advisor, fail-closed
# ---------------------------------------------------------------------------

_VALID_ADVISOR_ID = "11111111-2222-3333-4444-555555555555"


def _coordinator_secret(*, advisor_id: object = _VALID_ADVISOR_ID) -> str:
    entry: dict[str, object] = {
        "subject": "user-coord",
        "username": "coordinator",
        "display_name": "Coordinador DEV",
        "role": "coordinator",
        "password_hash": _hasher().hash("valid-password"),
    }
    if advisor_id is not None:
        entry["advisor_id"] = advisor_id
    return json.dumps({"users": [entry]})


@pytest.mark.parametrize(
    ("advisor_id", "expected"),
    [
        (_VALID_ADVISOR_ID, UUID(_VALID_ADVISOR_ID)),
        (None, None),
        ("", None),
        ("   ", None),
        ("no-es-uuid", None),
        (12345, None),
    ],
)
def test_parse_advisor_id_for_coordinator(advisor_id: object, expected: UUID | None) -> None:
    entry: dict[str, Any] = {}
    if advisor_id is not None:
        entry["advisor_id"] = advisor_id
    assert _parse_advisor_id(entry, "coordinator", "subject-coord") == expected


def test_parse_advisor_id_only_applies_to_portfolio_roles() -> None:
    entry = {"advisor_id": _VALID_ADVISOR_ID}
    assert _parse_advisor_id(entry, "advisor", "subject-1") == UUID(_VALID_ADVISOR_ID)
    assert _parse_advisor_id(entry, "coordinator", "subject-1") == UUID(_VALID_ADVISOR_ID)
    # Los roles sin cartera ignoran el campo (compatibilidad hacia atrás).
    for role in ("ceo", "cto", "admin", "executive", "operations", "readonly", "tester"):
        assert _parse_advisor_id(entry, role, "subject-1") is None


def test_coordinator_role_is_allowed_and_resolves_advisor_id() -> None:
    provider = SimpleDevAuth(_settings(secret=_coordinator_secret()), hasher=_hasher())

    result = provider.authenticate("coordinator", "valid-password")

    assert result.status == "authenticated"
    assert result.user is not None
    assert result.user.role == "coordinator"
    assert result.user.advisor_id == UUID(_VALID_ADVISOR_ID)


def test_coordinator_without_advisor_id_authenticates_fail_closed_to_none() -> None:
    provider = SimpleDevAuth(
        _settings(secret=_coordinator_secret(advisor_id=None)), hasher=_hasher()
    )

    result = provider.authenticate("coordinator", "valid-password")

    assert result.status == "authenticated"
    assert result.user is not None
    assert result.user.role == "coordinator"
    assert result.user.advisor_id is None

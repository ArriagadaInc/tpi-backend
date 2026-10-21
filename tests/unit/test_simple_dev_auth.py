"""Unit tests for the DEV-only auth boundary."""

from __future__ import annotations

import json

import pytest
from argon2 import PasswordHasher

from app.auth import AuthConfigurationError, AuthenticatedUser, SimpleDevAuth
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

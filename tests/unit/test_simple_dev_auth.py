"""Unit tests for the DEV-only auth boundary."""

from __future__ import annotations

import json

import pytest
from argon2 import PasswordHasher

from app.auth import AuthConfigurationError, AuthenticatedUser, SimpleDevAuth, guards
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


class _StopRenderingError(Exception):
    pass


class _Sidebar:
    def caption(self, _: str) -> None:
        return None

    def button(self, _: str, *, key: str) -> bool:
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.sidebar = _Sidebar()
        self.rerun_called = False

    def markdown(self, *_: object, **__: object) -> None:
        return None

    def title(self, _: str) -> None:
        return None

    def caption(self, _: str) -> None:
        return None

    def error(self, _: str) -> None:
        return None

    def stop(self) -> None:
        raise _StopRenderingError

    def rerun(self) -> None:
        self.rerun_called = True


def test_guard_blocks_unauthenticated_deployed_access(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_streamlit = _FakeStreamlit()
    monkeypatch.setattr(guards, "st", fake_streamlit)

    with pytest.raises(_StopRenderingError):
        guards.require_authenticated_user(settings=_settings(secret=None))


def test_guard_allows_authenticated_session_and_logout_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _FakeStreamlit()
    user = AuthenticatedUser("user-001", "tester", "Tester DEV", "tester")
    fake_streamlit.session_state["_tpi_auth_user"] = user
    fake_streamlit.session_state["_tpi_auth_failed_attempts"] = 3
    monkeypatch.setattr(guards, "st", fake_streamlit)

    assert guards.require_authenticated_user(settings=_settings(secret=None)) == user
    guards.logout()

    assert guards.get_current_user() is None
    assert fake_streamlit.rerun_called is True


def test_session_throttle_blocks_after_five_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_streamlit = _FakeStreamlit()
    monkeypatch.setattr(guards, "st", fake_streamlit)

    for _ in range(5):
        guards._record_failed_attempt(now=100.0)

    assert guards._blocked_seconds_remaining(now=100.0) == 5
    assert guards._auth_session_snapshot()["failed_attempts"] == 5

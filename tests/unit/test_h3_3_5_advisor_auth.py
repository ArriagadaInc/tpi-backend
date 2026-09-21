"""Unit tests for the H3.3.5 advisor_id auth extension.

Covers the parser contract: ``advisor_id`` is parsed only for ``advisor`` identities,
is optional/ignored for every other role, and a malformed value fails closed to ``None``
without breaking login or logging the raw value.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from argon2 import PasswordHasher

from app.auth import AuthConfigurationError, SimpleDevAuth
from app.config import Settings

ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)


def _settings(secret: str) -> Settings:
    return Settings(
        APP_ENV="aws-dev",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON=secret,
    )


def _secret(role: str, *, advisor_id: object = "MISSING") -> str:
    entry = {
        "subject": f"subject-{role}",
        "username": f"user-{role}",
        "display_name": f"User {role}",
        "role": role,
        "password_hash": _hasher().hash("password"),
    }
    if advisor_id != "MISSING":
        entry["advisor_id"] = advisor_id
    return json.dumps({"users": [entry]})


def _advisor_id(secret: str, username: str) -> UUID | None:
    provider = SimpleDevAuth(_settings(secret), hasher=_hasher())
    result = provider.authenticate(username, "password")
    assert result.status == "authenticated"
    assert result.user is not None
    return result.user.advisor_id


def test_non_advisor_roles_ignore_advisor_id() -> None:
    # Backward compatible: a non-advisor entry carrying advisor_id ignores it.
    for role in ("tester", "admin", "executive", "operations", "readonly", "ceo", "cto"):
        user_id = _advisor_id(_secret(role, advisor_id=str(ADVISOR_ID)), f"user-{role}")
        assert user_id is None


def test_advisor_with_valid_advisor_id_is_parsed() -> None:
    user_id = _advisor_id(_secret("advisor", advisor_id=str(ADVISOR_ID)), "user-advisor")
    assert user_id == ADVISOR_ID


def test_advisor_without_advisor_id_fails_closed() -> None:
    # No advisor_id key at all -> None (D4: empty portfolio, not global access).
    user_id = _advisor_id(_secret("advisor"), "user-advisor")
    assert user_id is None


def test_advisor_with_malformed_advisor_id_fails_closed() -> None:
    user_id = _advisor_id(_secret("advisor", advisor_id="not-a-uuid"), "user-advisor")
    assert user_id is None


def test_advisor_with_non_string_advisor_id_fails_closed() -> None:
    user_id = _advisor_id(_secret("advisor", advisor_id={"id": str(ADVISOR_ID)}), "user-advisor")
    assert user_id is None


def test_malformed_advisor_id_does_not_break_login() -> None:
    provider = SimpleDevAuth(_settings(_secret("advisor", advisor_id="garbage")), hasher=_hasher())
    result = provider.authenticate("user-advisor", "password")
    assert result.status == "authenticated"
    assert result.user is not None
    assert result.user.advisor_id is None


def test_duplicate_usernames_still_rejected() -> None:
    entry = {
        "subject": "s1",
        "username": "dup",
        "display_name": "Dup",
        "role": "advisor",
        "advisor_id": str(ADVISOR_ID),
        "password_hash": _hasher().hash("password"),
    }
    secret = json.dumps({"users": [entry, dict(entry)]})
    with pytest.raises(AuthConfigurationError, match="Duplicate auth username"):
        SimpleDevAuth(_settings(secret), hasher=_hasher())

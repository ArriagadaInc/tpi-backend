"""Unit tests for the H3.3.2 CEO/CTO superuser RBAC model.

AC-4/AC-5: CEO and CTO are functional superusers with a superset of existing
RBAC capabilities. This is enforced by a single SUPERUSER_ROLES source of truth
applied consistently across the service and web layers.
"""

from __future__ import annotations

from typing import Any, cast

from app.auth.models import SUPERUSER_ROLES, AuthenticatedUser, UserRole, is_superuser
from app.services.solicitud_service import SolicitudService
from app.web.routes.leads import _can_cleanup, _can_write

_ALL_ROLES = [
    "tester",
    "admin",
    "advisor",
    "executive",
    "operations",
    "readonly",
    "ceo",
    "cto",
]

_SUPERUSER_ROLES = ("ceo", "cto")


class _NoOpRepository:
    """Minimal repository stand-in; capability checks never touch persistence."""


def _user(role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
    )


def test_superuser_roles_are_exactly_ceo_and_cto() -> None:
    assert SUPERUSER_ROLES == frozenset(_SUPERUSER_ROLES)


def test_superuser_roles_are_all_valid_user_roles() -> None:
    assert SUPERUSER_ROLES <= frozenset(_ALL_ROLES)


def test_is_superuser_true_only_for_ceo_and_cto() -> None:
    for role in _ALL_ROLES:
        assert is_superuser(cast(UserRole, role)) is (role in _SUPERUSER_ROLES)


def test_service_capabilities_honor_superuser_superset() -> None:
    service = SolicitudService(repository=cast(Any, _NoOpRepository()))

    for role in _SUPERUSER_ROLES:
        user = _user(role)
        assert service.can_view_full_pii(user) is True
        assert service.can_assign_lead(user) is True

    assert service.can_view_full_pii(_user("readonly")) is False
    assert service.can_assign_lead(_user("readonly")) is False


def test_web_capabilities_honor_superuser_superset() -> None:
    for role in _SUPERUSER_ROLES:
        user = _user(role)
        assert _can_write(user) is True
        assert _can_cleanup(user) is True

    assert _can_write(_user("readonly")) is False
    assert _can_cleanup(_user("readonly")) is False
    assert _can_write(None) is False
    assert _can_cleanup(None) is False

"""Server-side access-control tests for the executive dashboard route."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.config import Settings
from app.models.executive_dashboard import (
    CurrentSnapshot,
    DashboardFilters,
    ExecutiveDashboard,
    PeriodActivity,
)
from app.services.executive_dashboard_service import ExecutiveDashboardService
from app.web.main import create_web_app


class _FakeAuthProvider:
    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        roles = {
            "ceo.local": "ceo",
            "cto.local": "cto",
            "advisor.local": "advisor",
        }
        role = roles.get(username)
        if role is None:
            return AuthenticationResult(status="invalid")
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"{role}-subject",
                username=username,
                display_name=f"{role.title()} Demo",
                role=role,  # type: ignore[arg-type]
            ),
        )


class _CountingDashboardService(ExecutiveDashboardService):
    def __init__(self) -> None:
        self.calls = 0

    def build_executive_dashboard(self, filters: DashboardFilters) -> ExecutiveDashboard:
        self.calls += 1
        return ExecutiveDashboard(
            filters=filters,
            current_snapshot=CurrentSnapshot(),
            period_activity=PeriodActivity(),
            alerts=[],
        )


def _build_client(service: ExecutiveDashboardService) -> TestClient:
    app = create_web_app()
    app.state.executive_dashboard_service = service
    app.state.auth_provider = _FakeAuthProvider()
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    return TestClient(app)


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/login",
        data={"username": username, "password": "irrelevant"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_ceo_can_access_dashboard() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "ceo.local")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert service.calls == 1


def test_cto_can_access_dashboard() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "cto.local")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert service.calls == 1


def test_other_authenticated_role_receives_403() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "advisor.local")
    response = client.get("/dashboard")
    assert response.status_code == 403


def test_anonymous_receives_403() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    response = client.get("/dashboard")
    assert response.status_code == 403


def test_no_dashboard_query_runs_on_rejection() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "advisor.local")
    response = client.get("/dashboard")
    assert response.status_code == 403
    assert service.calls == 0

    anonymous = _build_client(_CountingDashboardService())
    anonymous.get("/dashboard")
    # The anonymous client used its own service instance; assert the shared one
    # is still untouched for the authenticated-but-unauthorized case above.
    assert service.calls == 0


def test_invalid_date_range_returns_400_for_authorized_user() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "ceo.local")
    response = client.get("/dashboard?fecha_desde=2026-09-20&fecha_hasta=2026-09-01")
    assert response.status_code == 400
    assert service.calls == 0


def test_dashboard_route_does_not_leak_pii_in_rendered_placeholder() -> None:
    service = _CountingDashboardService()
    client = _build_client(service)
    _login(client, "ceo.local")
    response = client.get("/dashboard")
    assert response.status_code == 200
    for pii_token in ("nombre_completo", "telefono", "email"):
        assert pii_token not in response.text
    # No RUT-like value is rendered in the placeholder.
    assert re.search(r"\d{1,2}\.\d{3}\.\d{3}-[0-9kK]", response.text) is None

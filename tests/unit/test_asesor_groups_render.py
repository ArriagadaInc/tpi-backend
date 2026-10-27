"""Render tests for the grouped advisor summary in the executive dashboard (AC-5).

The «Resumen por asesor» card and its «Ver casos por estado y asesor» detail split
advisors into Coordinadores and Runners (Socios only defensively), each group with its
own title, the same columns, a count-only subtotal, and a per-group empty state.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult
from app.config import Settings
from app.models.executive_dashboard import (
    GRUPO_COORDINADOR,
    GRUPO_RUNNER,
    GRUPO_SOCIO,
    AsesorRow,
    CurrentSnapshot,
    DashboardFilters,
    EstadoAsesorCell,
    ExecutiveDashboard,
    PeriodActivity,
)
from app.services.executive_dashboard_service import ExecutiveDashboardService
from app.web.main import create_web_app


class _FakeAuthProvider:
    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        if username != "ceo.local":
            return AuthenticationResult(status="invalid")
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject="ceo-subject",
                username=username,
                display_name="CEO Demo",
                role="ceo",  # type: ignore[arg-type]
            ),
        )


def _asesor(id_asesor: str | None, nombre: str, grupo: str) -> AsesorRow:
    return AsesorRow(
        id_asesor=id_asesor,
        nombre=nombre,
        cartera_total=10,
        cartera_activa=6,
        estancados=2,
        tiempo_asignacion_dias=0.5,
        tiempo_primera_gestion_dias=1.0,
        grupo=grupo,
    )


def _dashboard(cartera: list[AsesorRow], casos: list[EstadoAsesorCell]) -> ExecutiveDashboard:
    return ExecutiveDashboard(
        filters=DashboardFilters.from_raw(),
        current_snapshot=CurrentSnapshot(
            cartera_por_asesor=cartera, casos_por_estado_y_asesor=casos
        ),
        period_activity=PeriodActivity(),
        alerts=[],
    )


class _StubService(ExecutiveDashboardService):
    def __init__(self, dashboard: ExecutiveDashboard) -> None:
        super().__init__(repository=object(), settings=Settings(APP_ENV="testing"))  # type: ignore[arg-type]
        self._dashboard = dashboard

    def build_executive_dashboard(self, filters: DashboardFilters) -> ExecutiveDashboard:
        return self._dashboard

    def get_filter_options(self) -> dict[str, list[object]]:
        return {"estados": [], "asesores": [], "afps": [], "origenes": [], "fuentes": []}


def _page(dashboard: ExecutiveDashboard) -> str:
    app = create_web_app()
    app.state.executive_dashboard_service = _StubService(dashboard)
    app.state.auth_provider = _FakeAuthProvider()
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    client = TestClient(app)
    login = client.post(
        "/login", data={"username": "ceo.local", "password": "x"}, follow_redirects=False
    )
    assert login.status_code == 303
    response = client.get("/dashboard")
    assert response.status_code == 200, response.status_code
    return response.text


def test_dashboard_shows_two_groups_with_titles_and_subtotals() -> None:
    body = _page(
        _dashboard(
            [
                _asesor("c1", "Coord Uno", GRUPO_COORDINADOR),
                _asesor("r1", "Runner Uno", GRUPO_RUNNER),
                _asesor(None, "Sin asesor", "sin_asesor"),
            ],
            [
                EstadoAsesorCell("c1", "Coord Uno", "nuevo", "Nuevo", 4, GRUPO_COORDINADOR),
                EstadoAsesorCell("r1", "Runner Uno", "nuevo", "Nuevo", 2, GRUPO_RUNNER),
            ],
        )
    )
    assert "Coordinadores" in body
    assert "Runners" in body
    assert "Coord Uno" in body
    assert "Runner Uno" in body
    assert "Sin asesor" in body
    assert "Subtotal" in body
    assert "asesor-subtotal" in body


def test_empty_coordinador_group_shows_per_group_empty_state() -> None:
    body = _page(
        _dashboard(
            [_asesor("r1", "Runner Uno", GRUPO_RUNNER)],
            [EstadoAsesorCell("r1", "Runner Uno", "nuevo", "Nuevo", 2, GRUPO_RUNNER)],
        )
    )
    assert "Sin coordinadores con cartera" in body
    assert "Runner Uno" in body


def test_socios_are_hidden_unless_they_have_leads() -> None:
    body = _page(
        _dashboard(
            [_asesor("r1", "Runner Uno", GRUPO_RUNNER)],
            [],
        )
    )
    assert "Socios" not in body

    # Defensivo: si un Socio tuviera leads, aparece un tercer grupo.
    body = _page(
        _dashboard(
            [_asesor("s1", "Socio Uno", GRUPO_SOCIO)],
            [EstadoAsesorCell("s1", "Socio Uno", "nuevo", "Nuevo", 1, GRUPO_SOCIO)],
        )
    )
    assert "Socios" in body
    assert "Socio Uno" in body

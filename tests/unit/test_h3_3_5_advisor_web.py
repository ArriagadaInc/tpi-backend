"""Web-layer tests for the H3.3.5 advisor portfolio and dashboard access.

Uses the real ``SolicitudService`` with a fake repository and the real FastAPI app
to verify: dashboard 403, navigation without the dashboard link, empty portfolio
for an unresolved advisor, 404 for foreign/unassigned leads, and no foreign PII in
the rendered HTML.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
FOREIGN_LEAD_ID = UUID("99999999-9999-9999-9999-999999999999")

_LEAD = {
    "id_lead": str(LEAD_ID),
    "rut": "12.345.678-5",
    "nombre_completo": "Juan Perez",
    "email": "juan@example.com",
    "telefono": "+56 9 1234 5678",
    "fecha_nacimiento": datetime(1990, 1, 1),
    "genero": "Masculino",
    "estado_civil": "Soltero",
    "afp": "Habitat",
    "saldo_afp": 1000000,
    "estado_lead": "contactado",
    "comentarios": "Solicitud original.",
    "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
}


class _Repo:
    def __init__(self) -> None:
        self.leads: dict[str, dict[str, Any]] = {str(LEAD_ID): dict(_LEAD)}
        self.owned: set[str] = {str(LEAD_ID)}
        self.board_calls: list[dict[str, Any]] = []

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if str(id_asesor) == str(ADVISOR_ID):
            return {
                "id_asesor": str(ADVISOR_ID),
                "rol": "asesor",
                "estado_disponibilidad": "activo",
            }
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return str(id_asesor) == str(ADVISOR_ID) and str(id_lead) in self.owned

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.leads[str(id_lead)]) if str(id_lead) in self.leads else None

    def get_crm_solicitudes(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        self.board_calls.append(dict(kwargs))
        portfolio = kwargs.get("portfolio_asesor_id")
        if portfolio is not None:
            rows = [dict(v) for k, v in self.leads.items() if k in self.owned]
            return rows, len(rows)
        return [dict(v) for v in self.leads.values()], len(self.leads)

    def get_active_afp(self) -> list[dict[str, Any]]:
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["nuevo", "contactado", "cerrado"]

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return []

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []


class _AuthProvider:
    def __init__(self, advisor_id: UUID | None) -> None:
        self._advisor_id = advisor_id

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject="advisor-subject",
                username=username,
                display_name="Asesor Desarrollo 1",
                role=cast(UserRole, "advisor"),
                advisor_id=self._advisor_id,
            ),
        )


def _client(advisor_id: UUID | None, repo: _Repo) -> TestClient:
    service = SolicitudService(repository=cast(Any, repo))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(advisor_id)
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON='{"users":[]}',
        WEB_MASK_PII=True,
    )
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": "asesor.desarrollo1", "password": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def test_dashboard_returns_403_for_valid_advisor() -> None:
    client = _client(ADVISOR_ID, _Repo())
    assert client.get("/dashboard").status_code == 403


def test_dashboard_returns_403_for_unresolved_advisor() -> None:
    client = _client(None, _Repo())
    assert client.get("/dashboard").status_code == 403


def test_advisor_navigation_hides_dashboard_link() -> None:
    client = _client(ADVISOR_ID, _Repo())
    body = client.get("/leads").text
    assert "Dashboard Ejecutivo" not in body


def test_valid_advisor_board_is_scoped_and_unmasked() -> None:
    repo = _Repo()
    client = _client(ADVISOR_ID, repo)
    body = client.get("/leads").text
    assert "Juan Perez" in body
    assert "12.345.678-5" in body  # own lead full RUT
    assert repo.board_calls[0]["portfolio_asesor_id"] == ADVISOR_ID


def test_unresolved_advisor_board_is_empty() -> None:
    repo = _Repo()
    client = _client(None, repo)
    body = client.get("/leads").text
    assert "Juan Perez" not in body
    assert repo.board_calls == []


def test_valid_advisor_own_detail_returns_full_pii() -> None:
    client = _client(ADVISOR_ID, _Repo())
    response = client.get(f"/leads/{LEAD_ID}")
    assert response.status_code == 200
    assert "12.345.678-5" in response.text
    assert "juan@example.com" in response.text
    assert "+56 9 1234 5678" in response.text


def test_valid_advisor_foreign_detail_is_404_without_pii() -> None:
    repo = _Repo()
    repo.leads[str(FOREIGN_LEAD_ID)] = {
        **_LEAD,
        "id_lead": str(FOREIGN_LEAD_ID),
        "rut": "19.999.999-9",
        "nombre_completo": "Otro Cliente",
        "email": "otro@example.com",
        "telefono": "+56 9 0000 0000",
    }
    client = _client(ADVISOR_ID, repo)
    response = client.get(f"/leads/{FOREIGN_LEAD_ID}")
    assert response.status_code == 404
    assert "Otro Cliente" not in response.text
    assert "otro@example.com" not in response.text


def test_unresolved_advisor_detail_is_404() -> None:
    client = _client(None, _Repo())
    assert client.get(f"/leads/{LEAD_ID}").status_code == 404


def test_advisor_assign_endpoint_is_403() -> None:
    client = _client(ADVISOR_ID, _Repo())
    response = client.post(
        f"/leads/{LEAD_ID}/assign",
        data={"csrf_token": "x", "id_asesor": str(ADVISOR_ID)},
        follow_redirects=False,
    )
    assert response.status_code == 403

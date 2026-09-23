"""Web-layer tests for the H3.3.6 executive XLSX export.

Uses the real ``SolicitudService`` with a fake repository and the real FastAPI app
to verify: the button is rendered only for ceo/cto, the route returns a real 403
for other authenticated roles, anonymous keeps the canonical login redirect, and
the download response carries the safe MIME/security headers and filename.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.services.solicitud_service import SolicitudService
from app.services.xlsx_export import EXPORT_MAX_ROWS
from app.web.main import create_web_app

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")


def _row() -> dict[str, Any]:
    return {
        "id_lead": str(LEAD_ID),
        "rut": "12.345.678-5",
        "nombre_completo": "Juan Perez",
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "genero": "Masculino",
        "estado_civil": "Soltero",
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "comentarios": "Solicitud original.",
        "estado_lead": "contactado",
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        "id_asesor": None,
        "asesor_nombre": None,
    }


class _Repo:
    def __init__(self) -> None:
        self.rows = [_row()]
        self.count_override: int | None = None

    def get_crm_bandeja(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "solicitudes": [dict(row) for row in self.rows],
            "total": len(self.rows),
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return []

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["nuevo", "contactado", "cerrado"]

    def count_crm_solicitudes(self, **kwargs: Any) -> int:
        return self.count_override if self.count_override is not None else len(self.rows)

    def get_crm_solicitudes_export(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]

    def record_xlsx_export_event(self, **kwargs: Any) -> None:
        return None


class _AuthProvider:
    def __init__(self, role: str) -> None:
        self._role = role

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"subject-{self._role}",
                username=username,
                display_name=f"User {self._role}",
                role=cast(UserRole, self._role),
            ),
        )


def _client(role: str, repo: _Repo | None = None) -> TestClient:
    service = SolicitudService(repository=cast(Any, repo or _Repo()))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(role)
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON='{"users":[]}',
        WEB_MASK_PII=True,
    )
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def _anonymous_client() -> TestClient:
    service = SolicitudService(repository=cast(Any, _Repo()))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider("ceo")
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    return TestClient(app)


def test_ceo_and_cto_see_export_button() -> None:
    for role in ("ceo", "cto"):
        body = _client(role).get("/leads").text
        assert "Exportar XLSX" in body, role
        assert "/leads/export.xlsx" in body, role


def test_non_superuser_roles_do_not_see_button() -> None:
    for role in ("advisor", "admin", "executive", "operations", "readonly", "tester"):
        body = _client(role).get("/leads").text
        assert "Exportar XLSX" not in body, role


def test_non_superuser_gets_403() -> None:
    for role in ("advisor", "admin", "executive", "operations", "readonly", "tester"):
        response = _client(role).get("/leads/export.xlsx")
        assert response.status_code == 403, role


def test_anonymous_redirects_to_login() -> None:
    response = _anonymous_client().get("/leads/export.xlsx")
    assert response.status_code == 307
    assert response.headers.get("location") == "/login"


def test_response_security_headers_and_filename() -> None:
    response = _client("ceo").get("/leads/export.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="leads_export_')
    assert disposition.endswith('.xlsx"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_limit_exceeded_clear_message() -> None:
    repo = _Repo()
    repo.count_override = EXPORT_MAX_ROWS + 1
    response = _client("ceo", repo).get("/leads/export.xlsx")
    assert response.status_code == 413
    assert "limite" in response.text.lower()
    assert "Acota los filtros" in response.text

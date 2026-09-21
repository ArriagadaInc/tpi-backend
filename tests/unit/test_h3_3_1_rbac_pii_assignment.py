"""
Unit tests for H3.3.1 acceptance criteria:
- AC-1: CEO/CTO view full PII in board and detail.
- AC-2: Restricted roles receive server-side masked PII without full PII in rendered HTML.
- AC-3: Manual assignment control appears only for authorized roles (admin, executive) and superusers (ceo, cto).
- AC-4: Assignment route behavior (CSRF, role authorization, conflict) is covered here; single-active-assignment, state transition and audit persistence are covered by tests/integration/test_database_runtime.py.
- AC-5: Documentation H3.3 updated without obsolete versions/acceptance items.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.models.crm_states import CRM_STATE_CONTRACT
from app.models.lead_assignment import LeadAssignmentConflictError
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app


class _H331RepositoryStub:
    def __init__(self) -> None:
        self.lead_id = "11111111-1111-1111-1111-111111111111"
        self.asesor_id = "22222222-2222-2222-2222-222222222222"
        self.raw_lead = {
            "id_lead": self.lead_id,
            "id_persona": "33333333-3333-3333-3333-333333333333",
            "rut": "12345678-5",
            "nombre_completo": "Juan Perez Test",
            "email": "juan.perez@example.com",
            "telefono": "+56912345678",
            "afp": "Habitat",
            "saldo_afp": 15000000,
            "estado_lead": "nuevo",
            "comentarios": "Solicitud de prueba H3.3.1",
            "created_at": datetime(2026, 9, 15, 10, 0, tzinfo=UTC),
            "asesor_nombre": None,
            "id_asesor": None,
        }
        self.asesores = [
            {
                "id_asesor": self.asesor_id,
                "nombre": "Maria Asesora",
                "rol": "asesor",
                "estado_disponibilidad": "activo",
                "especialidad": "General",
                "carga_activa": 0,
            }
        ]
        self.assigned = False
        self.assign_calls: list[dict[str, Any]] = []
        self.force_conflict = False

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        if str(id_lead) == self.lead_id:
            res = dict(self.raw_lead)
            if self.assigned:
                res["estado_lead"] = "asignado"
                res["asesor_nombre"] = "Maria Asesora"
                res["id_asesor"] = self.asesor_id
            return res
        return None

    def get_crm_solicitudes(
        self,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        res = dict(self.raw_lead)
        if self.assigned:
            res["estado_lead"] = "asignado"
            res["asesor_nombre"] = "Maria Asesora"
            res["id_asesor"] = self.asesor_id
        return [res], 1

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_active_afp(self) -> list[dict[str, Any]]:
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(CRM_STATE_CONTRACT)

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return list(self.asesores)

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def assign_lead(self, id_lead: UUID, id_asesor: UUID, *, actor: AuthenticatedUser) -> bool:
        if self.force_conflict:
            raise LeadAssignmentConflictError("El lead ya tiene una asignacion activa")
        if str(id_lead) == self.lead_id and str(id_asesor) == self.asesor_id:
            self.assigned = True
            self.assign_calls.append({"id_lead": id_lead, "id_asesor": id_asesor, "actor": actor})
            return True
        return False


class _StubAuthProvider:
    def __init__(self, role: str) -> None:
        self.role = role

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"usr-{self.role}",
                username=username,
                display_name=f"User {self.role.upper()}",
                role=cast(UserRole, self.role),
            ),
        )


def _build_stub_service() -> tuple[SolicitudService, _H331RepositoryStub]:
    repo = _H331RepositoryStub()
    return SolicitudService(repository=cast(Any, repo)), repo


def _user(role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"user-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role.upper()}",
        role=cast(UserRole, role),
    )


# ---------------------------------------------------------------------------
# AC-1 / AC-2: Service-level PII visibility by role
# ---------------------------------------------------------------------------


def test_ac1_ac2_pii_visibility_by_role() -> None:
    service, repo = _build_stub_service()

    # AC-1: CEO and CTO can view full PII
    for full_pii_role in ("ceo", "cto"):
        user = _user(full_pii_role)
        assert service.can_view_full_pii(user) is True

        # Board PII
        board = service.get_crm_bandeja(user=user, masked=True)
        sol = board["solicitudes"][0]
        assert sol["rut"] == "12345678-5"
        assert sol["email"] == "juan.perez@example.com"
        assert sol["telefono"] == "+56912345678"

        # Detail PII
        detail = service.get_solicitud_detalle_masked(UUID(repo.lead_id), user=user)
        assert detail is not None
        assert detail["rut"] == "12345678-5"
        assert detail["email"] == "juan.perez@example.com"
        assert detail["telefono"] == "+56912345678"

    # AC-2: Restricted roles receive server-side masked PII. ``advisor`` is excluded
    # here because H3.3.5 redefines it: an advisor without a valid advisor_id fails
    # closed to an empty portfolio (covered by tests/unit/test_h3_3_5_advisor_service.py).
    for restricted_role in ("operations", "admin", "executive", "readonly", "tester"):
        user = _user(restricted_role)
        assert service.can_view_full_pii(user) is False

        # Board PII masked
        board = service.get_crm_bandeja(user=user, masked=True)
        sol = board["solicitudes"][0]
        assert sol["rut"] != "12345678-5"
        assert sol["email"] != "juan.perez@example.com"
        assert sol["telefono"] != "+56912345678"
        assert "*" in sol["rut"]
        assert "*" in sol["email"]
        assert "*" in sol["telefono"]

        # Detail PII masked
        detail = service.get_solicitud_detalle_masked(UUID(repo.lead_id), user=user)
        assert detail is not None
        assert detail["rut"] != "12345678-5"
        assert detail["email"] != "juan.perez@example.com"
        assert detail["telefono"] != "+56912345678"
        assert "*" in detail["rut"]
        assert "*" in detail["email"]
        assert "*" in detail["telefono"]


# ---------------------------------------------------------------------------
# AC-3: Manual assignment authorization
# ---------------------------------------------------------------------------


def test_ac3_manual_assignment_authorization() -> None:
    service, _ = _build_stub_service()

    # Authorized assignment roles (admin, executive) plus superusers (ceo, cto).
    for role in ("admin", "executive", "ceo", "cto"):
        assert service.can_assign_lead(_user(role)) is True

    # Unauthorized assignment roles
    for role in ("advisor", "operations", "readonly", "tester"):
        assert service.can_assign_lead(_user(role)) is False


# ---------------------------------------------------------------------------
# Web client helpers
# ---------------------------------------------------------------------------


def _client_for_role(
    role: str,
    service: SolicitudService,
    *,
    web_mask_pii: bool = True,
) -> TestClient:
    web_app = create_web_app()
    web_app.state.web_service = service
    web_app.state.auth_provider = _StubAuthProvider(role)
    web_app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        AUTH_USERS_JSON='{"users":[]}',
        WEB_MASK_PII=web_mask_pii,
    )
    client = TestClient(web_app)
    client.post("/login", data={"username": "user", "password": "pass"})
    return client


def _get_csrf_token(client: TestClient, lead_id: str) -> str:
    """Extract the CSRF token from the lead detail page."""
    resp = client.get(f"/leads/{lead_id}")
    html = resp.text
    # Find csrf_token value in hidden input
    marker = 'name="csrf_token" value="'
    idx = html.find(marker)
    assert idx != -1, "CSRF token not found in detail page"
    start = idx + len(marker)
    end = html.index('"', start)
    return html[start:end]


# ---------------------------------------------------------------------------
# AC-1 / AC-2 / AC-3: Web HTML rendering
# ---------------------------------------------------------------------------


def test_ac1_ac2_ac3_web_html_rendering() -> None:
    service, repo = _build_stub_service()

    # 1. Restricted role web rendering (operations; advisor scoping is H3.3.5)
    client_adv = _client_for_role("operations", service)
    resp_board_res = client_adv.get("/leads")
    assert resp_board_res.status_code == 200
    html_board_res = resp_board_res.text
    assert "12345678-5" not in html_board_res
    assert "juan.perez@example.com" not in html_board_res
    assert "+56912345678" not in html_board_res
    assert "*" in html_board_res

    resp_detail_res = client_adv.get(f"/leads/{repo.lead_id}")
    assert resp_detail_res.status_code == 200
    html_detail_res = resp_detail_res.text
    assert "12345678-5" not in html_detail_res
    assert "juan.perez@example.com" not in html_detail_res
    assert "+56912345678" not in html_detail_res

    # 2. Privileged CEO web rendering
    client_ceo = _client_for_role("ceo", service)
    resp_board_ceo = client_ceo.get("/leads")
    assert resp_board_ceo.status_code == 200
    html_board_ceo = resp_board_ceo.text
    assert "12345678-5" in html_board_ceo

    resp_detail_ceo = client_ceo.get(f"/leads/{repo.lead_id}")
    assert resp_detail_ceo.status_code == 200
    html_detail_ceo = resp_detail_ceo.text
    assert "12345678-5" in html_detail_ceo
    assert "juan.perez@example.com" in html_detail_ceo
    assert "+56912345678" in html_detail_ceo

    # 3. Authorized assignment role web rendering (admin)
    client_admin = _client_for_role("admin", service)
    resp_detail_admin = client_admin.get(f"/leads/{repo.lead_id}")
    assert resp_detail_admin.status_code == 200
    assert "Maria Asesora" in resp_detail_admin.text


# ---------------------------------------------------------------------------
# AC-2 RV-03 fix: PII masking unconditional even with WEB_MASK_PII=False
# ---------------------------------------------------------------------------


def test_ac2_pii_masked_even_with_web_mask_pii_false() -> None:
    """
    Verifies that restricted roles do NOT see full PII in HTML even when the
    environment flag WEB_MASK_PII is set to False. This proves masking is
    unconditionally role-based (RV-H3.3.1-03 fix).
    """
    service, repo = _build_stub_service()

    for restricted_role in ("operations", "readonly", "tester"):
        client = _client_for_role(restricted_role, service, web_mask_pii=False)

        # Board must NOT expose full PII
        resp_board = client.get("/leads")
        assert resp_board.status_code == 200
        html_board = resp_board.text
        assert (
            "12345678-5" not in html_board
        ), f"Board HTML for {restricted_role} leaks RUT with WEB_MASK_PII=False"
        assert (
            "juan.perez@example.com" not in html_board
        ), f"Board HTML for {restricted_role} leaks email with WEB_MASK_PII=False"
        assert (
            "+56912345678" not in html_board
        ), f"Board HTML for {restricted_role} leaks phone with WEB_MASK_PII=False"

        # Detail must NOT expose full PII
        resp_detail = client.get(f"/leads/{repo.lead_id}")
        assert resp_detail.status_code == 200
        html_detail = resp_detail.text
        assert (
            "12345678-5" not in html_detail
        ), f"Detail HTML for {restricted_role} leaks RUT with WEB_MASK_PII=False"
        assert (
            "juan.perez@example.com" not in html_detail
        ), f"Detail HTML for {restricted_role} leaks email with WEB_MASK_PII=False"
        assert (
            "+56912345678" not in html_detail
        ), f"Detail HTML for {restricted_role} leaks phone with WEB_MASK_PII=False"


def test_ac1_ceo_sees_full_pii_with_web_mask_pii_false() -> None:
    """CEO still sees full PII when WEB_MASK_PII=False (no regression)."""
    service, repo = _build_stub_service()
    client = _client_for_role("ceo", service, web_mask_pii=False)

    resp_board = client.get("/leads")
    assert resp_board.status_code == 200
    assert "12345678-5" in resp_board.text

    resp_detail = client.get(f"/leads/{repo.lead_id}")
    assert resp_detail.status_code == 200
    assert "12345678-5" in resp_detail.text
    assert "juan.perez@example.com" in resp_detail.text
    assert "+56912345678" in resp_detail.text


# ---------------------------------------------------------------------------
# AC-4 / RV-06: Assignment web route tests
# ---------------------------------------------------------------------------


def test_ac4_assign_lead_web_success() -> None:
    """POST /leads/{id}/assign with valid CSRF and authorized role returns 303."""
    service, repo = _build_stub_service()
    client = _client_for_role("admin", service)
    csrf_token = _get_csrf_token(client, repo.lead_id)

    resp = client.post(
        f"/leads/{repo.lead_id}/assign",
        data={
            "csrf_token": csrf_token,
            "id_asesor": repo.asesor_id,
            "return_to": "/leads",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert repo.assigned is True
    assert len(repo.assign_calls) == 1
    assert repo.assign_calls[0]["actor"].subject == "usr-admin"


def test_ac4_assign_lead_invalid_csrf_returns_403() -> None:
    """POST /leads/{id}/assign with invalid CSRF returns 403."""
    service, repo = _build_stub_service()
    client = _client_for_role("admin", service)

    resp = client.post(
        f"/leads/{repo.lead_id}/assign",
        data={
            "csrf_token": "invalid-token",
            "id_asesor": repo.asesor_id,
        },
    )
    assert resp.status_code == 403
    assert repo.assigned is False


def test_ac4_assign_lead_unauthorized_role_returns_403() -> None:
    """POST /leads/{id}/assign with unauthorized role (readonly) returns 403."""
    service, repo = _build_stub_service()
    client = _client_for_role("readonly", service)

    resp = client.post(
        f"/leads/{repo.lead_id}/assign",
        data={
            "csrf_token": "any",
            "id_asesor": repo.asesor_id,
        },
    )
    assert resp.status_code == 403
    assert repo.assigned is False


def test_ac4_assign_lead_conflict_returns_409() -> None:
    """POST /leads/{id}/assign when lead already assigned returns 409."""
    service, repo = _build_stub_service()
    repo.force_conflict = True
    client = _client_for_role("admin", service)
    csrf_token = _get_csrf_token(client, repo.lead_id)

    resp = client.post(
        f"/leads/{repo.lead_id}/assign",
        data={
            "csrf_token": csrf_token,
            "id_asesor": repo.asesor_id,
        },
    )
    assert resp.status_code == 409
    assert "asignacion activa" in resp.text.lower() or "asignación activa" in resp.text.lower()


# ---------------------------------------------------------------------------
# AC-5: Documentation sanity
# ---------------------------------------------------------------------------


def test_ac5_documentation_h3_3_has_no_obsolete_versions() -> None:
    root = Path(__file__).parents[2]
    doc_h33 = (root / "docs/H3_3_CRM_LITE_WEB_UX.md").read_text(encoding="utf-8")
    doc_status = (root / "docs/PROJECT_STATUS.md").read_text(encoding="utf-8")

    # Ensure obsolete version labels are not present as current
    assert "h3-3-crm-web-1574d79-r1" not in doc_h33
    assert "h3-3-crm-web-1574d79-r1" not in doc_status

    # Ensure canonical active release label is documented
    assert "h3-3-crm-web-43101be-domainlocked-r1" in doc_h33
    assert "h3-3-crm-web-43101be-domainlocked-r1" in doc_status

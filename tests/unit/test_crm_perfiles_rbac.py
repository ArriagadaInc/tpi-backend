"""Unit tests for CRM-PERFILES-1-RBAC (Runner, Coordinador, Socio).

Covers the three business profiles end to end, server-side and fail-closed:

- AC-1: the ``coordinator`` role and the display-only profile labels.
- AC-2: the Coordinador shares the exact portfolio scope of the Runner (advisor).
- AC-3: only Socios (ceo/cto) assign leads; admin/executive lost the capability.
- AC-4: the simulator is available to the Coordinador (own portfolio) and Socios,
  and denied to the Runner.
- AC-5: per-profile state-change rules (server-side + role-aware UI options).
- AC-6: what does not change (dashboard/export/attachment deletion stay ceo/cto).
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.attachments.storage import StoredObject
from app.attachments.validation import ValidatedAttachment
from app.auth.models import (
    PORTFOLIO_ROLES,
    AuthenticatedUser,
    AuthenticationResult,
    UserRole,
    has_portfolio_scope,
    profile_label,
)
from app.config import Settings
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services.simulador_service import SimuladorService
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUNNER_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
COORDINATOR_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
FOREIGN_LEAD_ID = UUID("99999999-9999-9999-9999-999999999999")

RUNNER_ALLOWED_STATES = {
    "nuevo",
    "sin_contacto",
    "en_seguimiento",
    "reunion_agendada",
    "no_interesado",
    "datos_erroneos",
    "no_contactado",
    "perdido",
}
RUNNER_FORBIDDEN_STATES = {"reunion_realizada", "ficha_generada", "cerrado"}


def _lead(lead_id: UUID = LEAD_ID) -> dict[str, Any]:
    return {
        "id_lead": str(lead_id),
        "rut": "12.345.678-5",
        "nombre_completo": "Juan Perez",
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "fecha_nacimiento": datetime(1990, 1, 1),
        "genero": "Masculino",
        "estado_civil": "Soltero",
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "estado_lead": "en_seguimiento",
        "comentarios": "Solicitud original.",
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    }


def _user(role: str, advisor_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
        advisor_id=advisor_id,
    )


def _png(width: int = 1, height: int = 1) -> bytes:
    """Minimal valid 1x1 PNG payload for attachment upload tests."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    iend = struct.pack(">I", 0) + b"IEND" + b"\x00\x00\x00\x00"
    return signature + ihdr + iend


class _FakeStorage:
    """In-memory attachment storage recording every put/get/delete."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []

    def put(self, key: str, body: bytes, *, content_type: str, metadata: dict[str, str]) -> None:
        self.put_calls.append(key)
        self.objects[key] = StoredObject(content=body, content_type=content_type, metadata=metadata)

    def get(self, key: str) -> StoredObject | None:
        return self.objects.get(key)

    def get_tagging(self, key: str) -> dict[str, str] | None:
        return None

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.objects.pop(key, None)


class _Repo:
    """Fake repository exercising the portfolio scope of the real service."""

    def __init__(self, owned_by: dict[UUID, set[UUID]] | None = None) -> None:
        self.leads: dict[str, dict[str, Any]] = {str(LEAD_ID): _lead()}
        self.ownership: dict[UUID, set[UUID]] = owned_by or {
            ADVISOR_ID: {LEAD_ID},
            COORDINATOR_ID: {LEAD_ID},
        }
        self.board_calls: list[dict[str, Any]] = []
        self.status_calls: list[dict[str, Any]] = []
        self.comment_calls: list[dict[str, Any]] = []

    def _owned(self, id_asesor: UUID) -> set[str]:
        return {str(x) for x in self.ownership.get(id_asesor, set())}

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if id_asesor in self.ownership:
            return {
                "id_asesor": str(id_asesor),
                "rol": "asesor",
                "estado_disponibilidad": "activo",
            }
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return str(id_lead) in self._owned(id_asesor)

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.leads[str(id_lead)]) if str(id_lead) in self.leads else None

    def get_crm_solicitudes(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        self.board_calls.append(dict(kwargs))
        portfolio = kwargs.get("portfolio_asesor_id")
        if portfolio is not None:
            rows = [dict(v) for k, v in self.leads.items() if k in self._owned(portfolio)]
            return rows, len(rows)
        return [dict(v) for v in self.leads.values()], len(self.leads)

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(CRM_STATE_CONTRACT)

    def get_active_afp(self) -> list[dict[str, Any]]:
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return [{"id": "afp-1", "nombre": "Habitat"}]

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return []

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_simulation_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def update_lead_status(
        self,
        id_lead: UUID,
        estado_lead: str,
        *,
        actor: AuthenticatedUser,
        advisor_scope: UUID | None = None,
    ) -> bool:
        self.status_calls.append(
            {"id_lead": id_lead, "estado_lead": estado_lead, "advisor_scope": advisor_scope}
        )
        if advisor_scope is not None and str(id_lead) not in self._owned(advisor_scope):
            return False
        lead = self.leads.get(str(id_lead))
        if lead is not None:
            lead["estado_lead"] = estado_lead
        return True

    def append_lead_comment(
        self, id_lead: UUID, new_fragment: str, *, advisor_scope: UUID | None = None
    ) -> bool:
        self.comment_calls.append(
            {"id_lead": id_lead, "fragment": new_fragment, "advisor_scope": advisor_scope}
        )
        if advisor_scope is not None and str(id_lead) not in self._owned(advisor_scope):
            return False
        lead = self.leads.get(str(id_lead))
        if lead is not None:
            existing = str(lead.get("comentarios") or "")
            lead["comentarios"] = (
                f"{existing}\n\n{new_fragment}".strip() if existing else new_fragment
            )
        return True


def _service(repo: _Repo | None = None) -> tuple[SolicitudService, _Repo]:
    repository = repo or _Repo()
    return SolicitudService(repository=cast(Any, repository)), repository


class _AuthProvider:
    def __init__(self, role: str, advisor_id: UUID | None = None) -> None:
        self._role = role
        self._advisor_id = advisor_id

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        return AuthenticationResult(
            status="authenticated",
            user=AuthenticatedUser(
                subject=f"subject-{self._role}",
                username=username,
                display_name=f"User {self._role}",
                role=cast(UserRole, self._role),
                advisor_id=self._advisor_id,
            ),
        )


def _client(role: str, repo: _Repo, advisor_id: UUID | None = None) -> TestClient:
    service = SolicitudService(repository=cast(Any, repo))
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(role, advisor_id)
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
        data={"username": f"{role}.local", "password": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def _service_full(
    repo: _Repo | None = None,
    storage: _FakeStorage | None = None,
) -> tuple[SolicitudService, _Repo, _FakeStorage, list[dict[str, Any]]]:
    """Build a service wired to a fake attachment storage and audit sink."""
    repository = repo or _Repo()
    store = storage or _FakeStorage()
    audit_events: list[dict[str, Any]] = []

    def audit(**kwargs: Any) -> None:
        audit_events.append(dict(kwargs))

    service = SolicitudService(
        repository=cast(Any, repository),
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            ATTACHMENTS_ENABLED=True,
            ATTACHMENTS_BUCKET="bucket",
            WEB_MASK_PII=True,
        ),
        storage=cast(Any, store),
        attachment_audit=audit,
    )
    return service, repository, store, audit_events


def _client_full(
    role: str,
    repo: _Repo,
    *,
    advisor_id: UUID | None = None,
    storage: _FakeStorage | None = None,
    attachments_enabled: bool = True,
) -> tuple[TestClient, _Repo, _FakeStorage, list[dict[str, Any]]]:
    """Build a web client with attachments enabled and a fake storage/audit sink."""
    store = storage or _FakeStorage()
    audit_events: list[dict[str, Any]] = []

    def audit(**kwargs: Any) -> None:
        audit_events.append(dict(kwargs))

    service = SolicitudService(
        repository=cast(Any, repo),
        settings=Settings(
            APP_ENV="local",
            AUTH_ENABLED=True,
            AUTH_MODE="simple-dev",
            ATTACHMENTS_ENABLED=attachments_enabled,
            ATTACHMENTS_BUCKET="bucket" if attachments_enabled else None,
            WEB_MASK_PII=True,
        ),
        storage=cast(Any, store),
        attachment_audit=audit,
    )
    app = create_web_app()
    app.state.web_service = service
    app.state.auth_provider = _AuthProvider(role, advisor_id)
    app.state.settings = Settings(
        APP_ENV="local",
        AUTH_ENABLED=True,
        AUTH_MODE="simple-dev",
        ATTACHMENTS_ENABLED=attachments_enabled,
        ATTACHMENTS_BUCKET="bucket" if attachments_enabled else None,
        WEB_MASK_PII=True,
    )
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": f"{role}.local", "password": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client, repo, store, audit_events


# ---------------------------------------------------------------------------
# AC-1: roles y etiquetas de perfil
# ---------------------------------------------------------------------------


def test_profile_labels_map_the_three_business_profiles_only() -> None:
    assert profile_label(cast(UserRole, "advisor")) == "Runner"
    assert profile_label(cast(UserRole, "coordinator")) == "Coordinador"
    assert profile_label(cast(UserRole, "ceo")) == "Socio"
    assert profile_label(cast(UserRole, "cto")) == "Socio"
    # Technical roles keep their own value (solo etiqueta de pantalla).
    for role in ("tester", "admin", "executive", "operations", "readonly"):
        assert profile_label(cast(UserRole, role)) == role


def test_portfolio_scope_covers_advisor_and_coordinator_only() -> None:
    assert PORTFOLIO_ROLES == frozenset({"advisor", "coordinator"})
    assert has_portfolio_scope(cast(UserRole, "advisor")) is True
    assert has_portfolio_scope(cast(UserRole, "coordinator")) is True
    for role in ("tester", "admin", "executive", "operations", "readonly", "ceo", "cto"):
        assert has_portfolio_scope(cast(UserRole, role)) is False


# ---------------------------------------------------------------------------
# AC-2: cartera propia del coordinador (mismo alcance que el advisor)
# ---------------------------------------------------------------------------


def test_coordinator_resolves_identity_like_advisor() -> None:
    service, _ = _service()
    assert service.resolve_advisor_identity(_user("coordinator", COORDINATOR_ID)) == COORDINATOR_ID
    assert service.resolve_advisor_identity(_user("coordinator", None)) is None
    assert service.resolve_advisor_identity(_user("coordinator", ADVISOR_ID)) == ADVISOR_ID


def test_coordinator_board_is_scoped_to_own_portfolio() -> None:
    service, repo = _service()
    board = service.get_crm_bandeja(user=_user("coordinator", COORDINATOR_ID), masked=True)
    assert board["total"] == 1
    assert repo.board_calls[0]["portfolio_asesor_id"] == COORDINATOR_ID
    # Own portfolio rows are unmasked.
    assert board["solicitudes"][0]["rut"] == "12.345.678-5"


def test_coordinator_without_valid_advisor_id_fails_closed_to_empty_board() -> None:
    service, repo = _service()
    board = service.get_crm_bandeja(user=_user("coordinator", None), masked=True)
    assert board["total"] == 0
    assert board["solicitudes"] == []
    assert repo.board_calls == []


def test_coordinator_detail_own_lead_returns_full_pii() -> None:
    service, _ = _service()
    detail = service.get_solicitud_detalle_masked(
        LEAD_ID, user=_user("coordinator", COORDINATOR_ID)
    )
    assert detail is not None
    assert detail["rut"] == "12.345.678-5"
    assert detail["email"] == "juan@example.com"


def test_coordinator_foreign_lead_is_404() -> None:
    repo = _Repo(owned_by={COORDINATOR_ID: set()})
    service, _ = _service(repo)
    assert (
        service.get_solicitud_detalle_masked(LEAD_ID, user=_user("coordinator", COORDINATOR_ID))
        is None
    )


def test_cross_portfolio_isolation_between_runner_and_coordinator() -> None:
    # Runner A (ADVISOR_ID) owns LEAD_ID; the Coordinador owns FOREIGN_LEAD_ID.
    repo = _Repo(
        owned_by={
            ADVISOR_ID: {LEAD_ID},
            COORDINATOR_ID: {FOREIGN_LEAD_ID},
        }
    )
    repo.leads[str(FOREIGN_LEAD_ID)] = {**_lead(FOREIGN_LEAD_ID), "rut": "19.999.999-9"}
    service, _ = _service(repo)

    # Runner sees its own lead, not the Coordinador's.
    assert (
        service.get_solicitud_detalle_masked(LEAD_ID, user=_user("advisor", ADVISOR_ID)) is not None
    )
    assert (
        service.get_solicitud_detalle_masked(FOREIGN_LEAD_ID, user=_user("advisor", ADVISOR_ID))
        is None
    )
    # Coordinador sees its own lead, not the Runner's.
    assert (
        service.get_solicitud_detalle_masked(
            FOREIGN_LEAD_ID, user=_user("coordinator", COORDINATOR_ID)
        )
        is not None
    )
    assert (
        service.get_solicitud_detalle_masked(LEAD_ID, user=_user("coordinator", COORDINATOR_ID))
        is None
    )


# ---------------------------------------------------------------------------
# AC-3: asignación solo de socios
# ---------------------------------------------------------------------------


def test_can_assign_lead_is_true_only_for_socios() -> None:
    service, _ = _service()
    for role in ("ceo", "cto"):
        assert service.can_assign_lead(_user(role)) is True
    for role in (
        "advisor",
        "coordinator",
        "admin",
        "executive",
        "operations",
        "readonly",
        "tester",
    ):
        assert service.can_assign_lead(_user(role)) is False


def test_assign_lead_rejects_non_socio_server_side() -> None:
    service, _ = _service()
    with pytest.raises(PermissionError):
        service.assign_lead(LEAD_ID, ADVISOR_ID, actor=_user("admin"))


def test_assign_form_hidden_for_non_socios_and_403_on_post() -> None:
    # admin perdió la asignación: sin formulario y 403 real en el POST.
    client = _client("admin", _Repo())
    detail = client.get(f"/leads/{LEAD_ID}")
    assert detail.status_code == 200
    assert 'name="id_asesor"' not in detail.text

    denied = client.post(
        f"/leads/{LEAD_ID}/assign",
        data={"csrf_token": "x", "id_asesor": str(ADVISOR_ID)},
    )
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# AC-4: simulador y asesoría
# ---------------------------------------------------------------------------


def test_can_simulate_roles() -> None:
    for role in ("executive", "coordinator", "ceo", "cto"):
        assert SimuladorService.can_simulate(_user(role)) is True
    for role in ("advisor", "admin", "operations", "readonly", "tester"):
        assert SimuladorService.can_simulate(_user(role)) is False
    assert SimuladorService.can_simulate(None) is False


def test_runner_gets_real_403_on_simulator() -> None:
    client = _client("advisor", _Repo(), advisor_id=ADVISOR_ID)
    assert client.get(f"/leads/{LEAD_ID}/simulador").status_code == 403


def test_coordinator_opens_simulator_on_own_lead() -> None:
    client = _client("coordinator", _Repo(), advisor_id=COORDINATOR_ID)
    assert client.get(f"/leads/{LEAD_ID}/simulador").status_code == 200


def test_coordinator_gets_404_on_foreign_lead_simulator() -> None:
    repo = _Repo(owned_by={COORDINATOR_ID: set()})
    client = _client("coordinator", repo, advisor_id=COORDINATOR_ID)
    assert client.get(f"/leads/{LEAD_ID}/simulador").status_code == 404


# ---------------------------------------------------------------------------
# AC-5: cambio de estado por perfil
# ---------------------------------------------------------------------------


def test_runner_state_matrix() -> None:
    service, repo = _service()
    runner = _user("advisor", ADVISOR_ID)

    for state in RUNNER_ALLOWED_STATES:
        assert service.update_lead_status(LEAD_ID, state, actor=runner) is True
        assert repo.status_calls[-1]["advisor_scope"] == ADVISOR_ID

    for state in RUNNER_FORBIDDEN_STATES:
        with pytest.raises(PermissionError):
            service.update_lead_status(LEAD_ID, state, actor=runner)

    with pytest.raises(ValueError):
        service.update_lead_status(LEAD_ID, "asignado", actor=runner)


def test_coordinator_and_socio_state_matrix() -> None:
    service, _ = _service()
    for role in ("coordinator", "ceo", "cto"):
        actor = _user(role, COORDINATOR_ID if role == "coordinator" else None)
        for state in CRM_STATE_CONTRACT:
            if state == "asignado":
                with pytest.raises(ValueError):
                    service.update_lead_status(LEAD_ID, state, actor=actor)
            else:
                assert service.update_lead_status(LEAD_ID, state, actor=actor) is True


def test_state_options_are_role_aware() -> None:
    service, _ = _service()

    runner_options = service.get_crm_estado_lead_options_for_update(actor=_user("advisor"))
    assert "asignado" not in runner_options
    assert set(runner_options) == set(CRM_STATE_CONTRACT) - {"asignado", *RUNNER_FORBIDDEN_STATES}

    for role in ("coordinator", "ceo", "cto"):
        options = service.get_crm_estado_lead_options_for_update(actor=_user(role))
        assert "asignado" not in options
        assert set(options) == set(CRM_STATE_CONTRACT) - {"asignado"}


def test_runner_status_selector_does_not_offer_forbidden_states() -> None:
    client = _client("advisor", _Repo(), advisor_id=ADVISOR_ID)
    html = client.get(f"/leads/{LEAD_ID}").text
    for state in RUNNER_FORBIDDEN_STATES:
        assert f'value="{state}"' not in html
    for state in ("en_seguimiento", "perdido"):
        assert f'value="{state}"' in html


def test_runner_status_update_to_forbidden_state_is_rejected() -> None:
    client = _client("advisor", _Repo(), advisor_id=ADVISOR_ID)
    csrf = _extract_csrf(client, str(LEAD_ID))
    response = client.post(
        f"/leads/{LEAD_ID}/status",
        data={"csrf_token": csrf, "estado_lead": "cerrado", "return_to": "/leads"},
        follow_redirects=False,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AC-6: lo que no cambia
# ---------------------------------------------------------------------------


def test_runner_and_coordinator_do_not_see_dashboard_or_export() -> None:
    for role, advisor_id in (("advisor", ADVISOR_ID), ("coordinator", COORDINATOR_ID)):
        client = _client(role, _Repo(), advisor_id=advisor_id)
        assert client.get("/dashboard").status_code == 403
        assert client.get("/leads/export.xlsx").status_code == 403


def test_runner_and_coordinator_cannot_delete_attachments() -> None:
    # can_delete_attachments is bound to can_view_full_pii (ceo/cto).
    service, _ = _service()
    for role in ("advisor", "coordinator"):
        assert service.can_view_full_pii(_user(role)) is False


def test_own_portfolio_pii_stays_unmasked_for_runner_and_coordinator() -> None:
    service, _ = _service()
    for role, advisor_id in (("advisor", ADVISOR_ID), ("coordinator", COORDINATOR_ID)):
        detail = service.get_solicitud_detalle_masked(LEAD_ID, user=_user(role, advisor_id))
        assert detail is not None
        assert detail["rut"] == "12.345.678-5"
        assert detail["email"] == "juan@example.com"


# ---------------------------------------------------------------------------
# AC-1 (render): píldora de perfil en la barra superior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "advisor_id", "expected"),
    [
        ("advisor", ADVISOR_ID, "Runner"),
        ("coordinator", COORDINATOR_ID, "Coordinador"),
        ("ceo", None, "Socio"),
        ("cto", None, "Socio"),
        ("admin", None, "admin"),
    ],
)
def test_topbar_profile_pill_renders_profile_label(
    role: str, advisor_id: UUID | None, expected: str
) -> None:
    client = _client(role, _Repo(), advisor_id=advisor_id)
    html = client.get(f"/leads/{LEAD_ID}").text
    assert f'<span class="pill pill-muted">{expected}</span>' in html


# ---------------------------------------------------------------------------
# AC-2 (escrituras cruzadas): coordinador y runner sobre lead ajeno
# ---------------------------------------------------------------------------


def test_coordinator_own_mutations_assert_advisor_scope() -> None:
    repo = _Repo()  # COORDINATOR_ID owns LEAD_ID.
    service, _ = _service(repo)
    coordinator = _user("coordinator", COORDINATOR_ID)

    assert service.update_lead_status(LEAD_ID, "en_seguimiento", actor=coordinator) is True
    assert repo.status_calls[-1]["advisor_scope"] == COORDINATOR_ID

    assert service.append_lead_comment(LEAD_ID, "Nota propia", actor=coordinator) is True
    assert repo.comment_calls[-1]["advisor_scope"] == COORDINATOR_ID


def test_runner_and_coordinator_foreign_lead_mutations_rejected_without_writing() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = {**_lead(FOREIGN_LEAD_ID), "estado_lead": "nuevo"}
    service, _ = _service(repo)

    coordinator = _user("coordinator", COORDINATOR_ID)
    runner = _user("advisor", ADVISOR_ID)

    # El coordinador no muta el lead del runner: rechazo sin escribir.
    assert service.update_lead_status(LEAD_ID, "nuevo", actor=coordinator) is False
    assert repo.leads[str(LEAD_ID)]["estado_lead"] == "en_seguimiento"
    assert service.append_lead_comment(LEAD_ID, "Nota ajena", actor=coordinator) is False
    assert repo.leads[str(LEAD_ID)]["comentarios"] == "Solicitud original."

    # El runner tampoco muta el lead del coordinador.
    assert service.update_lead_status(FOREIGN_LEAD_ID, "en_seguimiento", actor=runner) is False
    assert repo.leads[str(FOREIGN_LEAD_ID)]["estado_lead"] == "nuevo"
    assert service.append_lead_comment(FOREIGN_LEAD_ID, "Nota ajena", actor=runner) is False
    assert repo.leads[str(FOREIGN_LEAD_ID)]["comentarios"] == "Solicitud original."


def test_runner_a_cannot_mutate_runner_b_lead_and_vice_versa() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, RUNNER_B_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = {**_lead(FOREIGN_LEAD_ID), "estado_lead": "nuevo"}
    service, _ = _service(repo)

    runner_a = _user("advisor", ADVISOR_ID)
    runner_b = _user("advisor", RUNNER_B_ID)

    # runner B no toca el lead del runner A.
    assert service.update_lead_status(LEAD_ID, "nuevo", actor=runner_b) is False
    assert repo.leads[str(LEAD_ID)]["estado_lead"] == "en_seguimiento"
    assert service.append_lead_comment(LEAD_ID, "Nota de B", actor=runner_b) is False

    # runner A no toca el lead del runner B.
    assert service.update_lead_status(FOREIGN_LEAD_ID, "en_seguimiento", actor=runner_a) is False
    assert repo.leads[str(FOREIGN_LEAD_ID)]["estado_lead"] == "nuevo"
    assert service.append_lead_comment(FOREIGN_LEAD_ID, "Nota de A", actor=runner_a) is False

    # Cada runner sí escribe en su propia cartera con su propio alcance.
    assert service.update_lead_status(LEAD_ID, "nuevo", actor=runner_a) is True
    assert repo.status_calls[-1]["advisor_scope"] == ADVISOR_ID
    assert service.append_lead_comment(FOREIGN_LEAD_ID, "Nota propia", actor=runner_b) is True
    assert repo.comment_calls[-1]["advisor_scope"] == RUNNER_B_ID


def test_coordinator_foreign_lead_attachment_upload_is_rejected_without_s3() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = _lead(FOREIGN_LEAD_ID)
    service, _, storage, audit = _service_full(repo)
    attachment = ValidatedAttachment(
        attachment_type="png", size=len(_png()), sha256="a" * 64, content=_png()
    )

    updated = service.append_lead_comment_with_attachments(
        LEAD_ID,
        "Nota ajena con adjunto",
        [attachment],
        actor=_user("coordinator", COORDINATOR_ID),
    )
    assert updated is False
    assert storage.put_calls == []
    assert audit == []


def test_coordinator_foreign_lead_http_mutations_return_404() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = _lead(FOREIGN_LEAD_ID)
    client = _client("coordinator", repo, advisor_id=COORDINATOR_ID)

    # Detalle ajeno: 404 (no filtra existencia).
    assert client.get(f"/leads/{LEAD_ID}").status_code == 404

    csrf = _extract_csrf(client, str(FOREIGN_LEAD_ID))

    # Estado: 404 real sin escribir.
    status = client.post(
        f"/leads/{LEAD_ID}/status",
        data={"csrf_token": csrf, "estado_lead": "nuevo", "return_to": "/leads"},
        follow_redirects=False,
    )
    assert status.status_code == 404
    assert repo.leads[str(LEAD_ID)]["estado_lead"] == "en_seguimiento"

    # Nota de texto: 404 real sin escribir.
    note = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota ajena", "return_to": "/leads"},
        follow_redirects=False,
    )
    assert note.status_code == 404
    assert repo.leads[str(LEAD_ID)]["comentarios"] == "Solicitud original."


# ---------------------------------------------------------------------------
# AC-4 (POST): simulador por perfil (simular y descargar_pdf)
# ---------------------------------------------------------------------------


def _simulable_repo() -> _Repo:
    repo = _Repo()
    repo.leads[str(LEAD_ID)]["fecha_nacimiento"] = datetime(1960, 1, 15)
    return repo


def _simulador_form(csrf: str) -> dict[str, str]:
    return {
        "csrf_token": csrf,
        "saldo_uf": "3000",
        "tasa_venta_pct": "4.7",
        "valor_uf": "",
        "meses_garantizados": "0",
        "meses_aumento_temporal": "0",
        "porcentaje_aumento_temporal": "0",
        "anios_diferidos": "0",
        "porcentaje_rvd": "100",
    }


def _csrf_from_simulator(client: TestClient, lead_id: str) -> str:
    html = client.get(f"/leads/{lead_id}/simulador").text
    marker = 'name="csrf_token" value="'
    idx = html.find(marker)
    assert idx != -1, "CSRF token not found in simulator page"
    start = idx + len(marker)
    end = html.index('"', start)
    return html[start:end]


def test_runner_post_simulator_is_403_for_simular_and_pdf() -> None:
    client = _client("advisor", _simulable_repo(), advisor_id=ADVISOR_ID)
    for intent in ("simular", "descargar_pdf"):
        response = client.post(
            f"/leads/{LEAD_ID}/simulador",
            data={"csrf_token": "x", "intent": intent},
        )
        assert response.status_code == 403


def test_coordinator_post_simulator_foreign_lead_is_404() -> None:
    repo = _simulable_repo()
    repo.ownership = {ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: set()}
    client = _client("coordinator", repo, advisor_id=COORDINATOR_ID)
    for intent in ("simular", "descargar_pdf"):
        response = client.post(
            f"/leads/{LEAD_ID}/simulador",
            data={"csrf_token": "x", "intent": intent},
        )
        assert response.status_code == 404


@pytest.mark.parametrize("role", ["coordinator", "ceo", "cto", "executive"])
def test_allowed_roles_post_simulator_own_lead(role: str) -> None:
    advisor_id = COORDINATOR_ID if role == "coordinator" else None
    client = _client(role, _simulable_repo(), advisor_id=advisor_id)
    csrf = _csrf_from_simulator(client, str(LEAD_ID))

    sim = client.post(
        f"/leads/{LEAD_ID}/simulador",
        data={**_simulador_form(csrf), "intent": "simular"},
    )
    assert sim.status_code == 200

    with patch("app.services.simulador_service.record_simulacion_event"):
        pdf = client.post(
            f"/leads/{LEAD_ID}/simulador",
            data={**_simulador_form(csrf), "intent": "descargar_pdf"},
        )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------
# AC-6 (adjuntos): coordinador y runner en su cartera
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "advisor_id"),
    [("coordinator", COORDINATOR_ID), ("advisor", ADVISOR_ID)],
)
def test_portfolio_role_uploads_attachment_on_own_lead_with_audit(
    role: str, advisor_id: UUID
) -> None:
    repo = _Repo()
    client, _, storage, audit = _client_full(role, repo, advisor_id=advisor_id)
    csrf = _extract_csrf(client, str(LEAD_ID))
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota con imagen", "return_to": "/leads"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert len(storage.put_calls) == 1
    assert storage.put_calls[0].startswith(f"leads/{LEAD_ID}/")
    assert any(event["accion"] == "adjunto_subido" for event in audit)


@pytest.mark.parametrize(
    ("role", "advisor_id"),
    [("coordinator", COORDINATOR_ID), ("advisor", ADVISOR_ID)],
)
def test_portfolio_role_views_and_downloads_own_attachment(role: str, advisor_id: UUID) -> None:
    repo = _Repo()
    client, _, storage, _audit = _client_full(role, repo, advisor_id=advisor_id)
    csrf = _extract_csrf(client, str(LEAD_ID))
    client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota con imagen", "return_to": "/leads"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    attachment_uuid = UUID(storage.put_calls[0].rsplit("/", 1)[-1])

    viewed = client.get(f"/leads/{LEAD_ID}/adjuntos/{attachment_uuid}")
    assert viewed.status_code == 200
    assert viewed.headers["content-disposition"].startswith("inline")

    downloaded = client.get(f"/leads/{LEAD_ID}/adjuntos/{attachment_uuid}?descargar=1")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-disposition"].startswith("attachment")


def test_coordinator_foreign_lead_attachment_returns_generic_unavailable() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = _lead(FOREIGN_LEAD_ID)
    client, _, _storage, _audit = _client_full("coordinator", repo, advisor_id=COORDINATOR_ID)

    response = client.get(f"/leads/{LEAD_ID}/adjuntos/{UUID(int=1)}")
    assert response.status_code == 404
    assert "no disponible" in response.text


def test_portfolio_role_foreign_lead_upload_is_404_and_no_s3() -> None:
    repo = _Repo(owned_by={ADVISOR_ID: {LEAD_ID}, COORDINATOR_ID: {FOREIGN_LEAD_ID}})
    repo.leads[str(FOREIGN_LEAD_ID)] = _lead(FOREIGN_LEAD_ID)
    client, _, storage, audit = _client_full("coordinator", repo, advisor_id=COORDINATOR_ID)
    csrf = _extract_csrf(client, str(FOREIGN_LEAD_ID))
    response = client.post(
        f"/leads/{LEAD_ID}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota ajena", "return_to": "/leads"},
        files=[("files", ("foto.png", _png(), "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert storage.put_calls == []
    assert audit == []


@pytest.mark.parametrize(
    ("role", "advisor_id"),
    [("coordinator", COORDINATOR_ID), ("advisor", ADVISOR_ID)],
)
def test_portfolio_role_cannot_delete_attachment_by_route(role: str, advisor_id: UUID) -> None:
    repo = _Repo()
    client, _, _storage, _audit = _client_full(role, repo, advisor_id=advisor_id)
    response = client.post(
        f"/leads/{LEAD_ID}/adjuntos/{UUID(int=1)}/eliminar",
        data={"csrf_token": "x", "return_to": "/leads"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def _extract_csrf(client: TestClient, lead_id: str) -> str:
    html = client.get(f"/leads/{lead_id}").text
    marker = 'name="csrf_token" value="'
    idx = html.find(marker)
    assert idx != -1, "CSRF token not found"
    start = idx + len(marker)
    end = html.index('"', start)
    return html[start:end]

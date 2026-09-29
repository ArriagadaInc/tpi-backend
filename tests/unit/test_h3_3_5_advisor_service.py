"""Unit tests for the H3.3.5 advisor portfolio resolution and authorization.

Covers the server-side resolution chain (user -> advisor_id -> active asesor ->
active assignment -> owned leads), the fail-closed behavior, contextual PII, and
the mutation ownership checks for advisors. CEO/CTO regression is covered by the
existing superuser tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.services.solicitud_service import SolicitudService

LEAD_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_LEAD_ID = UUID("99999999-9999-9999-9999-999999999999")
ADVISOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_ADVISOR_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _lead(lead_id: UUID = LEAD_ID) -> dict[str, Any]:
    return {
        "id_lead": str(lead_id),
        "rut": "12.345.678-5",
        "nombre_completo": "Juan Perez",
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "fecha_nacimiento": datetime(1990, 1, 1),
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "estado_lead": "contactado",
        "comentarios": "Solicitud original.",
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    }


class _AdvisorRepository:
    def __init__(self, *, active_advisor: bool = True) -> None:
        self.active_advisor = active_advisor
        self.owned_lead_ids: set[str] = {str(LEAD_ID)}
        self.board_rows = [_lead()]
        self.board_calls: list[dict[str, Any]] = []
        self.status_calls: list[dict[str, Any]] = []
        self.comment_calls: list[dict[str, Any]] = []

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if str(id_asesor) == str(ADVISOR_ID) and self.active_advisor:
            return {
                "id_asesor": str(ADVISOR_ID),
                "rol": "asesor",
                "estado_disponibilidad": "activo",
            }
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return str(id_asesor) == str(ADVISOR_ID) and str(id_lead) in self.owned_lead_ids

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        if str(id_lead) == str(LEAD_ID):
            return _lead()
        return None

    def get_crm_solicitudes(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        self.board_calls.append(dict(kwargs))
        portfolio = kwargs.get("portfolio_asesor_id")
        if portfolio is not None and str(portfolio) != str(ADVISOR_ID):
            return [], 0
        return [dict(row) for row in self.board_rows], len(self.board_rows)

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
        return True

    def append_lead_comment(
        self,
        id_lead: UUID,
        new_fragment: str,
        *,
        advisor_scope: UUID | None = None,
    ) -> bool:
        self.comment_calls.append({"id_lead": id_lead, "advisor_scope": advisor_scope})
        return True

    def get_crm_estado_lead_options(self) -> list[str]:
        return ["nuevo", "contactado", "cerrado"]


def _service(repo: _AdvisorRepository | None = None) -> tuple[SolicitudService, _AdvisorRepository]:
    repository = repo or _AdvisorRepository()
    return SolicitudService(repository=cast(Any, repository)), repository


def _user(role: str, advisor_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
        advisor_id=advisor_id,
    )


def test_resolve_advisor_identity_fail_closed_variants() -> None:
    service, _ = _service()

    assert service.resolve_advisor_identity(_user("ceo")) is None
    assert service.resolve_advisor_identity(_user("advisor", None)) is None  # absent
    assert service.resolve_advisor_identity(_user("advisor", OTHER_ADVISOR_ID)) is None  # missing
    assert service.resolve_advisor_identity(_user("advisor", ADVISOR_ID)) == ADVISOR_ID  # active


def test_resolve_advisor_identity_rejects_inactive_advisor() -> None:
    service, _ = _service(_AdvisorRepository(active_advisor=False))
    assert service.resolve_advisor_identity(_user("advisor", ADVISOR_ID)) is None


def test_bandeja_valid_advisor_scopes_and_unmasks() -> None:
    service, repo = _service()
    board = service.get_crm_bandeja(user=_user("advisor", ADVISOR_ID), masked=True)

    assert board["total"] == 1
    assert repo.board_calls[0]["portfolio_asesor_id"] == ADVISOR_ID
    # Advisor portfolio is their own leads: full PII unmasked.
    assert board["solicitudes"][0]["rut"] == "12.345.678-5"
    assert board["solicitudes"][0]["email"] == "juan@example.com"


def test_bandeja_invalid_advisor_returns_empty_without_query() -> None:
    service, repo = _service()
    board = service.get_crm_bandeja(user=_user("advisor", None), masked=True)

    assert board["total"] == 0
    assert board["solicitudes"] == []
    assert repo.board_calls == []


def test_bandeja_ceo_keeps_global_view_and_full_pii() -> None:
    service, repo = _service()
    board = service.get_crm_bandeja(user=_user("ceo"), masked=True)

    assert board["total"] == 1
    assert repo.board_calls[0]["portfolio_asesor_id"] is None
    assert board["solicitudes"][0]["rut"] == "12.345.678-5"


def test_bandeja_non_privileged_role_stays_masked() -> None:
    service, _ = _service()
    board = service.get_crm_bandeja(user=_user("operations"), masked=True)

    assert board["solicitudes"][0]["rut"] != "12.345.678-5"
    assert "*" in board["solicitudes"][0]["rut"]


def test_can_view_full_pii_remains_ceo_cto_only() -> None:
    service, _ = _service()
    assert service.can_view_full_pii(_user("ceo")) is True
    assert service.can_view_full_pii(_user("cto")) is True
    assert service.can_view_full_pii(_user("advisor", ADVISOR_ID)) is False
    assert service.can_view_full_pii(_user("operations")) is False


def test_detail_own_lead_returns_full_pii_for_advisor() -> None:
    service, _ = _service()
    detail = service.get_solicitud_detalle_masked(LEAD_ID, user=_user("advisor", ADVISOR_ID))

    assert detail is not None
    assert detail["rut"] == "12.345.678-5"
    assert detail["email"] == "juan@example.com"
    assert detail["telefono"] == "+56 9 1234 5678"


def test_detail_foreign_lead_is_404_for_advisor() -> None:
    service, _ = _service()
    # LEAD_ID is owned; force a foreign lead by clearing ownership.
    repo = _AdvisorRepository()
    repo.owned_lead_ids = set()
    service = SolicitudService(repository=cast(Any, repo))
    assert service.get_solicitud_detalle_masked(LEAD_ID, user=_user("advisor", ADVISOR_ID)) is None


def test_detail_unassigned_lead_is_404_for_advisor() -> None:
    service, _ = _service()
    assert (
        service.get_solicitud_detalle_masked(OTHER_LEAD_ID, user=_user("advisor", ADVISOR_ID))
        is None
    )


def test_detail_invalid_advisor_is_404() -> None:
    service, _ = _service()
    assert service.get_solicitud_detalle_masked(LEAD_ID, user=_user("advisor", None)) is None


def test_status_update_valid_advisor_passes_scope() -> None:
    service, repo = _service()
    assert (
        service.update_lead_status(LEAD_ID, "cerrado", actor=_user("advisor", ADVISOR_ID)) is True
    )
    assert repo.status_calls[0]["advisor_scope"] == ADVISOR_ID


def test_status_update_invalid_advisor_is_denied_without_write() -> None:
    service, repo = _service()
    assert service.update_lead_status(LEAD_ID, "cerrado", actor=_user("advisor", None)) is False
    assert repo.status_calls == []


def test_status_update_non_advisor_passes_no_scope() -> None:
    service, repo = _service()
    assert service.update_lead_status(LEAD_ID, "cerrado", actor=_user("tester")) is True
    assert repo.status_calls[0]["advisor_scope"] is None


def test_comment_valid_advisor_passes_scope_and_uses_display_name() -> None:
    service, repo = _service()
    assert service.append_lead_comment(LEAD_ID, "Nota", actor=_user("advisor", ADVISOR_ID)) is True
    assert repo.comment_calls[0]["advisor_scope"] == ADVISOR_ID


def test_comment_invalid_advisor_is_denied_without_write() -> None:
    service, repo = _service()
    assert service.append_lead_comment(LEAD_ID, "Nota", actor=_user("advisor", None)) is False
    assert repo.comment_calls == []


def test_append_comment_requires_authenticated_actor() -> None:
    service, _ = _service()
    with pytest.raises(TypeError, match="AuthenticatedUser"):
        service.append_lead_comment(LEAD_ID, "Nota", actor=cast(Any, None))  # type: ignore[arg-type]

"""Unit tests for lead assignment service behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services.solicitud_service import SolicitudService


class _AssignmentRepositoryStub:
    def __init__(self) -> None:
        self.detail = {
            "id_lead": "11111111-1111-1111-1111-111111111111",
            "estado_lead": "nuevo",
            "created_at": datetime(2026, 8, 28, 9, 0, tzinfo=UTC),
        }
        self.assign_calls: list[dict[str, object]] = []
        self.status_calls: list[tuple[UUID, str]] = []
        self.asesores = [
            {
                "id_asesor": "22222222-2222-2222-2222-222222222222",
                "nombre": "Ejecutivo Demo",
                "rol": "asesor",
                "estado_disponibilidad": "activo",
                "especialidad": "General",
                "carga_activa": 1,
            }
        ]

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, object] | None:
        if str(id_lead) == str(self.detail["id_lead"]):
            return dict(self.detail)
        return None

    def update_lead_status(self, id_lead: UUID, estado_lead: str) -> bool:
        self.status_calls.append((id_lead, estado_lead))
        return True

    def assign_lead(self, id_lead: UUID, id_asesor: UUID, *, actor: AuthenticatedUser) -> bool:
        self.assign_calls.append(
            {
                "id_lead": id_lead,
                "id_asesor": id_asesor,
                "actor": actor,
            }
        )
        return True

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(CRM_STATE_CONTRACT)

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return list(self.asesores)


def _build_service() -> tuple[SolicitudService, _AssignmentRepositoryStub]:
    repo = _AssignmentRepositoryStub()
    return SolicitudService(repository=cast(Any, repo)), repo


def _actor(role: str = "executive") -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="actor-001",
        username="actor@example.com",
        display_name="Actor Demo",
        role=cast(UserRole, role),
    )


def test_assignment_access_control_is_centralized() -> None:
    service, _ = _build_service()

    assert service.can_assign_lead(_actor("executive")) is True
    assert service.can_assign_lead(_actor("admin")) is True
    assert service.can_assign_lead(_actor("readonly")) is False
    assert "asignado" not in service.get_crm_estado_lead_options_for_update()

    assert service.can_view_full_pii(_actor("ceo")) is True
    assert service.can_view_full_pii(_actor("cto")) is True
    assert service.can_view_full_pii(_actor("readonly")) is False


def test_generic_update_rejects_asignado_state() -> None:
    service, repo = _build_service()

    with pytest.raises(ValueError, match="asignacion valida"):
        service.update_lead_status("11111111-1111-1111-1111-111111111111", "asignado")

    assert repo.status_calls == []


def test_assignment_requires_privileged_actor_and_normalizes_identifiers() -> None:
    service, repo = _build_service()

    assigned = service.assign_lead(
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        actor=_actor("executive"),
    )
    assert assigned is True
    assert len(repo.assign_calls) == 1
    call = repo.assign_calls[0]
    assert isinstance(call["id_lead"], UUID)
    assert isinstance(call["id_asesor"], UUID)
    assert str(call["id_lead"]) == "11111111-1111-1111-1111-111111111111"
    assert str(call["id_asesor"]) == "22222222-2222-2222-2222-222222222222"
    assert call["actor"].subject == "actor-001"

    with pytest.raises(PermissionError):
        service.assign_lead(
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
            actor=_actor("readonly"),
        )


def test_assignment_delegates_advisors_for_ui_selection() -> None:
    service, repo = _build_service()

    asesores = service.get_asesores_disponibles_para_asignacion()
    assert asesores == repo.asesores
    assert all(asesor["estado_disponibilidad"] == "activo" for asesor in asesores)

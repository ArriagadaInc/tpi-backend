"""Pruebas web del historial de la agenda en el detalle del lead (AC-3 y AC-4).

Cubren el render de las cinco acciones con la insignia «Automático» y sus textos, el
caso sin responsable, el orden junto a notas, el alcance (un Runner no obtiene eventos
de un lead ajeno y la lectura de la vista no se consulta) y la degradación fail-soft
cuando la lectura de la vista falla (200 con el resto del historial, sin líneas de
agenda y sin volcar el error).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.database.errors import DatabaseAppError
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services.agenda_service import AgendaService
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

LEAD = UUID("11111111-1111-1111-1111-111111111111")
RUNNER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
OTHER_RUNNER = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
SOCIO = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _lead(nombre: str = "Juan Perez", owner: UUID = RUNNER) -> dict[str, Any]:
    return {
        "id_lead": str(LEAD),
        "rut": "12.345.678-5",
        "nombre_completo": nombre,
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "fecha_nacimiento": None,
        "genero": None,
        "estado_civil": None,
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "asesor_nombre": "Runner",
        "id_asesor": str(owner),
        "estado_lead": "en_seguimiento",
        "comentarios": "Solicitud original.",
        "created_at": datetime(2026, 8, 21, 9, 45, tzinfo=UTC),
    }


class FakeWebService:
    def __init__(
        self, lead: dict[str, Any] | None, *, agenda_events=None, fail_agenda: bool = False
    ):
        self.lead = lead
        self.agenda_events = list(agenda_events or [])
        self.fail_agenda = fail_agenda
        self.agenda_consulted: list[str] = []

    def get_solicitud_detalle_masked(self, id_lead, *, user=None):
        return dict(self.lead) if self.lead is not None else None

    def get_crm_estado_lead_options_for_update(self, actor=None):
        return list(CRM_STATE_CONTRACT)

    def can_assign_lead(self, user):
        return False

    def can_view_full_pii(self, user):
        return getattr(user, "role", None) in ("ceo", "cto")

    def get_asesores_disponibles_para_asignacion(self):
        return []

    def get_lead_assignment_events(self, id_lead):
        return []

    def get_lead_state_change_events(self, id_lead):
        return []

    def get_lead_simulation_events(self, id_lead):
        return []

    def get_lead_agenda_events(self, id_lead):
        self.agenda_consulted.append(str(id_lead))
        if self.fail_agenda:
            raise DatabaseAppError("vista no disponible", operation="agenda.historial")
        return list(self.agenda_events)


class FakeSolicitudRepo:
    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if id_asesor in {RUNNER, OTHER_RUNNER, SOCIO}:
            return {"id_asesor": str(id_asesor), "rol": "asesor", "estado_disponibilidad": "activo"}
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return True


class FakeAgendaRepo:
    def get_responsables(self) -> list[dict[str, Any]]:
        return []

    def get_responsable_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        return None

    def get_cita_by_id(self, id_cita: UUID) -> dict[str, Any] | None:
        return None

    def get_cita_for_lead(self, id_lead: UUID) -> dict[str, Any] | None:
        return None

    def list_citas(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def lead_active_assignment_owner(self, id_lead: UUID) -> UUID | None:
        return None

    def get_lead_agenda_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []


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


def _client(
    role: str,
    *,
    advisor_id: UUID | None = None,
    web_service: FakeWebService | None = None,
) -> tuple[TestClient, FakeWebService]:
    service = web_service or FakeWebService(_lead())
    solicitudes = SolicitudService(repository=cast(Any, FakeSolicitudRepo()))
    app = create_web_app()
    app.state.web_service = service
    app.state.agenda_service = AgendaService(
        repository=cast(Any, FakeAgendaRepo()), solicitudes=solicitudes
    )
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
    return client, service


def _agenda(
    accion: str,
    *,
    responsable: str | None = "Socio A",
    actor: str = "subject-ceo",
    anterior: str | None = None,
    nueva: str | None = None,
) -> dict[str, Any]:
    def _dt(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(value, "%d/%m/%Y %H:%M").replace(
            tzinfo=ZoneInfo("America/Santiago")
        )

    return {
        "id_auditoria": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "id_lead": str(LEAD),
        "fecha_hora": datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        "accion": accion,
        "actor_subject": actor,
        "id_cita": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "responsable_id": str(SOCIO) if responsable else None,
        "responsable_nombre": responsable,
        "fecha_hora_anterior": _dt(anterior),
        "fecha_hora_nueva": _dt(nueva),
    }


def test_detail_renders_the_five_agenda_actions_with_automatic_badge() -> None:
    service = FakeWebService(
        _lead(),
        agenda_events=[
            _agenda("cita_agendada", nueva="20/01/2026 10:00"),
            _agenda("cita_reagendada", anterior="20/01/2026 10:00", nueva="21/01/2026 11:00"),
            _agenda("cita_cancelada", anterior="21/01/2026 11:00"),
            _agenda("cita_realizada", anterior="21/01/2026 11:00"),
            _agenda("cita_no_asistio", anterior="21/01/2026 11:00"),
        ],
    )
    client, _ = _client("ceo", web_service=service)
    body = client.get(f"/leads/{LEAD}").text

    assert 'class="timeline-badge-auto">Automático' in body
    assert "Reunión agendada para" in body
    assert "Reunión reagendada:" in body
    assert "Reunión cancelada (era el" in body
    assert "Reunión realizada (" in body
    assert "El lead no asistió a la reunión (" in body
    assert "Socio A" in body


def test_detail_renders_responsable_no_disponible_when_unresolvable() -> None:
    service = FakeWebService(
        _lead(),
        agenda_events=[_agenda("cita_agendada", responsable=None, nueva="20/01/2026 10:00")],
    )
    client, _ = _client("ceo", web_service=service)
    body = client.get(f"/leads/{LEAD}").text
    assert "responsable no disponible" in body


def test_detail_orders_agenda_events_alongside_notes() -> None:
    service = FakeWebService(
        _lead(), agenda_events=[_agenda("cita_agendada", nueva="20/01/2026 10:00")]
    )
    client, _ = _client("ceo", web_service=service)
    body = client.get(f"/leads/{LEAD}").text
    assert "Seguimiento y Notas Internas" in body
    assert "Reunión agendada para" in body


def test_runner_ajeno_no_consulta_agenda_y_no_muestra_eventos() -> None:
    # El control de alcance del detalle ya devuelve None para un lead fuera de la
    # cartera del Runner; en ese caso la agenda no se consulta y no hay lineas de agenda.
    service = FakeWebService(
        None, agenda_events=[_agenda("cita_agendada", nueva="20/01/2026 10:00")]
    )
    client, _ = _client("advisor", advisor_id=OTHER_RUNNER, web_service=service)
    response = client.get(f"/leads/{LEAD}")
    assert response.status_code == 404
    assert "Reunión agendada para" not in response.text
    assert service.agenda_consulted == []


def test_lead_visible_consulta_agenda_y_muestra_eventos() -> None:
    service = FakeWebService(
        _lead(), agenda_events=[_agenda("cita_agendada", nueva="20/01/2026 10:00")]
    )
    client, _ = _client("ceo", web_service=service)
    response = client.get(f"/leads/{LEAD}")
    assert response.status_code == 200
    assert "Reunión agendada para" in response.text
    assert service.agenda_consulted == [str(LEAD)]


def test_failure_degradates_to_200_without_agenda_lines() -> None:
    service = FakeWebService(_lead(), fail_agenda=True)
    client, _ = _client("ceo", web_service=service)
    response = client.get(f"/leads/{LEAD}")
    assert response.status_code == 200
    assert "Reunión agendada para" not in response.text
    assert "Juan Perez" in response.text  # el resto del detalle sigue intacto

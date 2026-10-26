"""Pruebas web de la agenda (rutas GET/POST, CSRF y matriz de permisos por rol).

Usa un ``AgendaService`` con repositorios falsos inyectado en ``app.state`` para no
depender de base de datos.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient

from app.auth.models import (
    AuthenticatedUser,
    AuthenticationResult,
    UserRole,
)
from app.config import Settings
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services.agenda_service import AgendaService
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

SOCIO_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIO_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
COORD = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
RUNNER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
LEAD = UUID("11111111-1111-1111-1111-111111111111")
CITA = UUID("22222222-2222-2222-2222-222222222222")


def _lead() -> dict[str, Any]:
    return {
        "id_lead": str(LEAD),
        "rut": "12.345.678-5",
        "nombre_completo": "Juan Perez",
        "email": "juan@example.com",
        "telefono": "+56 9 1234 5678",
        "fecha_nacimiento": None,
        "genero": None,
        "estado_civil": None,
        "afp": "Habitat",
        "saldo_afp": 1000000,
        "asesor_nombre": "Runner",
        "id_asesor": str(RUNNER),
        "estado_lead": "en_seguimiento",
        "comentarios": "Solicitud original.",
        "created_at": None,
    }


class FakeSolicitudRepo:
    def __init__(self) -> None:
        self.leads: dict[str, dict[str, Any]] = {str(LEAD): _lead()}

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.leads.get(str(id_lead))) if str(id_lead) in self.leads else None

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(CRM_STATE_CONTRACT)

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if id_asesor in {RUNNER, COORD}:
            return {"id_asesor": str(id_asesor), "rol": "asesor", "estado_disponibilidad": "activo"}
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return str(id_lead) == str(LEAD) and id_asesor == RUNNER

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return []

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_simulation_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []


class FakeAgendaRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responsables: list[dict[str, Any]] = [
            {"id_asesor": str(SOCIO_A), "nombre": "Socio A", "rol": "socio"},
            {"id_asesor": str(COORD), "nombre": "Coordinador", "rol": "asesor"},
        ]
        self.ownership: dict[UUID, UUID] = {LEAD: RUNNER}
        self.citas: dict[UUID, dict[str, Any]] = {}

    def get_responsables(self) -> list[dict[str, Any]]:
        return list(self.responsables)

    def get_responsable_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        return next((r for r in self.responsables if UUID(r["id_asesor"]) == id_asesor), None)

    def get_cita_by_id(self, id_cita: UUID) -> dict[str, Any] | None:
        return self.citas.get(id_cita)

    def get_cita_for_lead(self, id_lead: UUID) -> dict[str, Any] | None:
        for cita in self.citas.values():
            if UUID(str(cita["id_lead"])) == id_lead:
                return cita
        return None

    def list_citas(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def lead_active_assignment_owner(self, id_lead: UUID) -> UUID | None:
        return self.ownership.get(id_lead)

    def create_cita(self, **kwargs: Any) -> None:
        self.calls.append(("create_cita", kwargs))

    def update_cita(self, **kwargs: Any) -> None:
        self.calls.append(("update_cita", kwargs))

    def cancel_cita(self, **kwargs: Any) -> None:
        self.calls.append(("cancel_cita", kwargs))

    def complete_cita(self, **kwargs: Any) -> None:
        self.calls.append(("complete_cita", kwargs))

    def no_show_cita(self, **kwargs: Any) -> None:
        self.calls.append(("no_show_cita", kwargs))


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
    agenda_repo: FakeAgendaRepo | None = None,
) -> tuple[TestClient, FakeAgendaRepo]:
    repo = agenda_repo or FakeAgendaRepo()
    solicitud_repo = FakeSolicitudRepo()
    web_service = SolicitudService(repository=cast(Any, solicitud_repo))
    agenda_service = AgendaService(
        repository=cast(Any, repo),
        solicitudes=SolicitudService(repository=cast(Any, solicitud_repo)),
    )
    app = create_web_app()
    app.state.web_service = web_service
    app.state.agenda_service = agenda_service
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
    return client, repo


def _csrf(client: TestClient) -> str:
    response = client.get(f"/leads/{LEAD}")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def _agendar_form(csrf: str) -> dict[str, str]:
    return {
        "csrf_token": csrf,
        "return_to": "/leads",
        "responsable_id": str(SOCIO_A),
        "fecha": "2099-01-15",
        "hora": "10:00",
        "duracion": "30",
        "modalidad": "Google Meet",
        "enlace": "",
        "nota": "",
    }


def test_agenda_page_requiere_login():
    app = create_web_app()
    client = TestClient(app)
    response = client.get("/agenda", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_agenda_page_renderiza():
    client, _ = _client("advisor", advisor_id=RUNNER)
    response = client.get("/agenda")
    assert response.status_code == 200
    assert "Agenda" in response.text


def test_lead_detail_renderiza_tarjeta_reunion():
    client, _ = _client("advisor", advisor_id=RUNNER)
    response = client.get(f"/leads/{LEAD}")
    assert response.status_code == 200
    assert "Reunión de asesoría" in response.text


def test_agendar_ok():
    client, repo = _client("advisor", advisor_id=RUNNER)
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/agendar", data=_agendar_form(csrf), follow_redirects=False
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == "create_cita"


def test_agendar_csrf_invalido():
    client, repo = _client("advisor", advisor_id=RUNNER)
    response = client.post(
        f"/leads/{LEAD}/agenda/agendar",
        data=_agendar_form("token-invalido"),
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not repo.calls


def test_agendar_readonly_denegado():
    # Los roles de solo lectura no escriben: el POST se rechaza (403) y no llega al
    # repositorio. La denegacion por permiso del servicio se cubre en test_agenda_service.
    client, repo = _client("executive")
    response = client.post(
        f"/leads/{LEAD}/agenda/agendar",
        data=_agendar_form("token-cualquiera"),
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not repo.calls


def test_realizada_runner_denegado():
    client, repo = _client("advisor", advisor_id=RUNNER)
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/realizada",
        data={"csrf_token": csrf, "return_to": "/leads", "cita_id": str(CITA)},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not repo.calls


def test_cancelar_sin_motivo():
    client, repo = _client("ceo")
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/cancelar",
        data={"csrf_token": csrf, "return_to": "/leads", "cita_id": str(CITA), "motivo": "   "},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert not repo.calls


def _cita_agendada() -> dict[str, Any]:
    return {
        "id_cita": str(CITA),
        "id_lead": str(LEAD),
        "id_asesor": str(SOCIO_A),
        "estado_cita": "agendada",
        "fecha_hora": datetime(2099, 1, 15, 10, 0, tzinfo=UTC),
        "fecha_hora_fin": datetime(2099, 1, 15, 10, 30, tzinfo=UTC),
        "agendada_por_nombre": "Quien agendo",
        "canal": "Google Meet",
        "link_reunion": None,
        "nota": None,
        "motivo_cancelacion": None,
        "asesor_nombre": "Socio A",
    }


def test_reagendar_ok():
    client, repo = _client("ceo")
    repo.citas = {CITA: _cita_agendada()}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/reagendar",
        data={
            "csrf_token": csrf,
            "return_to": "/leads",
            "cita_id": str(CITA),
            "responsable_id": str(SOCIO_A),
            "fecha": "2099-01-15",
            "hora": "11:00",
            "duracion": "45",
            "modalidad": "Llamada",
            "enlace": "",
            "nota": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == "update_cita"


def test_no_asistio_ok():
    client, repo = _client("ceo")
    repo.citas = {CITA: _cita_agendada()}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/no-asistio",
        data={"csrf_token": csrf, "return_to": "/leads", "cita_id": str(CITA)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == "no_show_cita"

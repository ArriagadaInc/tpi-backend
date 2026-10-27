"""Pruebas web de la agenda (rutas GET/POST, CSRF y matriz de permisos por rol).

Usa un ``AgendaService`` con repositorios falsos inyectado en ``app.state`` para no
depender de base de datos. La matriz rol x accion x alcance (propio / ajeno de Runner /
ajeno de Coordinador) cubre GET y POST con CSRF valido, peticiones sin sesion y los
roles de solo lectura (AC-4, AC-6).
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.auth.models import (
    AuthenticatedUser,
    AuthenticationResult,
    UserRole,
)
from app.config import Settings
from app.models.agenda import AGENDA_TZ
from app.models.crm_states import CRM_STATE_CONTRACT
from app.services.agenda_service import AgendaService
from app.services.solicitud_service import SolicitudService
from app.web.main import create_web_app

SOCIO_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIO_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
COORD = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
COORD_B = UUID("cccccccc-cccc-cccc-cccc-cccccccccccd")
RUNNER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
RUNNER_B = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
LEAD = UUID("11111111-1111-1111-1111-111111111111")
LEAD_RUNNER_B = UUID("55555555-5555-5555-5555-555555555555")
LEAD_COORD = UUID("66666666-6666-6666-6666-666666666666")
LEAD_COORD_B = UUID("77777777-7777-7777-7777-777777777777")
CITA = UUID("22222222-2222-2222-2222-222222222222")
CITA_RUNNER_B = UUID("33333333-3333-3333-3333-333333333333")
CITA_COORD = UUID("44444444-4444-4444-4444-444444444444")

DEFAULT_OWNERSHIP: dict[UUID, UUID] = {
    LEAD: RUNNER,
    LEAD_RUNNER_B: RUNNER_B,
    LEAD_COORD: COORD,
    LEAD_COORD_B: COORD_B,
}


def _lead(
    lead_id: UUID = LEAD,
    owner: UUID = RUNNER,
    nombre: str = "Juan Perez",
) -> dict[str, Any]:
    return {
        "id_lead": str(lead_id),
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
        "created_at": None,
    }


class FakeSolicitudRepo:
    def __init__(self, ownership: dict[UUID, UUID] | None = None) -> None:
        self.ownership = ownership if ownership is not None else dict(DEFAULT_OWNERSHIP)
        self.leads: dict[str, dict[str, Any]] = {
            str(LEAD): _lead(LEAD, RUNNER, "Juan Perez"),
            str(LEAD_RUNNER_B): _lead(LEAD_RUNNER_B, RUNNER_B, "Maria Gomez"),
            str(LEAD_COORD): _lead(LEAD_COORD, COORD, "Pedro Soto"),
            str(LEAD_COORD_B): _lead(LEAD_COORD_B, COORD_B, "Lucia Rojas"),
        }

    def get_solicitud_by_id(self, id_lead: UUID) -> dict[str, Any] | None:
        return dict(self.leads.get(str(id_lead))) if str(id_lead) in self.leads else None

    def get_crm_estado_lead_options(self) -> list[str]:
        return list(CRM_STATE_CONTRACT)

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if id_asesor in {RUNNER, RUNNER_B, COORD, COORD_B}:
            return {"id_asesor": str(id_asesor), "rol": "asesor", "estado_disponibilidad": "activo"}
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return self.ownership.get(id_lead) == id_asesor

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return []

    def get_lead_assignment_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_state_change_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []

    def get_lead_simulation_events(self, id_lead: UUID) -> list[dict[str, Any]]:
        return []


class FakeAgendaRepo:
    def __init__(
        self,
        ownership: dict[UUID, UUID] | None = None,
        responsables: list[dict[str, Any]] | None = None,
        citas: dict[UUID, dict[str, Any]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ownership = ownership if ownership is not None else dict(DEFAULT_OWNERSHIP)
        self.responsables: list[dict[str, Any]] = responsables or [
            {"id_asesor": str(SOCIO_A), "nombre": "Socio A", "rol": "socio"},
            {"id_asesor": str(SOCIO_B), "nombre": "Socio B", "rol": "socio"},
            {"id_asesor": str(COORD), "nombre": "Coordinador", "rol": "asesor"},
        ]
        self.citas: dict[UUID, dict[str, Any]] = citas if citas is not None else {}
        self.citas_rows: list[dict[str, Any]] = []

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
        return list(self.citas_rows)

    def get_lead_agenda_events(self, id_lead: UUID) -> list[dict[str, Any]]:
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
    ownership: dict[UUID, UUID] | None = None,
) -> tuple[TestClient, FakeAgendaRepo]:
    client, repo, _app = _client_full(
        role, advisor_id=advisor_id, agenda_repo=agenda_repo, ownership=ownership
    )
    return client, repo


def _client_full(
    role: str,
    *,
    advisor_id: UUID | None = None,
    agenda_repo: FakeAgendaRepo | None = None,
    ownership: dict[UUID, UUID] | None = None,
) -> tuple[TestClient, FakeAgendaRepo, Any]:
    ownership = ownership if ownership is not None else dict(DEFAULT_OWNERSHIP)
    repo = agenda_repo or FakeAgendaRepo(ownership=ownership)
    solicitud_repo = FakeSolicitudRepo(ownership=ownership)
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
    return client, repo, app


def _session_csrf(client: TestClient, app: Any) -> str:
    """Extrae el token CSRF de la sesion firmada (para roles que no renderizan formularios)."""
    for mw in app.user_middleware:
        if getattr(mw, "cls", None) is SessionMiddleware:
            secret_key = str(mw.kwargs["secret_key"])
            max_age = mw.kwargs.get("max_age")
            cookie = client.cookies.get("session")
            assert cookie is not None
            signer = itsdangerous.TimestampSigner(secret_key)
            data = signer.unsign(cookie.encode("utf-8"), max_age=max_age)
            session = json.loads(base64.b64decode(data))
            return str(session["_tpi_web_csrf_token"])
    raise AssertionError("SessionMiddleware no encontrado")


def _csrf(client: TestClient, lead_id: UUID = LEAD) -> str:
    response = client.get(f"/leads/{lead_id}")
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


def _post_data(csrf: str, action: str, cita_id: UUID = CITA) -> dict[str, str]:
    if action == "agendar":
        return _agendar_form(csrf)
    if action == "reagendar":
        data = _agendar_form(csrf)
        data["cita_id"] = str(cita_id)
        return data
    if action == "cancelar":
        return {
            "csrf_token": csrf,
            "return_to": "/leads",
            "cita_id": str(cita_id),
            "motivo": "No puede asistir",
        }
    if action in ("realizada", "no-asistio"):
        return {"csrf_token": csrf, "return_to": "/leads", "cita_id": str(cita_id)}
    raise ValueError(action)


def _cita(lead_id: UUID = LEAD, cita_id: UUID = CITA) -> dict[str, Any]:
    return {
        "id_cita": str(cita_id),
        "id_lead": str(lead_id),
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


def _agenda_row(
    lead_id: UUID,
    owner: UUID,
    nombre: str,
    cita_id: UUID,
) -> dict[str, Any]:
    ahora = datetime.now(AGENDA_TZ)
    return {
        "id_cita": str(cita_id),
        "id_lead": str(lead_id),
        "id_asesor": str(SOCIO_A),
        "fecha_hora": ahora,
        "fecha_hora_fin": ahora,
        "agendada_por_nombre": "Quien agendo",
        "canal": "Google Meet",
        "estado_cita": "agendada",
        "nota": None,
        "motivo_cancelacion": None,
        "asesor_nombre": "Socio A",
        "link_reunion": "https://meet.example/abc",
        "lead_nombre": nombre,
        "lead_asesor_id": str(owner),
    }


# ------------------------------------------------------------------ GET


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


@pytest.mark.parametrize("vista", ["semana", "lista"])
def test_agenda_get_recorta_lead_ajeno_runner(vista: str):
    client, repo = _client("advisor", advisor_id=RUNNER)
    repo.citas_rows = [
        _agenda_row(LEAD, RUNNER, "Juan Perez", CITA),
        _agenda_row(LEAD_COORD, COORD, "Pedro Soto", CITA_COORD),
    ]
    response = client.get(f"/agenda?vista={vista}")
    assert response.status_code == 200
    text = response.text
    # El lead propio aparece con nombre y enlace.
    assert "Juan Perez" in text
    assert f"/leads/{LEAD}" in text
    # El lead ajeno no aparece con nombre, id ni enlace; se etiqueta como otra cartera.
    assert "Pedro Soto" not in text
    assert f"/leads/{LEAD_COORD}" not in text
    assert str(LEAD_COORD) not in text
    assert "De otra cartera" in text


@pytest.mark.parametrize("vista", ["semana", "lista"])
def test_agenda_get_recorta_lead_ajeno_coordinador(vista: str):
    client, repo = _client("coordinator", advisor_id=COORD)
    repo.citas_rows = [
        _agenda_row(LEAD_COORD, COORD, "Pedro Soto", CITA_COORD),
        _agenda_row(LEAD, RUNNER, "Juan Perez", CITA),
    ]
    response = client.get(f"/agenda?vista={vista}")
    assert response.status_code == 200
    text = response.text
    assert "Pedro Soto" in text
    assert f"/leads/{LEAD_COORD}" in text
    assert "Juan Perez" not in text
    assert f"/leads/{LEAD}" not in text
    assert str(LEAD) not in text
    assert "De otra cartera" in text


@pytest.mark.parametrize("role", ["ceo", "cto"])
@pytest.mark.parametrize("vista", ["semana", "lista"])
def test_agenda_get_socio_ve_todos(role: str, vista: str):
    client, repo = _client(role)
    repo.citas_rows = [
        _agenda_row(LEAD, RUNNER, "Juan Perez", CITA),
        _agenda_row(LEAD_COORD, COORD, "Pedro Soto", CITA_COORD),
    ]
    response = client.get(f"/agenda?vista={vista}")
    assert response.status_code == 200
    assert "Juan Perez" in response.text
    assert "Pedro Soto" in response.text


def test_agenda_conserva_parametros_en_los_enlaces():
    # El filtro por responsable, la navegacion por semanas y el selector Semana/Lista
    # conservan los parametros de la URL (fecha, responsable y vista).
    client, _ = _client("ceo")
    response = client.get(f"/agenda?vista=lista&responsable={SOCIO_A}&fecha=2026-10-26")
    assert response.status_code == 200
    text = response.text
    # El selector Semana/Lista conserva fecha y responsable (el HTML escapa & como &amp;).
    assert f"/agenda?fecha=2026-10-26&amp;responsable={SOCIO_A}&amp;vista=semana" in text
    assert f"/agenda?fecha=2026-10-26&amp;responsable={SOCIO_A}&amp;vista=lista" in text
    # La navegacion por semanas conserva responsable y vista.
    assert f"/agenda?fecha=2026-10-19&amp;responsable={SOCIO_A}&amp;vista=lista" in text
    assert f"/agenda?fecha=2026-11-02&amp;responsable={SOCIO_A}&amp;vista=lista" in text
    # El chip "Todos" conserva fecha y vista (sin responsable).
    assert "/agenda?fecha=2026-10-26&amp;vista=lista" in text


# ------------------------------------------------------------------ CSS del historial


def _ultimo_background_de_regla(css: str, selector: str) -> str | None:
    """Devuelve el ``background`` de la ultima regla cuyo selector abre una linea.

    Se ancla al inicio de linea para no confundir ``.timeline-item`` con
    ``[data-theme="dark"] .timeline-item``.
    """
    patron = re.compile(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}")
    bloques = patron.findall(css)
    if not bloques:
        return None
    m = re.search(r"background:\s*([^;]+)", bloques[-1])
    return m.group(1).strip() if m else None


def test_timeline_item_usa_surface_soft_en_tema_claro():
    # AC-4: en el tema claro el historial usa el mismo fondo que la solicitud original.
    css = Path("app/web/static/css/app.css").read_text(encoding="utf-8")
    assert _ultimo_background_de_regla(css, ".timeline-item") == "var(--surface-soft)"
    assert _ultimo_background_de_regla(css, ".original-request-box") == "var(--surface-soft)"


def test_timeline_item_tema_oscuro_sin_cambios():
    css = Path("app/web/static/css/app.css").read_text(encoding="utf-8")
    assert _ultimo_background_de_regla(css, '[data-theme="dark"] .timeline-item') == (
        "var(--surface-soft)"
    )


# ------------------------------------------------------------------ escritura basica


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


def test_reagendar_ok():
    client, repo = _client("ceo")
    repo.citas = {CITA: _cita(LEAD, CITA)}
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
    repo.citas = {CITA: _cita(LEAD, CITA)}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/no-asistio",
        data={"csrf_token": csrf, "return_to": "/leads", "cita_id": str(CITA)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == "no_show_cita"


# ------------------------------------------------------------------ matriz de permisos


# Acciones de escritura permitidas a Runner/Coordinador (agendar, reagendar, cancelar).
_ACCIONES_ESCRITURA = ("agendar", "reagendar", "cancelar")
# Acciones de asistencia, solo Coordinador y Socio.
_ACCIONES_ASISTENCIA = ("realizada", "no-asistio")
# Todas las rutas de escritura (para el POST sin sesion).
_TODAS_ACCIONES = _ACCIONES_ESCRITURA + _ACCIONES_ASISTENCIA

_WRITE_CALL = {
    "agendar": "create_cita",
    "reagendar": "update_cita",
    "cancelar": "cancel_cita",
    "realizada": "complete_cita",
    "no-asistio": "no_show_cita",
}


@pytest.mark.parametrize("action", _TODAS_ACCIONES)
def test_post_sin_sesion_redirige_a_login(action: str):
    app = create_web_app()
    client = TestClient(app)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data("token-cualquiera", action),
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("action", _ACCIONES_ESCRITURA)
def test_runner_escribe_su_lead(action: str):
    client, repo = _client("advisor", advisor_id=RUNNER)
    repo.citas = {CITA: _cita(LEAD, CITA)}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data(csrf, action),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == _WRITE_CALL[action]


@pytest.mark.parametrize("action", _ACCIONES_ESCRITURA)
@pytest.mark.parametrize(
    "lead_ajeno,cita_ajena",
    [
        (LEAD_RUNNER_B, CITA_RUNNER_B),
        (LEAD_COORD, CITA_COORD),
    ],
)
def test_runner_lead_ajeno_es_404(action: str, lead_ajeno: UUID, cita_ajena: UUID):
    client, repo = _client("advisor", advisor_id=RUNNER)
    repo.citas = {cita_ajena: _cita(lead_ajeno, cita_ajena)}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{lead_ajeno}/agenda/{action}",
        data=_post_data(csrf, action, cita_ajena),
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert not repo.calls


@pytest.mark.parametrize("action", _ACCIONES_ESCRITURA)
def test_coordinador_escribe_su_lead(action: str):
    client, repo = _client("coordinator", advisor_id=COORD)
    repo.citas = {CITA_COORD: _cita(LEAD_COORD, CITA_COORD)}
    csrf = _csrf(client, LEAD_COORD)
    response = client.post(
        f"/leads/{LEAD_COORD}/agenda/{action}",
        data=_post_data(csrf, action, CITA_COORD),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == _WRITE_CALL[action]


@pytest.mark.parametrize("action", _ACCIONES_ESCRITURA)
@pytest.mark.parametrize(
    "lead_ajeno,cita_ajena",
    [
        (LEAD, CITA),
        (LEAD_COORD_B, UUID("88888888-8888-8888-8888-888888888888")),
    ],
)
def test_coordinador_lead_ajeno_es_404(action: str, lead_ajeno: UUID, cita_ajena: UUID):
    client, repo = _client("coordinator", advisor_id=COORD)
    repo.citas = {cita_ajena: _cita(lead_ajeno, cita_ajena)}
    csrf = _csrf(client, LEAD_COORD)
    response = client.post(
        f"/leads/{lead_ajeno}/agenda/{action}",
        data=_post_data(csrf, action, cita_ajena),
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert not repo.calls


@pytest.mark.parametrize("action", _ACCIONES_ASISTENCIA)
def test_runner_asistencia_denegada_por_rol(action: str):
    client, repo = _client("advisor", advisor_id=RUNNER)
    repo.citas = {CITA: _cita(LEAD, CITA)}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data(csrf, action),
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not repo.calls


@pytest.mark.parametrize("action", _ACCIONES_ASISTENCIA)
def test_coordinador_asistencia_su_lead(action: str):
    client, repo = _client("coordinator", advisor_id=COORD)
    repo.citas = {CITA_COORD: _cita(LEAD_COORD, CITA_COORD)}
    csrf = _csrf(client, LEAD_COORD)
    response = client.post(
        f"/leads/{LEAD_COORD}/agenda/{action}",
        data=_post_data(csrf, action, CITA_COORD),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == _WRITE_CALL[action]


@pytest.mark.parametrize("action", _ACCIONES_ASISTENCIA)
def test_coordinador_asistencia_lead_ajeno_es_404(action: str):
    client, repo = _client("coordinator", advisor_id=COORD)
    repo.citas = {CITA: _cita(LEAD, CITA)}
    csrf = _csrf(client, LEAD_COORD)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data(csrf, action),
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert not repo.calls


@pytest.mark.parametrize("role", ["ceo", "cto"])
@pytest.mark.parametrize("action", _TODAS_ACCIONES)
def test_socio_escribe_cualquier_lead(role: str, action: str):
    client, repo = _client(role)
    repo.citas = {CITA: _cita(LEAD, CITA)}
    csrf = _csrf(client)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data(csrf, action),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repo.calls and repo.calls[0][0] == _WRITE_CALL[action]


@pytest.mark.parametrize("role", ["executive", "readonly"])
@pytest.mark.parametrize("action", _TODAS_ACCIONES)
def test_rol_solo_lectura_denegado(role: str, action: str):
    # CSRF valido (de la sesion): la denegacion es por perfil, no por token, y no
    # llega al repositorio. Los roles de solo lectura no renderizan formularios, asi
    # que el token se extrae de la sesion firmada.
    client, repo, app = _client_full(role)
    repo.citas = {CITA: _cita(LEAD, CITA)}
    assert client.get(f"/leads/{LEAD}").status_code == 200
    csrf = _session_csrf(client, app)
    response = client.post(
        f"/leads/{LEAD}/agenda/{action}",
        data=_post_data(csrf, action),
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert not repo.calls


def test_agendar_lead_ajeno_resuelve_alcance_antes_del_responsable():
    # Un Coordinador que elige como responsable al dueno de un lead ajeno debe recibir
    # 404 (como todo lead ajeno), no 400: el alcance se valida antes que el responsable
    # para no poder inferir el dueno conociendo su UUID (R1-MINOR-02).
    repo = FakeAgendaRepo(
        responsables=[
            {"id_asesor": str(SOCIO_A), "nombre": "Socio A", "rol": "socio"},
            {"id_asesor": str(COORD_B), "nombre": "Coord B", "rol": "asesor"},
        ]
    )
    client, repo = _client("coordinator", advisor_id=COORD, agenda_repo=repo)
    csrf = _csrf(client, LEAD_COORD)
    data = {
        "csrf_token": csrf,
        "return_to": "/leads",
        "responsable_id": str(COORD_B),
        "fecha": "2099-01-15",
        "hora": "10:00",
        "duracion": "30",
        "modalidad": "Google Meet",
        "enlace": "",
        "nota": "",
    }
    response = client.post(
        f"/leads/{LEAD_COORD_B}/agenda/agendar", data=data, follow_redirects=False
    )
    assert response.status_code == 404
    assert not repo.calls

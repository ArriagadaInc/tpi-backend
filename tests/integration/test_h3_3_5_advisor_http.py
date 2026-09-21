"""HTTP tests (real routes + real repository) for the H3.3.5 advisor mutations.

These go through the real FastAPI app and the real ``SolicitudService`` (real
PostgreSQL repository), so the ownership checks are the production ones, not mocks.
Covered: POST /status, /comments, /cleanup, /assign and GET /dashboard for advisor
(own/foreign/unassigned/invalid) and CEO/CTO no-regression.
"""

from __future__ import annotations

import re
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.models import AuthenticatedUser, AuthenticationResult, UserRole
from app.config import Settings
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.web.main import create_web_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


class _AuthProvider:
    def __init__(self, role: str, advisor_id: Any = None) -> None:
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


class _World:
    def __init__(self) -> None:
        suffix = uuid4().hex[:12]
        self.a1_name = f"HTTP Advisor 1 {suffix}"
        self.a2_name = f"HTTP Advisor 2 {suffix}"
        self.a1: Any = None
        self.a2: Any = None
        self.lead_own: Any = None
        self.lead_other: Any = None
        self.lead_unassigned: Any = None
        self._id_persona_by_lead: dict[str, Any] = {}


def _insert_advisor(cur: Any, nombre: str) -> Any:
    cur.execute(
        "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad) "
        "VALUES (%s, 'asesor', 'activo') RETURNING id_asesor",
        (nombre,),
    )
    return cur.fetchone()["id_asesor"]


def _insert_lead(cur: Any, rut: str, nombre: str) -> Any:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, created_at) "
        "VALUES (%s, %s, now()) RETURNING id_persona",
        (rut, nombre),
    )
    id_persona = cur.fetchone()["id_persona"]
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, created_at) "
        "VALUES (%s, now(), 'nuevo', now()) RETURNING id_lead",
        (str(id_persona),),
    )
    return cur.fetchone()["id_lead"], id_persona


def _assign(cur: Any, id_lead: Any, id_asesor: Any) -> None:
    cur.execute(
        "INSERT INTO tpi.asignaciones (id_lead, id_asesor, estado_asignacion) "
        "VALUES (%s, %s, 'activa')",
        (str(id_lead), str(id_asesor)),
    )


@pytest.fixture
def world() -> _World:
    w = _World()
    with get_db_connection(operation="h3_3_5_http_world_setup") as conn:
        with conn.cursor() as cur:
            w.a1 = _insert_advisor(cur, w.a1_name)
            w.a2 = _insert_advisor(cur, w.a2_name)
            w.lead_own, own_persona = _insert_lead(cur, "40111111-1", "HTTP Own")
            w.lead_other, other_persona = _insert_lead(cur, "40222222-2", "HTTP Other")
            w.lead_unassigned, una_persona = _insert_lead(cur, "40333333-3", "HTTP Unassigned")
            _assign(cur, w.lead_own, w.a1)
            _assign(cur, w.lead_other, w.a2)
            w._id_persona_by_lead = {
                str(w.lead_own): own_persona,
                str(w.lead_other): other_persona,
                str(w.lead_unassigned): una_persona,
            }
        conn.commit()

    yield w

    with get_db_connection(operation="h3_3_5_http_world_cleanup") as conn:
        with conn.cursor() as cur:
            for id_lead in (w.lead_own, w.lead_other, w.lead_unassigned):
                cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (str(id_lead),))
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(id_lead),))
                cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(id_lead),))
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(id_lead),))
            for id_asesor in (w.a1, w.a2):
                cur.execute("DELETE FROM tpi.asesores WHERE id_asesor = %s", (str(id_asesor),))
            for id_persona in w._id_persona_by_lead.values():
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(id_persona),))
        conn.commit()


def _client(role: str, advisor_id: Any = None) -> TestClient:
    app = create_web_app()
    app.state.auth_provider = _AuthProvider(role, advisor_id)
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def _csrf(client: TestClient, lead_id: Any) -> str:
    html = client.get(f"/leads/{lead_id}").text
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _lead_state(lead_id: Any) -> str:
    with get_db_connection(operation="h3_3_5_http_read_state") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (str(lead_id),))
            return str(cur.fetchone()["estado_lead"])


def test_advisor_status_comment_own_allowed(world: _World) -> None:
    client = _client("advisor", world.a1)
    csrf = _csrf(client, world.lead_own)

    status = client.post(
        f"/leads/{world.lead_own}/status",
        data={"csrf_token": csrf, "estado_lead": "contactado"},
        follow_redirects=False,
    )
    assert status.status_code == 303
    assert _lead_state(world.lead_own) == "contactado"

    comment = client.post(
        f"/leads/{world.lead_own}/comments",
        data={"csrf_token": csrf, "new_comment": "Nota propia HTTP"},
        follow_redirects=False,
    )
    assert comment.status_code == 303


def test_advisor_status_comment_foreign_and_unassigned_404(world: _World) -> None:
    client = _client("advisor", world.a1)

    for lead_id in (world.lead_other, world.lead_unassigned):
        csrf = _csrf(client, world.lead_own)  # any valid token
        status = client.post(
            f"/leads/{lead_id}/status",
            data={"csrf_token": csrf, "estado_lead": "contactado"},
            follow_redirects=False,
        )
        assert status.status_code == 404
        assert _lead_state(lead_id) == "nuevo"

        comment = client.post(
            f"/leads/{lead_id}/comments",
            data={"csrf_token": csrf, "new_comment": "Nota ajena HTTP"},
            follow_redirects=False,
        )
        assert comment.status_code == 404


def test_advisor_cleanup_and_assign_are_403(world: _World) -> None:
    client = _client("advisor", world.a1)
    csrf = _csrf(client, world.lead_own)

    cleanup = client.post(
        f"/leads/{world.lead_own}/cleanup",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert cleanup.status_code == 403

    assign = client.post(
        f"/leads/{world.lead_own}/assign",
        data={"csrf_token": csrf, "id_asesor": str(world.a2)},
        follow_redirects=False,
    )
    assert assign.status_code == 403


def test_advisor_dashboard_403_and_invalid_advisor_denied(world: _World) -> None:
    valid = _client("advisor", world.a1)
    assert valid.get("/dashboard").status_code == 403

    invalid = _client("advisor", None)
    assert invalid.get("/dashboard").status_code == 403
    # Invalid advisor cannot open the detail (404, no existence/PII reveal).
    assert invalid.get(f"/leads/{world.lead_own}").status_code == 404


def test_ceo_keeps_global_mutation_and_dashboard(world: _World) -> None:
    client = _client("ceo")
    csrf = _csrf(client, world.lead_own)

    status = client.post(
        f"/leads/{world.lead_own}/status",
        data={"csrf_token": csrf, "estado_lead": "cerrado"},
        follow_redirects=False,
    )
    assert status.status_code == 303
    assert _lead_state(world.lead_own) == "cerrado"

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200

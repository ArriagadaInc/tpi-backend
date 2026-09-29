"""Integration tests (real PostgreSQL) for the H3.3.6 executive XLSX export.

Exercises the real routes, service and repository: pagination independence,
combined filters, the PII-free audit event, no business-data mutation, the empty
result and the ceo/advisor authorization boundary. Every assertion is scoped to
this test's own data via a unique per-world search token.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

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


class _World:
    def __init__(self) -> None:
        self.suffix = uuid4().hex[:8]
        self.advisor_id: Any = None
        self.lead_ids: list[Any] = []
        self.persona_ids: list[Any] = []
        self.ruts: list[str] = []


def _insert_lead(cur: Any, rut: str, nombre: str, estado: str) -> tuple[Any, Any]:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, created_at) "
        "VALUES (%s, %s, now()) RETURNING id_persona",
        (rut, nombre),
    )
    id_persona = cur.fetchone()["id_persona"]
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, created_at) "
        "VALUES (%s, now(), %s, now()) RETURNING id_lead",
        (str(id_persona), estado),
    )
    return cur.fetchone()["id_lead"], id_persona


@pytest.fixture
def world() -> _World:
    w = _World()
    with get_db_connection(operation="h3_3_6_export_world_setup") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad) "
                "VALUES (%s, 'asesor', 'activo') RETURNING id_asesor",
                (f"Export Advisor {w.suffix}",),
            )
            w.advisor_id = cur.fetchone()["id_asesor"]
            for i in range(12):
                rut = f"5{1000000 + i:07d}-{i % 10}"
                estado = "contactado" if i % 2 == 0 else "nuevo"
                lead, persona = _insert_lead(cur, rut, f"Export Lead {w.suffix} {i:02d}", estado)
                w.lead_ids.append(lead)
                w.persona_ids.append(persona)
                w.ruts.append(rut)
        conn.commit()

    yield w

    with get_db_connection(operation="h3_3_6_export_world_cleanup") as conn:
        with conn.cursor() as cur:
            for lead in w.lead_ids:
                cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (str(lead),))
                cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(lead),))
                cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(lead),))
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(lead),))
            for persona in w.persona_ids:
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(persona),))
            cur.execute("DELETE FROM tpi.auditoria WHERE accion = 'exportacion_xlsx'")
            if w.advisor_id is not None:
                cur.execute("DELETE FROM tpi.asesores WHERE id_asesor = %s", (str(w.advisor_id),))
        conn.commit()


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


def _client(role: str) -> TestClient:
    app = create_web_app()
    app.state.auth_provider = _AuthProvider(role)
    app.state.settings = Settings(APP_ENV="local", AUTH_ENABLED=True, AUTH_MODE="simple-dev")
    client = TestClient(app)
    response = client.post(
        "/login", data={"username": f"{role}.local", "password": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def _data_rows(content: bytes) -> list[tuple[Any, ...]]:
    workbook = load_workbook(BytesIO(content))
    sheet = workbook.active
    return list(sheet.iter_rows(min_row=2, values_only=True))


def _lead_states(world: _World) -> dict[str, str]:
    with get_db_connection(operation="h3_3_6_read_states") as conn:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(world.lead_ids))
            cur.execute(
                f"SELECT id_lead::text AS id_lead, estado_lead FROM tpi.leads "
                f"WHERE id_lead IN ({placeholders}) ORDER BY id_lead",
                [str(lead) for lead in world.lead_ids],
            )
            return {str(row["id_lead"]): str(row["estado_lead"]) for row in cur.fetchall()}


def test_export_ignores_pagination_and_contains_all_rows(world: _World) -> None:
    response = _client("ceo").get("/leads/export.xlsx", params={"search": world.suffix})
    assert response.status_code == 200
    rows = _data_rows(response.content)
    assert len(rows) == 12  # page_size is 10, export must not paginate


def test_export_respects_combined_filters(world: _World) -> None:
    response = _client("ceo").get(
        "/leads/export.xlsx",
        params={"search": world.suffix, "estado_lead": "contactado"},
    )
    assert response.status_code == 200
    rows = _data_rows(response.content)
    assert len(rows) == 6
    # Column 11 (index 10) is "Estado" in the allowlist.
    assert all(row[10] == "contactado" for row in rows)


def test_export_writes_audit_event_without_pii(world: _World) -> None:
    search_rut = world.ruts[0]
    response = _client("ceo").get("/leads/export.xlsx", params={"search": search_rut})
    assert response.status_code == 200

    with get_db_connection(operation="h3_3_6_read_audit") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT detalle->>'actor_subject' AS actor_subject,
                       detalle->>'role' AS role,
                       (detalle->>'row_count')::int AS row_count,
                       detalle->>'format' AS format,
                       detalle->'filters'->>'search_applied' AS search_applied,
                       detalle::text AS full_detalle
                FROM tpi.auditoria
                WHERE accion = 'exportacion_xlsx'
                ORDER BY fecha_hora DESC
                LIMIT 1
                """)
            row = cur.fetchone()

    assert row is not None
    assert row["actor_subject"] == "subject-ceo"
    assert row["role"] == "ceo"
    assert row["row_count"] == 1
    assert row["format"] == "xlsx"
    assert row["search_applied"] == "true"
    assert search_rut not in row["full_detalle"]


def test_export_does_not_mutate_leads(world: _World) -> None:
    before = _lead_states(world)
    response = _client("cto").get("/leads/export.xlsx", params={"search": world.suffix})
    assert response.status_code == 200
    after = _lead_states(world)
    assert before == after


def test_empty_export_returns_valid_file(world: _World) -> None:
    response = _client("ceo").get(
        "/leads/export.xlsx", params={"search": f"zzz-no-match-{world.suffix}"}
    )
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook.active
    assert sheet.max_row == 1  # headers only


def test_ceo_export_and_advisor_403(world: _World) -> None:
    ceo = _client("ceo").get("/leads/export.xlsx", params={"search": world.suffix})
    assert ceo.status_code == 200
    assert ceo.content[:2] == b"PK"

    advisor = _client("advisor").get("/leads/export.xlsx")
    assert advisor.status_code == 403

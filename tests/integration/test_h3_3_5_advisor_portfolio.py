"""Integration tests (real PostgreSQL) for the H3.3.5 advisor portfolio scope.

These exercise the actual SQL of the repository and service against a real
PostgreSQL database (the CI mechanism from scripts/init_test_database.py), not a
fake repository. They cover portfolio isolation, counts/pagination, ownership
checks for mutations, and the fail-closed/superuser scope behavior.

Run by CI on Linux with the PostgreSQL service; skipped locally when the database
is unavailable (mirrors tests/integration/test_crm_lite_board.py).
"""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.repositories.solicitud_repository import SolicitudRepository
from app.services.solicitud_service import SolicitudService

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    health = full_health_check()
    if not health.get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _user(role: str, advisor_id: Any = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
        advisor_id=advisor_id,
    )


def _insert_advisor(cur: Any, *, rol: str, estado: str, nombre: str) -> Any:
    cur.execute(
        """
        INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad)
        VALUES (%s, %s, %s)
        RETURNING id_asesor
        """,
        (nombre, rol, estado),
    )
    return cur.fetchone()["id_asesor"]


def _insert_persona_lead(cur: Any, *, rut: str, nombre: str) -> Any:
    cur.execute(
        """
        INSERT INTO tpi.personas (rut, nombre_completo, created_at)
        VALUES (%s, %s, now())
        RETURNING id_persona
        """,
        (rut, nombre),
    )
    id_persona = cur.fetchone()["id_persona"]
    cur.execute(
        """
        INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, created_at)
        VALUES (%s, now(), 'nuevo', now())
        RETURNING id_lead
        """,
        (str(id_persona),),
    )
    return cur.fetchone()["id_lead"]


def _insert_asignacion(
    cur: Any,
    *,
    id_lead: Any,
    id_asesor: Any,
    estado: str = "activa",
) -> None:
    cur.execute(
        """
        INSERT INTO tpi.asignaciones (id_lead, id_asesor, estado_asignacion)
        VALUES (%s, %s, %s)
        """,
        (str(id_lead), str(id_asesor), estado),
    )


def _delete_lead_cascade(cur: Any, id_lead: Any) -> None:
    cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (str(id_lead),))
    cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (str(id_lead),))
    cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (str(id_lead),))
    cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (str(id_lead),))


class _AdvisorWorld:
    """Deterministic data world: two active advisors, one inactive, one non-advisor."""

    def __init__(self) -> None:
        suffix = uuid4().hex[:12]
        self.a1_name = f"Rework Advisor 1 {suffix}"
        self.a2_name = f"Rework Advisor 2 {suffix}"
        self.a3_name = f"Rework Advisor 3 inactive {suffix}"
        self.a4_name = f"Rework Gerente {suffix}"
        self.a1: Any = None
        self.a2: Any = None
        self.a3: Any = None
        self.a4: Any = None
        self.lead_ids: list[Any] = []
        self._id_persona_by_lead: dict[str, Any] = {}


@pytest.fixture
def world() -> _AdvisorWorld:
    w = _AdvisorWorld()
    with get_db_connection(operation="h3_3_5_advisor_world_setup") as conn:
        with conn.cursor() as cur:
            w.a1 = _insert_advisor(cur, rol="asesor", estado="activo", nombre=w.a1_name)
            w.a2 = _insert_advisor(cur, rol="asesor", estado="activo", nombre=w.a2_name)
            w.a3 = _insert_advisor(cur, rol="asesor", estado="inactivo", nombre=w.a3_name)
            w.a4 = _insert_advisor(cur, rol="gerente", estado="activo", nombre=w.a4_name)
        conn.commit()

    yield w

    with get_db_connection(operation="h3_3_5_advisor_world_cleanup") as conn:
        with conn.cursor() as cur:
            for id_lead in w.lead_ids:
                _delete_lead_cascade(cur, id_lead)
            for id_asesor in (w.a1, w.a2, w.a3, w.a4):
                cur.execute("DELETE FROM tpi.asesores WHERE id_asesor = %s", (str(id_asesor),))
            for id_persona in w._id_persona_by_lead.values():
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(id_persona),))
        conn.commit()


def _make_lead(world: _AdvisorWorld, *, rut: str, nombre: str) -> Any:
    with get_db_connection(operation="h3_3_5_advisor_lead_setup") as conn:
        with conn.cursor() as cur:
            id_lead = _insert_persona_lead(cur, rut=rut, nombre=nombre)
            cur.execute("SELECT id_persona FROM tpi.leads WHERE id_lead = %s", (str(id_lead),))
            id_persona = cur.fetchone()["id_persona"]
            world._id_persona_by_lead[str(id_lead)] = id_persona
        conn.commit()
    world.lead_ids.append(id_lead)
    return id_lead


def _assign(world: _AdvisorWorld, id_lead: Any, id_asesor: Any, *, estado: str = "activa") -> None:
    with get_db_connection(operation="h3_3_5_advisor_asign_setup") as conn:
        with conn.cursor() as cur:
            _insert_asignacion(cur, id_lead=id_lead, id_asesor=id_asesor, estado=estado)
        conn.commit()


def test_advisor_portfolio_isolation_counts_and_pagination(world: _AdvisorWorld) -> None:
    lead_a1 = _make_lead(world, rut="30111111-1", nombre="Lead A1 Propio")
    lead_a2 = _make_lead(world, rut="30222222-2", nombre="Lead A2 Propio")
    lead_unassigned = _make_lead(world, rut="30333333-3", nombre="Lead Sin Asignar")
    lead_historical = _make_lead(world, rut="30444444-4", nombre="Lead Historico A1")

    _assign(world, lead_a1, world.a1)
    _assign(world, lead_a2, world.a2)
    # Historical/inactive assignment of A1 must not grant access.
    _assign(world, lead_historical, world.a1, estado="inactiva")

    rows_a1, total_a1 = SolicitudRepository.get_crm_solicitudes(portfolio_asesor_id=world.a1)
    rows_a2, total_a2 = SolicitudRepository.get_crm_solicitudes(portfolio_asesor_id=world.a2)

    assert {str(row["id_lead"]) for row in rows_a1} == {str(lead_a1)}
    assert total_a1 == 1
    assert {str(row["id_lead"]) for row in rows_a2} == {str(lead_a2)}
    assert total_a2 == 1

    # Unassigned and historically-assigned leads never appear.
    assert str(lead_unassigned) not in {str(row["id_lead"]) for row in rows_a1}
    assert str(lead_historical) not in {str(row["id_lead"]) for row in rows_a1}

    # Pagination keeps the scope (page_size 1 -> 1 page for A1).
    page, page_total = SolicitudRepository.get_crm_solicitudes(
        limit=1, offset=0, portfolio_asesor_id=world.a1
    )
    assert page_total == 1
    assert len(page) == 1
    assert str(page[0]["id_lead"]) == str(lead_a1)


def test_advisor_resolution_and_ownership_helpers(world: _AdvisorWorld) -> None:
    lead_a1 = _make_lead(world, rut="30555555-5", nombre="Lead Resolucion")
    lead_a2 = _make_lead(world, rut="30666666-6", nombre="Lead Resolucion A2")
    lead_unassigned = _make_lead(world, rut="30777777-7", nombre="Lead Resolucion Sin")
    _assign(world, lead_a1, world.a1)
    _assign(world, lead_a2, world.a2)

    assert SolicitudRepository.get_active_advisor_by_id(world.a1) is not None
    assert SolicitudRepository.get_active_advisor_by_id(world.a3) is None  # inactive
    assert SolicitudRepository.get_active_advisor_by_id(world.a4) is None  # rol != asesor
    assert SolicitudRepository.get_active_advisor_by_id(uuid4()) is None  # missing

    assert SolicitudRepository.lead_active_assignment_belongs_to(lead_a1, world.a1) is True
    assert SolicitudRepository.lead_active_assignment_belongs_to(lead_a2, world.a1) is False
    assert SolicitudRepository.lead_active_assignment_belongs_to(lead_unassigned, world.a1) is False


def test_advisor_mutations_ownership_and_rollback(world: _AdvisorWorld) -> None:
    lead_own = _make_lead(world, rut="30888888-8", nombre="Lead Mutacion Propio")
    lead_other = _make_lead(world, rut="30999999-9", nombre="Lead Mutacion Ajeno")
    lead_unassigned = _make_lead(world, rut="31000000-0", nombre="Lead Mutacion Sin")
    _assign(world, lead_own, world.a1)
    _assign(world, lead_other, world.a2)

    actor = _user("advisor", advisor_id=world.a1)

    # Own lead: status update succeeds and writes audit.
    assert (
        SolicitudRepository.update_lead_status(
            lead_own, "contactado", actor=actor, advisor_scope=world.a1
        )
        is True
    )
    with get_db_connection(operation="h3_3_5_assert_own_status") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (str(lead_own),))
            assert cur.fetchone()["estado_lead"] == "contactado"

    # Own lead: comment append succeeds (F1 regression).
    assert (
        SolicitudRepository.append_lead_comment(
            lead_own, "[10/09/2026 10:00] Asesor\nNota propia", advisor_scope=world.a1
        )
        is True
    )
    with get_db_connection(operation="h3_3_5_assert_own_comment") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT comentarios FROM tpi.leads WHERE id_lead = %s", (str(lead_own),))
            assert "Nota propia" in (cur.fetchone()["comentarios"] or "")

    # Other lead: no write, no audit.
    before = _audit_count(lead_other)
    assert (
        SolicitudRepository.update_lead_status(
            lead_other, "contactado", actor=actor, advisor_scope=world.a1
        )
        is False
    )
    assert (
        SolicitudRepository.append_lead_comment(lead_other, "Nota ajena", advisor_scope=world.a1)
        is False
    )
    assert _audit_count(lead_other) == before

    # Unassigned lead: no write.
    assert (
        SolicitudRepository.update_lead_status(
            lead_unassigned, "contactado", actor=actor, advisor_scope=world.a1
        )
        is False
    )
    assert (
        SolicitudRepository.append_lead_comment(
            lead_unassigned, "Nota sin asignar", advisor_scope=world.a1
        )
        is False
    )


def test_invalid_advisor_empty_and_superuser_global(world: _AdvisorWorld) -> None:
    lead_a1 = _make_lead(world, rut="31111111-1", nombre="Lead Scope A1")
    lead_a2 = _make_lead(world, rut="31222222-2", nombre="Lead Scope A2")
    _assign(world, lead_a1, world.a1)
    _assign(world, lead_a2, world.a2)

    service = SolicitudService()

    # Invalid advisor (no advisor_id) -> empty board, no query.
    board_invalid = service.get_crm_bandeja(user=_user("advisor", None), masked=True)
    assert board_invalid["total"] == 0
    assert board_invalid["solicitudes"] == []

    # Inactive advisor (a3) -> empty board.
    board_inactive = service.get_crm_bandeja(user=_user("advisor", world.a3), masked=True)
    assert board_inactive["total"] == 0

    # Valid advisor -> only own lead.
    board_a1 = service.get_crm_bandeja(user=_user("advisor", world.a1), masked=True)
    assert board_a1["total"] == 1
    assert {str(row["id_lead"]) for row in board_a1["solicitudes"]} == {str(lead_a1)}

    # CEO/CTO -> global access (both leads).
    for role in ("ceo", "cto"):
        board = service.get_crm_bandeja(user=_user(role), masked=True)
        ids = {str(row["id_lead"]) for row in board["solicitudes"]}
        assert str(lead_a1) in ids
        assert str(lead_a2) in ids


def _audit_count(id_lead: Any) -> int:
    with get_db_connection(operation="h3_3_5_audit_count") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM tpi.auditoria WHERE id_lead = %s",
                (str(id_lead),),
            )
            return int(cur.fetchone()["n"])

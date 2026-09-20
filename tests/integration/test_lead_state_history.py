"""Integration tests for the H3.3.4 transactional general state-change write path."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.database.connection import get_db_connection
from app.database.errors import DatabaseAppError
from app.database.healthcheck import full_health_check
from app.repositories import SolicitudRepository

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _actor(subject: str = "actor-001") -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=subject,
        username=f"{subject}@example.com",
        display_name="Actor Demo",
        role=cast(UserRole, "executive"),
    )


def _make_lead(cur, rut: str, *, estado: str = "nuevo") -> tuple[str, str]:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "State History Integration", f"{rut}@example.com", "+56912345678"),
    )
    persona_id = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id_lead",
        (persona_id, datetime.now(UTC), estado, "integration", "integration"),
    )
    return str(cur.fetchone()["id_lead"]), persona_id


def _new_lead(estado: str = "nuevo") -> tuple[str, str]:
    with get_db_connection(operation="integration.state_history.seed") as conn:
        with conn.cursor() as cur:
            lead_id, persona_id = _make_lead(cur, uuid4().hex[:11], estado=estado)
        conn.commit()
    return lead_id, persona_id


def _cleanup_lead(lead_id: str) -> None:
    with get_db_connection(operation="integration.state_history.cleanup") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_persona FROM tpi.leads WHERE id_lead = %s", (lead_id,))
            row = cur.fetchone()
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead_id,))
            if row is not None:
                cur.execute(
                    "DELETE FROM tpi.personas WHERE id_persona = %s", (str(row["id_persona"]),)
                )
        conn.commit()


def _state_change_events(lead_id: str) -> list[dict]:
    with get_db_connection(operation="integration.state_history.read") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id_auditoria, fecha_hora, detalle->>'actor_subject' AS actor_subject,
                    detalle->>'estado_anterior' AS estado_anterior,
                    detalle->>'estado_nuevo' AS estado_nuevo
                FROM tpi.auditoria
                WHERE id_lead = %s AND accion = 'cambio_estado_lead' AND tabla_afectada = 'tpi.leads'
                ORDER BY fecha_hora ASC, id_auditoria ASC
                """,
                (lead_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def test_effective_change_records_actor_timestamp_states_and_single_event() -> None:
    lead_id, _ = _new_lead(estado="nuevo")
    try:
        updated = SolicitudRepository.update_lead_status(
            UUID(lead_id), "contactado", actor=_actor("actor-001")
        )
        assert updated is True

        events = _state_change_events(lead_id)
        assert len(events) == 1
        event = events[0]
        assert event["actor_subject"] == "actor-001"
        assert event["estado_anterior"] == "nuevo"
        assert event["estado_nuevo"] == "contactado"
        assert event["fecha_hora"] is not None

        with get_db_connection(operation="integration.state_history.verify") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (lead_id,))
                assert cur.fetchone()["estado_lead"] == "contactado"
    finally:
        _cleanup_lead(lead_id)


def test_noop_does_not_update_nor_duplicate_audit() -> None:
    lead_id, _ = _new_lead(estado="contactado")
    try:
        with get_db_connection(operation="integration.state_history.before") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT updated_at FROM tpi.leads WHERE id_lead = %s", (lead_id,))
                updated_at_before = cur.fetchone()["updated_at"]

        updated = SolicitudRepository.update_lead_status(
            UUID(lead_id), "contactado", actor=_actor("actor-001")
        )
        assert updated is True
        assert _state_change_events(lead_id) == []

        with get_db_connection(operation="integration.state_history.after") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT estado_lead, updated_at FROM tpi.leads WHERE id_lead = %s",
                    (lead_id,),
                )
                row = cur.fetchone()
                assert row["estado_lead"] == "contactado"
                assert row["updated_at"] == updated_at_before
    finally:
        _cleanup_lead(lead_id)


def test_audit_failure_rolls_back_state() -> None:
    lead_id, _ = _new_lead(estado="nuevo")
    try:
        with get_db_connection(operation="integration.state_history.trigger_on") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE FUNCTION _force_audit_failure() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION 'forced audit failure';
                    END
                    $$ LANGUAGE plpgsql
                    """)
                cur.execute("""
                    CREATE TRIGGER _force_audit_failure_trigger
                    BEFORE INSERT ON tpi.auditoria
                    FOR EACH ROW EXECUTE FUNCTION _force_audit_failure()
                    """)
            conn.commit()

        with pytest.raises(DatabaseAppError):
            SolicitudRepository.update_lead_status(
                UUID(lead_id), "contactado", actor=_actor("actor-001")
            )

        with get_db_connection(operation="integration.state_history.verify_rollback") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (lead_id,))
                assert cur.fetchone()["estado_lead"] == "nuevo"
        assert _state_change_events(lead_id) == []
    finally:
        with get_db_connection(operation="integration.state_history.trigger_off") as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TRIGGER IF EXISTS _force_audit_failure_trigger ON tpi.auditoria")
                cur.execute("DROP FUNCTION IF EXISTS _force_audit_failure()")
            conn.commit()
        _cleanup_lead(lead_id)


def test_concurrent_updates_serialize_without_lost_update_or_duplicate_events() -> None:
    lead_id, _ = _new_lead(estado="nuevo")
    try:
        barrier = Barrier(2)

        def _attempt(target: str) -> bool:
            barrier.wait()
            return SolicitudRepository.update_lead_status(
                UUID(lead_id), target, actor=_actor("actor-concurrent")
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(_attempt, ("contactado", "citado")))

        assert results == [True, True]

        events = _state_change_events(lead_id)
        assert len(events) == 2
        starts = [e for e in events if e["estado_anterior"] == "nuevo"]
        assert len(starts) == 1
        others = [e for e in events if e is not starts[0]]
        assert len(others) == 1
        assert others[0]["estado_anterior"] == starts[0]["estado_nuevo"]
        assert others[0]["estado_nuevo"] in {"contactado", "citado"}
        assert starts[0]["estado_nuevo"] in {"contactado", "citado"}

        with get_db_connection(operation="integration.state_history.concurrent_verify") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (lead_id,))
                assert cur.fetchone()["estado_lead"] == others[0]["estado_nuevo"]
    finally:
        _cleanup_lead(lead_id)


def test_update_rejects_asignado_state_at_repository_level() -> None:
    lead_id, _ = _new_lead(estado="nuevo")
    try:
        with pytest.raises(ValueError, match="asignacion valida"):
            SolicitudRepository.update_lead_status(
                UUID(lead_id), "asignado", actor=_actor("actor-001")
            )
        assert _state_change_events(lead_id) == []
    finally:
        _cleanup_lead(lead_id)


def test_update_returns_false_for_missing_lead() -> None:
    missing = uuid4()
    assert (
        SolicitudRepository.update_lead_status(missing, "contactado", actor=_actor("actor-001"))
        is False
    )

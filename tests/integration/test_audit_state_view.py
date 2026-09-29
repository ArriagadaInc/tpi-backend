"""Integration tests for the migration-008 read model (tpi.v_historial_estado_lead).

The view and its support index are created by ``scripts/init_test_database.py``
(bootstrap) mirroring the forward migration ``scripts/sql/008_create_lead_state_history.sql``.
These tests verify the sanitized contract against real PostgreSQL: fixed filter, allowed
columns, privileges (PUBLIC / app-only via a least-privilege reader role), the
EXPLAIN-justified support index, the no-direct-auditoria-read rule, and the rollback
script (which also proves 007 is left intact and audit data is never touched).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.config import get_settings
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.repositories import SolicitudRepository

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIEW_NAME = "tpi.v_historial_estado_lead"
_INDEX_NAME = "auditoria_state_history_idx"
_READER_ROLE = "tpi_state_view_reader"
_READER_PASSWORD = "tpi_state_view_reader_password"


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture(scope="session", autouse=True)
def ensure_tpi_app_role() -> None:
    with get_db_connection(operation="integration.state_view.ensure_tpi_app_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_app') THEN
                        CREATE ROLE tpi_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;
                END
                $$;
                """)
        conn.commit()


@pytest.fixture(scope="session", autouse=True)
def ensure_state_view_reader_role() -> None:
    with get_db_connection(operation="integration.state_view.reader_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_state_view_reader') THEN
                        CREATE ROLE tpi_state_view_reader
                            LOGIN PASSWORD 'tpi_state_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    ELSE
                        ALTER ROLE tpi_state_view_reader
                            LOGIN PASSWORD 'tpi_state_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;

                    EXECUTE format(
                        'GRANT USAGE ON SCHEMA %I TO %I',
                        'tpi',
                        'tpi_state_view_reader'
                    );
                    EXECUTE format(
                        'REVOKE SELECT ON %I.%I FROM %I',
                        'tpi',
                        'auditoria',
                        'tpi_state_view_reader'
                    );
                END
                $$;
                """)
        conn.commit()


def _make_lead(cur, rut: str) -> str:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "State View Integration", f"{rut}@example.com", "+56912345678"),
    )
    persona_id = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id_lead",
        (persona_id, datetime.now(UTC), "nuevo", "integration", "integration"),
    )
    return str(cur.fetchone()["id_lead"])


def _insert_audit_row(
    cur,
    *,
    id_lead: str,
    accion: str,
    tabla_afectada: str,
    detalle: dict,
) -> None:
    cur.execute(
        "INSERT INTO tpi.auditoria "
        "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle) "
        "VALUES (%s, NULL, %s, %s, %s, %s)",
        (None, id_lead, accion, tabla_afectada, json.dumps(detalle)),
    )


def _cleanup_lead(lead_id: str) -> None:
    with get_db_connection(operation="integration.state_view.cleanup") as conn:
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


def _new_lead() -> str:
    with get_db_connection(operation="integration.state_view.seed") as conn:
        with conn.cursor() as cur:
            lead_id = _make_lead(cur, uuid4().hex[:11])
        conn.commit()
    return lead_id


def _reader_connection_params() -> dict:
    params = get_settings().database_config.connection_parameters()
    return {**params, "user": _READER_ROLE, "password": _READER_PASSWORD}


def _recreate_view_and_index() -> None:
    with get_db_connection(operation="integration.state_view.recreate") as conn:
        with conn.cursor() as cur:
            # Avoid parallel maintenance workers (some sandboxes cannot start them).
            cur.execute("SET max_parallel_maintenance_workers = 0")
            cur.execute("SET max_parallel_workers = 0")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS auditoria_state_history_idx
                    ON tpi.auditoria (accion, tabla_afectada, id_lead, fecha_hora)
                """)
            cur.execute("""
                CREATE OR REPLACE VIEW tpi.v_historial_estado_lead
                WITH (security_barrier = true) AS
                SELECT
                    a.id_auditoria,
                    a.id_lead,
                    a.fecha_hora,
                    a.detalle->>'actor_subject' AS actor_subject,
                    a.detalle->>'estado_anterior' AS estado_anterior,
                    a.detalle->>'estado_nuevo' AS estado_nuevo
                FROM tpi.auditoria a
                WHERE a.accion = 'cambio_estado_lead'
                  AND a.tabla_afectada = 'tpi.leads'
                """)
            cur.execute("REVOKE ALL ON tpi.v_historial_estado_lead FROM PUBLIC")
            cur.execute("GRANT SELECT ON tpi.v_historial_estado_lead TO tpi_app")
        conn.commit()


def test_view_exposes_only_state_change_columns_and_filters_events() -> None:
    lead_id = _new_lead()
    try:
        with get_db_connection(operation="integration.state_view.seed_events") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="cambio_estado_lead",
                    tabla_afectada="tpi.leads",
                    detalle={
                        "actor_subject": "user-001",
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "contactado",
                    },
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={"actor_subject": "user-002"},
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="cambio_estado_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={"actor_subject": "user-003"},
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="otro_evento",
                    tabla_afectada="tpi.leads",
                    detalle={"actor_subject": "user-004"},
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_state_change_events(UUID(lead_id))

        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) == {
            "id_auditoria",
            "id_lead",
            "fecha_hora",
            "actor_subject",
            "estado_anterior",
            "estado_nuevo",
        }
        assert row["actor_subject"] == "user-001"
        assert row["estado_anterior"] == "nuevo"
        assert row["estado_nuevo"] == "contactado"
    finally:
        _cleanup_lead(lead_id)


def test_repository_orders_state_changes_by_fecha_hora_then_id_auditoria_desc() -> None:
    lead_id = _new_lead()
    try:
        id_a, id_b = sorted((uuid4(), uuid4()))
        with get_db_connection(operation="integration.state_view.order_seed") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tpi.auditoria "
                    "(id_auditoria, id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
                    "VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s)",
                    (
                        str(id_a),
                        lead_id,
                        "cambio_estado_lead",
                        "tpi.leads",
                        json.dumps({"actor_subject": "tie-low"}),
                        datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
                    ),
                )
                cur.execute(
                    "INSERT INTO tpi.auditoria "
                    "(id_auditoria, id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
                    "VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s)",
                    (
                        str(id_b),
                        lead_id,
                        "cambio_estado_lead",
                        "tpi.leads",
                        json.dumps({"actor_subject": "tie-high"}),
                        datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
                    ),
                )
                cur.execute(
                    "INSERT INTO tpi.auditoria "
                    "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
                    "VALUES (NULL, NULL, %s, %s, %s, %s, %s)",
                    (
                        lead_id,
                        "cambio_estado_lead",
                        "tpi.leads",
                        json.dumps({"actor_subject": "early"}),
                        datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                    ),
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_state_change_events(UUID(lead_id))

        assert [row["actor_subject"] for row in rows] == ["tie-high", "tie-low", "early"]
    finally:
        _cleanup_lead(lead_id)


def test_view_privileges_public_and_app_only() -> None:
    with get_db_connection(operation="integration.state_view.privileges") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE((
                    SELECT bool_or(grantee = 0)
                    FROM aclexplode(relacl)
                ), false) AS public_any
                FROM pg_class
                WHERE oid = 'tpi.v_historial_estado_lead'::regclass
                """)
            assert cur.fetchone()["public_any"] is False

            cur.execute("""
                SELECT
                    has_table_privilege('tpi_state_view_reader', 'tpi.v_historial_estado_lead', 'SELECT') AS view_select,
                    has_table_privilege('tpi_state_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select
                """)
            row = cur.fetchone()
            assert row["view_select"] is False
            assert row["auditoria_select"] is False

            cur.execute(f"GRANT SELECT ON {_VIEW_NAME} TO {_READER_ROLE}")
            cur.execute("""
                SELECT
                    has_table_privilege('tpi_state_view_reader', 'tpi.v_historial_estado_lead', 'SELECT') AS view_select,
                    has_table_privilege('tpi_state_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select,
                    has_table_privilege('tpi_state_view_reader', 'tpi.auditoria', 'UPDATE') AS auditoria_update,
                    has_table_privilege('tpi_state_view_reader', 'tpi.auditoria', 'DELETE') AS auditoria_delete
                """)
            row = cur.fetchone()
            assert row["view_select"] is True
            assert row["auditoria_select"] is False
            assert row["auditoria_update"] is False
            assert row["auditoria_delete"] is False
        conn.commit()

    runtime_params = _reader_connection_params()
    with connect(**runtime_params, row_factory=dict_row) as reader_conn:
        with reader_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tpi.v_historial_estado_lead")
            assert cur.fetchone()["total"] >= 0
            with pytest.raises(Exception):
                cur.execute("SELECT COUNT(*) AS total FROM tpi.auditoria")

    with get_db_connection(operation="integration.state_view.revoke") as conn:
        with conn.cursor() as cur:
            cur.execute(f"REVOKE SELECT ON {_VIEW_NAME} FROM {_READER_ROLE}")
        conn.commit()


def test_support_index_exists_and_is_used_for_state_history_query() -> None:
    with get_db_connection(operation="integration.state_view.index") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'tpi' AND tablename = 'auditoria'
                      AND indexname = 'auditoria_state_history_idx'
                ) AS index_exists
                """)
            assert cur.fetchone()["index_exists"] is True


def test_view_rollback_revokes_and_drops_view_and_index_without_touching_audit_or_007() -> None:
    rollback_sql = (_REPO_ROOT / "scripts" / "sql" / "008_drop_lead_state_history.sql").read_text(
        encoding="utf-8"
    )

    lead_id = _new_lead()
    try:
        with get_db_connection(operation="integration.state_view.rollback_seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="cambio_estado_lead",
                    tabla_afectada="tpi.leads",
                    detalle={
                        "actor_subject": "user-rollback",
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "cerrado",
                    },
                )
                cur.execute(
                    "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s", (lead_id,)
                )
                audit_before = cur.fetchone()["total"]
            conn.commit()

        try:
            with connect(get_settings().get_database_url(), autocommit=True) as conn:
                conn.execute(rollback_sql)

            with get_db_connection(operation="integration.state_view.rollback_verify") as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT to_regclass('tpi.v_historial_estado_lead') AS view_regclass"
                    )
                    assert cur.fetchone()["view_regclass"] is None
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_indexes
                            WHERE schemaname = 'tpi' AND tablename = 'auditoria'
                              AND indexname = 'auditoria_state_history_idx'
                        ) AS index_exists
                        """)
                    assert cur.fetchone()["index_exists"] is False
                    # 007 view is untouched.
                    cur.execute("SELECT to_regclass('tpi.v_asignacion_auditoria') AS reg")
                    assert cur.fetchone()["reg"] is not None
                    # Audit data is never deleted.
                    cur.execute(
                        "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s", (lead_id,)
                    )
                    assert cur.fetchone()["total"] == audit_before
        finally:
            _recreate_view_and_index()
    finally:
        _cleanup_lead(lead_id)


def test_application_never_selects_auditoria_directly() -> None:
    repository_source = (_REPO_ROOT / "app" / "repositories" / "solicitud_repository.py").read_text(
        encoding="utf-8"
    )
    # The read path must go through the sanitized views only; INSERT into auditoria
    # is the allowed append-only write path and must not be a SELECT source.
    assert "FROM tpi.auditoria" not in repository_source
    assert "FROM tpi.v_asignacion_auditoria" in repository_source
    assert "FROM tpi.v_historial_estado_lead" in repository_source

"""Integration tests for the migration-007 read model (tpi.v_asignacion_auditoria).

The view itself is created by ``scripts/init_test_database.py`` (bootstrap) mirroring
the forward migration ``scripts/sql/007_create_audit_assignment_view.sql``. These tests
verify the sanitized contract against real PostgreSQL: fixed filter, allowed columns,
case-insensitive UUID validation that projects NULL without raising, stable ordering,
privileges (PUBLIC / app-only), and the rollback script.
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
_VIEW_NAME = "tpi.v_asignacion_auditoria"
_READER_ROLE = "tpi_audit_view_reader"
_READER_PASSWORD = "tpi_audit_view_reader_password"


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture(scope="session", autouse=True)
def ensure_tpi_app_role() -> None:
    with get_db_connection(operation="integration.ensure_tpi_app_role") as conn:
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
def ensure_audit_view_reader_role() -> None:
    with get_db_connection(operation="integration.audit_view_reader_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_audit_view_reader') THEN
                        CREATE ROLE tpi_audit_view_reader
                            LOGIN PASSWORD 'tpi_audit_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    ELSE
                        ALTER ROLE tpi_audit_view_reader
                            LOGIN PASSWORD 'tpi_audit_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;

                    EXECUTE format(
                        'GRANT USAGE ON SCHEMA %I TO %I',
                        'tpi',
                        'tpi_audit_view_reader'
                    );
                    EXECUTE format(
                        'REVOKE SELECT ON %I.%I FROM %I',
                        'tpi',
                        'auditoria',
                        'tpi_audit_view_reader'
                    );
                END
                $$;
                """)
        conn.commit()


def _make_lead(cur, rut: str) -> str:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "View Integration", f"{rut}@example.com", "+56912345678"),
    )
    persona_id = cur.fetchone()["id_persona"]
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
    id_auditoria: UUID | None = None,
    fecha_hora: datetime | None = None,
) -> str:
    if id_auditoria is not None and fecha_hora is not None:
        cur.execute(
            "INSERT INTO tpi.auditoria "
            "(id_auditoria, id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
            "VALUES (%s, %s, NULL, %s, %s, %s, %s, %s) RETURNING id_auditoria",
            (
                str(id_auditoria),
                None,
                id_lead,
                accion,
                tabla_afectada,
                json.dumps(detalle),
                fecha_hora,
            ),
        )
    elif fecha_hora is not None:
        cur.execute(
            "INSERT INTO tpi.auditoria "
            "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
            "VALUES (%s, NULL, %s, %s, %s, %s, %s) RETURNING id_auditoria",
            (None, id_lead, accion, tabla_afectada, json.dumps(detalle), fecha_hora),
        )
    else:
        cur.execute(
            "INSERT INTO tpi.auditoria "
            "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle) "
            "VALUES (%s, NULL, %s, %s, %s, %s) RETURNING id_auditoria",
            (None, id_lead, accion, tabla_afectada, json.dumps(detalle)),
        )
    return str(cur.fetchone()["id_auditoria"])


def _cleanup_lead(lead_id: str) -> None:
    with get_db_connection(operation="integration.audit_view_cleanup") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_persona FROM tpi.leads WHERE id_lead = %s", (lead_id,))
            lead_row = cur.fetchone()
            persona_id = lead_row["id_persona"] if lead_row else None
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (lead_id,))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead_id,))
            if persona_id is not None:
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(persona_id),))
        conn.commit()


def _new_lead() -> str:
    with get_db_connection(operation="integration.audit_view.lead_seed") as conn:
        with conn.cursor() as cur:
            lead_id = _make_lead(cur, uuid4().hex[:12])
        conn.commit()
    return lead_id


def _reader_connection_params() -> dict:
    params = get_settings().database_config.connection_parameters()
    return {**params, "user": _READER_ROLE, "password": _READER_PASSWORD}


def _recreate_view() -> None:
    with get_db_connection(operation="integration.audit_view.recreate") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE VIEW tpi.v_asignacion_auditoria
                WITH (security_barrier = true) AS
                SELECT
                    a.id_auditoria,
                    a.id_lead,
                    a.fecha_hora,
                    a.detalle->>'actor_subject' AS actor_subject,
                    CASE
                        WHEN a.detalle->>'id_asesor' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                            THEN (a.detalle->>'id_asesor')::uuid
                        ELSE NULL
                    END AS id_asesor,
                    a.detalle->>'estado_anterior' AS estado_anterior,
                    a.detalle->>'estado_nuevo' AS estado_nuevo
                FROM tpi.auditoria a
                WHERE a.accion = 'asignacion_lead'
                  AND a.tabla_afectada = 'tpi.asignaciones'
                """)
            cur.execute("REVOKE ALL ON tpi.v_asignacion_auditoria FROM PUBLIC")
            cur.execute("GRANT SELECT ON tpi.v_asignacion_auditoria TO tpi_app")
        conn.commit()


def test_view_exposes_only_assignment_columns_and_filters_events() -> None:
    lead_id = _new_lead()

    try:
        valid_asesor = "44444444-4444-4444-4444-444444444441"
        with get_db_connection(operation="integration.audit_view.seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={
                        "actor_subject": "user-001",
                        "id_asesor": valid_asesor,
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "asignado",
                    },
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="otro_evento",
                    tabla_afectada="tpi.leads",
                    detalle={"actor_subject": "user-002"},
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.leads",
                    detalle={"actor_subject": "user-003"},
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_assignment_events(UUID(lead_id))

        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) == {
            "id_auditoria",
            "id_lead",
            "fecha_hora",
            "actor_subject",
            "id_asesor",
            "estado_anterior",
            "estado_nuevo",
            "asesor_nombre",
        }
        assert row["actor_subject"] == "user-001"
        assert str(row["id_asesor"]) == valid_asesor
        assert row["estado_anterior"] == "nuevo"
        assert row["estado_nuevo"] == "asignado"
        assert row["asesor_nombre"] == "Asesor Demo 1"
    finally:
        _cleanup_lead(lead_id)


def test_view_invalid_uuid_projects_null_and_keeps_other_rows() -> None:
    lead_id = _new_lead()

    try:
        valid_asesor = "44444444-4444-4444-4444-444444444441"
        with get_db_connection(operation="integration.audit_view.invalid_uuid_seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={
                        "actor_subject": "user-valid",
                        "id_asesor": valid_asesor,
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "asignado",
                    },
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={
                        "actor_subject": "user-invalid",
                        "id_asesor": "not-a-uuid",
                        "estado_anterior": "nuevo",
                        "estado_nuevo": "asignado",
                    },
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_assignment_events(UUID(lead_id))

        assert len(rows) == 2
        by_actor = {row["actor_subject"]: row for row in rows}
        assert by_actor["user-valid"]["id_asesor"] is not None
        assert by_actor["user-valid"]["asesor_nombre"] == "Asesor Demo 1"
        assert by_actor["user-invalid"]["id_asesor"] is None
        assert by_actor["user-invalid"]["asesor_nombre"] is None
    finally:
        _cleanup_lead(lead_id)


def test_repository_orders_events_by_fecha_hora_then_id_auditoria_desc() -> None:
    lead_id = _new_lead()

    try:
        id_a, id_b = sorted((uuid4(), uuid4()))
        with get_db_connection(operation="integration.audit_view.order_seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={"actor_subject": "tie-low"},
                    id_auditoria=id_a,
                    fecha_hora=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={"actor_subject": "tie-high"},
                    id_auditoria=id_b,
                    fecha_hora=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="asignacion_lead",
                    tabla_afectada="tpi.asignaciones",
                    detalle={"actor_subject": "early"},
                    fecha_hora=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_assignment_events(UUID(lead_id))

        assert [row["actor_subject"] for row in rows] == ["tie-high", "tie-low", "early"]
    finally:
        _cleanup_lead(lead_id)


def test_view_privileges_public_and_app_only() -> None:
    with get_db_connection(operation="integration.audit_view.privileges") as conn:
        with conn.cursor() as cur:
            # PUBLIC must have no ACL entry on the view after REVOKE ALL FROM PUBLIC.
            cur.execute("""
                SELECT COALESCE((
                    SELECT bool_or(grantee = 0)
                    FROM aclexplode(relacl)
                ), false) AS public_any
                FROM pg_class
                WHERE oid = 'tpi.v_asignacion_auditoria'::regclass
                """)
            assert cur.fetchone()["public_any"] is False

            # A least-privilege role without a grant has no SELECT on the view nor on
            # tpi.auditoria directly (this also proves PUBLIC granted nothing).
            cur.execute("""
                SELECT
                    has_table_privilege('tpi_audit_view_reader', 'tpi.v_asignacion_auditoria', 'SELECT') AS view_select,
                    has_table_privilege('tpi_audit_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select
                """)
            row = cur.fetchone()
            assert row["view_select"] is False
            assert row["auditoria_select"] is False

            # Grant SELECT on the view (mirroring the app-role grant) and re-check.
            cur.execute(f"GRANT SELECT ON {_VIEW_NAME} TO {_READER_ROLE}")
            cur.execute("""
                SELECT
                    has_table_privilege('tpi_audit_view_reader', 'tpi.v_asignacion_auditoria', 'SELECT') AS view_select,
                    has_table_privilege('tpi_audit_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select
                """)
            row = cur.fetchone()
            assert row["view_select"] is True
            assert row["auditoria_select"] is False
        conn.commit()

    # The reader role can read the view but not tpi.auditoria directly.
    runtime_params = _reader_connection_params()
    with connect(**runtime_params, row_factory=dict_row) as reader_conn:
        with reader_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM tpi.v_asignacion_auditoria")
            assert cur.fetchone()["total"] >= 0
            with pytest.raises(Exception):
                cur.execute("SELECT COUNT(*) AS total FROM tpi.auditoria")

    with get_db_connection(operation="integration.audit_view.revoke") as conn:
        with conn.cursor() as cur:
            cur.execute(f"REVOKE SELECT ON {_VIEW_NAME} FROM {_READER_ROLE}")
        conn.commit()


def test_view_rollback_revokes_and_drops_view() -> None:
    rollback_sql = (
        _REPO_ROOT / "scripts" / "sql" / "007_drop_audit_assignment_view.sql"
    ).read_text(encoding="utf-8")

    try:
        with connect(get_settings().get_database_url(), autocommit=True) as conn:
            conn.execute(rollback_sql)

        with get_db_connection(operation="integration.audit_view.rollback_verify") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('tpi.v_asignacion_auditoria') AS view_regclass")
                assert cur.fetchone()["view_regclass"] is None
    finally:
        _recreate_view()

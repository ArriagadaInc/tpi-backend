"""Integration tests for the SIM-HISTORIAL-LINEA-TIEMPO read model (tpi.v_historial_simulaciones).

The view is created by ``scripts/init_test_database.py`` (bootstrap) mirroring the forward
migration ``scripts/sql/009_create_historial_simulaciones.sql``. These tests verify the
sanitized contract against real PostgreSQL: fixed filter, allowed columns, privileges
(PUBLIC / app-only via a least-privilege reader role), the reuse of the 008 support index,
the no-direct-auditoria-read rule, and the rollback script (which also proves 007/008 are
left intact and audit data is never touched).
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
from app.web.presentation import build_timeline_items

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIEW_NAME = "tpi.v_historial_simulaciones"
_READER_ROLE = "tpi_sim_view_reader"
_READER_PASSWORD = "tpi_sim_view_reader_password"


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture(scope="session", autouse=True)
def ensure_sim_view_reader_role() -> None:
    with get_db_connection(operation="integration.sim_view.reader_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_sim_view_reader') THEN
                        CREATE ROLE tpi_sim_view_reader
                            LOGIN PASSWORD 'tpi_sim_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    ELSE
                        ALTER ROLE tpi_sim_view_reader
                            LOGIN PASSWORD 'tpi_sim_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;

                    EXECUTE format(
                        'GRANT USAGE ON SCHEMA %I TO %I',
                        'tpi',
                        'tpi_sim_view_reader'
                    );
                    EXECUTE format(
                        'REVOKE SELECT ON %I.%I FROM %I',
                        'tpi',
                        'auditoria',
                        'tpi_sim_view_reader'
                    );
                END
                $$;
                """)
        conn.commit()


def _make_lead(cur, rut: str) -> str:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "Sim View Integration", f"{rut}@example.com", "+56912345678"),
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
    with get_db_connection(operation="integration.sim_view.cleanup") as conn:
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
    with get_db_connection(operation="integration.sim_view.seed") as conn:
        with conn.cursor() as cur:
            lead_id = _make_lead(cur, uuid4().hex[:11])
        conn.commit()
    return lead_id


def _reader_connection_params() -> dict:
    params = get_settings().database_config.connection_parameters()
    return {**params, "user": _READER_ROLE, "password": _READER_PASSWORD}


def _recreate_view() -> None:
    with get_db_connection(operation="integration.sim_view.recreate") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE VIEW tpi.v_historial_simulaciones
                WITH (security_barrier = true) AS
                SELECT
                    a.id_auditoria,
                    a.id_lead,
                    a.fecha_hora,
                    a.detalle->>'actor_subject' AS actor_subject,
                    a.detalle->>'tipo_escenario' AS tipo_escenario,
                    a.detalle->>'version_modelo' AS version_modelo,
                    a.detalle->>'codigo_verificacion' AS codigo_verificacion,
                    a.detalle->'entradas' AS entradas,
                    a.detalle->'resultado' AS resultado
                FROM tpi.auditoria a
                WHERE a.accion = 'simulacion_renta_vitalicia'
                  AND a.tabla_afectada = 'tpi.leads'
                """)
            cur.execute("REVOKE ALL ON tpi.v_historial_simulaciones FROM PUBLIC")
        conn.commit()


def _simulation_detalle() -> dict:
    return {
        "schema_version": 1,
        "actor_subject": "user-001",
        "role": "executive",
        "tipo_escenario": "renta_inmediata_familia",
        "version_modelo": "sim-rv-v1",
        "codigo_verificacion": "abc123def456",
        "entradas": {
            "fecha_simulacion": "2026-10-15",
            "saldo_uf": 1000.0,
            "tasa_venta_pct": 2.63,
            "valor_uf": 38000.0,
            "meses_garantizados": 120,
            "meses_aumento_temporal": 0,
            "pct_aumento_temporal": 0.0,
            "anios_diferidos": 0,
            "porcentaje_rvd": 100.0,
            "causante": {"sexo": "H", "fecha_nacimiento": "1960-01-15"},
            "beneficiarios": [
                {
                    "parentesco": "conyuge",
                    "sexo": "M",
                    "fecha_nacimiento": "1962-03-20",
                    "invalidez": None,
                    "comun": None,
                }
            ],
        },
        "resultado": {"pension_uf": 5.23, "renta_temporal_uf": None, "meses_diferidos": 0},
    }


def test_view_exposes_only_simulation_columns_and_filters_events() -> None:
    lead_id = _new_lead()
    try:
        with get_db_connection(operation="integration.sim_view.seed_events") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="simulacion_renta_vitalicia",
                    tabla_afectada="tpi.leads",
                    detalle=_simulation_detalle(),
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
                    accion="simulacion_renta_vitalicia",
                    tabla_afectada="tpi.asignaciones",
                    detalle=_simulation_detalle(),
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="otro_evento",
                    tabla_afectada="tpi.leads",
                    detalle={"actor_subject": "user-004"},
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_simulation_events(UUID(lead_id))

        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) == {
            "id_auditoria",
            "id_lead",
            "fecha_hora",
            "actor_subject",
            "tipo_escenario",
            "version_modelo",
            "codigo_verificacion",
            "entradas",
            "resultado",
        }
        assert row["actor_subject"] == "user-001"
        assert row["tipo_escenario"] == "renta_inmediata_familia"
        assert row["codigo_verificacion"] == "abc123def456"
        # Full evidence is exposed: entradas (causante + beneficiarios) and resultado.
        assert row["entradas"]["causante"]["fecha_nacimiento"] == "1960-01-15"
        assert row["entradas"]["beneficiarios"][0]["parentesco"] == "conyuge"
        assert row["resultado"]["pension_uf"] == 5.23
    finally:
        _cleanup_lead(lead_id)


def test_view_exposes_legacy_and_complete_simulation_evidence_forms() -> None:
    lead_id = _new_lead()
    try:
        legacy_detalle = {
            "actor_subject": "user-legacy",
            "role": "executive",
            "tipo_escenario": "renta_inmediata_familia",
            "version_modelo": "sim-rv-v1",
            "codigo_verificacion": "legacy-code",
        }
        with get_db_connection(operation="integration.sim_view.legacy_seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="simulacion_renta_vitalicia",
                    tabla_afectada="tpi.leads",
                    detalle=legacy_detalle,
                )
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="simulacion_renta_vitalicia",
                    tabla_afectada="tpi.leads",
                    detalle=_simulation_detalle(),
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_simulation_events(UUID(lead_id))
        assert len(rows) == 2

        legacy = next(r for r in rows if r["codigo_verificacion"] == "legacy-code")
        complete = next(r for r in rows if r["codigo_verificacion"] == "abc123def456")

        # Legacy rows (pre SIM-EVIDENCIA-ENTRADAS) have no entradas/resultado in detalle.
        assert legacy["entradas"] is None
        assert legacy["resultado"] is None
        assert legacy["actor_subject"] == "user-legacy"
        assert legacy["tipo_escenario"] == "renta_inmediata_familia"
        assert legacy["version_modelo"] == "sim-rv-v1"

        # Complete rows expose the full evidence.
        assert complete["entradas"]["causante"]["fecha_nacimiento"] == "1960-01-15"
        assert complete["resultado"]["pension_uf"] == 5.23

        # The presentation layer flags the legacy form without raising on either form.
        items = build_timeline_items([], [], [], rows)
        by_code = {item["codigo_verificacion"]: item for item in items}
        assert by_code["legacy-code"]["es_legacy"] is True
        assert by_code["abc123def456"]["es_legacy"] is False
    finally:
        _cleanup_lead(lead_id)


def test_repository_orders_simulations_by_fecha_hora_then_id_auditoria_desc() -> None:
    lead_id = _new_lead()
    try:
        id_a, id_b = sorted((uuid4(), uuid4()))
        with get_db_connection(operation="integration.sim_view.order_seed") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tpi.auditoria "
                    "(id_auditoria, id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
                    "VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s)",
                    (
                        str(id_a),
                        lead_id,
                        "simulacion_renta_vitalicia",
                        "tpi.leads",
                        json.dumps({**_simulation_detalle(), "codigo_verificacion": "tie-low"}),
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
                        "simulacion_renta_vitalicia",
                        "tpi.leads",
                        json.dumps({**_simulation_detalle(), "codigo_verificacion": "tie-high"}),
                        datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
                    ),
                )
                cur.execute(
                    "INSERT INTO tpi.auditoria "
                    "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle, fecha_hora) "
                    "VALUES (NULL, NULL, %s, %s, %s, %s, %s)",
                    (
                        lead_id,
                        "simulacion_renta_vitalicia",
                        "tpi.leads",
                        json.dumps({**_simulation_detalle(), "codigo_verificacion": "early"}),
                        datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
                    ),
                )
            conn.commit()

        rows = SolicitudRepository.get_lead_simulation_events(UUID(lead_id))

        assert [row["codigo_verificacion"] for row in rows] == ["tie-high", "tie-low", "early"]
    finally:
        _cleanup_lead(lead_id)


def test_view_privileges_public_and_app_only() -> None:
    with get_db_connection(operation="integration.sim_view.privileges") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE((
                    SELECT bool_or(grantee = 0)
                    FROM aclexplode(relacl)
                ), false) AS public_any
                FROM pg_class
                WHERE oid = 'tpi.v_historial_simulaciones'::regclass
                """)
            assert cur.fetchone()["public_any"] is False

            cur.execute("""
                SELECT
                    has_table_privilege('tpi_sim_view_reader', 'tpi.v_historial_simulaciones', 'SELECT') AS view_select,
                    has_table_privilege('tpi_sim_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select
                """)
            row = cur.fetchone()
            assert row["view_select"] is False
            assert row["auditoria_select"] is False

            cur.execute(f"GRANT SELECT ON {_VIEW_NAME} TO {_READER_ROLE}")
            cur.execute("""
                SELECT
                    has_table_privilege('tpi_sim_view_reader', 'tpi.v_historial_simulaciones', 'SELECT') AS view_select,
                    has_table_privilege('tpi_sim_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select,
                    has_table_privilege('tpi_sim_view_reader', 'tpi.auditoria', 'UPDATE') AS auditoria_update,
                    has_table_privilege('tpi_sim_view_reader', 'tpi.auditoria', 'DELETE') AS auditoria_delete
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
            cur.execute("SELECT COUNT(*) AS total FROM tpi.v_historial_simulaciones")
            assert cur.fetchone()["total"] >= 0
            with pytest.raises(Exception):
                cur.execute("SELECT COUNT(*) AS total FROM tpi.auditoria")

    with get_db_connection(operation="integration.sim_view.revoke") as conn:
        with conn.cursor() as cur:
            cur.execute(f"REVOKE SELECT ON {_VIEW_NAME} FROM {_READER_ROLE}")
        conn.commit()


def test_support_index_from_008_is_reused_for_simulation_query() -> None:
    # 009 introduces no new index; the timeline query is served by 008's support index
    # whose leading columns (accion, tabla_afectada, id_lead) match this view's filter.
    with get_db_connection(operation="integration.sim_view.index") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = 'tpi' AND tablename = 'auditoria'
                      AND indexname = 'auditoria_state_history_idx'
                ) AS index_exists
                """)
            assert cur.fetchone()["index_exists"] is True


def test_view_rollback_revokes_and_drops_view_without_touching_audit_or_007_008() -> None:
    rollback_sql = (
        _REPO_ROOT / "scripts" / "sql" / "009_drop_historial_simulaciones.sql"
    ).read_text(encoding="utf-8")

    lead_id = _new_lead()
    try:
        with get_db_connection(operation="integration.sim_view.rollback_seed") as conn:
            with conn.cursor() as cur:
                _insert_audit_row(
                    cur,
                    id_lead=lead_id,
                    accion="simulacion_renta_vitalicia",
                    tabla_afectada="tpi.leads",
                    detalle=_simulation_detalle(),
                )
                cur.execute(
                    "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s", (lead_id,)
                )
                audit_before = cur.fetchone()["total"]
            conn.commit()

        try:
            with connect(get_settings().get_database_url(), autocommit=True) as conn:
                conn.execute(rollback_sql)

            with get_db_connection(operation="integration.sim_view.rollback_verify") as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT to_regclass('tpi.v_historial_simulaciones') AS view_regclass"
                    )
                    assert cur.fetchone()["view_regclass"] is None
                    # 007 and 008 views are untouched.
                    cur.execute("SELECT to_regclass('tpi.v_asignacion_auditoria') AS reg")
                    assert cur.fetchone()["reg"] is not None
                    cur.execute("SELECT to_regclass('tpi.v_historial_estado_lead') AS reg")
                    assert cur.fetchone()["reg"] is not None
                    # Audit data is never deleted.
                    cur.execute(
                        "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s", (lead_id,)
                    )
                    assert cur.fetchone()["total"] == audit_before
        finally:
            _recreate_view()
    finally:
        _cleanup_lead(lead_id)


def test_application_never_selects_auditoria_directly() -> None:
    repository_source = (_REPO_ROOT / "app" / "repositories" / "solicitud_repository.py").read_text(
        encoding="utf-8"
    )
    # The read path must go through the sanitized views only; INSERT into auditoria
    # is the allowed append-only write path and must not be a SELECT source.
    assert "FROM tpi.auditoria" not in repository_source

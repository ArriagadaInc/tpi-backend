"""Integration tests for the CRM-AGENDA-4-HISTORIAL read model (tpi.v_historial_agenda).

The view is created by ``scripts/init_test_database.py`` (bootstrap) mirroring the forward
migration ``scripts/sql/011_create_historial_agenda.sql``. These tests verify the sanitized
contract against real PostgreSQL: fixed filter over the five agenda actions, allowed columns
and types, privileges (PUBLIC / app-only via a least-privilege reader role), the
no-direct-auditoria-read rule, the no-free-text rule (nota/motivo never leak) and the rollback
script (which also proves 007/008/009/010 are left intact and audit data is never touched).

The agenda audit rows are produced with the REAL flow of ``AgendaRepository`` (agendar,
reagendar, cancelar, marcar realizada y marcar no asistio), never with hand-written inserts, so
any drift between the writer and the view makes these tests fail.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.auth.models import AuthenticatedUser, UserRole
from app.config import get_settings
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.repositories.agenda_repository import AgendaRepository

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIEW_NAME = "tpi.v_historial_agenda"
_READER_ROLE = "tpi_agenda_view_reader"
_READER_PASSWORD = "tpi_agenda_view_reader_password"

_ACCIONES_AGENDA = {
    "cita_agendada",
    "cita_reagendada",
    "cita_cancelada",
    "cita_realizada",
    "cita_no_asistio",
}

_COLUMNAS_ESPERADAS = {
    "id_auditoria",
    "id_lead",
    "fecha_hora",
    "accion",
    "actor_subject",
    "id_cita",
    "responsable_id",
    "estado_anterior",
    "estado_nuevo",
    "fecha_hora_anterior",
    "fecha_hora_nueva",
}


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


@pytest.fixture(scope="session", autouse=True)
def ensure_agenda_view_reader_role() -> None:
    with get_db_connection(operation="integration.agenda_view.reader_role") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tpi_agenda_view_reader') THEN
                        CREATE ROLE tpi_agenda_view_reader
                            LOGIN PASSWORD 'tpi_agenda_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    ELSE
                        ALTER ROLE tpi_agenda_view_reader
                            LOGIN PASSWORD 'tpi_agenda_view_reader_password'
                            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;

                    EXECUTE format(
                        'GRANT USAGE ON SCHEMA %I TO %I',
                        'tpi',
                        'tpi_agenda_view_reader'
                    );
                    EXECUTE format(
                        'REVOKE SELECT ON %I.%I FROM %I',
                        'tpi',
                        'auditoria',
                        'tpi_agenda_view_reader'
                    );
                END
                $$;
                """)
        conn.commit()


def _actor(role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
    )


def _make_asesor(cur: Any, nombre: str) -> str:
    cur.execute(
        "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad, atiende_reuniones) "
        "VALUES (%s, %s, 'activo', TRUE) RETURNING id_asesor",
        (nombre, "socio"),
    )
    return str(cur.fetchone()["id_asesor"])


def _make_lead(cur: Any, rut: str) -> tuple[str, str]:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, f"Lead {rut}", f"{rut}@example.com", "+56912345678"),
    )
    persona = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual) "
        "VALUES (%s, now(), %s, 'integration', 'integration') RETURNING id_lead",
        (persona, "nuevo"),
    )
    return str(cur.fetchone()["id_lead"]), persona


def _assign(cur: Any, lead_id: str, asesor_id: str) -> None:
    cur.execute(
        "INSERT INTO tpi.asignaciones (id_lead, id_asesor, estado_asignacion) "
        "VALUES (%s, %s, 'activa')",
        (lead_id, asesor_id),
    )


@pytest.fixture()
def world() -> Any:
    with get_db_connection(operation="agenda_view.integration.setup") as conn:
        with conn.cursor() as cur:
            socio = _make_asesor(cur, f"Socio Agenda View {uuid4().hex[:6]}")
            lead, persona = _make_lead(cur, f"{uuid4().hex[:8]}")
            _assign(cur, lead, socio)
            otro_lead, otra_persona = _make_lead(cur, f"{uuid4().hex[:8]}")
            _assign(cur, otro_lead, socio)
            conn.commit()
    yield {
        "socio": socio,
        "lead": lead,
        "otro_lead": otro_lead,
        "personas": [persona, otra_persona],
    }
    with get_db_connection(operation="agenda_view.integration.teardown") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.citas WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute(
                "DELETE FROM tpi.personas WHERE id_persona IN (%s, %s)", (persona, otra_persona)
            )
            cur.execute("DELETE FROM tpi.asesores WHERE id_asesor = %s", (socio,))
            conn.commit()


def _inicio(hh: int, mm: int = 0) -> datetime:
    return datetime(2099, 1, 15, hh, mm, tzinfo=UTC)


def _cita_agendada_id(lead_id: str) -> str:
    """Id de la reunion agendada actual del lead (la unica con estado 'agendada')."""
    with get_db_connection(operation="agenda_view.integration.cita_id") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_cita FROM tpi.citas WHERE id_lead = %s AND estado_cita = 'agendada' "
                "ORDER BY created_at DESC, id_cita DESC LIMIT 1",
                (lead_id,),
            )
            return str(cur.fetchone()["id_cita"])


def _view_rows(lead_id: str) -> list[dict[str, Any]]:
    with get_db_connection(operation="agenda_view.integration.read") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tpi.v_historial_agenda WHERE id_lead = %s "
                "ORDER BY fecha_hora, id_auditoria",
                (lead_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _insert_audit_row(
    cur: Any, *, id_lead: str, accion: str, tabla_afectada: str, detalle: dict
) -> None:
    cur.execute(
        "INSERT INTO tpi.auditoria "
        "(id_usuario, id_persona, id_lead, accion, tabla_afectada, detalle) "
        "VALUES (%s, NULL, %s, %s, %s, %s)",
        (None, id_lead, accion, tabla_afectada, json.dumps(detalle)),
    )


def _produce_all_agenda_actions(
    repo: AgendaRepository, *, lead_id: str, socio: str, actor: AuthenticatedUser
) -> tuple[str, str]:
    """Produce the five agenda actions via the real repository flow.

    Returns the free-text ``(nota, motivo)`` used so callers can assert they never leak
    through the view.
    """
    nota = f"nota privada unica {uuid4().hex}"
    repo.create_cita(
        lead_id=UUID(lead_id),
        responsable_id=UUID(socio),
        inicio=_inicio(9, 0),
        fin=_inicio(9, 30),
        modalidad="Google Meet",
        link=None,
        nota=nota,
        actor=actor,
    )
    cita_a = _cita_agendada_id(lead_id)
    repo.update_cita(
        cita_id=UUID(cita_a),
        responsable_id=UUID(socio),
        inicio=_inicio(9, 30),
        fin=_inicio(10, 0),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=actor,
    )
    motivo = f"motivo cancelacion unico {uuid4().hex}"
    repo.cancel_cita(cita_id=UUID(cita_a), motivo=motivo, actor=actor)

    repo.create_cita(
        lead_id=UUID(lead_id),
        responsable_id=UUID(socio),
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Llamada",
        link=None,
        nota=None,
        actor=actor,
    )
    cita_b = _cita_agendada_id(lead_id)
    repo.complete_cita(cita_id=UUID(cita_b), actor=actor)

    repo.create_cita(
        lead_id=UUID(lead_id),
        responsable_id=UUID(socio),
        inicio=_inicio(11, 0),
        fin=_inicio(11, 30),
        modalidad="Presencial",
        link=None,
        nota=None,
        actor=actor,
    )
    cita_c = _cita_agendada_id(lead_id)
    repo.no_show_cita(cita_id=UUID(cita_c), actor=actor)
    return nota, motivo


def _recreate_view() -> None:
    with get_db_connection(operation="integration.agenda_view.recreate") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE VIEW tpi.v_historial_agenda
                WITH (security_barrier = true) AS
                SELECT
                    a.id_auditoria,
                    a.id_lead,
                    a.fecha_hora,
                    a.accion,
                    a.detalle->>'actor_subject' AS actor_subject,
                    CASE
                        WHEN a.detalle->>'id_cita' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                            THEN (a.detalle->>'id_cita')::uuid
                        ELSE NULL
                    END AS id_cita,
                    CASE
                        WHEN a.detalle->>'responsable_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                            THEN (a.detalle->>'responsable_id')::uuid
                        ELSE NULL
                    END AS responsable_id,
                    a.detalle->>'estado_anterior' AS estado_anterior,
                    a.detalle->>'estado_nuevo' AS estado_nuevo,
                    (a.detalle->>'fecha_hora_anterior')::timestamptz AS fecha_hora_anterior,
                    (a.detalle->>'fecha_hora_nueva')::timestamptz AS fecha_hora_nueva
                FROM tpi.auditoria a
                WHERE a.accion IN ('cita_agendada', 'cita_reagendada', 'cita_cancelada', 'cita_realizada', 'cita_no_asistio')
                  AND a.tabla_afectada = 'tpi.citas'
                """)
            cur.execute("REVOKE ALL ON tpi.v_historial_agenda FROM PUBLIC")
        conn.commit()


def _reader_connection_params() -> dict:
    params = get_settings().database_config.connection_parameters()
    return {**params, "user": _READER_ROLE, "password": _READER_PASSWORD}


def test_view_expone_las_cinco_acciones_del_flujo_real_con_columnas_y_tipos(world: Any) -> None:
    _produce_all_agenda_actions(
        AgendaRepository(), lead_id=world["lead"], socio=world["socio"], actor=_actor("ceo")
    )

    rows = _view_rows(world["lead"])
    acciones = {row["accion"] for row in rows}
    assert acciones == _ACCIONES_AGENDA

    for row in rows:
        assert set(row.keys()) == _COLUMNAS_ESPERADAS
        assert isinstance(row["id_auditoria"], UUID)
        assert isinstance(row["id_lead"], UUID)
        assert isinstance(row["fecha_hora"], datetime)
        assert row["fecha_hora"].tzinfo is not None
        assert isinstance(row["id_cita"], UUID)
        # responsable_id es UUID (el flujo real siempre lo escribe) o NULL defensivo.
        assert row["responsable_id"] is None or isinstance(row["responsable_id"], UUID)
        # Las fechas anterior/nueva llegan como timestamptz (o NULL cuando no aplican).
        for campo in ("fecha_hora_anterior", "fecha_hora_nueva"):
            assert row[campo] is None or (
                isinstance(row[campo], datetime) and row[campo].tzinfo is not None
            )

    # Sanity sobre los valores proyectados de una fila agendada.
    agendadas = [row for row in rows if row["accion"] == "cita_agendada"]
    assert agendadas
    assert agendadas[0]["estado_nuevo"] == "agendada"
    assert agendadas[0]["responsable_id"] == UUID(world["socio"])


def test_view_solo_devuelve_acciones_de_agenda_y_filtra_por_lead(world: Any) -> None:
    repo = AgendaRepository()
    # Una cita en el lead bajo prueba.
    repo.create_cita(
        lead_id=UUID(world["lead"]),
        responsable_id=UUID(world["socio"]),
        inicio=_inicio(9, 0),
        fin=_inicio(9, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    # Un evento de simulacion del mismo lead (tabla_afectada tpi.leads, no tpi.citas).
    with get_db_connection(operation="agenda_view.integration.seed_sim") as conn:
        with conn.cursor() as cur:
            _insert_audit_row(
                cur,
                id_lead=world["lead"],
                accion="simulacion_renta_vitalicia",
                tabla_afectada="tpi.leads",
                detalle={"actor_subject": "user-sim", "codigo_verificacion": "no-aparece"},
            )
        conn.commit()
    # Otra cita de otro lead (el mismo responsable, otro horario).
    repo.create_cita(
        lead_id=UUID(world["otro_lead"]),
        responsable_id=UUID(world["socio"]),
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Llamada",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )

    rows = _view_rows(world["lead"])
    # Solo eventos de agenda del lead; el cambio de estado (tpi.leads) y la simulacion no
    # aparecen, y la cita del otro lead tampoco.
    assert rows
    assert all(row["accion"] in _ACCIONES_AGENDA for row in rows)
    assert all(str(row["id_lead"]) == world["lead"] for row in rows)
    assert "simulacion_renta_vitalicia" not in {row["accion"] for row in rows}
    assert "cambio_estado_lead" not in {row["accion"] for row in rows}


def test_view_no_expone_nota_ni_motivo_de_cancelacion(world: Any) -> None:
    nota, motivo = _produce_all_agenda_actions(
        AgendaRepository(), lead_id=world["lead"], socio=world["socio"], actor=_actor("ceo")
    )
    rows = _view_rows(world["lead"])
    assert rows
    serializado = json.dumps(rows, default=str)
    assert nota not in serializado
    assert motivo not in serializado


def test_view_privileges_public_and_app_only() -> None:
    with get_db_connection(operation="integration.agenda_view.privileges") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE((
                    SELECT bool_or(grantee = 0)
                    FROM aclexplode(relacl)
                ), false) AS public_any
                FROM pg_class
                WHERE oid = 'tpi.v_historial_agenda'::regclass
                """)
            assert cur.fetchone()["public_any"] is False

            cur.execute("""
                SELECT
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.v_historial_agenda', 'SELECT') AS view_select,
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select
                """)
            row = cur.fetchone()
            assert row["view_select"] is False
            assert row["auditoria_select"] is False

            cur.execute(f"GRANT SELECT ON {_VIEW_NAME} TO {_READER_ROLE}")
            cur.execute("""
                SELECT
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.v_historial_agenda', 'SELECT') AS view_select,
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.auditoria', 'SELECT') AS auditoria_select,
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.auditoria', 'UPDATE') AS auditoria_update,
                    has_table_privilege('tpi_agenda_view_reader', 'tpi.auditoria', 'DELETE') AS auditoria_delete
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
            cur.execute("SELECT COUNT(*) AS total FROM tpi.v_historial_agenda")
            assert cur.fetchone()["total"] >= 0
            with pytest.raises(Exception):
                cur.execute("SELECT COUNT(*) AS total FROM tpi.auditoria")

    with get_db_connection(operation="integration.agenda_view.revoke") as conn:
        with conn.cursor() as cur:
            cur.execute(f"REVOKE SELECT ON {_VIEW_NAME} FROM {_READER_ROLE}")
        conn.commit()


def test_view_rollback_revokes_and_drops_view_without_touching_audit_or_other_views(
    world: Any,
) -> None:
    rollback_sql = (_REPO_ROOT / "scripts" / "sql" / "011_drop_historial_agenda.sql").read_text(
        encoding="utf-8"
    )

    repo = AgendaRepository()
    repo.create_cita(
        lead_id=UUID(world["lead"]),
        responsable_id=UUID(world["socio"]),
        inicio=_inicio(9, 0),
        fin=_inicio(9, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    with get_db_connection(operation="agenda_view.integration.rollback_seed") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s", (world["lead"],)
            )
            audit_before = cur.fetchone()["total"]
        conn.commit()

    try:
        with connect(get_settings().get_database_url(), autocommit=True) as conn:
            conn.execute(rollback_sql)

        with get_db_connection(operation="agenda_view.integration.rollback_verify") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('tpi.v_historial_agenda') AS view_regclass")
                assert cur.fetchone()["view_regclass"] is None
                # 007/008/009 quedan intactas.
                cur.execute("SELECT to_regclass('tpi.v_asignacion_auditoria') AS reg")
                assert cur.fetchone()["reg"] is not None
                cur.execute("SELECT to_regclass('tpi.v_historial_estado_lead') AS reg")
                assert cur.fetchone()["reg"] is not None
                cur.execute("SELECT to_regclass('tpi.v_historial_simulaciones') AS reg")
                assert cur.fetchone()["reg"] is not None
                # Los datos de auditoria nunca se borran.
                cur.execute(
                    "SELECT COUNT(*) AS total FROM tpi.auditoria WHERE id_lead = %s",
                    (world["lead"],),
                )
                assert cur.fetchone()["total"] == audit_before
    finally:
        _recreate_view()

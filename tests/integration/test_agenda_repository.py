"""Pruebas de integración del repositorio de la agenda (requieren PostgreSQL).

Verifican que las escrituras son transaccionales (cita + estado del lead + auditoria en
una sola operación), que las restricciones de superposición y de una-agendada-por-lead se
traducen a errores de dominio claros, y que la lectura del calendario entrega los datos
que el servicio recorta (nombre y dueño de cartera). Se omiten sin base de datos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.models.agenda import (
    AgendaConflictError,
    AgendaNotFoundError,
    AgendaValidationError,
)
from app.repositories.agenda_repository import AgendaRepository

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _actor(role: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
    )


def _make_asesor(cur: Any, nombre: str, rol: str = "asesor") -> str:
    cur.execute(
        "INSERT INTO tpi.asesores (nombre, rol, estado_disponibilidad, atiende_reuniones) "
        "VALUES (%s, %s, 'activo', TRUE) RETURNING id_asesor",
        (nombre, rol),
    )
    return str(cur.fetchone()["id_asesor"])


def _make_lead(cur: Any, rut: str, estado: str = "nuevo") -> tuple[str, str]:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, f"Lead {rut}", f"{rut}@example.com", "+56912345678"),
    )
    persona = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual) "
        "VALUES (%s, now(), %s, 'integration', 'integration') RETURNING id_lead",
        (persona, estado),
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
    with get_db_connection(operation="agenda.integration.setup") as conn:
        with conn.cursor() as cur:
            socio = _make_asesor(cur, f"Socio Agenda {uuid4().hex[:6]}", rol="socio")
            coordinador = _make_asesor(cur, f"Coord Agenda {uuid4().hex[:6]}", rol="asesor")
            lead, persona = _make_lead(cur, f"{uuid4().hex[:8]}", estado="nuevo")
            _assign(cur, lead, socio)
            otro_lead, otra_persona = _make_lead(cur, f"{uuid4().hex[:8]}", estado="nuevo")
            _assign(cur, otro_lead, socio)
            conn.commit()
    yield {
        "socio": socio,
        "coordinador": coordinador,
        "lead": lead,
        "otro_lead": otro_lead,
        "personas": [persona, otra_persona],
    }
    with get_db_connection(operation="agenda.integration.teardown") as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tpi.auditoria WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.citas WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute("DELETE FROM tpi.leads WHERE id_lead IN (%s, %s)", (lead, otro_lead))
            cur.execute(
                "DELETE FROM tpi.personas WHERE id_persona IN (%s, %s)", (persona, otra_persona)
            )
            cur.execute(
                "DELETE FROM tpi.asesores WHERE id_asesor IN (%s, %s)", (socio, coordinador)
            )
            conn.commit()


def _inicio(hh: int, mm: int = 0) -> datetime:
    return datetime(2099, 1, 15, hh, mm, tzinfo=UTC)


def _audit_rows(lead_id: str) -> list[dict[str, Any]]:
    with get_db_connection(operation="agenda.integration.audit") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT accion, tabla_afectada, id_lead, detalle FROM tpi.auditoria "
                "WHERE id_lead = %s ORDER BY fecha_hora, id_auditoria",
                (lead_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def _cita_id(lead_id: str) -> str:
    with get_db_connection(operation="agenda.integration.cita_id") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_cita FROM tpi.citas WHERE id_lead = %s", (lead_id,))
            return str(cur.fetchone()["id_cita"])


def test_create_cita_actualiza_lead_y_audita(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    with get_db_connection(operation="agenda.integration.verify_create") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado_cita FROM tpi.citas WHERE id_lead = %s", (world["lead"],))
            assert cur.fetchone()["estado_cita"] == "agendada"
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (world["lead"],))
            assert cur.fetchone()["estado_lead"] == "reunion_agendada"

    rows = _audit_rows(world["lead"])
    acciones = {r["accion"]: r for r in rows}
    assert "cita_agendada" in acciones
    assert "cambio_estado_lead" in acciones
    assert acciones["cita_agendada"]["tabla_afectada"] == "tpi.citas"
    detalle = acciones["cita_agendada"]["detalle"]
    assert isinstance(detalle, dict)
    assert detalle.get("responsable_id") == world["socio"]
    assert detalle.get("estado_nuevo") == "agendada"
    # El detalle no lleva nombre ni datos personales del lead.
    assert "Lead" not in str(detalle)


@pytest.mark.parametrize(
    "estado", ["cerrado", "perdido", "no_interesado", "datos_erroneos", "no_contactado"]
)
def test_create_cita_rechaza_lead_inactivo(world: Any, estado: str) -> None:
    repo = AgendaRepository()
    with get_db_connection(operation="agenda.integration.inactive.setup") as conn:
        with conn.cursor() as cur:
            lead, persona = _make_lead(cur, f"{uuid4().hex[:8]}", estado=estado)
            _assign(cur, lead, world["socio"])
            conn.commit()
    try:
        with pytest.raises(AgendaValidationError):
            repo.create_cita(
                lead_id=lead,
                responsable_id=world["socio"],
                inicio=_inicio(10, 0),
                fin=_inicio(10, 30),
                modalidad="Google Meet",
                link=None,
                nota=None,
                actor=_actor("ceo"),
            )
        with get_db_connection(operation="agenda.integration.inactive.verify") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM tpi.citas WHERE id_lead = %s", (lead,))
                assert cur.fetchone()["n"] == 0
                cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (lead,))
                assert cur.fetchone()["estado_lead"] == estado
                cur.execute("SELECT COUNT(*) AS n FROM tpi.auditoria WHERE id_lead = %s", (lead,))
                assert cur.fetchone()["n"] == 0
    finally:
        with get_db_connection(operation="agenda.integration.inactive.teardown") as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (lead,))
                cur.execute("DELETE FROM tpi.citas WHERE id_lead = %s", (lead,))
                cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (lead,))
                cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead,))
                cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (persona,))
                conn.commit()


def test_update_cita_rechaza_lead_inactivo(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])
    with get_db_connection(operation="agenda.integration.inactive_reagendar.setup") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tpi.leads SET estado_lead = 'cerrado' WHERE id_lead = %s", (world["lead"],)
            )
            conn.commit()

    with pytest.raises(AgendaValidationError):
        repo.update_cita(
            cita_id=cita_id,
            responsable_id=world["coordinador"],
            inicio=_inicio(15, 0),
            fin=_inicio(15, 45),
            modalidad="Presencial",
            link=None,
            nota=None,
            actor=_actor("ceo"),
        )

    with get_db_connection(operation="agenda.integration.inactive_reagendar.verify") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT estado_cita, fecha_hora, id_asesor FROM tpi.citas WHERE id_cita = %s",
                (cita_id,),
            )
            row = cur.fetchone()
            assert row["estado_cita"] == "agendada"
            assert row["fecha_hora"] == _inicio(10, 0)
            assert str(row["id_asesor"]) == world["socio"]


def test_superposicion_mismo_responsable_se_rechaza(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    with pytest.raises(AgendaConflictError):
        repo.create_cita(
            lead_id=world["otro_lead"],
            responsable_id=world["socio"],
            inicio=_inicio(10, 15),
            fin=_inicio(10, 45),
            modalidad="Llamada",
            link=None,
            nota=None,
            actor=_actor("ceo"),
        )


def test_lead_no_admite_dos_agendadas(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    with pytest.raises(AgendaValidationError):
        repo.create_cita(
            lead_id=world["lead"],
            responsable_id=world["coordinador"],
            inicio=_inicio(14, 0),
            fin=_inicio(14, 30),
            modalidad="Google Meet",
            link=None,
            nota=None,
            actor=_actor("ceo"),
        )


def test_cancelar_devuelve_lead_en_seguimiento(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])

    repo.cancel_cita(cita_id=cita_id, motivo="Lead no pudo asistir", actor=_actor("ceo"))

    with get_db_connection(operation="agenda.integration.verify_cancel") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT estado_cita, motivo_cancelacion FROM tpi.citas WHERE id_cita = %s",
                (cita_id,),
            )
            row = cur.fetchone()
            assert row["estado_cita"] == "cancelada"
            assert row["motivo_cancelacion"] == "Lead no pudo asistir"
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (world["lead"],))
            assert cur.fetchone()["estado_lead"] == "en_seguimiento"
    assert "cita_cancelada" in {r["accion"] for r in _audit_rows(world["lead"])}


def test_realizada_pasa_lead_reunion_realizada(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])

    repo.complete_cita(cita_id=cita_id, actor=_actor("ceo"))

    with get_db_connection(operation="agenda.integration.verify_complete") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado_cita FROM tpi.citas WHERE id_cita = %s", (cita_id,))
            assert cur.fetchone()["estado_cita"] == "realizada"
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (world["lead"],))
            assert cur.fetchone()["estado_lead"] == "reunion_realizada"
    assert "cita_realizada" in {r["accion"] for r in _audit_rows(world["lead"])}


def test_no_asistio_devuelve_lead_en_seguimiento(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])

    repo.no_show_cita(cita_id=cita_id, actor=_actor("ceo"))

    with get_db_connection(operation="agenda.integration.verify_no_show") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado_cita FROM tpi.citas WHERE id_cita = %s", (cita_id,))
            assert cur.fetchone()["estado_cita"] == "no_asistio"
            cur.execute("SELECT estado_lead FROM tpi.leads WHERE id_lead = %s", (world["lead"],))
            assert cur.fetchone()["estado_lead"] == "en_seguimiento"
    assert "cita_no_asistio" in {r["accion"] for r in _audit_rows(world["lead"])}


def test_list_citas_devuelve_nombre_y_dueno(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link="https://meet.example/abc",
        nota=None,
        actor=_actor("ceo"),
    )
    rows = repo.list_citas(desde=_inicio(9, 0), hasta=_inicio(11, 0))
    assert len(rows) == 1
    row = rows[0]
    assert str(row["lead_nombre"]).startswith("Lead ")
    assert row["link_reunion"] == "https://meet.example/abc"
    assert str(row["lead_asesor_id"]) == world["socio"]


def test_reagendar_actualiza_la_misma_cita(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])

    repo.update_cita(
        cita_id=cita_id,
        responsable_id=world["coordinador"],
        inicio=_inicio(15, 0),
        fin=_inicio(15, 45),
        modalidad="Presencial",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )

    with get_db_connection(operation="agenda.integration.verify_reagendar") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT estado_cita, canal, id_asesor, fecha_hora, fecha_hora_fin "
                "FROM tpi.citas WHERE id_cita = %s",
                (cita_id,),
            )
            row = cur.fetchone()
            assert row["estado_cita"] == "agendada"
            assert row["canal"] == "Presencial"
            assert str(row["id_asesor"]) == world["coordinador"]
            assert row["fecha_hora"] == _inicio(15, 0)
            assert row["fecha_hora_fin"] == _inicio(15, 45)
    assert "cita_reagendada" in {r["accion"] for r in _audit_rows(world["lead"])}


def test_read_responsables_y_responsable_por_id(world: Any) -> None:
    repo = AgendaRepository()
    responsables = repo.get_responsables()
    ids = {str(r["id_asesor"]) for r in responsables}
    assert world["socio"] in ids
    assert world["coordinador"] in ids

    socio = repo.get_responsable_by_id(UUID(world["socio"]))
    assert socio is not None
    assert socio["rol"] == "socio"
    assert repo.get_responsable_by_id(uuid4()) is None


def test_get_cita_by_id_y_for_lead(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])
    by_id = repo.get_cita_by_id(cita_id)
    assert by_id is not None
    assert by_id["estado_cita"] == "agendada"
    assert repo.get_cita_by_id(uuid4()) is None

    for_lead = repo.get_cita_for_lead(world["lead"])
    assert for_lead is not None
    assert str(for_lead["id_lead"]) == world["lead"]
    assert repo.get_cita_for_lead(uuid4()) is None


def test_lead_active_assignment_owner(world: Any) -> None:
    repo = AgendaRepository()
    assert str(repo.lead_active_assignment_owner(UUID(world["lead"]))) == world["socio"]
    assert repo.lead_active_assignment_owner(uuid4()) is None


def test_cancelar_reunion_no_agendada_se_rechaza(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])
    repo.cancel_cita(cita_id=cita_id, motivo="ya", actor=_actor("ceo"))

    with pytest.raises(AgendaValidationError):
        repo.cancel_cita(cita_id=cita_id, motivo="otra vez", actor=_actor("ceo"))


def test_reagendar_reunion_inexistente_es_404(world: Any) -> None:
    repo = AgendaRepository()
    with pytest.raises(AgendaNotFoundError):
        repo.update_cita(
            cita_id=uuid4(),
            responsable_id=world["socio"],
            inicio=_inicio(10, 0),
            fin=_inicio(10, 30),
            modalidad="Google Meet",
            link=None,
            nota=None,
            actor=_actor("ceo"),
        )


def test_completar_reunion_no_agendada_se_rechaza(world: Any) -> None:
    repo = AgendaRepository()
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_actor("ceo"),
    )
    cita_id = _cita_id(world["lead"])
    repo.complete_cita(cita_id=cita_id, actor=_actor("ceo"))

    with pytest.raises(AgendaValidationError):
        repo.complete_cita(cita_id=cita_id, actor=_actor("ceo"))


def _cita_agendada_id(lead_id: str) -> str:
    """Id de la reunion agendada actual del lead (la unica con estado 'agendada')."""
    with get_db_connection(operation="agenda.integration.cita_agendada_id") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_cita FROM tpi.citas WHERE id_lead = %s AND estado_cita = 'agendada' "
                "ORDER BY created_at DESC, id_cita DESC LIMIT 1",
                (lead_id,),
            )
            return str(cur.fetchone()["id_cita"])


def test_get_lead_agenda_events_devuelve_cinco_acciones_con_responsable(world: Any) -> None:
    repo = AgendaRepository()
    with get_db_connection(operation="agenda.integration.nombre_socio") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nombre FROM tpi.asesores WHERE id_asesor = %s", (world["socio"],))
            nombre_socio = str(cur.fetchone()["nombre"])

    actor = _actor("ceo")
    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(9, 0),
        fin=_inicio(9, 30),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=actor,
    )
    cita_a = _cita_agendada_id(world["lead"])
    repo.update_cita(
        cita_id=cita_a,
        responsable_id=world["socio"],
        inicio=_inicio(9, 30),
        fin=_inicio(10, 0),
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=actor,
    )
    repo.cancel_cita(cita_id=cita_a, motivo="motivo de prueba", actor=actor)

    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(10, 0),
        fin=_inicio(10, 30),
        modalidad="Llamada",
        link=None,
        nota=None,
        actor=actor,
    )
    cita_b = _cita_agendada_id(world["lead"])
    repo.complete_cita(cita_id=cita_b, actor=actor)

    repo.create_cita(
        lead_id=world["lead"],
        responsable_id=world["socio"],
        inicio=_inicio(11, 0),
        fin=_inicio(11, 30),
        modalidad="Presencial",
        link=None,
        nota=None,
        actor=actor,
    )
    cita_c = _cita_agendada_id(world["lead"])
    repo.no_show_cita(cita_id=cita_c, actor=actor)

    eventos = repo.get_lead_agenda_events(UUID(world["lead"]))
    acciones = {e["accion"] for e in eventos}
    assert acciones == {
        "cita_agendada",
        "cita_reagendada",
        "cita_cancelada",
        "cita_realizada",
        "cita_no_asistio",
    }
    # Cada evento trae el nombre del responsable por el LEFT JOIN con tpi.asesores.
    assert all(e["responsable_nombre"] == nombre_socio for e in eventos)
    # Orden estable: fecha_hora DESC, id_auditoria DESC.
    fechas = [e["fecha_hora"] for e in eventos]
    assert fechas == sorted(fechas, reverse=True)

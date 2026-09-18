"""Integration tests for the executive dashboard aggregate repository.

These tests run against real PostgreSQL and verify every metric definition with
controlled data: zero data, single lead, unassigned leads, historical/inactive
assignments, unknown states, individual and combined filters, inclusive date
boundaries, America/Santiago timezone, daily/weekly/monthly granularity,
fan-out-free counts, active portfolio, staleness, age buckets, time-to-assignment,
first management, funnel pre/post-cutover, and representative volume with EXPLAIN.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.models.executive_dashboard import DashboardFilters
from app.repositories.executive_dashboard_repository import ExecutiveDashboardRepository

pytestmark = pytest.mark.integration

_TZ = ZoneInfo("America/Santiago")
_REPO = ExecutiveDashboardRepository()


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _now() -> datetime:
    return datetime.now(_TZ)


def _marker() -> str:
    return f"h334_dash_{uuid4().hex[:12]}"


def _make_lead(
    cur,
    *,
    marker: str,
    rut: str,
    estado: str = "nuevo",
    fecha_ingreso: datetime,
    origen: str | None = None,
    fuente: str | None = None,
    afp_id: UUID | None = None,
    comentarios: str | None = None,
) -> str:
    cur.execute(
        "INSERT INTO tpi.personas (rut, nombre_completo, email, telefono) "
        "VALUES (%s, %s, %s, %s) RETURNING id_persona",
        (rut, "Integration Dashboard", f"{rut}@example.com", "+56912345678"),
    )
    persona_id = str(cur.fetchone()["id_persona"])
    cur.execute(
        "INSERT INTO tpi.leads "
        "(id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual, afp_id, comentarios) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id_lead",
        (
            persona_id,
            fecha_ingreso,
            estado,
            origen or marker,
            fuente or "integration",
            str(afp_id) if afp_id else None,
            comentarios,
        ),
    )
    return str(cur.fetchone()["id_lead"])


def _make_asesor(cur, nombre: str) -> str:
    cur.execute(
        "INSERT INTO tpi.asesores (nombre, email, rol, estado_disponibilidad) "
        "VALUES (%s, %s, 'asesor', 'activo') RETURNING id_asesor",
        (nombre, f"{nombre.replace(' ', '').casefold()}@example.com"),
    )
    return str(cur.fetchone()["id_asesor"])


def _assign(cur, id_lead: str, id_asesor: str, fecha: datetime, estado: str = "activa") -> None:
    cur.execute(
        "INSERT INTO tpi.asignaciones (id_lead, id_asesor, fecha_asignacion, estado_asignacion) "
        "VALUES (%s, %s, %s, %s)",
        (id_lead, id_asesor, fecha, estado),
    )


def _state_change(cur, id_lead: str, anterior: str, nuevo: str, fecha: datetime) -> None:
    cur.execute(
        "INSERT INTO tpi.auditoria (id_lead, accion, tabla_afectada, fecha_hora, detalle) "
        "VALUES (%s, 'cambio_estado_lead', 'tpi.leads', %s, %s)",
        (
            id_lead,
            fecha,
            json.dumps(
                {
                    "actor_subject": "integration",
                    "estado_anterior": anterior,
                    "estado_nuevo": nuevo,
                }
            ),
        ),
    )


def _note_header(fecha: datetime) -> str:
    return fecha.strftime("%d/%m/%Y %H:%M")


def _cleanup(cur, lead_ids: list[str], asesor_ids: list[str] | None = None) -> None:
    for lead_id in lead_ids:
        cur.execute("SELECT id_persona FROM tpi.leads WHERE id_lead = %s", (lead_id,))
        row = cur.fetchone()
        cur.execute("DELETE FROM tpi.auditoria WHERE id_lead = %s", (lead_id,))
        cur.execute("DELETE FROM tpi.asignaciones WHERE id_lead = %s", (lead_id,))
        cur.execute("DELETE FROM tpi.consentimientos WHERE id_lead = %s", (lead_id,))
        cur.execute("DELETE FROM tpi.leads WHERE id_lead = %s", (lead_id,))
        if row is not None:
            cur.execute("DELETE FROM tpi.personas WHERE id_persona = %s", (str(row["id_persona"]),))
    for asesor_id in asesor_ids or []:
        cur.execute("DELETE FROM tpi.asesores WHERE id_asesor = %s", (asesor_id,))


def _filters(marker: str, **kwargs) -> DashboardFilters:
    return DashboardFilters.from_raw(origen=marker, **kwargs)


def test_zero_data_returns_empty_metrics() -> None:
    filters = _filters("no_such_marker_anywhere")
    kpis = _REPO.get_kpi_snapshot(filters)
    assert kpis == {"total_leads": 0, "cartera_activa": 0, "sin_asignar": 0}
    assert _REPO.get_estancados(filters) == 0
    assert _REPO.get_casos_por_estado(filters) == []
    assert _REPO.get_cartera_por_asesor(filters) == []


def test_single_lead_metrics() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="11111111-1", fecha_ingreso=_now()))
            conn.commit()
    try:
        kpis = _REPO.get_kpi_snapshot(_filters(marker))
        assert kpis["total_leads"] == 1
        assert kpis["cartera_activa"] == 1
        assert kpis["sin_asignar"] == 1
        casos = _REPO.get_casos_por_estado(_filters(marker))
        assert casos == [{"estado": "nuevo", "n": 1}]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_leads_sin_asesor_have_own_bucket() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="22222222-2", fecha_ingreso=_now()))
            asesor_ids.append(_make_asesor(cur, "Asesor Sin Asignar Test"))
            conn.commit()
    try:
        rows = _REPO.get_cartera_por_asesor(_filters(marker))
        assert any(row["id_asesor"] is None for row in rows)
        unassigned = next(row for row in rows if row["id_asesor"] is None)
        assert unassigned["cartera_total"] == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_inactive_assignments_do_not_count_and_fanout_is_safe() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor_a = _make_asesor(cur, "Asesor Activo Test")
            asesor_ids.append(asesor_a)

            # Lead with an inactive assignment only -> unassigned bucket.
            lead_ids.append(_make_lead(cur, marker=marker, rut="33333333-3", fecha_ingreso=_now()))
            _assign(cur, lead_ids[-1], asesor_a, _now() - timedelta(days=3), estado="inactiva")

            # Lead with inactive + active assignments -> counted once under active asesor.
            lead_ids.append(_make_lead(cur, marker=marker, rut="44444444-4", fecha_ingreso=_now()))
            _assign(cur, lead_ids[-1], asesor_a, _now() - timedelta(days=3), estado="inactiva")
            _assign(cur, lead_ids[-1], asesor_a, _now() - timedelta(days=1), estado="activa")
            conn.commit()
    try:
        rows = _REPO.get_cartera_por_asesor(_filters(marker))
        by_id = {str(row["id_asesor"]) if row["id_asesor"] else None: row for row in rows}
        assert by_id[asesor_a]["cartera_total"] == 1  # not duplicated by fan-out
        assert by_id[None]["cartera_total"] == 1
        assert _REPO.get_kpi_snapshot(_filters(marker))["total_leads"] == 2
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_unknown_states_are_preserved() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut="55555555-5", estado="estado_raro", fecha_ingreso=_now()
                )
            )
            conn.commit()
    try:
        casos = _REPO.get_casos_por_estado(_filters(marker))
        assert casos == [{"estado": "estado_raro", "n": 1}]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_cartera_activa_excludes_closed_states() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="66666666-6", fecha_ingreso=_now()))
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut="77777777-7", estado="cerrado", fecha_ingreso=_now()
                )
            )
            conn.commit()
    try:
        kpis = _REPO.get_kpi_snapshot(_filters(marker))
        assert kpis["total_leads"] == 2
        assert kpis["cartera_activa"] == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_individual_and_combined_filters() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="88888888-8",
                    estado="nuevo",
                    fecha_ingreso=_now(),
                    fuente="fuente_a",
                )
            )
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="99999999-9",
                    estado="cerrado",
                    fecha_ingreso=_now(),
                    fuente="fuente_b",
                )
            )
            conn.commit()
    try:
        assert _REPO.get_kpi_snapshot(_filters(marker, estado="nuevo"))["total_leads"] == 1
        assert _REPO.get_kpi_snapshot(_filters(marker, fuente="fuente_a"))["total_leads"] == 1
        assert (
            _REPO.get_kpi_snapshot(_filters(marker, estado="nuevo", fuente="fuente_b"))[
                "total_leads"
            ]
            == 0
        )
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_inclusive_date_boundaries() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    base = datetime(2026, 9, 10, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="10101010-0",
                    fecha_ingreso=datetime(2026, 9, 1, 0, 0, tzinfo=_TZ),
                )
            )
            lead_ids.append(_make_lead(cur, marker=marker, rut="10101010-1", fecha_ingreso=base))
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="10101010-2",
                    fecha_ingreso=datetime(2026, 9, 20, 0, 0, tzinfo=_TZ),
                )
            )
            conn.commit()
    try:
        filters = _filters(marker, fecha_desde="2026-09-10", fecha_hasta="2026-09-10")
        assert _REPO.get_leads_ingresados(filters) == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_evolucion_granularity_and_santiago_timezone() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    # 2026-09-01 02:00 UTC == 2026-08-31 22:00 America/Santiago (UTC-4).
    lead_utc_night = datetime(2026, 9, 1, 2, 0, tzinfo=ZoneInfo("UTC"))
    lead_local_day = datetime(2026, 9, 2, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(cur, marker=marker, rut="11111111-a", fecha_ingreso=lead_utc_night)
            )
            lead_ids.append(
                _make_lead(cur, marker=marker, rut="11111111-b", fecha_ingreso=lead_local_day)
            )
            conn.commit()
    try:
        diaria = _REPO.get_evolucion(
            _filters(
                marker, fecha_desde="2026-08-31", fecha_hasta="2026-09-05", granularidad="diaria"
            )
        )
        by_day = {row["bucket"].strftime("%Y-%m-%d"): row["n"] for row in diaria}
        # The UTC-02:00 lead falls on 2026-08-31 in Santiago, not 2026-09-01.
        assert by_day["2026-08-31"] == 1
        assert by_day["2026-09-02"] == 1

        semanal = _REPO.get_evolucion(
            _filters(
                marker, fecha_desde="2026-08-31", fecha_hasta="2026-09-05", granularidad="semanal"
            )
        )
        assert sum(row["n"] for row in semanal) == 2

        mensual = _REPO.get_evolucion(
            _filters(
                marker, fecha_desde="2026-08-01", fecha_hasta="2026-09-30", granularidad="mensual"
            )
        )
        assert sum(row["n"] for row in mensual) == 2
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_estancamiento_counts_only_no_recent_movement() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    old = _now() - timedelta(days=10)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Stuck: only old fecha_ingreso, no movement.
            lead_ids.append(_make_lead(cur, marker=marker, rut="12121212-1", fecha_ingreso=old))
            # Recent note -> not stuck.
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="12121212-2",
                    fecha_ingreso=old,
                    comentarios=f"[{_note_header(_now() - timedelta(days=1))}] Autor\nnota",
                )
            )
            # Recent assignment -> not stuck.
            asesor_ids.append(_make_asesor(cur, "Asesor Movimiento Test"))
            lead_ids.append(_make_lead(cur, marker=marker, rut="12121212-3", fecha_ingreso=old))
            _assign(cur, lead_ids[-1], asesor_ids[-1], _now() - timedelta(days=1))
            # Recent state change -> not stuck.
            lead_ids.append(_make_lead(cur, marker=marker, rut="12121212-4", fecha_ingreso=old))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", _now() - timedelta(days=2))
            conn.commit()
    try:
        assert _REPO.get_estancados(_filters(marker)) == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_note_timestamp_is_interpreted_in_santiago_timezone() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    ingreso = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="17171717-1",
                    fecha_ingreso=ingreso,
                    comentarios="Solicitud original\n\n[01/09/2026 20:00] Autor\nnota",
                )
            )
            conn.commit()
    try:
        tiempo = _REPO.get_tiempo_primera_gestion(_filters(marker), cutover=date(2020, 1, 1))
        assert tiempo["n"] == 1
        # 20:00 Santiago minus 12:00 Santiago = 8 h = 0.333 d. If the note wall
        # clock were interpreted as UTC the delta would be ~4 h, so this pins the
        # America/Santiago interpretation of the note header.
        assert abs(float(tiempo["media_dias"]) - (8 / 24)) < 0.01
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_note_timestamp_crosses_midnight_correctly() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    ingreso = datetime(2026, 9, 1, 23, 50, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="17171717-2",
                    fecha_ingreso=ingreso,
                    comentarios="Solicitud original\n\n[02/09/2026 00:10] Autor\nnota",
                )
            )
            conn.commit()
    try:
        tiempo = _REPO.get_tiempo_primera_gestion(_filters(marker), cutover=date(2020, 1, 1))
        assert tiempo["n"] == 1
        # 00:10 of the next day minus 23:50 = 20 minutes = 1/72 days: the note
        # date/time components must combine across the midnight boundary.
        assert abs(float(tiempo["media_dias"]) - (1 / 72)) < 0.005
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_note_parser_ignores_bare_dates_in_free_text() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    old = _now() - timedelta(days=10)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # A bare date in free text (no canonical "[dd/mm/YYYY HH:MM]" header)
            # must never be read as an operational note.
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="17171717-3",
                    fecha_ingreso=old,
                    comentarios="Cliente llamo el 05/09/2026 10:30 para consultar",
                )
            )
            conn.commit()
    try:
        assert _REPO.get_estancados(_filters(marker)) == 1
        tiempo = _REPO.get_tiempo_primera_gestion(_filters(marker), cutover=date(2020, 1, 1))
        assert tiempo["n"] == 0
        assert tiempo["media_dias"] is None
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_note_parser_uses_earliest_of_multiple_notes() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    ingreso = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="17171717-4",
                    fecha_ingreso=ingreso,
                    comentarios=(
                        "Solicitud original\n\n"
                        "[03/09/2026 09:00] Autor\nnota mas reciente\n\n"
                        "[02/09/2026 09:00] Autor\nnota mas antigua"
                    ),
                )
            )
            conn.commit()
    try:
        tiempo = _REPO.get_tiempo_primera_gestion(_filters(marker), cutover=date(2020, 1, 1))
        assert tiempo["n"] == 1
        # First note is 02/09 09:00 = 21 h after 01/09 12:00 = 0.875 d.
        assert abs(float(tiempo["media_dias"]) - (21 / 24)) < 0.01
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_antiguedad_buckets() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut="13131313-1", fecha_ingreso=_now() - timedelta(days=1)
                )
            )
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut="13131313-2", fecha_ingreso=_now() - timedelta(days=5)
                )
            )
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut="13131313-3", fecha_ingreso=_now() - timedelta(days=40)
                )
            )
            conn.commit()
    try:
        buckets = {row["bucket"]: row["n"] for row in _REPO.get_antiguedad(_filters(marker))}
        assert buckets == {"0-2": 1, "3-7": 1, "+30": 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_tiempo_asignacion_media() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    ingreso = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor_ids.append(_make_asesor(cur, "Asesor Tiempo Test"))
            lead_ids.append(_make_lead(cur, marker=marker, rut="14141414-1", fecha_ingreso=ingreso))
            _assign(cur, lead_ids[-1], asesor_ids[-1], ingreso + timedelta(days=2))
            lead_ids.append(_make_lead(cur, marker=marker, rut="14141414-2", fecha_ingreso=ingreso))
            conn.commit()
    try:
        tiempo = _REPO.get_tiempo_asignacion(_filters(marker))
        assert tiempo["n"] == 1
        assert abs(float(tiempo["media_dias"]) - 2.0) < 0.01
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_tiempo_primera_gestion_excludes_assignment() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    ingreso = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor_ids.append(_make_asesor(cur, "Asesor Gestion Test"))
            # Note 1 day after, state change 3 days after -> first management = 1 day.
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut="15151515-1",
                    fecha_ingreso=ingreso,
                    comentarios=f"[{_note_header(ingreso + timedelta(days=1))}] Autor\nnota",
                )
            )
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=3))
            _assign(cur, lead_ids[-1], asesor_ids[-1], ingreso + timedelta(hours=1))
            # No note, no state change -> no first management.
            lead_ids.append(_make_lead(cur, marker=marker, rut="15151515-2", fecha_ingreso=ingreso))
            conn.commit()
    try:
        tiempo = _REPO.get_tiempo_primera_gestion(_filters(marker), cutover=date(2020, 1, 1))
        assert tiempo["n"] == 1
        assert abs(float(tiempo["media_dias"]) - 1.0) < 0.01
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_funnel_excludes_pre_cutover_leads() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    pre = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    post = datetime(2026, 9, 11, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="16161616-1", fecha_ingreso=pre))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", pre + timedelta(days=1))
            lead_ids.append(_make_lead(cur, marker=marker, rut="16161616-2", fecha_ingreso=post))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", post + timedelta(days=1))
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-01", fecha_hasta="2026-09-30"), cutover=cutover
        )
        assert funnel["cobertura_completa"] is True
        assert funnel["excluidos_pre_cutover"] == 1
        assert funnel["denominador"] == 1
        assert funnel["steps"] == [{"origen": "nuevo", "destino": "contactado", "n": 1}]
        assert funnel["bases"] == {"nuevo": 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_funnel_missing_cutover_yields_no_rates() -> None:
    funnel = _REPO.get_funnel(DashboardFilters.from_raw(), cutover=None)
    assert funnel["cobertura_completa"] is False
    assert funnel["steps"] == []
    assert funnel["denominador"] == 0


def test_funnel_period_fully_before_cutover_yields_no_rates() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    ingreso = datetime(2026, 9, 1, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="18181818-1", fecha_ingreso=ingreso))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=1))
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-01", fecha_hasta="2026-09-05"), cutover=cutover
        )
        # The whole period precedes the cutover: no lead has complete history.
        assert funnel["excluidos_pre_cutover"] == 1
        assert funnel["denominador"] == 0
        assert funnel["steps"] == []
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_funnel_period_fully_after_cutover_computes_rates() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    ingreso = datetime(2026, 9, 11, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="18181818-2", fecha_ingreso=ingreso))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=1))
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-11", fecha_hasta="2026-09-30"), cutover=cutover
        )
        assert funnel["excluidos_pre_cutover"] == 0
        assert funnel["denominador"] == 1
        assert funnel["steps"] == [{"origen": "nuevo", "destino": "contactado", "n": 1}]
        assert funnel["bases"] == {"nuevo": 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_funnel_zero_denominator_yields_no_transitions() -> None:
    marker = _marker()
    cutover = date(2026, 9, 10)
    funnel = _REPO.get_funnel(
        _filters(marker, fecha_desde="2026-09-11", fecha_hasta="2026-09-30"), cutover=cutover
    )
    # No lead of this marker in the period: zero denominator, no invented rates.
    assert funnel["denominador"] == 0
    assert funnel["excluidos_pre_cutover"] == 0
    assert funnel["steps"] == []


def test_funnel_preserves_unknown_states() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    ingreso = datetime(2026, 9, 11, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="18181818-3", fecha_ingreso=ingreso))
            _state_change(
                cur, lead_ids[-1], "nuevo", "estado_x_desconocido", ingreso + timedelta(days=1)
            )
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-11", fecha_hasta="2026-09-30"), cutover=cutover
        )
        assert funnel["steps"] == [{"origen": "nuevo", "destino": "estado_x_desconocido", "n": 1}]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_funnel_repeated_transition_is_counted_once() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    ingreso = datetime(2026, 9, 11, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="18181818-4", fecha_ingreso=ingreso))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=1))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=2))
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-11", fecha_hasta="2026-09-30"), cutover=cutover
        )
        # COUNT(DISTINCT id_lead) collapses the duplicated transition to one.
        assert funnel["steps"] == [{"origen": "nuevo", "destino": "contactado", "n": 1}]
        assert funnel["bases"] == {"nuevo": 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_funnel_return_to_previous_state_keeps_both_transitions() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    cutover = date(2026, 9, 10)
    ingreso = datetime(2026, 9, 11, 12, 0, tzinfo=_TZ)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(_make_lead(cur, marker=marker, rut="18181818-5", fecha_ingreso=ingreso))
            _state_change(cur, lead_ids[-1], "nuevo", "contactado", ingreso + timedelta(days=1))
            _state_change(cur, lead_ids[-1], "contactado", "nuevo", ingreso + timedelta(days=2))
            conn.commit()
    try:
        funnel = _REPO.get_funnel(
            _filters(marker, fecha_desde="2026-09-11", fecha_hasta="2026-09-30"), cutover=cutover
        )
        steps = {f"{s['origen']}->{s['destino']}": s["n"] for s in funnel["steps"]}
        assert steps == {"nuevo->contactado": 1, "contactado->nuevo": 1}
        assert funnel["bases"] == {"nuevo": 1, "contactado": 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_repository_never_reads_auditoria_directly() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "repositories"
        / "executive_dashboard_repository.py"
    ).read_text(encoding="utf-8")
    assert "FROM tpi.auditoria" not in source
    assert "JOIN tpi.auditoria" not in source
    assert "tpi.v_historial_estado_lead" in source
    assert "tpi.v_asignacion_auditoria" not in source  # assignment time uses tpi.asignaciones


def test_explain_state_history_uses_support_index() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Force the index path to prove the 008 support index is available and
            # applicable to the funnel/state aggregation (a tiny table would
            # otherwise prefer a sequential scan, which is correct behavior).
            cur.execute("BEGIN")
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("""
                EXPLAIN (FORMAT JSON)
                SELECT v.estado_anterior, v.estado_nuevo, COUNT(DISTINCT v.id_lead)
                FROM tpi.v_historial_estado_lead v
                JOIN tpi.leads l ON l.id_lead = v.id_lead
                WHERE l.fecha_ingreso >= '2026-01-01'
                GROUP BY v.estado_anterior, v.estado_nuevo
                """)
            plan = cur.fetchone()["QUERY PLAN"]
            conn.rollback()
    plan_text = json.dumps(plan)
    assert "auditoria_state_history_idx" in plan_text


def test_performance_representative_volume() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    base = _now() - timedelta(days=10)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for _ in range(1500):
                lead_ids.append(
                    _make_lead(
                        cur,
                        marker=marker,
                        rut=f"p{uuid4().hex[:11]}",
                        fecha_ingreso=base,
                    )
                )
            conn.commit()
    try:
        import time

        start = time.monotonic()
        kpis = _REPO.get_kpi_snapshot(_filters(marker))
        estancados = _REPO.get_estancados(_filters(marker))
        elapsed = time.monotonic() - start
        assert kpis["total_leads"] == 1500
        assert estancados == 1500
        assert elapsed < 5.0
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()

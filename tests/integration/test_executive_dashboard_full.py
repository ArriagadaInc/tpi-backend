"""Integration tests for the full Executive Dashboard against real PostgreSQL.

Covers what the data-layer session could not: the per-advisor operational
metrics, the parity between an alert count and the ``/leads`` listing it links
to, the filter-option queries, and the cost of building the whole dashboard
(query count and wall time) with a representative volume.

The seeding helpers are imported from the repository test module so both suites
share one definition of how a lead, an assignment and a state change are built.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.models.executive_dashboard import DashboardFilters, estancamiento_dias_default
from app.repositories.executive_dashboard_repository import ExecutiveDashboardRepository
from app.repositories.solicitud_repository import SolicitudRepository
from app.services.executive_dashboard_service import ExecutiveDashboardService
from tests.integration.test_executive_dashboard_repository import (
    _assign,
    _cleanup,
    _make_asesor,
    _make_lead,
    _marker,
    _note_header,
    _now,
    _state_change,
)

pytestmark = pytest.mark.integration

_REPO = ExecutiveDashboardRepository()


@pytest.fixture(scope="session", autouse=True)
def verify_database() -> None:
    if not full_health_check().get("all_ready"):
        pytest.skip("Base de datos no disponible para tests de integración")


def _filters(marker: str, **kwargs: Any) -> DashboardFilters:
    return DashboardFilters.from_raw(origen=marker, **kwargs)


def _service(marker: str, cutover: date | None = None) -> ExecutiveDashboardService:
    from app.config import Settings

    settings_kwargs: dict[str, Any] = {"APP_ENV": "testing"}
    if cutover is not None:
        settings_kwargs["LEAD_STATE_HISTORY_CUTOVER"] = cutover.isoformat()
    return ExecutiveDashboardService(repository=_REPO, settings=Settings(**settings_kwargs))


# --------------------------------------------------------------------------- #
# Per-advisor operational metrics
# --------------------------------------------------------------------------- #


def test_per_advisor_metrics_use_the_shared_definitions() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    cutover = (now - timedelta(days=40)).date()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor = _make_asesor(cur, f"Asesor {uuid4().hex[:6]}")
            asesor_ids.append(asesor)

            # Stale lead: ingested 30 days ago, assigned the same day, nothing since.
            stale = _make_lead(
                cur,
                marker=marker,
                rut=f"s{uuid4().hex[:11]}",
                fecha_ingreso=now - timedelta(days=30),
            )
            _assign(cur, stale, asesor, now - timedelta(days=30))
            lead_ids.append(stale)

            # Fresh lead: ingested 10 days ago, assigned 2 days later, note yesterday.
            fresh_ingreso = now - timedelta(days=10)
            fresh = _make_lead(
                cur,
                marker=marker,
                rut=f"f{uuid4().hex[:11]}",
                fecha_ingreso=fresh_ingreso,
                comentarios=(
                    "Solicitud original\n\n"
                    f"[{_note_header(now - timedelta(days=1))}] Ejecutivo\nSeguimiento"
                ),
            )
            _assign(cur, fresh, asesor, fresh_ingreso + timedelta(days=2))
            _state_change(cur, fresh, "nuevo", "contactado", fresh_ingreso + timedelta(days=3))
            lead_ids.append(fresh)
            conn.commit()
    try:
        rows = _REPO.get_metricas_operacionales_por_asesor(
            _filters(marker), estancamiento_dias_default(), cutover
        )
        by_asesor = {str(row["id_asesor"]): row for row in rows if row["id_asesor"] is not None}
        assert asesor in by_asesor
        row = by_asesor[asesor]
        assert row["estancados"] == 1
        assert row["n_asignacion"] == 2
        # Mean of 0 days and 2 days to assignment.
        assert 0.9 <= float(row["tiempo_asignacion_dias"]) <= 1.1
        # Only the lead that actually has a note / state change counts; the stale
        # lead has neither, so it is excluded instead of contributing a zero.
        assert row["n_primera_gestion"] == 1
        assert row["tiempo_primera_gestion_dias"] is not None
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_first_management_is_unavailable_without_a_cutover() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=f"n{uuid4().hex[:11]}", fecha_ingreso=_now())
            )
            conn.commit()
    try:
        rows = _REPO.get_metricas_operacionales_por_asesor(
            _filters(marker), estancamiento_dias_default(), None
        )
        assert rows
        assert all(row["n_primera_gestion"] == 0 for row in rows)
        assert all(row["tiempo_primera_gestion_dias"] is None for row in rows)
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_advisor_rows_expose_no_pii_beyond_the_visible_name() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor = _make_asesor(cur, f"Asesor {uuid4().hex[:6]}")
            asesor_ids.append(asesor)
            lead = _make_lead(cur, marker=marker, rut=f"p{uuid4().hex[:11]}", fecha_ingreso=_now())
            _assign(cur, lead, asesor, _now())
            lead_ids.append(lead)
            conn.commit()
    try:
        service = _service(marker)
        dashboard = service.build_executive_dashboard(_filters(marker))
        assert dashboard.current_snapshot.cartera_por_asesor
        for row in dashboard.current_snapshot.cartera_por_asesor:
            fields = set(row.__slots__)
            assert "email" not in fields
            assert "rut" not in fields
            assert "telefono" not in fields
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


# --------------------------------------------------------------------------- #
# Alert / listing parity
# --------------------------------------------------------------------------- #


def _listing_total(**kwargs: Any) -> int:
    _, total = SolicitudRepository.get_crm_solicitudes(limit=1, offset=0, **kwargs)
    return total


def test_unassigned_alert_count_matches_the_listing_it_links_to() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor = _make_asesor(cur, f"Asesor {uuid4().hex[:6]}")
            asesor_ids.append(asesor)
            for index in range(4):
                lead = _make_lead(cur, marker=marker, rut=f"u{uuid4().hex[:11]}", fecha_ingreso=now)
                lead_ids.append(lead)
                if index < 2:
                    _assign(cur, lead, asesor, now)
            conn.commit()
    try:
        alerts = {
            alert.key: alert.count
            for alert in _service(marker).build_executive_dashboard(_filters(marker)).alerts
        }
        listing = _listing_total(origen_lead=marker, sin_asignar=True)
        assert alerts["sin_asignar"] == 2
        assert listing == alerts["sin_asignar"]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_stale_alert_count_matches_the_listing_it_links_to() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for _ in range(3):
                lead_ids.append(
                    _make_lead(
                        cur,
                        marker=marker,
                        rut=f"e{uuid4().hex[:11]}",
                        fecha_ingreso=now - timedelta(days=20),
                    )
                )
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=f"r{uuid4().hex[:11]}", fecha_ingreso=now)
            )
            conn.commit()
    try:
        alerts = {
            alert.key: alert.count
            for alert in _service(marker).build_executive_dashboard(_filters(marker)).alerts
        }
        listing = _listing_total(origen_lead=marker, estancado=True)
        assert alerts["estancados"] == 3
        assert listing == alerts["estancados"]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


def test_parity_holds_under_a_combined_dimension_filter() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for estado in ("nuevo", "nuevo", "cerrado"):
                lead_ids.append(
                    _make_lead(
                        cur,
                        marker=marker,
                        rut=f"c{uuid4().hex[:11]}",
                        estado=estado,
                        fecha_ingreso=now - timedelta(days=20),
                    )
                )
            conn.commit()
    try:
        filters = _filters(marker, estado="nuevo")
        alerts = {
            alert.key: alert.count
            for alert in _service(marker).build_executive_dashboard(filters).alerts
        }
        listing = _listing_total(origen_lead=marker, estado_lead="nuevo", estancado=True)
        assert alerts["estancados"] == 2
        assert listing == alerts["estancados"]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids)
                conn.commit()


# --------------------------------------------------------------------------- #
# Filter options
# --------------------------------------------------------------------------- #


def test_filter_options_expose_only_mvp_categories_without_pii() -> None:
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            asesor_ids.append(_make_asesor(cur, f"Asesor {uuid4().hex[:6]}"))
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut=f"o{uuid4().hex[:11]}",
                    fecha_ingreso=_now(),
                    fuente="fuente_integracion",
                )
            )
            conn.commit()
    try:
        options = _service(marker).get_filter_options()
        assert set(options) == {"estados", "asesores", "afps", "origenes", "fuentes"}
        assert marker in options["origenes"]
        assert "fuente_integracion" in options["fuentes"]
        for asesor in options["asesores"]:
            assert set(asesor) == {"value", "label"}
            assert "@" not in asesor["label"]
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


# --------------------------------------------------------------------------- #
# Cost of the full dashboard: query count and wall time
# --------------------------------------------------------------------------- #


@contextmanager
def _counting_statements() -> Iterator[list[int]]:
    """Count every statement the repository actually sends to PostgreSQL.

    The repository calls its fetch helpers through the class name, so the count
    is taken by swapping those two helpers for the duration of the block.
    """
    counter = [0]
    original_all = ExecutiveDashboardRepository._fetch_all
    original_one = ExecutiveDashboardRepository._fetch_one

    def counted_all(query, params):
        counter[0] += 1
        return original_all(query, params)

    def counted_one(query, params):
        counter[0] += 1
        return original_one(query, params)

    ExecutiveDashboardRepository._fetch_all = staticmethod(counted_all)  # type: ignore[method-assign]
    ExecutiveDashboardRepository._fetch_one = staticmethod(counted_one)  # type: ignore[method-assign]
    try:
        yield counter
    finally:
        ExecutiveDashboardRepository._fetch_all = staticmethod(original_all)  # type: ignore[method-assign]
        ExecutiveDashboardRepository._fetch_one = staticmethod(original_one)  # type: ignore[method-assign]


def _seed_volume(marker: str, leads: int, advisors: int) -> tuple[list[str], list[str]]:
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for index in range(advisors):
                asesor_ids.append(_make_asesor(cur, f"Asesor Volumen {index} {uuid4().hex[:6]}"))
            estados = ("nuevo", "contactado", "citado", "cerrado", "perdido")
            for index in range(leads):
                fecha = now - timedelta(days=index % 60)
                comentarios = None
                if index % 5 == 0:
                    comentarios = (
                        "Solicitud original\n\n"
                        f"[{_note_header(fecha + timedelta(days=1))}] Ejecutivo\nNota"
                    )
                lead = _make_lead(
                    cur,
                    marker=marker,
                    rut=f"v{uuid4().hex[:11]}",
                    estado=estados[index % len(estados)],
                    fecha_ingreso=fecha,
                    comentarios=comentarios,
                )
                lead_ids.append(lead)
                if index % 3 != 0:
                    _assign(cur, lead, asesor_ids[index % advisors], fecha + timedelta(hours=6))
                if index % 4 == 0:
                    _state_change(cur, lead, "nuevo", "contactado", fecha + timedelta(days=1))
            conn.commit()
    return lead_ids, asesor_ids


def test_full_dashboard_query_count_is_bounded_and_free_of_n_plus_1() -> None:
    """The query count must not grow with the number of leads or advisors."""
    small_marker = _marker()
    large_marker = _marker()
    small_ids = _seed_volume(small_marker, leads=20, advisors=2)
    large_ids = _seed_volume(large_marker, leads=400, advisors=12)
    cutover = (_now() - timedelta(days=90)).date()
    desde = (_now() - timedelta(days=60)).date().isoformat()
    try:
        with _counting_statements() as count_small:
            _service(small_marker, cutover).build_executive_dashboard(
                _filters(small_marker, fecha_desde=desde)
            )
        with _counting_statements() as count_large:
            _service(large_marker, cutover).build_executive_dashboard(
                _filters(large_marker, fecha_desde=desde)
            )
        assert count_small[0] > 0
        assert count_small[0] == count_large[0], "query count must not depend on data volume"
        assert count_large[0] <= 20, f"unexpected query fan-out: {count_large[0]}"
        print(f"\n[H3.3.4 perf] dashboard statements per render = {count_large[0]}")
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, small_ids[0], small_ids[1])
                _cleanup(cur, large_ids[0], large_ids[1])
                conn.commit()


def test_full_dashboard_latency_with_representative_volume() -> None:
    """Measure the real end-to-end latency of the whole dashboard, not a threshold proxy."""
    marker = _marker()
    lead_ids, asesor_ids = _seed_volume(marker, leads=2000, advisors=12)
    cutover = (_now() - timedelta(days=90)).date()
    try:
        service = _service(marker, cutover)
        filters = _filters(
            marker,
            fecha_desde=(_now() - timedelta(days=60)).date().isoformat(),
            fecha_hasta=_now().date().isoformat(),
        )
        # Warm up the connection pool so the measurement reflects the queries.
        service.build_executive_dashboard(filters)
        with _counting_statements() as counter:
            started = time.monotonic()
            dashboard = service.build_executive_dashboard(filters)
            elapsed = time.monotonic() - started
            dashboard_statements = counter[0]
            options_started = time.monotonic()
            service.get_filter_options()
            options_elapsed = time.monotonic() - options_started
            options_statements = counter[0] - dashboard_statements

        assert dashboard.current_snapshot.total_leads == 2000
        assert dashboard.failed_sections == ()

        # Time every query individually so the slowest section is a measurement,
        # not a guess.
        cutover_date = service.cutover
        calls = {
            "get_kpi_snapshot": lambda: _REPO.get_kpi_snapshot(filters),
            "get_estancados": lambda: _REPO.get_estancados(filters, 5),
            "get_casos_por_estado": lambda: _REPO.get_casos_por_estado(filters),
            "get_antiguedad": lambda: _REPO.get_antiguedad(filters),
            "get_estancados_por_antiguedad": lambda: _REPO.get_estancados_por_antiguedad(
                filters, 5
            ),
            "get_cartera_por_asesor": lambda: _REPO.get_cartera_por_asesor(filters),
            "get_metricas_operacionales_por_asesor": (
                lambda: _REPO.get_metricas_operacionales_por_asesor(filters, 5, cutover_date)
            ),
            "get_casos_por_estado_y_asesor": lambda: _REPO.get_casos_por_estado_y_asesor(filters),
            "get_distribucion_afp": lambda: _REPO.get_distribucion_afp(filters),
            "get_distribucion_origen": lambda: _REPO.get_distribucion_origen(filters),
            "get_distribucion_fuente": lambda: _REPO.get_distribucion_fuente(filters),
            "get_leads_ingresados": lambda: _REPO.get_leads_ingresados(filters),
            "get_evolucion": lambda: _REPO.get_evolucion(filters),
            "get_funnel": lambda: _REPO.get_funnel(filters, cutover_date),
            "get_tiempo_asignacion": lambda: _REPO.get_tiempo_asignacion(filters),
            "get_tiempo_primera_gestion": lambda: _REPO.get_tiempo_primera_gestion(
                filters, cutover_date
            ),
        }
        measured: dict[str, float] = {}
        for name, call in calls.items():
            query_started = time.monotonic()
            call()
            measured[name] = time.monotonic() - query_started
        slowest = sorted(measured.items(), key=lambda item: item[1], reverse=True)[:3]

        print(
            f"\n[H3.3.4 perf] leads=2000 advisors=12 "
            f"dashboard_statements={dashboard_statements} dashboard_seconds={elapsed:.3f} "
            f"filter_option_statements={options_statements} "
            f"filter_options_seconds={options_elapsed:.3f}"
        )
        print(
            "[H3.3.4 perf] slowest queries: "
            + ", ".join(f"{name}={seconds:.3f}s" for name, seconds in slowest)
        )
        assert elapsed < 10.0, f"dashboard too slow: {elapsed:.3f}s"
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()

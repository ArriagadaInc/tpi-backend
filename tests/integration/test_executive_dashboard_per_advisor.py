"""Integration tests for the per-advisor executive dashboard metrics (F7 remediation).

These tests assert exact values for the three per-advisor aggregations cited by
``docs/H3_3_4_REQUIREMENTS_MATRIX.md`` under REQ-B-12/REQ-B-13/REQ-B-14 and AC-12:

- ``get_cartera_por_asesor``: total and active portfolio per advisor, with the
  exact active-portfolio exclusion (``cerrado``/``perdido``/``no_califica``/
  ``duplicado``), the "Sin asesor" bucket, and fan-out safety.
- ``get_casos_por_estado_y_asesor``: the state x advisor matrix with exact cell
  counts, unassigned leads, and fan-out safety.
- ``get_metricas_operacionales_por_asesor``: stuck count, time-to-assignment and
  time-to-first-management per advisor, with N/D (NULL) when no base exists and
  the same universe/definitions as the global dashboard metrics.

The seeding helpers are imported from the repository test module so every suite
shares one definition of how a lead, an assignment and a state change are built.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.database.connection import get_db_connection
from app.database.healthcheck import full_health_check
from app.models.executive_dashboard import DashboardFilters, estancamiento_dias_default
from app.repositories.executive_dashboard_repository import ExecutiveDashboardRepository
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


def _filters(marker: str, **kwargs: object) -> DashboardFilters:
    return DashboardFilters.from_raw(origen=marker, **kwargs)  # type: ignore[arg-type]


def _rut(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:11]}"


def _by_asesor(rows: list[dict[str, object]]) -> dict[str | None, dict[str, object]]:
    return {str(r["id_asesor"]) if r["id_asesor"] else None: r for r in rows}


def test_cartera_por_asesor_exact_total_active_and_sin_asesor() -> None:
    """REQ-B-13: exact total/active per advisor and the active-portfolio exclusion."""
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            a1 = _make_asesor(cur, f"Asesor Cartera A {uuid4().hex[:6]}")
            a2 = _make_asesor(cur, f"Asesor Cartera B {uuid4().hex[:6]}")
            asesor_ids.extend([a1, a2])

            # a1: one active + one unknown (both active) + the four inactive states.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("a"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now)
            for estado in ("cerrado", "perdido", "no_califica", "duplicado"):
                lead_ids.append(
                    _make_lead(cur, marker=marker, rut=_rut("b"), estado=estado, fecha_ingreso=now)
                )
                _assign(cur, lead_ids[-1], a1, now)
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut=_rut("c"), estado="estado_raro", fecha_ingreso=now
                )
            )
            _assign(cur, lead_ids[-1], a1, now)

            # a2: one active lead.
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut=_rut("d"), estado="contactado", fecha_ingreso=now
                )
            )
            _assign(cur, lead_ids[-1], a2, now)

            # Unassigned lead -> its own bucket.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("e"), estado="nuevo", fecha_ingreso=now)
            )
            conn.commit()
    try:
        rows = _REPO.get_cartera_por_asesor(_filters(marker))
        by_id = _by_asesor(rows)
        assert by_id[a1]["cartera_total"] == 6  # 1 nuevo + 4 inactivos + 1 desconocido
        assert by_id[a1]["cartera_activa"] == 2  # solo "nuevo" y "estado_raro"
        assert by_id[a1]["nombre"] is not None
        assert by_id[a2]["cartera_total"] == 1
        assert by_id[a2]["cartera_activa"] == 1
        assert by_id[None]["cartera_total"] == 1
        assert by_id[None]["cartera_activa"] == 1
        assert by_id[None]["id_asesor"] is None
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_cartera_por_asesor_fanout_safe_and_dimensional_filter() -> None:
    """REQ-B-13: one lead per id_lead despite multiple assignment rows; filters apply."""
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            a1 = _make_asesor(cur, f"Asesor Fanout {uuid4().hex[:6]}")
            asesor_ids.append(a1)

            # Inactive + active assignment -> counted once under a1 (no fan-out).
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("f"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now - timedelta(days=3), estado="inactiva")
            _assign(cur, lead_ids[-1], a1, now - timedelta(days=1), estado="activa")

            # Only an inactive assignment -> unassigned bucket.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("g"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now - timedelta(days=2), estado="inactiva")

            # Closed lead under a1 -> excluded from cartera activa.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("h"), estado="cerrado", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now)
            conn.commit()
    try:
        rows = _REPO.get_cartera_por_asesor(_filters(marker))
        by_id = _by_asesor(rows)
        assert by_id[a1]["cartera_total"] == 2  # nuevo + cerrado, no duplicated
        assert by_id[a1]["cartera_activa"] == 1  # only the "nuevo" lead
        assert by_id[None]["cartera_total"] == 1  # inactive-only lead

        filtered = _REPO.get_cartera_por_asesor(_filters(marker, estado="nuevo"))
        by_filtered = _by_asesor(filtered)
        assert by_filtered[a1]["cartera_total"] == 1
        assert by_filtered[None]["cartera_total"] == 1
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_casos_por_estado_y_asesor_exact_matrix_counts() -> None:
    """REQ-B-14: exact estado x asesor cells (incl. unknown states), unassigned
    bucket, one row per (asesor, estado) and zero fan-out."""
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            a1 = _make_asesor(cur, f"Asesor Matrix A {uuid4().hex[:6]}")
            a2 = _make_asesor(cur, f"Asesor Matrix B {uuid4().hex[:6]}")
            asesor_ids.extend([a1, a2])

            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now)
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut=_rut("m"), estado="contactado", fecha_ingreso=now
                )
            )
            _assign(cur, lead_ids[-1], a1, now)
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="cerrado", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now)
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a2, now)
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="perdido", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a2, now)
            # Unassigned lead.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="nuevo", fecha_ingreso=now)
            )
            # Fan-out: inactive + active assignment still forms one cell.
            lead_ids.append(
                _make_lead(cur, marker=marker, rut=_rut("m"), estado="nuevo", fecha_ingreso=now)
            )
            _assign(cur, lead_ids[-1], a1, now - timedelta(days=3), estado="inactiva")
            _assign(cur, lead_ids[-1], a1, now - timedelta(days=1), estado="activa")
            # Unknown states (not in the catalog), one assigned and one unassigned.
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut=_rut("m"),
                    estado="estado_desconocido_xyz",
                    fecha_ingreso=now,
                )
            )
            _assign(cur, lead_ids[-1], a1, now)
            lead_ids.append(
                _make_lead(
                    cur,
                    marker=marker,
                    rut=_rut("m"),
                    estado="estado_desconocido_xyz",
                    fecha_ingreso=now,
                )
            )
            conn.commit()
    try:
        rows = _REPO.get_casos_por_estado_y_asesor(_filters(marker))
        cells = {
            (str(r["id_asesor"]) if r["id_asesor"] else None, r["estado"]): int(r["n"])
            for r in rows
        }
        assert cells[(a1, "nuevo")] == 2
        assert cells[(a1, "contactado")] == 1
        assert cells[(a1, "cerrado")] == 1
        assert cells[(a1, "estado_desconocido_xyz")] == 1  # unknown state preserved
        assert cells[(a2, "nuevo")] == 1
        assert cells[(a2, "perdido")] == 1
        assert cells[(None, "nuevo")] == 1
        assert cells[(None, "estado_desconocido_xyz")] == 1  # unassigned unknown state
        assert len(rows) == len(cells)  # one row per (asesor, estado): no duplicate rows
        assert sum(cells.values()) == len(lead_ids)  # each lead counted exactly once

        filtered = _REPO.get_casos_por_estado_y_asesor(_filters(marker, estado="nuevo"))
        fcells = {
            (str(r["id_asesor"]) if r["id_asesor"] else None, r["estado"]): int(r["n"])
            for r in filtered
        }
        assert fcells == {(a1, "nuevo"): 2, (a2, "nuevo"): 1, (None, "nuevo"): 1}

        unknown_only = _REPO.get_casos_por_estado_y_asesor(
            _filters(marker, estado="estado_desconocido_xyz")
        )
        ucells = {
            (str(r["id_asesor"]) if r["id_asesor"] else None, r["estado"]): int(r["n"])
            for r in unknown_only
        }
        assert ucells == {(a1, "estado_desconocido_xyz"): 1, (None, "estado_desconocido_xyz"): 1}
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()


def test_metricas_operacionales_por_asesor_stuck_assignment_and_first_management() -> None:
    """REQ-B-12: per-advisor stuck count and response times with the shared definitions."""
    marker = _marker()
    lead_ids: list[str] = []
    asesor_ids: list[str] = []
    now = _now()
    cutover = (now - timedelta(days=40)).date()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            a1 = _make_asesor(cur, f"Asesor Ops A {uuid4().hex[:6]}")
            a2 = _make_asesor(cur, f"Asesor Ops B {uuid4().hex[:6]}")
            asesor_ids.extend([a1, a2])

            # Stale: ingested 30 days ago, assigned the same day, nothing since.
            stale = _make_lead(
                cur, marker=marker, rut=_rut("o"), fecha_ingreso=now - timedelta(days=30)
            )
            _assign(cur, stale, a1, now - timedelta(days=30))
            lead_ids.append(stale)

            # Fresh: ingested 10 days ago, assigned 2 days later, note 7 days after
            # ingestion and state change 9 days after ingestion (note wins LEAST).
            ingreso = now - timedelta(days=10)
            fresh = _make_lead(
                cur,
                marker=marker,
                rut=_rut("o"),
                fecha_ingreso=ingreso,
                comentarios=(
                    "Solicitud original\n\n"
                    f"[{_note_header(now - timedelta(days=3))}] Ejecutivo\nSeguimiento"
                ),
            )
            _assign(cur, fresh, a2, ingreso + timedelta(days=2))
            _state_change(cur, fresh, "nuevo", "contactado", now - timedelta(days=1))
            lead_ids.append(fresh)

            # Unassigned stale lead.
            lead_ids.append(
                _make_lead(
                    cur, marker=marker, rut=_rut("o"), fecha_ingreso=now - timedelta(days=30)
                )
            )
            conn.commit()
    try:
        filters = _filters(marker)
        rows = _REPO.get_metricas_operacionales_por_asesor(
            filters, estancamiento_dias_default(), cutover
        )
        by_id = _by_asesor(rows)

        assert by_id[a1]["estancados"] == 1
        assert by_id[a1]["n_asignacion"] == 1
        assert abs(float(by_id[a1]["tiempo_asignacion_dias"])) < 0.1
        assert by_id[a1]["n_primera_gestion"] == 0
        assert by_id[a1]["tiempo_primera_gestion_dias"] is None

        assert by_id[a2]["estancados"] == 0
        assert by_id[a2]["n_asignacion"] == 1
        assert 1.9 <= float(by_id[a2]["tiempo_asignacion_dias"]) <= 2.1
        assert by_id[a2]["n_primera_gestion"] == 1
        assert 6.8 <= float(by_id[a2]["tiempo_primera_gestion_dias"]) <= 7.2

        assert by_id[None]["estancados"] == 1
        assert by_id[None]["n_asignacion"] == 0
        assert by_id[None]["tiempo_asignacion_dias"] is None
        assert by_id[None]["n_primera_gestion"] == 0
        assert by_id[None]["tiempo_primera_gestion_dias"] is None

        # Same universe and shared definitions as the global dashboard metrics.
        assert sum(int(r["estancados"]) for r in rows) == _REPO.get_estancados(filters)
        assert (
            sum(int(r["n_asignacion"]) for r in rows) == _REPO.get_tiempo_asignacion(filters)["n"]
        )
        assert (
            sum(int(r["n_primera_gestion"]) for r in rows)
            == _REPO.get_tiempo_primera_gestion(filters, cutover)["n"]
        )
    finally:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, lead_ids, asesor_ids)
                conn.commit()

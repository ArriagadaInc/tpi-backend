"""Aggregate read model for the Executive CRM Dashboard (H3.3.4, Parte B).

This repository returns only aggregated metrics (``COUNT(DISTINCT id_lead)`` as
the single fan-out-safe denominator) and never exposes lead PII nor advisor PII
beyond ``id_asesor`` + visible ``nombre``. It reads operational tables
(``tpi.leads``, ``tpi.asignaciones``, ``tpi.asesores``, ``tpi.catalogo_afp``)
plus the sanitized view ``tpi.v_historial_estado_lead`` (008) for general
state-change history. Assignment movement and time-to-assignment read
``tpi.asignaciones`` (the operational source). It never reads ``tpi.auditoria``
directly, mirroring the least-privilege contract of the lead timeline.

All user input is passed as ``%s`` parameters. The only interpolated fragments
are fixed, whitelisted constants (granularity field, bucket boundaries, the
note-timestamp expression) wrapped in ``psycopg.sql.SQL``, mirroring the
safe-query pattern already used by ``SolicitudRepository.get_crm_solicitudes``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import IsolationLevel, sql
from psycopg.rows import dict_row

from app.database.connection import get_db_connection
from app.models.crm_states import crm_state_filter_terms
from app.models.executive_dashboard import (
    CARTERA_INACTIVA_ESTADOS,
    DashboardFilters,
    granularity_sql_field,
)
from app.models.lead_assignment import ASSIGNMENT_ACTIVE_STATE
from app.repositories.lead_activity_sql import (
    NOTE_TS_EXPR,
    NOTE_TS_PATTERN,
    estancado_params,
    estancado_predicate,
    sin_asignar_predicate,
)

_CRM_TZ = ZoneInfo("America/Santiago")

# Kept as module aliases so the shared definitions in ``lead_activity_sql`` remain
# the single source of truth for "movimiento operativo" and "estancado".
_NOTE_TS_PATTERN = NOTE_TS_PATTERN
_NOTE_TS_EXPR = NOTE_TS_EXPR

_CARTERA_INACTIVA_SQL = ", ".join(["%s"] * len(CARTERA_INACTIVA_ESTADOS))

# Connection shared by every aggregate query of a single dashboard render. When
# set (inside :func:`dashboard_read_snapshot`), ``_fetch_all``/``_fetch_one`` run
# on this connection instead of opening a new one, so all metrics observe the
# same database snapshot.
_snapshot_conn: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "executive_dashboard_snapshot_conn", default=None
)


@contextmanager
def dashboard_read_snapshot(operation: str = "executive_dashboard_snapshot") -> Iterator[Any]:
    """Run every dashboard aggregate under one REPEATABLE READ READ ONLY snapshot.

    The executive dashboard is built from many independent aggregate queries. If
    each query opened its own transaction, a render could mix counts captured at
    different instants under concurrent writes (for example an alert count and the
    KPI total disagreeing). This context manager pins one read-only snapshot for
    the whole build:

    - ``REPEATABLE READ``: every statement sees the database as of the first
      statement of the transaction.
    - ``READ ONLY``: no write lock is taken and no write can be issued, so the
      dashboard never blocks or mutates writers.
    - each aggregate still runs inside a savepoint (see ``_fetch_all``), so an
      individual query failure does not abort the whole transaction and the
      section-isolation contract of the service is preserved.

    The snapshot is released by rolling back on exit and the pooled connection's
    session defaults are restored before it returns to the pool.
    """
    with get_db_connection(operation=operation) as conn:
        previous_isolation = conn.isolation_level
        previous_read_only = conn.read_only
        conn.isolation_level = IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        token = _snapshot_conn.set(conn)
        try:
            with conn.transaction():
                yield conn
        finally:
            _snapshot_conn.reset(token)
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.isolation_level = previous_isolation
                conn.read_only = previous_read_only
            except Exception:
                pass


class ExecutiveDashboardRepository:
    """Aggregate queries for the executive dashboard, scoped by validated filters."""

    @staticmethod
    def _dimension_clauses(filters: DashboardFilters) -> tuple[list[str], list[Any]]:
        """Build shared dimension-filter clauses (no date range, no ``WHERE``)."""
        clauses: list[str] = []
        params: list[Any] = []

        if filters.estado:
            terms = crm_state_filter_terms(filters.estado)
            if terms:
                placeholders = ", ".join(["%s"] * len(terms))
                clauses.append(f"LOWER(TRIM(l.estado_lead)) IN ({placeholders})")
                params.extend(terms)

        if filters.asesor is not None:
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM tpi.asignaciones _fa "
                "WHERE _fa.id_lead = l.id_lead "
                "AND _fa.estado_asignacion = %s "
                "AND _fa.id_asesor = %s"
                ")"
            )
            params.extend([ASSIGNMENT_ACTIVE_STATE, str(filters.asesor)])

        if filters.afp is not None:
            clauses.append("l.afp_id = %s")
            params.append(str(filters.afp))

        if filters.origen:
            clauses.append("LOWER(TRIM(l.origen_lead)) = LOWER(%s)")
            params.append(filters.origen)

        if filters.fuente:
            clauses.append("LOWER(TRIM(l.fuente_actual)) = LOWER(%s)")
            params.append(filters.fuente)

        return clauses, params

    @staticmethod
    def _period_clauses(filters: DashboardFilters) -> tuple[list[str], list[Any]]:
        """Return the inclusive ``fecha_ingreso`` range clauses (no ``WHERE``)."""
        clauses: list[str] = []
        params: list[Any] = []
        if filters.fecha_desde is not None:
            clauses.append("l.fecha_ingreso >= %s")
            params.append(datetime.combine(filters.fecha_desde, time.min, tzinfo=_CRM_TZ))
        if filters.fecha_hasta is not None:
            clauses.append("l.fecha_ingreso <= %s")
            params.append(datetime.combine(filters.fecha_hasta, time.max, tzinfo=_CRM_TZ))
        return clauses, params

    @staticmethod
    def _where(clauses: list[str]) -> str:
        present = [clause for clause in clauses if clause]
        if not present:
            return ""
        return "WHERE " + " AND ".join(present)

    @staticmethod
    def _cartera_activa_clause() -> str:
        return f"LOWER(TRIM(l.estado_lead)) NOT IN ({_CARTERA_INACTIVA_SQL})"

    @staticmethod
    def _active_assignment_cte() -> str:
        return """
            active_assignment AS (
                SELECT DISTINCT ON (a.id_lead) a.id_lead, a.id_asesor
                FROM tpi.asignaciones a
                WHERE a.estado_asignacion = %s
                ORDER BY a.id_lead, a.fecha_asignacion DESC, a.id_asignacion DESC
            )
        """

    @staticmethod
    def _antiguedad_case() -> str:
        return """
            CASE
                WHEN dias <= 2 THEN '0-2'
                WHEN dias <= 7 THEN '3-7'
                WHEN dias <= 15 THEN '8-15'
                WHEN dias <= 30 THEN '16-30'
                ELSE '+30'
            END
        """

    @staticmethod
    def _dias_desde_ingreso() -> str:
        return (
            "((now() AT TIME ZONE 'America/Santiago')::date "
            "- (l.fecha_ingreso AT TIME ZONE 'America/Santiago')::date)"
        )

    @staticmethod
    def _fetch_all(query: sql.SQL | sql.Composed, params: list[Any]) -> list[dict[str, Any]]:
        conn = _snapshot_conn.get()
        if conn is not None:
            with conn.cursor(row_factory=dict_row) as cur:
                rows = ExecutiveDashboardRepository._execute_in_savepoint(
                    cur, query, params, fetch_one=False
                )
                return [dict(row) for row in rows]
        with get_db_connection(operation="executive_dashboard") as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def _fetch_one(query: sql.SQL | sql.Composed, params: list[Any]) -> dict[str, Any] | None:
        conn = _snapshot_conn.get()
        if conn is not None:
            with conn.cursor(row_factory=dict_row) as cur:
                row = ExecutiveDashboardRepository._execute_in_savepoint(
                    cur, query, params, fetch_one=True
                )
                return dict(row) if row else None
        with get_db_connection(operation="executive_dashboard") as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def _execute_in_savepoint(
        cur: Any, query: sql.SQL | sql.Composed, params: list[Any], *, fetch_one: bool
    ) -> Any:
        """Run one aggregate inside a savepoint of the shared snapshot transaction.

        A failing aggregate would otherwise abort the whole read-only transaction
        (``InFailedSqlTransaction``) and break the service's per-section isolation.
        The savepoint contains the failure: on error the savepoint is rolled back
        and the exception re-raised so the service marks that section as failed
        while the rest of the dashboard keeps reading the same snapshot.
        """
        cur.execute("SAVEPOINT exec_dashboard_query")
        try:
            cur.execute(query, params)
            if fetch_one:
                row = cur.fetchone()
            else:
                rows = cur.fetchall()
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT exec_dashboard_query")
            raise
        cur.execute("RELEASE SAVEPOINT exec_dashboard_query")
        return row if fetch_one else rows

    @staticmethod
    def get_kpi_snapshot(filters: DashboardFilters) -> dict[str, int]:
        """Total leads, active portfolio and unassigned leads (current snapshot)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT
                COUNT(DISTINCT l.id_lead) AS total_leads,
                COUNT(DISTINCT l.id_lead) FILTER (
                    WHERE LOWER(TRIM(l.estado_lead)) NOT IN ({cartera_inactiva})
                ) AS cartera_activa,
                COUNT(DISTINCT l.id_lead) FILTER (
                    WHERE {sin_asignar}
                ) AS sin_asignar
            FROM tpi.leads l
            {where}
            """).format(
            cartera_inactiva=sql.SQL(_CARTERA_INACTIVA_SQL),
            sin_asignar=sql.SQL(sin_asignar_predicate("l")),
            where=sql.SQL(where),
        )
        params = [*list(CARTERA_INACTIVA_ESTADOS), ASSIGNMENT_ACTIVE_STATE, *dimension_params]
        row = ExecutiveDashboardRepository._fetch_one(query, params) or {}
        return {
            "total_leads": int(row.get("total_leads") or 0),
            "cartera_activa": int(row.get("cartera_activa") or 0),
            "sin_asignar": int(row.get("sin_asignar") or 0),
        }

    @staticmethod
    def get_estancados(filters: DashboardFilters, threshold_days: int = 5) -> int:
        """Count leads whose last operational movement is older than the threshold.

        Movement = human note, assignment or general state change; if none exists,
        ``fecha_ingreso`` is the reproducible floor. ``updated_at`` is never used.
        """
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        query = sql.SQL("""
            SELECT COUNT(DISTINCT l.id_lead) AS estancados
            FROM tpi.leads l
            {where_estancado}
            """).format(
            where_estancado=sql.SQL(
                ExecutiveDashboardRepository._where([estancado_predicate("l"), *dimension_clauses])
            )
        )
        params = [*estancado_params(threshold_days), *dimension_params]
        row = ExecutiveDashboardRepository._fetch_one(query, params) or {}
        return int(row.get("estancados") or 0)

    @staticmethod
    def get_antiguedad(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Age buckets of the active portfolio (calendar days since ``fecha_ingreso``)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        inner_clauses = [ExecutiveDashboardRepository._cartera_activa_clause(), *dimension_clauses]
        inner_where = ExecutiveDashboardRepository._where(inner_clauses)
        dias_expr = ExecutiveDashboardRepository._dias_desde_ingreso()
        bucket_expr = ExecutiveDashboardRepository._antiguedad_case()
        query = sql.SQL("""
            SELECT
                {bucket_expr} AS bucket,
                COUNT(DISTINCT id_lead) AS n
            FROM (
                SELECT l.id_lead, ({dias_expr}) AS dias
                FROM tpi.leads l
                {inner_where}
            ) t
            GROUP BY bucket
            ORDER BY MIN(dias)
            """).format(
            bucket_expr=sql.SQL(bucket_expr),
            dias_expr=sql.SQL(dias_expr),
            inner_where=sql.SQL(inner_where),
        )
        params = [*list(CARTERA_INACTIVA_ESTADOS), *dimension_params]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_estancados_por_antiguedad(
        filters: DashboardFilters, threshold_days: int = 5
    ) -> list[dict[str, Any]]:
        """Stuck leads bucketed by age (calendar days since ``fecha_ingreso``)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        dias_expr = ExecutiveDashboardRepository._dias_desde_ingreso()
        bucket_expr = ExecutiveDashboardRepository._antiguedad_case()
        query = sql.SQL("""
            SELECT {bucket_expr} AS bucket, COUNT(DISTINCT id_lead) AS n
            FROM (
                SELECT l.id_lead, ({dias_expr}) AS dias
                FROM tpi.leads l
                {where_estancado}
            ) t
            GROUP BY bucket
            ORDER BY MIN(dias)
            """).format(
            where_estancado=sql.SQL(
                ExecutiveDashboardRepository._where([estancado_predicate("l"), *dimension_clauses])
            ),
            dias_expr=sql.SQL(dias_expr),
            bucket_expr=sql.SQL(bucket_expr),
        )
        params = [*estancado_params(threshold_days), *dimension_params]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_casos_por_estado(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Cases by raw state (unknown states preserved; labels resolved in Python)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT l.estado_lead AS estado, COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            {where}
            GROUP BY l.estado_lead
            ORDER BY n DESC, l.estado_lead ASC
            """).format(where=sql.SQL(where))
        return ExecutiveDashboardRepository._fetch_all(query, dimension_params)

    @staticmethod
    def get_cartera_por_asesor(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Total and active portfolio per advisor (leads without one form their own bucket)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        cte = ExecutiveDashboardRepository._active_assignment_cte()
        query = sql.SQL("""
            WITH {cte}
            SELECT
                aa.id_asesor,
                ases.nombre AS nombre,
                COUNT(DISTINCT l.id_lead) AS cartera_total,
                COUNT(DISTINCT l.id_lead) FILTER (
                    WHERE LOWER(TRIM(l.estado_lead)) NOT IN ({cartera_inactiva})
                ) AS cartera_activa
            FROM tpi.leads l
            LEFT JOIN active_assignment aa ON aa.id_lead = l.id_lead
            LEFT JOIN tpi.asesores ases ON ases.id_asesor = aa.id_asesor
            {where}
            GROUP BY aa.id_asesor, ases.nombre
            ORDER BY cartera_total DESC, ases.nombre ASC
            """).format(
            cte=sql.SQL(cte),
            cartera_inactiva=sql.SQL(_CARTERA_INACTIVA_SQL),
            where=sql.SQL(where),
        )
        params = [ASSIGNMENT_ACTIVE_STATE, *list(CARTERA_INACTIVA_ESTADOS), *dimension_params]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_metricas_operacionales_por_asesor(
        filters: DashboardFilters,
        threshold_days: int,
        cutover: date | None,
    ) -> list[dict[str, Any]]:
        """Stuck count and response times per advisor, with the shared definitions.

        Every metric reuses the same definition as its global counterpart: the
        stale predicate comes from :mod:`app.repositories.lead_activity_sql`, time
        to assignment is measured against the first ``tpi.asignaciones`` row, and
        first management is the earliest of the first human note and the first
        general state change (never the assignment), restricted to post-cutover
        leads because pre-cutover leads have no complete state history.

        All joins are one-row-per-lead, so the averages cannot fan out; counts use
        ``COUNT(DISTINCT id_lead)`` regardless.
        """
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        cte = ExecutiveDashboardRepository._active_assignment_cte()

        gestion_params: list[Any] = []
        if cutover is None:
            # No cutover configured: first management has no observable window, so
            # the metric is reported as unavailable instead of being invented.
            gestion_join = (
                "LEFT JOIN LATERAL (SELECT NULL::timestamptz AS primera_gestion) pg ON TRUE"
            )
        else:
            gestion_join = f"""
                LEFT JOIN LATERAL (
                    SELECT LEAST(
                        (SELECT MIN({_NOTE_TS_EXPR})
                         FROM regexp_matches(l.comentarios, %s, 'g') AS m),
                        (SELECT MIN(v.fecha_hora)
                         FROM tpi.v_historial_estado_lead v
                         WHERE v.id_lead = l.id_lead)
                    ) AS primera_gestion
                    WHERE l.fecha_ingreso >= %s
                ) pg ON TRUE
            """
            gestion_params = [
                _NOTE_TS_PATTERN,
                datetime.combine(cutover, time.min, tzinfo=_CRM_TZ),
            ]

        query = sql.SQL("""
            WITH {cte}
            SELECT
                aa.id_asesor,
                COUNT(DISTINCT l.id_lead) FILTER (WHERE {estancado}) AS estancados,
                COUNT(fa.first_ts) AS n_asignacion,
                AVG(EXTRACT(EPOCH FROM (fa.first_ts - l.fecha_ingreso)) / 86400.0)
                    AS tiempo_asignacion_dias,
                COUNT(pg.primera_gestion) AS n_primera_gestion,
                AVG(EXTRACT(EPOCH FROM (pg.primera_gestion - l.fecha_ingreso)) / 86400.0)
                    AS tiempo_primera_gestion_dias
            FROM tpi.leads l
            LEFT JOIN active_assignment aa ON aa.id_lead = l.id_lead
            LEFT JOIN LATERAL (
                SELECT MIN(a.fecha_asignacion) AS first_ts
                FROM tpi.asignaciones a
                WHERE a.id_lead = l.id_lead
            ) fa ON TRUE
            {gestion_join}
            {where}
            GROUP BY aa.id_asesor
            """).format(
            cte=sql.SQL(cte),
            estancado=sql.SQL(estancado_predicate("l")),
            gestion_join=sql.SQL(gestion_join),
            where=sql.SQL(where),
        )
        params = [
            ASSIGNMENT_ACTIVE_STATE,
            *estancado_params(threshold_days),
            *gestion_params,
            *dimension_params,
        ]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_asesor_options() -> list[dict[str, Any]]:
        """Advisor filter options: technical id and visible name only (no PII)."""
        query = sql.SQL("""
            SELECT ases.id_asesor, ases.nombre
            FROM tpi.asesores ases
            ORDER BY ases.nombre ASC, ases.id_asesor ASC
            """)
        return ExecutiveDashboardRepository._fetch_all(query, [])

    @staticmethod
    def get_afp_options() -> list[dict[str, Any]]:
        """AFP filter options from the catalog (MVP category)."""
        query = sql.SQL("""
            SELECT ca.id, ca.nombre
            FROM tpi.catalogo_afp ca
            WHERE ca.activo = TRUE
            ORDER BY ca.orden_visual ASC, ca.nombre ASC
            """)
        return ExecutiveDashboardRepository._fetch_all(query, [])

    @staticmethod
    def get_origen_options() -> list[str]:
        """Distinct non-empty lead origins actually present in the data."""
        query = sql.SQL("""
            SELECT DISTINCT TRIM(l.origen_lead) AS valor
            FROM tpi.leads l
            WHERE NULLIF(TRIM(l.origen_lead), '') IS NOT NULL
            ORDER BY valor ASC
            """)
        return [str(row["valor"]) for row in ExecutiveDashboardRepository._fetch_all(query, [])]

    @staticmethod
    def get_fuente_options() -> list[str]:
        """Distinct non-empty current sources actually present in the data."""
        query = sql.SQL("""
            SELECT DISTINCT TRIM(l.fuente_actual) AS valor
            FROM tpi.leads l
            WHERE NULLIF(TRIM(l.fuente_actual), '') IS NOT NULL
            ORDER BY valor ASC
            """)
        return [str(row["valor"]) for row in ExecutiveDashboardRepository._fetch_all(query, [])]

    @staticmethod
    def get_casos_por_estado_y_asesor(filters: DashboardFilters) -> list[dict[str, Any]]:
        """State x advisor matrix (unknown states preserved)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        cte = ExecutiveDashboardRepository._active_assignment_cte()
        query = sql.SQL("""
            WITH {cte}
            SELECT
                aa.id_asesor,
                ases.nombre AS nombre,
                l.estado_lead AS estado,
                COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            LEFT JOIN active_assignment aa ON aa.id_lead = l.id_lead
            LEFT JOIN tpi.asesores ases ON ases.id_asesor = aa.id_asesor
            {where}
            GROUP BY aa.id_asesor, ases.nombre, l.estado_lead
            ORDER BY n DESC, ases.nombre ASC, l.estado_lead ASC
            """).format(cte=sql.SQL(cte), where=sql.SQL(where))
        params = [ASSIGNMENT_ACTIVE_STATE, *dimension_params]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_distribucion_afp(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Current AFP distribution (via ``afp_id`` -> ``catalogo_afp``)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT
                COALESCE(ca.nombre, 'Sin AFP') AS categoria,
                COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            LEFT JOIN tpi.catalogo_afp ca ON ca.id = l.afp_id
            {where}
            GROUP BY COALESCE(ca.nombre, 'Sin AFP')
            ORDER BY n DESC, categoria ASC
            """).format(where=sql.SQL(where))
        return ExecutiveDashboardRepository._fetch_all(query, dimension_params)

    @staticmethod
    def get_distribucion_origen(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Current origin distribution (unknown/empty values kept safely)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT
                COALESCE(NULLIF(TRIM(l.origen_lead), ''), 'Sin origen') AS categoria,
                COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            {where}
            GROUP BY COALESCE(NULLIF(TRIM(l.origen_lead), ''), 'Sin origen')
            ORDER BY n DESC, categoria ASC
            """).format(where=sql.SQL(where))
        return ExecutiveDashboardRepository._fetch_all(query, dimension_params)

    @staticmethod
    def get_distribucion_fuente(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Current source distribution (unknown/empty values kept safely)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT
                COALESCE(NULLIF(TRIM(l.fuente_actual), ''), 'Sin fuente') AS categoria,
                COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            {where}
            GROUP BY COALESCE(NULLIF(TRIM(l.fuente_actual), ''), 'Sin fuente')
            ORDER BY n DESC, categoria ASC
            """).format(where=sql.SQL(where))
        return ExecutiveDashboardRepository._fetch_all(query, dimension_params)

    @staticmethod
    def get_leads_ingresados(filters: DashboardFilters) -> int:
        """Leads ingested inside the inclusive ``fecha_ingreso`` range (period activity)."""
        period_clauses, period_params = ExecutiveDashboardRepository._period_clauses(filters)
        if not period_clauses:
            return 0
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where([*period_clauses, *dimension_clauses])
        query = sql.SQL("""
            SELECT COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            {where}
            """).format(where=sql.SQL(where))
        params = [*period_params, *dimension_params]
        row = ExecutiveDashboardRepository._fetch_one(query, params) or {}
        return int(row.get("n") or 0)

    @staticmethod
    def get_evolucion(filters: DashboardFilters) -> list[dict[str, Any]]:
        """Ingestion series bucketed by the whitelisted granularity (period activity)."""
        period_clauses, period_params = ExecutiveDashboardRepository._period_clauses(filters)
        if not period_clauses:
            return []
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where([*period_clauses, *dimension_clauses])
        field = granularity_sql_field(filters.granularidad)
        query = sql.SQL("""
            SELECT
                date_trunc({field}, l.fecha_ingreso AT TIME ZONE 'America/Santiago') AS bucket,
                COUNT(DISTINCT l.id_lead) AS n
            FROM tpi.leads l
            {where}
            GROUP BY 1
            ORDER BY 1
            """).format(field=sql.Literal(field), where=sql.SQL(where))
        params = [*period_params, *dimension_params]
        return ExecutiveDashboardRepository._fetch_all(query, params)

    @staticmethod
    def get_funnel(filters: DashboardFilters, cutover: date | None) -> dict[str, Any]:
        """Observable transition funnel (period activity; post-cutover leads only)."""
        if cutover is None:
            return {
                "cutover": None,
                "cobertura_completa": False,
                "excluidos_pre_cutover": 0,
                "denominador": 0,
                "steps": [],
                "bases": {},
            }

        period_clauses, period_params = ExecutiveDashboardRepository._period_clauses(filters)
        if not period_clauses:
            return {
                "cutover": cutover.isoformat(),
                "cobertura_completa": True,
                "excluidos_pre_cutover": 0,
                "denominador": 0,
                "steps": [],
                "bases": {},
            }
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        post_clause = "l.fecha_ingreso >= %s"
        cutover_dt = datetime.combine(cutover, time.min, tzinfo=_CRM_TZ)

        steps_where = ExecutiveDashboardRepository._where(
            [post_clause, *period_clauses, *dimension_clauses]
        )
        steps_query = sql.SQL("""
            SELECT
                v.estado_anterior AS origen,
                v.estado_nuevo AS destino,
                COUNT(DISTINCT v.id_lead) AS n
            FROM tpi.v_historial_estado_lead v
            JOIN tpi.leads l ON l.id_lead = v.id_lead
            {steps_where}
            GROUP BY v.estado_anterior, v.estado_nuevo
            ORDER BY n DESC, v.estado_anterior ASC, v.estado_nuevo ASC
            """).format(steps_where=sql.SQL(steps_where))
        steps_params = [cutover_dt, *period_params, *dimension_params]
        steps = ExecutiveDashboardRepository._fetch_all(steps_query, steps_params)

        bases_where = ExecutiveDashboardRepository._where(
            [post_clause, *period_clauses, *dimension_clauses]
        )
        bases_query = sql.SQL("""
            SELECT v.estado_anterior AS origen, COUNT(DISTINCT v.id_lead) AS base
            FROM tpi.v_historial_estado_lead v
            JOIN tpi.leads l ON l.id_lead = v.id_lead
            {bases_where}
            GROUP BY v.estado_anterior
            """).format(bases_where=sql.SQL(bases_where))
        bases_params = [cutover_dt, *period_params, *dimension_params]
        bases = {
            row["origen"]: int(row["base"])
            for row in ExecutiveDashboardRepository._fetch_all(bases_query, bases_params)
        }

        coverage_where = ExecutiveDashboardRepository._where([*period_clauses, *dimension_clauses])
        coverage_query = sql.SQL("""
            SELECT
                COUNT(DISTINCT l.id_lead) FILTER (WHERE l.fecha_ingreso < %s) AS excluidos_pre_cutover,
                COUNT(DISTINCT l.id_lead) FILTER (WHERE l.fecha_ingreso >= %s) AS denominador
            FROM tpi.leads l
            {coverage_where}
            """).format(coverage_where=sql.SQL(coverage_where))
        coverage_params = [cutover_dt, cutover_dt, *period_params, *dimension_params]
        coverage = ExecutiveDashboardRepository._fetch_one(coverage_query, coverage_params) or {}

        return {
            "cutover": cutover.isoformat(),
            "cobertura_completa": True,
            "excluidos_pre_cutover": int(coverage.get("excluidos_pre_cutover") or 0),
            "denominador": int(coverage.get("denominador") or 0),
            "steps": steps,
            "bases": bases,
        }

    @staticmethod
    def get_tiempo_asignacion(filters: DashboardFilters) -> dict[str, Any]:
        """Mean days from ``fecha_ingreso`` to first assignment (observable via 007)."""
        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        where = ExecutiveDashboardRepository._where(dimension_clauses)
        query = sql.SQL("""
            SELECT
                COUNT(*) AS n,
                AVG(EXTRACT(EPOCH FROM (fa.first_ts - l.fecha_ingreso)) / 86400.0) AS media_dias
            FROM (
                SELECT a.id_lead, MIN(a.fecha_asignacion) AS first_ts
                FROM tpi.asignaciones a
                GROUP BY a.id_lead
            ) fa
            JOIN tpi.leads l ON l.id_lead = fa.id_lead
            {where}
            """).format(where=sql.SQL(where))
        row = ExecutiveDashboardRepository._fetch_one(query, dimension_params) or {}
        return {"n": int(row.get("n") or 0), "media_dias": row.get("media_dias")}

    @staticmethod
    def get_tiempo_primera_gestion(
        filters: DashboardFilters, cutover: date | None
    ) -> dict[str, Any]:
        """Mean days from ``fecha_ingreso`` to first management event (post-cutover).

        First management = earliest of the first human note and the first general
        state change; assignment is never counted. Pre-cutover leads lack complete
        state-change history and are excluded, so a missing cutover yields no metric.
        """
        if cutover is None:
            return {"n": 0, "media_dias": None}

        dimension_clauses, dimension_params = ExecutiveDashboardRepository._dimension_clauses(
            filters
        )
        post_clause = "l.fecha_ingreso >= %s"
        cutover_dt = datetime.combine(cutover, time.min, tzinfo=_CRM_TZ)
        where = ExecutiveDashboardRepository._where([post_clause, *dimension_clauses])
        query = sql.SQL("""
            WITH eventos AS (
                SELECT
                    l.id_lead,
                    l.fecha_ingreso,
                    (SELECT MIN({note_ts_expr})
                     FROM regexp_matches(l.comentarios, %s, 'g') AS m) AS primera_nota,
                    (SELECT MIN(v.fecha_hora)
                     FROM tpi.v_historial_estado_lead v
                     WHERE v.id_lead = l.id_lead) AS primer_cambio
                FROM tpi.leads l
                {where}
            ),
            gestion AS (
                SELECT id_lead, fecha_ingreso,
                       LEAST(primera_nota, primer_cambio) AS primera_gestion
                FROM eventos
                WHERE primera_nota IS NOT NULL OR primer_cambio IS NOT NULL
            )
            SELECT
                COUNT(*) AS n,
                AVG(EXTRACT(EPOCH FROM (primera_gestion - fecha_ingreso)) / 86400.0) AS media_dias
            FROM gestion
            """).format(note_ts_expr=sql.SQL(_NOTE_TS_EXPR), where=sql.SQL(where))
        params = [_NOTE_TS_PATTERN, cutover_dt, *dimension_params]
        row = ExecutiveDashboardRepository._fetch_one(query, params) or {}
        return {"n": int(row.get("n") or 0), "media_dias": row.get("media_dias")}

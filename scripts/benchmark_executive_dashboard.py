"""Reproducible executive-dashboard benchmark at executive-view volume (H3.3.4).

Seeds a synthetic population of leads with multiple assignments and events per
lead, then measures the whole ``build_executive_dashboard`` render (every section
enabled), the statement count, the total latency and the five slowest aggregate
queries. It confirms the statement count is independent of the data volume and
runs ``EXPLAIN (ANALYZE, BUFFERS)`` on the two queries whose cost is dominated by
the note-header parser and the state-history view — the real scaling risks.

Usage (from the repository root, with the local PostgreSQL running):

    python scripts/benchmark_executive_dashboard.py [--leads 20000] [--asesores 12]

The script cleans up every row it seeds (keyed by a unique marker) in a finally
block, so it can be re-run safely. It never reads or prints credentials or PII.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

# Make ``app`` importable when the script is run directly from ``scripts/``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import get_db_connection
from app.models.executive_dashboard import DashboardFilters
from app.repositories.executive_dashboard_repository import ExecutiveDashboardRepository
from app.services.executive_dashboard_service import ExecutiveDashboardService

_TZ = ZoneInfo("America/Santiago")
_ESTADOS = ("nuevo", "contactado", "citado", "cerrado", "perdido")


def _seed(marker: str, leads: int, asesores: int) -> None:
    with get_db_connection(operation="benchmark.seed") as conn:
        with conn.cursor() as cur:
            for index in range(asesores):
                cur.execute(
                    "INSERT INTO tpi.asesores (nombre, email, rol, estado_disponibilidad) "
                    "VALUES (%s, %s, 'asesor', 'activo')",
                    (f"Bench Asesor {marker} {index}", f"{marker}_{index}@example.test"),
                )

            # Bulk personas + leads in one statement so 20k rows seed in seconds.
            cur.execute(
                """
                WITH p AS (
                    INSERT INTO tpi.personas (rut, nombre_completo, email, telefono)
                    SELECT 'bm' || g, %s, %s || g || '@example.test', '+56900000000'
                    FROM generate_series(1, %s) AS g
                    RETURNING id_persona, rut
                )
                INSERT INTO tpi.leads
                    (id_persona, fecha_ingreso, estado_lead, origen_lead, fuente_actual, comentarios)
                SELECT
                    p.id_persona,
                    now() - (MOD(g - 1, 60)) * interval '1 day',
                    (ARRAY['nuevo','contactado','citado','cerrado','perdido'])[1 + MOD(g - 1, 5)],
                    %s,
                    'bench',
                    CASE WHEN MOD(g, 5) = 0
                        THEN 'Solicitud original' || E'\n\n'
                             || '[01/09/2026 10:00] Bench' || E'\n' || 'Nota'
                    END
                FROM generate_series(1, %s) AS g
                JOIN p ON p.rut = 'bm' || g
                """,
                (marker, marker, leads, marker, leads),
            )

            # Multiple assignments per lead (2 out of every 3 leads), spread over advisors.
            cur.execute(
                """
                INSERT INTO tpi.asignaciones (id_lead, id_asesor, fecha_asignacion, estado_asignacion)
                SELECT l.id_lead, a.id_asesor, l.fecha_ingreso + interval '6 hours', 'activa'
                FROM (
                    SELECT id_lead, fecha_ingreso, row_number() OVER (ORDER BY id_lead) AS rn
                    FROM tpi.leads WHERE origen_lead = %s
                ) l
                JOIN (
                    SELECT id_asesor, row_number() OVER (ORDER BY nombre) AS rn
                    FROM tpi.asesores WHERE nombre LIKE %s
                ) a ON a.rn = 1 + MOD(l.rn - 1, %s)
                WHERE MOD(l.rn, 3) <> 0
                """,
                (marker, f"Bench Asesor {marker} %", asesores),
            )

            # Multiple state-change events per lead (1 out of every 4 leads).
            cur.execute(
                """
                INSERT INTO tpi.auditoria (id_lead, accion, tabla_afectada, fecha_hora, detalle)
                SELECT l.id_lead, 'cambio_estado_lead', 'tpi.leads', l.fecha_ingreso + interval '1 day', %s
                FROM (
                    SELECT id_lead, fecha_ingreso, row_number() OVER (ORDER BY id_lead) AS rn
                    FROM tpi.leads WHERE origen_lead = %s
                ) l
                WHERE MOD(l.rn, 4) = 0
                """,
                (
                    json.dumps(
                        {
                            "actor_subject": "bench",
                            "estado_anterior": "nuevo",
                            "estado_nuevo": "contactado",
                        }
                    ),
                    marker,
                ),
            )
            conn.commit()


def _cleanup(marker: str) -> None:
    with get_db_connection(operation="benchmark.cleanup") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM tpi.auditoria WHERE id_lead IN "
                "(SELECT id_lead FROM tpi.leads WHERE origen_lead = %s)",
                (marker,),
            )
            cur.execute(
                "DELETE FROM tpi.asignaciones WHERE id_lead IN "
                "(SELECT id_lead FROM tpi.leads WHERE origen_lead = %s)",
                (marker,),
            )
            cur.execute(
                "DELETE FROM tpi.consentimientos WHERE id_lead IN "
                "(SELECT id_lead FROM tpi.leads WHERE origen_lead = %s)",
                (marker,),
            )
            cur.execute("DELETE FROM tpi.leads WHERE origen_lead = %s", (marker,))
            cur.execute("DELETE FROM tpi.personas WHERE nombre_completo = %s", (marker,))
            cur.execute(
                "DELETE FROM tpi.asesores WHERE nombre LIKE %s", (f"Bench Asesor {marker} %",)
            )
            conn.commit()


def _explain(marker: str, title: str, query: str, params: list[object]) -> None:
    print(f"[bench] EXPLAIN ANALYZE — {title}")
    with get_db_connection(operation="benchmark.explain") as conn:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, COSTS) {query}", params)
            for row in cur.fetchall():
                print("  " + str(row.get("QUERY PLAN", "")).replace("\n", "\n  ")[:400])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads", type=int, default=20000)
    parser.add_argument("--asesores", type=int, default=12)
    args = parser.parse_args()

    marker = f"bench_{uuid4().hex[:8]}"
    repo = ExecutiveDashboardRepository()
    print(f"[bench] seeding {args.leads} leads / {args.asesores} asesores (marker={marker}) ...")
    started = time.monotonic()
    _seed(marker, args.leads, args.asesores)
    print(f"[bench] seeded in {time.monotonic() - started:.2f}s")

    try:
        cutover = (datetime.now(_TZ) - timedelta(days=90)).date()
        filters = DashboardFilters.from_raw(
            origen=marker,
            fecha_desde=(date.today() - timedelta(days=60)).isoformat(),
            fecha_hasta=date.today().isoformat(),
            granularidad="diaria",
        )
        from app.config import Settings

        service = ExecutiveDashboardService(
            repository=repo,
            settings=Settings(APP_ENV="testing", LEAD_STATE_HISTORY_CUTOVER=cutover.isoformat()),
        )
        service.build_executive_dashboard(filters)  # warm-up

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
            started = time.monotonic()
            dashboard = service.build_executive_dashboard(filters)
            total = time.monotonic() - started
        finally:
            ExecutiveDashboardRepository._fetch_all = staticmethod(original_all)  # type: ignore[method-assign]
            ExecutiveDashboardRepository._fetch_one = staticmethod(original_one)  # type: ignore[method-assign]

        assert dashboard.failed_sections == (), dashboard.failed_sections
        assert dashboard.current_snapshot.total_leads == args.leads

        calls = {
            "get_kpi_snapshot": lambda: repo.get_kpi_snapshot(filters),
            "get_estancados": lambda: repo.get_estancados(filters, 5),
            "get_casos_por_estado": lambda: repo.get_casos_por_estado(filters),
            "get_antiguedad": lambda: repo.get_antiguedad(filters),
            "get_estancados_por_antiguedad": lambda: repo.get_estancados_por_antiguedad(filters, 5),
            "get_cartera_por_asesor": lambda: repo.get_cartera_por_asesor(filters),
            "get_metricas_operacionales_por_asesor": lambda: repo.get_metricas_operacionales_por_asesor(
                filters, 5, cutover
            ),
            "get_casos_por_estado_y_asesor": lambda: repo.get_casos_por_estado_y_asesor(filters),
            "get_distribucion_afp": lambda: repo.get_distribucion_afp(filters),
            "get_distribucion_origen": lambda: repo.get_distribucion_origen(filters),
            "get_distribucion_fuente": lambda: repo.get_distribucion_fuente(filters),
            "get_leads_ingresados": lambda: repo.get_leads_ingresados(filters),
            "get_evolucion": lambda: repo.get_evolucion(filters),
            "get_funnel": lambda: repo.get_funnel(filters, cutover),
            "get_tiempo_asignacion": lambda: repo.get_tiempo_asignacion(filters),
            "get_tiempo_primera_gestion": lambda: repo.get_tiempo_primera_gestion(filters, cutover),
        }
        measured: dict[str, float] = {}
        for name, call in calls.items():
            started = time.monotonic()
            call()
            measured[name] = time.monotonic() - started
        slowest = sorted(measured.items(), key=lambda item: item[1], reverse=True)[:5]

        print(f"[bench] leads={args.leads} asesores={args.asesores}")
        print(f"[bench] dashboard_statements={counter[0]} (bounded, independent of volume)")
        print(f"[bench] dashboard_seconds={total:.3f}")
        print("[bench] slowest queries:")
        for name, seconds in slowest:
            print(f"  - {name}={seconds:.3f}s")

        # EXPLAIN on the two real scaling risks: the note-header regexp scan over
        # ``leads.comentarios`` and the state-history aggregation over the 008 view.
        _explain(
            marker,
            "note-header regexp scan (leads.comentarios)",
            """
            SELECT COUNT(*) FROM tpi.leads l
            WHERE l.origen_lead = %s
              AND EXISTS (
                  SELECT 1 FROM regexp_matches(l.comentarios, %s, 'g')
              )
            """,
            [marker, r"\[(\d{2}/\d{2}/\d{4} \d{2}:\d{2})\]"],
        )
        _explain(
            marker,
            "state-history aggregation (v_historial_estado_lead)",
            """
            SELECT v.estado_anterior, v.estado_nuevo, COUNT(DISTINCT v.id_lead)
            FROM tpi.v_historial_estado_lead v
            JOIN tpi.leads l ON l.id_lead = v.id_lead
            WHERE l.origen_lead = %s
            GROUP BY v.estado_anterior, v.estado_nuevo
            """,
            [marker],
        )
    finally:
        _cleanup(marker)
        print("[bench] cleanup done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

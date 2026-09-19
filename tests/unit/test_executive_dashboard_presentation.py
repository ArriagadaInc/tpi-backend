"""Unit tests for the server-side chart/presentation layer of the dashboard.

Covers the rules that keep the charts honest: percentages always carry ``n`` and
their denominator, zero and single-observation series produce a valid chart
instead of a division by zero, and the funnel is withheld whenever coverage is
not complete.
"""

from __future__ import annotations

import pytest

from app.models.executive_dashboard import (
    FUNNEL_COBERTURA_PARCIAL,
    FUNNEL_SIN_CUTOVER,
    FUNNEL_SIN_PERIODO,
    FUNNEL_SIN_TRANSICIONES,
    AlertTarget,
    AntiguedadBucket,
    DistribucionBucket,
    EstadoBucket,
    EvolucionPoint,
    Funnel,
    FunnelStep,
)
from app.web.dashboard_presentation import (
    SCOPE_EXPLANATION,
    build_age_ladder,
    build_alert_views,
    build_categoria_rows,
    build_estado_rows,
    build_funnel_rows,
    build_timeseries,
    format_bucket_label,
    format_dias,
    format_int,
    format_percentage,
    format_ratio,
    funnel_unavailable_reason,
)

# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0"), (7, "7"), (1842, "1.842"), (1000000, "1.000.000"), (None, "—")],
)
def test_format_int_uses_chilean_thousand_separator(value, expected) -> None:
    assert format_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.326, "32,6%"), (1.0, "100,0%"), (0.0, "0,0%"), (None, "—")],
)
def test_format_percentage_uses_chilean_decimal_comma(value, expected) -> None:
    assert format_percentage(value) == expected


def test_format_dias_reports_missing_events_as_nd_never_zero() -> None:
    assert format_dias(None) == "N/D"
    assert format_dias(0.0) == "0,0 d"
    assert format_dias(1.25) == "1,2 d"


def test_percentage_always_carries_n_and_denominator() -> None:
    text = format_ratio(600, 1842, 0.3257)
    assert "600" in text
    assert "1.842" in text
    assert "32,6%" in text


def test_percentage_without_denominator_is_not_invented() -> None:
    text = format_ratio(5, 0, None)
    assert "%" not in text
    assert "—" in text


# --------------------------------------------------------------------------- #
# Bar lists
# --------------------------------------------------------------------------- #


def _estado(estado: str, label: str, n: int, total: int) -> EstadoBucket:
    return EstadoBucket(
        estado=estado,
        label=label,
        n=n,
        denominador=total,
        percentage=(round(n / total, 4) if total else None),
    )


def test_bar_widths_are_relative_to_the_observed_maximum() -> None:
    rows = build_estado_rows(
        [_estado("cerrado", "Cerrado", 600, 1000), _estado("nuevo", "Nuevo", 300, 1000)]
    )
    assert rows[0].width_pct == 100.0
    assert rows[1].width_pct == 50.0


def test_bar_widths_are_safe_when_every_value_is_zero() -> None:
    rows = build_estado_rows([_estado("cerrado", "Cerrado", 0, 0), _estado("nuevo", "Nuevo", 0, 0)])
    assert [row.width_pct for row in rows] == [0.0, 0.0]
    assert all(row.percentage_text == "—" for row in rows)


def test_unknown_state_keeps_its_raw_value_as_label() -> None:
    rows = build_estado_rows([_estado("estado_legacy", "estado_legacy", 3, 10)])
    assert rows[0].label == "estado_legacy"


def test_categoria_rows_preserve_repository_order() -> None:
    rows = build_categoria_rows(
        [
            DistribucionBucket("Habitat", 512, 1842, 0.2779),
            DistribucionBucket("Sin AFP", 430, 1842, 0.2334),
        ]
    )
    assert [row.label for row in rows] == ["Habitat", "Sin AFP"]


# --------------------------------------------------------------------------- #
# Age ladder
# --------------------------------------------------------------------------- #


def test_age_ladder_returns_the_five_approved_buckets_in_order() -> None:
    steps = build_age_ladder([AntiguedadBucket("0-2", 10, 10, 1.0)])
    assert [step.bucket for step in steps] == ["0-2", "3-7", "8-15", "16-30", "+30"]
    assert [step.level for step in steps] == [1, 2, 3, 4, 5]
    assert steps[1].n == 0


def test_age_ladder_flags_the_priority_bucket_with_text_not_only_colour() -> None:
    steps = build_age_ladder([AntiguedadBucket("+30", 81, 1041, 0.0778)])
    priority = [step for step in steps if step.bucket == "+30"][0]
    assert priority.flag == "Prioridad alta de revisión"
    assert all(step.flag is None for step in steps if step.bucket != "+30")


def test_age_ladder_is_empty_when_there_is_nothing_to_classify() -> None:
    assert build_age_ladder([]) == []


# --------------------------------------------------------------------------- #
# Timeseries
# --------------------------------------------------------------------------- #


def test_timeseries_is_none_without_observations() -> None:
    assert build_timeseries([], "diaria") is None


def test_timeseries_with_a_single_observation_has_no_polyline() -> None:
    series = build_timeseries([EvolucionPoint("2026-09-17", 7)], "diaria")
    assert series is not None
    assert series.polyline is None
    assert len(series.points) == 1
    assert "Una sola observación" in series.summary


def test_timeseries_with_all_zero_values_stays_on_the_baseline() -> None:
    points = [EvolucionPoint(f"2026-09-0{i}", 0) for i in range(1, 4)]
    series = build_timeseries(points, "diaria")
    assert series is not None
    assert {point.y for point in series.points} == {series.baseline_y}


def test_timeseries_never_fabricates_points() -> None:
    points = [EvolucionPoint("2026-09-01", 4), EvolucionPoint("2026-09-05", 9)]
    series = build_timeseries(points, "diaria")
    assert series is not None
    assert [point.n for point in series.points] == [4, 9]


def test_timeseries_axis_anchors_keep_extreme_labels_inside_the_viewbox() -> None:
    points = [EvolucionPoint(f"2026-09-{day:02d}", day) for day in range(1, 15)]
    series = build_timeseries(points, "diaria")
    assert series is not None
    assert series.axis_ticks[0].anchor == "start"
    assert series.axis_ticks[-1].anchor == "end"


@pytest.mark.parametrize(
    ("granularidad", "expected"),
    [
        ("diaria", "01/09/2026"),
        ("semanal", "Semana del 01/09/2026"),
        ("mensual", "09/2026"),
    ],
)
def test_bucket_labels_follow_the_selected_granularity(granularidad, expected) -> None:
    assert format_bucket_label("2026-09-01", granularidad) == expected


def test_unparseable_bucket_label_is_kept_verbatim() -> None:
    assert format_bucket_label("no-es-fecha", "diaria") == "no-es-fecha"


# --------------------------------------------------------------------------- #
# Funnel availability
# --------------------------------------------------------------------------- #


def _funnel(**overrides) -> Funnel:
    base = {
        "scope": "period_activity",
        "cutover": "2026-09-05",
        "cobertura_completa": True,
        "excluidos_pre_cutover": 0,
        "denominador": 214,
        "steps": [FunnelStep("nuevo", "contactado", "Nuevo", "Contactado", 162, 214, 0.757)],
        "periodo_activo": True,
    }
    base.update(overrides)
    return Funnel(**base)  # type: ignore[arg-type]


def test_funnel_is_available_with_complete_coverage() -> None:
    funnel = _funnel()
    assert funnel.disponible is True
    rows = build_funnel_rows(funnel)
    assert len(rows) == 1
    assert "162" in rows[0].value_text
    assert "214" in rows[0].value_text
    assert "75,7%" in rows[0].value_text
    assert funnel_unavailable_reason(funnel) is None


def test_funnel_is_withheld_without_cutover() -> None:
    funnel = _funnel(cutover=None)
    assert funnel.disponible is False
    assert funnel.motivo_no_disponible == FUNNEL_SIN_CUTOVER
    assert build_funnel_rows(funnel) == []
    assert "corte de la migración 008" in (funnel_unavailable_reason(funnel) or "")


def test_funnel_is_withheld_without_a_period() -> None:
    funnel = _funnel(periodo_activo=False)
    assert funnel.motivo_no_disponible == FUNNEL_SIN_PERIODO
    assert build_funnel_rows(funnel) == []


def test_funnel_is_withheld_when_coverage_is_partial() -> None:
    funnel = _funnel(excluidos_pre_cutover=412)
    assert funnel.motivo_no_disponible == FUNNEL_COBERTURA_PARCIAL
    assert build_funnel_rows(funnel) == []
    assert "historia completa" in (funnel_unavailable_reason(funnel) or "")


def test_funnel_is_withheld_without_observable_transitions() -> None:
    funnel = _funnel(steps=[])
    assert funnel.motivo_no_disponible == FUNNEL_SIN_TRANSICIONES
    assert build_funnel_rows(funnel) == []


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #


def test_alert_views_carry_real_links_and_self_sufficient_text() -> None:
    views = build_alert_views(
        [
            AlertTarget("sin_asignar", 37, {"sin_asignar": True}),
            AlertTarget("estancados", 58, {"estancado": True}),
        ],
        {"sin_asignar": "/leads?sin_asignar=1", "estancados": "/leads?estancado=1"},
        5,
    )
    assert views[0].href == "/leads?sin_asignar=1"
    assert "37 leads sin asignar" in views[0].text
    assert views[1].href == "/leads?estancado=1"
    assert "58 leads estancados" in views[1].text
    assert "5 días corridos" in views[1].text


def test_scope_explanation_separates_snapshot_from_period() -> None:
    assert "situación actual" in SCOPE_EXPLANATION
    assert "período seleccionado" in SCOPE_EXPLANATION

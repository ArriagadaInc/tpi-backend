"""Server-side presentation layer for the Executive Dashboard (H3.3.4, Parte B).

Every chart of the dashboard is produced here, in Python, from the typed contract
in :mod:`app.models.executive_dashboard`: bar widths, SVG geometry, textual
summaries and accessible table rows. The templates only iterate over the objects
returned by this module, so no metric is ever recomputed, interpolated or
reinterpreted in Jinja or in JavaScript.

Rules enforced in this module:

- A percentage never appears without its ``n`` and its denominator.
- A zero or missing denominator yields ``—`` / ``N/D``, never a fabricated ratio.
- Chart scales are derived from the observed maximum; a maximum of zero produces
  a flat, valid chart instead of a division by zero.
- The only values placed in inline styles are bounded geometric numbers (0..100
  percentages), emitted through a CSS custom property.
- Labels come straight from the data and are escaped by the template; unknown or
  long values are never truncated silently.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from app.models.executive_dashboard import (
    ANTIGUEDAD_BUCKETS,
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
)

# Visible explanation of the two scopes. Matches the contract in
# app/models/executive_dashboard.py: dimension filters apply to both scopes, the
# date range only restricts period activity.
SCOPE_EXPLANATION = (
    "Las métricas de cartera representan la situación actual. El período "
    "seleccionado se aplica a ingresos, evolución y métricas de actividad."
)

AGE_PRIORITY_BUCKET = "+30"
AGE_PRIORITY_FLAG = "Prioridad alta de revisión"

_NO_VALUE = "—"
_NO_DATA = "N/D"

# Timeseries geometry (user units of the SVG viewBox; the element itself is fluid).
_TS_WIDTH = 720.0
_TS_HEIGHT = 220.0
_TS_PAD_LEFT = 8.0
_TS_PAD_RIGHT = 8.0
_TS_PAD_TOP = 16.0
_TS_BASELINE = 180.0
_TS_MAX_TICKS = 6


# --------------------------------------------------------------------------- #
# Chilean number formatting (thousands ".", decimals ",")
# --------------------------------------------------------------------------- #


def format_int(value: int | float | None) -> str:
    """Format an integer with Chilean thousand separators (``1.842``)."""
    if value is None:
        return _NO_VALUE
    return f"{int(value):,}".replace(",", ".")


def format_decimal(value: float | None, decimals: int = 1) -> str:
    """Format a decimal with a Chilean decimal comma, or ``—`` when missing."""
    if value is None:
        return _NO_VALUE
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def format_percentage(fraction: float | None) -> str:
    """Format a 0..1 fraction as ``32,6%``; ``—`` when the ratio does not exist."""
    if fraction is None:
        return _NO_VALUE
    return f"{format_decimal(fraction * 100, 1)}%"


def format_dias(value: float | None) -> str:
    """Format a duration in days; ``N/D`` when the event never happened."""
    if value is None:
        return _NO_DATA
    return f"{format_decimal(value, 1)} d"


def format_ratio(n: int, denominador: int, fraction: float | None) -> str:
    """Render a percentage always accompanied by ``n`` and its denominator."""
    if denominador <= 0:
        return f"{format_int(n)} ({_NO_VALUE})"
    return f"{format_int(n)} · {format_percentage(fraction)} ({format_int(n)}/{format_int(denominador)})"


def _width_pct(n: int, maximo: int) -> float:
    """Bar width relative to the largest observed value; safe when the max is 0."""
    if maximo <= 0 or n <= 0:
        return 0.0
    return round(min(100.0, 100.0 * n / maximo), 1)


# --------------------------------------------------------------------------- #
# Horizontal bar lists (estado, AFP, origen, fuente)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BarRow:
    label: str
    n: int
    denominador: int
    percentage: float | None
    width_pct: float
    value_text: str
    percentage_text: str
    href: str | None = None


def _bar_rows(rows: Sequence[tuple[str, int, int, float | None, str | None]]) -> list[BarRow]:
    maximo = max((n for _, n, _, _, _ in rows), default=0)
    return [
        BarRow(
            label=label,
            n=n,
            denominador=denominador,
            percentage=fraction,
            width_pct=_width_pct(n, maximo),
            value_text=format_ratio(n, denominador, fraction),
            percentage_text=format_percentage(fraction),
            href=href,
        )
        for label, n, denominador, fraction, href in rows
    ]


def build_estado_rows(
    buckets: Sequence[EstadoBucket],
    href_for_estado: Callable[[str], str] | None = None,
) -> list[BarRow]:
    """Cases by state, in the repository's reproducible order (n desc, estado asc).

    ``href_for_estado`` turns each bar into a real link that applies that state as
    a filter, as specified in the approved design. It is optional so the rows can
    be built (and tested) without a request context.
    """
    return _bar_rows(
        [
            (
                b.label or b.estado,
                b.n,
                b.denominador,
                b.percentage,
                href_for_estado(b.estado) if href_for_estado is not None else None,
            )
            for b in buckets
        ]
    )


def build_categoria_rows(buckets: Sequence[DistribucionBucket]) -> list[BarRow]:
    """MVP category distribution (AFP / origen / fuente), reproducible order.

    These bars are not links: the AFP filter keys on the catalog id, which the
    aggregate does not carry, and the ``Sin origen`` / ``Sin fuente`` buckets are
    synthesized labels with no filterable value. A link is only rendered where it
    would actually reproduce the view.
    """
    return _bar_rows([(b.categoria, b.n, b.denominador, b.percentage, None) for b in buckets])


# --------------------------------------------------------------------------- #
# Age ladder (signature element)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AgeStep:
    bucket: str
    label: str
    n: int
    denominador: int
    percentage: float | None
    width_pct: float
    level: int
    flag: str | None
    value_text: str


_AGE_LABELS: dict[str, str] = {
    "0-2": "0–2 días",
    "3-7": "3–7 días",
    "8-15": "8–15 días",
    "16-30": "16–30 días",
    "+30": "Más de 30 días",
}


def build_age_ladder(buckets: Sequence[AntiguedadBucket]) -> list[AgeStep]:
    """Return the five approved buckets in fixed order, zero-filling the absent ones.

    Returns an empty list when there is nothing to classify, so the caller can
    render the empty state instead of a ladder of zeros.
    """
    if not buckets:
        return []
    by_bucket = {bucket.bucket: bucket for bucket in buckets}
    denominador = next((bucket.denominador for bucket in buckets), 0)
    maximo = max((bucket.n for bucket in buckets), default=0)
    steps: list[AgeStep] = []
    for level, key in enumerate(ANTIGUEDAD_BUCKETS, start=1):
        found = by_bucket.get(key)
        n = found.n if found is not None else 0
        fraction = found.percentage if found is not None else None
        steps.append(
            AgeStep(
                bucket=key,
                label=_AGE_LABELS.get(key, key),
                n=n,
                denominador=denominador,
                percentage=fraction,
                width_pct=_width_pct(n, maximo),
                level=level,
                flag=AGE_PRIORITY_FLAG if key == AGE_PRIORITY_BUCKET else None,
                value_text=format_ratio(n, denominador, fraction),
            )
        )
    return steps


# --------------------------------------------------------------------------- #
# Timeseries (evolution)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    label: str
    n: int
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class AxisTick:
    """One x-axis label. ``anchor`` keeps the first and last labels inside the viewBox."""

    label: str
    x: float
    anchor: str


@dataclass(frozen=True, slots=True)
class Timeseries:
    width: float
    height: float
    baseline_y: float
    points: list[SeriesPoint]
    polyline: str | None
    axis_ticks: list[AxisTick]
    maximo: int
    minimo: int
    total: int
    summary: str


_GRANULARITY_NOUN: dict[str, str] = {
    "diaria": "diaria",
    "semanal": "semanal",
    "mensual": "mensual",
}


def format_bucket_label(raw: str, granularidad: str) -> str:
    """Render a bucket key in Chilean format; unknown keys are kept verbatim."""
    try:
        parsed = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return str(raw)
    if granularidad == "mensual":
        return parsed.strftime("%m/%Y")
    if granularidad == "semanal":
        return f"Semana del {parsed.strftime('%d/%m/%Y')}"
    return parsed.strftime("%d/%m/%Y")


def build_timeseries(points: Sequence[EvolucionPoint], granularidad: str) -> Timeseries | None:
    """Build the SVG geometry for the ingestion series.

    Returns ``None`` when there is no observation: no point is ever fabricated to
    fill a chart. One single observation renders as a single marker (no line),
    and an all-zero series renders flat on the baseline instead of dividing by
    zero.
    """
    if not points:
        return None

    values = [max(0, int(point.n)) for point in points]
    maximo = max(values)
    minimo = min(values)
    plot_width = _TS_WIDTH - _TS_PAD_LEFT - _TS_PAD_RIGHT
    plot_height = _TS_BASELINE - _TS_PAD_TOP
    step = plot_width / (len(points) - 1) if len(points) > 1 else 0.0

    series: list[SeriesPoint] = []
    for index, point in enumerate(points):
        n = values[index]
        x = _TS_PAD_LEFT + (index * step if len(points) > 1 else plot_width / 2)
        ratio = (n / maximo) if maximo > 0 else 0.0
        y = _TS_BASELINE - (ratio * plot_height)
        series.append(
            SeriesPoint(
                label=format_bucket_label(point.bucket, granularidad),
                n=n,
                x=round(x, 2),
                y=round(y, 2),
            )
        )

    polyline = " ".join(f"{item.x},{item.y}" for item in series) if len(series) > 1 else None
    stride = max(1, -(-len(series) // _TS_MAX_TICKS))
    tick_points = series[::stride]
    if tick_points[-1] is not series[-1]:
        tick_points = [*tick_points, series[-1]]
    ticks = [
        AxisTick(
            label=item.label,
            x=item.x,
            # Anchoring the extremes inward keeps long dates inside the viewBox
            # instead of clipping them at the edges.
            anchor=(
                "start"
                if item is series[0]
                else "end" if item is series[-1] and len(series) > 1 else "middle"
            ),
        )
        for item in tick_points
    ]

    total = sum(values)
    noun = _GRANULARITY_NOUN.get(granularidad, granularidad)
    if len(series) == 1:
        summary = (
            f"Una sola observación {noun}: {format_int(series[0].n)} leads ingresados "
            f"el {series[0].label}."
        )
    else:
        summary = (
            f"Evolución {noun} con {format_int(len(series))} observaciones entre "
            f"{series[0].label} y {series[-1].label}: {format_int(total)} leads "
            f"ingresados, mínimo {format_int(minimo)} y máximo {format_int(maximo)} "
            f"por punto."
        )

    return Timeseries(
        width=_TS_WIDTH,
        height=_TS_HEIGHT,
        baseline_y=_TS_BASELINE,
        points=series,
        polyline=polyline,
        axis_ticks=ticks,
        maximo=maximo,
        minimo=minimo,
        total=total,
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# Funnel
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FunnelRow:
    """One observable transition.

    Field names mirror :class:`BarRow` so both render through the same macro;
    ``denominador`` is the transition base (``COUNT(DISTINCT id_lead)`` of the
    origin state) and ``percentage`` is the observed rate.
    """

    label: str
    n: int
    denominador: int
    percentage: float | None
    width_pct: float
    value_text: str
    percentage_text: str
    href: str | None = None


_FUNNEL_REASONS: dict[str, str] = {
    FUNNEL_SIN_CUTOVER: (
        "No hay fecha de corte de la migración 008 configurada, por lo que ninguna "
        "transición tiene cobertura histórica verificable. No se calculan tasas."
    ),
    FUNNEL_SIN_PERIODO: (
        "El funnel se calcula sobre la actividad de un período. Selecciona un rango "
        "de fechas para evaluar las transiciones observables."
    ),
    FUNNEL_COBERTURA_PARCIAL: (
        "Parte de los leads del período ingresó antes del corte de la migración 008 "
        "y no tiene historia completa de transiciones. Se omiten las tasas en lugar "
        "de calcularlas sobre una base incompleta."
    ),
    FUNNEL_SIN_TRANSICIONES: (
        "No se registraron transiciones de estado observables en el período "
        "seleccionado, por lo que no hay tasas que mostrar."
    ),
}

FUNNEL_UNAVAILABLE_TITLE = "No disponible con cobertura suficiente"


def build_funnel_rows(funnel: Funnel) -> list[FunnelRow]:
    """Observable transition rows; empty when the funnel must not be shown."""
    if not funnel.disponible:
        return []
    maximo = max((step.n for step in funnel.steps), default=0)
    return [
        FunnelRow(
            label=f"{step.origen_label or step.origen} → {step.destino_label or step.destino}",
            n=step.n,
            denominador=step.base,
            percentage=step.rate,
            width_pct=_width_pct(step.n, maximo),
            value_text=format_ratio(step.n, step.base, step.rate),
            percentage_text=format_percentage(step.rate),
            href=None,
        )
        for step in funnel.steps
    ]


def funnel_unavailable_reason(funnel: Funnel) -> str | None:
    """Human explanation of why the funnel is withheld, or ``None`` when shown."""
    motivo = funnel.motivo_no_disponible
    if motivo is None:
        return None
    return _FUNNEL_REASONS.get(motivo, _FUNNEL_REASONS[FUNNEL_SIN_TRANSICIONES])


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AlertView:
    key: str
    count: int
    count_text: str
    text: str
    tone: str
    icon: str
    href: str
    link_label: str


_ALERT_COPY: dict[str, tuple[str, str, str]] = {
    "sin_asignar": ("warning", "⚠", "sin asignar"),
    "estancados": ("danger", "⏱", "estancados"),
}


def build_alert_views(
    alerts: Sequence[AlertTarget],
    hrefs: dict[str, str],
    estancamiento_dias: int,
) -> list[AlertView]:
    """Turn alert targets into chips with real, reproducible listing links."""
    views: list[AlertView] = []
    for alert in alerts:
        tone, icon, noun = _ALERT_COPY.get(alert.key, ("warning", "•", alert.key))
        if alert.key == "estancados":
            text = (
                f"{format_int(alert.count)} leads {noun} "
                f"(≥{estancamiento_dias} días corridos sin movimiento operativo)"
            )
        else:
            text = f"{format_int(alert.count)} leads {noun}"
        views.append(
            AlertView(
                key=alert.key,
                count=alert.count,
                count_text=format_int(alert.count),
                text=text,
                tone=tone,
                icon=icon,
                href=hrefs.get(alert.key, "/leads"),
                link_label=f"Ver leads {noun}",
            )
        )
    return views

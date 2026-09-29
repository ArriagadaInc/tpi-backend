"""Executive dashboard route (H3.3.4, Parte B) with server-side access control.

Access is exclusively server-side and limited to ``ceo``/``cto`` (superusers).
Any other authenticated role and any anonymous request receives a real ``403``
before any dashboard query executes; no dashboard data is ever rendered or
serialized for an unauthorized request.

The route assembles the typed contract, turns it into the render-ready view
objects of :mod:`app.web.dashboard_presentation` and renders the approved design
(``docs/H3_3_4_DASHBOARD_DESIGN.md``, alternative C). All chart geometry is
computed here, server-side: the page carries no chart JavaScript and no embedded
dataset.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth.models import AuthenticatedUser, UserRole, is_superuser
from app.models.executive_dashboard import DashboardFilters
from app.services.executive_dashboard_service import ExecutiveDashboardService
from app.web.dashboard_presentation import (
    FUNNEL_UNAVAILABLE_TITLE,
    SCOPE_EXPLANATION,
    build_age_ladder,
    build_alert_views,
    build_categoria_rows,
    build_estado_rows,
    build_funnel_rows,
    build_timeseries,
    format_dias,
    format_int,
    format_percentage,
    funnel_unavailable_reason,
)

router = APIRouter()

_CRM_TZ = ZoneInfo("America/Santiago")
_logger = logging.getLogger(__name__)

_TEMPLATE = "executive_dashboard.html"

# Dimension filters shared between the dashboard and the /leads listing, so an
# alert count and the listing it links to always describe the same population.
_LISTING_PARAM_BY_FILTER: dict[str, str] = {
    "estado": "estado_lead",
    "asesor": "asesor",
    "afp": "afp_id",
    "origen": "origen",
    "fuente": "fuente",
}


def require_executive_access(request: Request) -> AuthenticatedUser:
    """Return the authenticated superuser or raise a real 403 (fail closed).

    The query is not executed on rejection: callers must obtain the user through
    this function before building the dashboard.
    """
    user = _require_web_user(request)
    if user is None or not is_superuser(user.role):
        raise HTTPException(status_code=403, detail="Acceso no autorizado")
    return user


def _require_web_user(request: Request) -> AuthenticatedUser | None:
    user = request.session.get("web_user")
    if not isinstance(user, dict):
        return None
    subject = str(user.get("subject", "")).strip()
    username = str(user.get("username", "")).strip()
    display_name = str(user.get("display_name", "")).strip()
    role = str(user.get("role", "")).strip()
    if not subject or not username or not display_name or not role:
        return None
    return AuthenticatedUser(
        subject=subject,
        username=username,
        display_name=display_name,
        role=cast(UserRole, role),
    )


def _resolve_service(request: Request) -> ExecutiveDashboardService:
    service = getattr(request.app.state, "executive_dashboard_service", None)
    if isinstance(service, ExecutiveDashboardService):
        return service
    return ExecutiveDashboardService()


def _raw_filters(request: Request) -> dict[str, str]:
    params = request.query_params
    keys = (
        "fecha_desde",
        "fecha_hasta",
        "granularidad",
        "estado",
        "asesor",
        "afp",
        "origen",
        "fuente",
    )
    return {key: (params.get(key) or "") for key in keys}


def _build_filters(raw: dict[str, str]) -> DashboardFilters:
    return DashboardFilters.from_raw(
        fecha_desde=raw["fecha_desde"] or None,
        fecha_hasta=raw["fecha_hasta"] or None,
        granularidad=raw["granularidad"] or None,
        estado=raw["estado"] or None,
        asesor=raw["asesor"] or None,
        afp=raw["afp"] or None,
        origen=raw["origen"] or None,
        fuente=raw["fuente"] or None,
    )


def _listing_query(filters: DashboardFilters) -> dict[str, str]:
    """Dimension filters translated to the ``/leads`` listing parameter names.

    The date range is deliberately not propagated: alerts belong to the current
    snapshot scope, which the period selector never restricts.
    """
    values = {
        "estado": filters.estado,
        "asesor": str(filters.asesor) if filters.asesor is not None else None,
        "afp": str(filters.afp) if filters.afp is not None else None,
        "origen": filters.origen,
        "fuente": filters.fuente,
    }
    return {_LISTING_PARAM_BY_FILTER[key]: value for key, value in values.items() if value}


def _alert_hrefs(filters: DashboardFilters) -> dict[str, str]:
    base = _listing_query(filters)
    return {
        "sin_asignar": "/leads?" + urlencode({**base, "sin_asignar": "1"}),
        "estancados": "/leads?" + urlencode({**base, "estancado": "1"}),
    }


def _quick_ranges(raw: dict[str, str], today: date) -> list[dict[str, Any]]:
    """Reproducible period shortcuts resolved to explicit dates server-side."""
    preserved = {
        key: value
        for key, value in raw.items()
        if value and key not in {"fecha_desde", "fecha_hasta"}
    }
    definitions = (
        ("Últimos 30 días", today - timedelta(days=29), today),
        ("Últimos 90 días", today - timedelta(days=89), today),
        ("Este año", date(today.year, 1, 1), today),
    )
    ranges: list[dict[str, Any]] = []
    for label, desde, hasta in definitions:
        query = {
            **preserved,
            "fecha_desde": desde.isoformat(),
            "fecha_hasta": hasta.isoformat(),
        }
        ranges.append(
            {
                "label": label,
                "href": "/dashboard?" + urlencode(query),
                "active": raw["fecha_desde"] == desde.isoformat()
                and raw["fecha_hasta"] == hasta.isoformat(),
            }
        )
    return ranges


def _estado_href_builder(raw: dict[str, str]) -> Callable[[str], str]:
    """Build a reproducible dashboard URL that applies one state as a filter.

    Every other selected filter is preserved, so the link reproduces the current
    view narrowed to that state.
    """
    preserved = {key: value for key, value in raw.items() if value and key != "estado"}

    def href(estado: str) -> str:
        return "/dashboard?" + urlencode({**preserved, "estado": estado})

    return href


def _period_label(filters: DashboardFilters) -> str:
    if not filters.period_active:
        return "Sin período seleccionado"
    desde = filters.fecha_desde.strftime("%d/%m/%Y") if filters.fecha_desde else "inicio"
    hasta = filters.fecha_hasta.strftime("%d/%m/%Y") if filters.fecha_hasta else "hoy"
    return f"{desde} — {hasta}"


def _base_context(request: Request, user: AuthenticatedUser) -> dict[str, Any]:
    return {
        "request": request,
        "selected_user": user,
        "can_view_executive_dashboard": True,
        "active_nav": "dashboard",
        "page_title": "Dashboard Ejecutivo",
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "scope_explanation": SCOPE_EXPLANATION,
    }


def _empty_filter_options() -> dict[str, list[Any]]:
    return {"estados": [], "asesores": [], "afps": [], "origenes": [], "fuentes": []}


@router.get("/dashboard", response_class=HTMLResponse)
def executive_dashboard(request: Request) -> HTMLResponse:
    user = require_executive_access(request)
    raw = _raw_filters(request)
    today = date.today()

    service = _resolve_service(request)
    context = _base_context(request, user)
    context["raw_filters"] = raw
    context["quick_ranges"] = _quick_ranges(raw, today)

    try:
        filters = _build_filters(raw)
    except ValueError as exc:
        # Invalid filter input: the page renders with the submitted values and a
        # clear message, and no dashboard query runs.
        context.update(
            {
                "filter_error": str(exc),
                "dashboard": None,
                "filter_options": _empty_filter_options(),
                "period_label": "Sin período seleccionado",
            }
        )
        return cast(
            HTMLResponse,
            request.app.state.templates.TemplateResponse(
                request, _TEMPLATE, context, status_code=400
            ),
        )

    try:
        dashboard = service.build_executive_dashboard(filters)
    except Exception as exc:  # noqa: BLE001 - surfaced as a safe global error state
        _logger.warning(
            "executive dashboard unavailable error_type=%s",
            type(exc).__name__,
        )
        context.update(
            {
                "dashboard": None,
                "global_error": (
                    "No fue posible cargar el Dashboard Ejecutivo en este momento. "
                    "Vuelve a intentarlo en unos minutos."
                ),
                "filter_options": _empty_filter_options(),
                "period_label": _period_label(filters),
            }
        )
        return cast(
            HTMLResponse,
            request.app.state.templates.TemplateResponse(
                request, _TEMPLATE, context, status_code=503
            ),
        )

    try:
        filter_options = service.get_filter_options()
    except Exception as exc:  # noqa: BLE001 - the dashboard still renders
        _logger.warning(
            "executive dashboard filter options unavailable error_type=%s",
            type(exc).__name__,
        )
        filter_options = _empty_filter_options()

    snapshot = dashboard.current_snapshot
    period = dashboard.period_activity
    context.update(
        {
            "dashboard": dashboard,
            "filters": filters,
            "filter_options": filter_options,
            "period_label": _period_label(filters),
            "estancamiento_dias": service.estancamiento_dias,
            "cutover": service.cutover,
            "alerts": build_alert_views(
                dashboard.alerts, _alert_hrefs(filters), service.estancamiento_dias
            ),
            "estado_rows": build_estado_rows(snapshot.casos_por_estado, _estado_href_builder(raw)),
            "age_steps": build_age_ladder(snapshot.antiguedad),
            "afp_rows": build_categoria_rows(snapshot.distribucion_afp),
            "origen_rows": build_categoria_rows(snapshot.distribucion_origen),
            "fuente_rows": build_categoria_rows(snapshot.distribucion_fuente),
            "timeseries": build_timeseries(period.evolucion, filters.granularidad),
            "funnel_rows": build_funnel_rows(period.funnel),
            "funnel_unavailable_title": FUNNEL_UNAVAILABLE_TITLE,
            "funnel_unavailable_reason": funnel_unavailable_reason(period.funnel),
            "asesor_rows": snapshot.cartera_por_asesor,
            "kpi_total": format_int(snapshot.total_leads),
            "kpi_ingresados": format_int(period.leads_ingresados),
            "kpi_cartera_activa": format_int(snapshot.cartera_activa),
            "kpi_cartera_activa_pct": format_percentage(
                (snapshot.cartera_activa / snapshot.total_leads)
                if snapshot.total_leads > 0
                else None
            ),
            "kpi_sin_asignar": format_int(snapshot.sin_asignar),
            "tiempo_asignacion_text": format_dias(period.tiempo_asignacion.media_dias),
            "tiempo_gestion_text": format_dias(period.tiempo_primera_gestion.media_dias),
        }
    )

    return cast(
        HTMLResponse,
        request.app.state.templates.TemplateResponse(request, _TEMPLATE, context),
    )

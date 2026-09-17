"""Executive dashboard route (H3.3.4, Parte B) with server-side access control.

Access is exclusively server-side and limited to ``ceo``/``cto`` (superusers).
Any other authenticated role and any anonymous request receives a real ``403``
before any dashboard query executes; no dashboard data is ever rendered or
serialized for an unauthorized request.

The productive HTML template is intentionally out of scope for this data-layer
session: the route builds the typed contract and renders a minimal placeholder
so the access boundary can be exercised end-to-end. The visual session replaces
the placeholder with the approved design (``docs/H3_3_4_DASHBOARD_DESIGN.md``).
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.auth.models import AuthenticatedUser, UserRole, is_superuser
from app.models.executive_dashboard import DashboardFilters
from app.services.executive_dashboard_service import ExecutiveDashboardService

router = APIRouter()


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


def _build_filters(request: Request) -> DashboardFilters:
    params = request.query_params
    return DashboardFilters.from_raw(
        fecha_desde=params.get("fecha_desde") or None,
        fecha_hasta=params.get("fecha_hasta") or None,
        granularidad=params.get("granularidad") or None,
        estado=params.get("estado") or None,
        asesor=params.get("asesor") or None,
        afp=params.get("afp") or None,
        origen=params.get("origen") or None,
        fuente=params.get("fuente") or None,
    )


@router.get("/dashboard", response_class=HTMLResponse)
def executive_dashboard(request: Request) -> HTMLResponse:
    user = require_executive_access(request)
    try:
        filters = _build_filters(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = _resolve_service(request)
    dashboard = service.build_executive_dashboard(filters)

    return cast(
        HTMLResponse,
        request.app.state.templates.TemplateResponse(
            request,
            "executive_dashboard.html",
            {
                "request": request,
                "selected_user": user,
                "dashboard": dashboard,
                "page_title": "Dashboard Ejecutivo",
            },
        ),
    )

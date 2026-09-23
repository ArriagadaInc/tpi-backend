"""CRM leads routes for the web UX."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from app.auth.models import AuthenticatedUser, UserRole, is_superuser
from app.models.crm_states import normalize_crm_state_for_display
from app.models.lead_assignment import (
    LeadAssignmentConflictError,
    LeadAssignmentValidationError,
)
from app.services.xlsx_export import ExportLimitExceededError
from app.web.dependencies import build_service_for_web
from app.web.presentation import (
    build_timeline_items,
    parse_lead_comments,
    state_history_cutover_notice,
)

router = APIRouter()
_WRITE_ROLES = {"tester", "advisor", "operations", "admin"}
_CLEANUP_ROLES = {"tester", "admin"}
_FLASH_KEY = "_tpi_web_flash"
_CSRF_KEY = "_tpi_web_csrf_token"


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
        advisor_id=_parse_session_advisor_id(user.get("advisor_id")),
    )


def _parse_session_advisor_id(value: Any) -> UUID | None:
    """Parse the session ``advisor_id``; a malformed value fails closed to ``None``.

    The session value is derived server-side at login from the authenticated user,
    never from client input, but it is still validated on read.
    """
    if value is None:
        return None
    try:
        return UUID(str(value).strip())
    except (ValueError, AttributeError):
        return None


def _can_write(user: AuthenticatedUser | None) -> bool:
    if not user:
        return False
    return is_superuser(user.role) or user.role in _WRITE_ROLES


def _can_view_executive_dashboard(user: AuthenticatedUser | None) -> bool:
    """Whether to render the dashboard nav link.

    This only hides a link: /dashboard enforces the real 403 server-side.
    """
    return bool(user) and is_superuser(user.role)  # type: ignore[union-attr]


def _can_export_xlsx(user: AuthenticatedUser | None) -> bool:
    """Whether to render the export button.

    This only hides a button: /leads/export.xlsx enforces the real server-side
    authorization (403 for any non-ceo/cto authenticated role).
    """
    return bool(user) and is_superuser(user.role)  # type: ignore[union-attr]


def _export_filename(now: datetime | None = None) -> str:
    """Server-generated, predictable download filename (no user-controlled input)."""
    timestamp = now or datetime.now(UTC)
    return f"leads_export_{timestamp.strftime('%Y%m%d_%H%M%S')}.xlsx"


def _export_error_html(message: str) -> str:
    """Minimal, self-contained error page for the export (clear message, no PII)."""
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Exportacion XLSX</title></head><body style='font-family:sans-serif;"
        "max-width:40rem;margin:3rem auto;padding:0 1rem'>"
        f"<h1>Exportacion XLSX</h1><p>{message}</p>"
        "<p><a href='/leads'>Volver a Leads</a></p></body></html>"
    )


def _active_filter_labels(sin_asignar: bool, estancado: bool) -> list[str]:
    """Visible chips describing the operational filters coming from the dashboard."""
    labels: list[str] = []
    if sin_asignar:
        labels.append("Solo leads sin asignar")
    if estancado:
        labels.append("Solo leads estancados")
    return labels


def _can_cleanup(user: AuthenticatedUser | None) -> bool:
    if not user:
        return False
    return is_superuser(user.role) or user.role in _CLEANUP_ROLES


def _build_query_url(base_path: str, params: dict[str, Any]) -> str:
    query = {key: value for key, value in params.items() if value not in (None, "", [])}
    return f"{base_path}?{urlencode(query, doseq=True)}" if query else base_path


def _sanitize_return_to(return_to: str | None) -> str | None:
    if not return_to:
        return None

    candidate = return_to.strip()
    if not candidate or candidate.startswith("//"):
        return None

    parts = urlsplit(candidate)
    if parts.scheme or parts.netloc:
        return None
    if not parts.path.startswith("/leads"):
        return None

    return _build_query_url(
        parts.path, {key: values for key, values in parse_qs(parts.query).items()}
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_uuid(value: str | None) -> UUID | None:
    """Accept only a well-formed UUID; anything else is ignored (fail closed)."""
    if not value:
        return None
    try:
        return UUID(str(value).strip())
    except (ValueError, AttributeError):
        return None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _parse_flag(value: str | None) -> bool:
    """Whitelisted truthy values for boolean query params."""
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "si", "sí", "on", "yes"}


def _parse_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def _resolve_service(request: Request):
    return getattr(request.app.state, "web_service", None) or build_service_for_web()


def _get_csrf_token(request: Request) -> str:
    token = request.session.get(_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_KEY] = token
    return token


def _validate_csrf_token(request: Request, token: str | None) -> bool:
    current = request.session.get(_CSRF_KEY)
    return (
        isinstance(current, str) and bool(current) and isinstance(token, str) and token == current
    )


def _set_flash(request: Request, message: str, kind: str = "success") -> None:
    request.session[_FLASH_KEY] = {"message": message, "kind": kind}


def _pop_flash(request: Request) -> dict[str, str] | None:
    payload = request.session.pop(_FLASH_KEY, None)
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    kind = payload.get("kind")
    return {
        "message": message.strip(),
        "kind": kind if isinstance(kind, str) else "success",
    }


def _resolve_board_data(request: Request) -> dict[str, Any]:
    service = _resolve_service(request)
    user = _require_web_user(request)
    params = request.query_params
    page = _parse_int(params.get("page"), 1)
    page_size = 10
    search = params.get("search") or None
    afp_id = params.get("afp_id") or None
    estado_raw = params.get("estado_lead") or None
    estado = normalize_crm_state_for_display(estado_raw) or estado_raw
    sort_by = params.get("sort_by") or "created_at"
    sort_direction = params.get("sort_direction") or "desc"
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    asesor_id = _parse_uuid(params.get("asesor"))
    origen = _normalize_text(params.get("origen"))
    fuente = _normalize_text(params.get("fuente"))
    sin_asignar = _parse_flag(params.get("sin_asignar"))
    estancado = _parse_flag(params.get("estancado"))

    # PII masking is unconditionally role-based: only can_view_full_pii
    # (ceo/cto) bypasses masking. The environment flag does not override roles.
    effective_mask_pii = not (user is not None and service.can_view_full_pii(user))

    board = service.get_crm_bandeja(
        page=page,
        page_size=page_size,
        search=search,
        estado_lead=estado,
        afp_id=afp_id,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_direction=sort_direction,
        masked=True,
        user=user,
        asesor_id=asesor_id,
        origen_lead=origen,
        fuente_actual=fuente,
        sin_asignar=sin_asignar,
        estancado=estancado,
    )
    afp_options = service.get_catalogo_afp()
    estado_options = service.get_crm_estado_lead_options()
    current_query = {
        "search": search,
        "afp_id": afp_id,
        "estado_lead": estado,
        "date_from": params.get("date_from") or None,
        "date_to": params.get("date_to") or None,
        "sort_by": sort_by,
        "sort_direction": sort_direction,
        "asesor": str(asesor_id) if asesor_id is not None else None,
        "origen": origen,
        "fuente": fuente,
        "sin_asignar": "1" if sin_asignar else None,
        "estancado": "1" if estancado else None,
    }
    current_board_url = _build_query_url("/leads", current_query | {"page": page})

    board_solicitudes = []
    for row in list(board.get("solicitudes") or []):
        if isinstance(row, dict):
            item = dict(row)
            lead_id = item.get("id_lead")
            if lead_id:
                item["detail_url"] = _build_query_url(
                    f"/leads/{lead_id}",
                    {"return_to": current_board_url},
                )
            board_solicitudes.append(item)
        else:
            board_solicitudes.append(row)

    board = {**board, "solicitudes": board_solicitudes}

    def _url_for_page(page_number: int) -> str | None:
        if page_number < 1:
            return None
        query: dict[str, str | int] = {
            key: value for key, value in current_query.items() if value not in (None, "")
        }
        query["page"] = page_number
        return _build_query_url("/leads", query)

    return {
        "board": board,
        "mask_pii": effective_mask_pii,
        "afp_options": afp_options,
        "estado_options": estado_options,
        "current_filters": {
            "search": search or "",
            "afp_id": afp_id or "",
            "estado_lead": estado or "",
            "date_from": params.get("date_from") or "",
            "date_to": params.get("date_to") or "",
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "asesor": str(asesor_id) if asesor_id is not None else "",
            "origen": origen or "",
            "fuente": fuente or "",
            "sin_asignar": sin_asignar,
            "estancado": estancado,
        },
        "active_filter_labels": _active_filter_labels(sin_asignar, estancado),
        "page_title": "Leads",
        "selected_user": user,
        "can_view_executive_dashboard": _can_view_executive_dashboard(user),
        "can_export_xlsx": _can_export_xlsx(user),
        "export_url": _build_query_url("/leads/export.xlsx", current_query),
        "active_nav": "leads",
        "can_write": _can_write(user),
        "csrf_token": _get_csrf_token(request),
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "web_cleanup_enabled": bool(getattr(request.app.state, "web_cleanup_enabled", False)),
        "simulator_url": getattr(request.app.state, "web_simulator_url", None),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "service_mode": "real" if hasattr(service, "repository") else "mock",
        "pagination_prev_url": _url_for_page(page - 1) if page > 1 else None,
        "pagination_next_url": (
            _url_for_page(page + 1) if page < int(board.get("total_pages") or 0) else None
        ),
    }


def _build_return_to_url(request: Request) -> str:
    params = {
        key: value
        for key, value in request.query_params.items()
        if key != "return_to" and value not in (None, "")
    }
    return _build_query_url("/leads", params)


def _build_detail_redirect_url(request: Request, lead_id: str) -> str:
    return_to = _sanitize_return_to(request.query_params.get("return_to")) or _build_return_to_url(
        request
    )
    return _build_query_url(f"/leads/{lead_id}", {"return_to": return_to})


def _build_detail_redirect_url_from_value(lead_id: str, return_to: str | None) -> str:
    clean_return_to = _sanitize_return_to(return_to) or "/leads"
    return _build_query_url(f"/leads/{lead_id}", {"return_to": clean_return_to})


def _resolve_detail_context(
    request: Request,
    lead_id: str,
    *,
    lead: dict[str, Any] | None = None,
    status_code: int = 200,
    lead_not_found: bool = False,
    error_message: str | None = None,
) -> tuple[dict[str, Any], int]:
    service = _resolve_service(request)
    user = _require_web_user(request)
    # PII masking is unconditionally role-based in detail view.
    # Always use the masked variant which respects can_view_full_pii.
    selected_lead = lead
    if selected_lead is None:
        selected_lead = service.get_solicitud_detalle_masked(lead_id, user=user)

    state_options = service.get_crm_estado_lead_options_for_update()
    can_assign = bool(user and service.can_assign_lead(user))
    parsed_comments = parse_lead_comments(
        (selected_lead or {}).get("comentarios") if selected_lead else None
    )
    timeline_items: list[dict[str, Any]] = []
    if selected_lead is not None:
        events = service.get_lead_assignment_events(lead_id)
        state_changes = service.get_lead_state_change_events(lead_id)
        timeline_items = build_timeline_items(events, parsed_comments.notes, state_changes)

    app_settings = getattr(request.app.state, "settings", None)
    cutover = getattr(app_settings, "lead_state_history_cutover", None)
    context = {
        "request": request,
        "selected_user": user,
        "can_view_executive_dashboard": _can_view_executive_dashboard(user),
        "active_nav": "leads",
        "can_write": _can_write(user),
        "can_assign": can_assign,
        "can_cleanup": _can_cleanup(user),
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "web_cleanup_enabled": bool(getattr(request.app.state, "web_cleanup_enabled", False)),
        "simulator_url": getattr(request.app.state, "web_simulator_url", None),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "mask_pii": not (user is not None and service.can_view_full_pii(user)),
        "selected_lead": selected_lead,
        "selected_lead_id": lead_id,
        "selected_lead_state_canonical": normalize_crm_state_for_display(
            (selected_lead or {}).get("estado_lead") if selected_lead else None
        ),
        "lead_status_options": state_options,
        "assignment_asesores": (
            service.get_asesores_disponibles_para_asignacion() if can_assign else []
        ),
        "comment_view": parsed_comments,
        "timeline_items": timeline_items,
        "state_history_cutover_notice": state_history_cutover_notice(cutover),
        "csrf_token": _get_csrf_token(request),
        "return_to_url": _sanitize_return_to(request.query_params.get("return_to"))
        or _build_return_to_url(request),
        "flash_message": _pop_flash(request),
        "error_message": error_message,
        "lead_not_found": lead_not_found,
    }
    return context, status_code


@router.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    context = _resolve_board_data(request)
    template = request.app.state.templates.TemplateResponse(
        request, "leads.html", {"request": request, **context}
    )
    return template


@router.get("/leads/board", response_class=HTMLResponse)
def leads_board(request: Request):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    context = _resolve_board_data(request)
    return request.app.state.templates.TemplateResponse(
        request,
        "leads_board.html",
        {"request": request, **context},
    )


@router.get("/leads/clear", response_class=HTMLResponse)
def leads_clear(request: Request):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    return RedirectResponse(url="/leads", status_code=303)


@router.get("/leads/export.xlsx")
def leads_export(request: Request):
    user = _require_web_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=307)
    if not is_superuser(user.role):
        return PlainTextResponse("No autorizado", status_code=403)

    service = _resolve_service(request)
    params = request.query_params
    estado_raw = params.get("estado_lead") or None
    estado = normalize_crm_state_for_display(estado_raw) or estado_raw

    try:
        content = service.export_leads_xlsx(
            user,
            search=params.get("search") or None,
            estado_lead=estado,
            afp_id=params.get("afp_id") or None,
            date_from=_parse_date(params.get("date_from")),
            date_to=_parse_date(params.get("date_to")),
            sort_by=params.get("sort_by") or "created_at",
            sort_direction=params.get("sort_direction") or "desc",
            asesor_id=_parse_uuid(params.get("asesor")),
            origen_lead=_normalize_text(params.get("origen")),
            fuente_actual=_normalize_text(params.get("fuente")),
            sin_asignar=_parse_flag(params.get("sin_asignar")),
            estancado=_parse_flag(params.get("estancado")),
        )
    except ExportLimitExceededError as exc:
        message = (
            f"La exportacion supera el limite de {exc.limit} filas "
            f"({exc.total} coinciden). Acota los filtros e intenta nuevamente."
        )
        return HTMLResponse(_export_error_html(message), status_code=413)
    except (ValueError, TypeError):
        return HTMLResponse(
            _export_error_html("No fue posible generar la exportacion."),
            status_code=400,
        )
    except Exception:
        # Fail closed without a traceback: the exception message could embed a
        # cell value (PII). The client gets a clear page; nothing is logged here.
        return HTMLResponse(
            _export_error_html("No fue posible generar la exportacion. Intenta nuevamente."),
            status_code=500,
        )

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{_export_filename()}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(request: Request, lead_id: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    service = _resolve_service(request)
    user = _require_web_user(request)
    # PII masking is unconditionally role-based; always use masked variant.
    lead = service.get_solicitud_detalle_masked(lead_id, user=user)
    if not lead:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead=None,
            status_code=404,
            lead_not_found=True,
            error_message="No encontramos el lead solicitado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=404,
        )
    context, _ = _resolve_detail_context(request, lead_id, lead=lead)
    return request.app.state.templates.TemplateResponse(
        request,
        "lead_detail.html",
        context,
    )


@router.post("/leads/{lead_id}/assign", response_class=HTMLResponse)
async def lead_assign(request: Request, lead_id: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    user = _require_web_user(request)
    service = _resolve_service(request)
    if not user or not service.can_assign_lead(user):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Esta accion no esta disponible para este usuario.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La sesion de seguridad ha expirado. Recarga la pagina e intenta nuevamente.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    id_asesor = str(form.get("id_asesor") or "").strip()
    if not id_asesor:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Debes seleccionar un ejecutivo valido.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    try:
        assigned = service.assign_lead(lead_id, id_asesor, actor=user)
    except LeadAssignmentConflictError:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="El lead ya tiene una asignacion activa.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=409,
        )
    except (LeadAssignmentValidationError, TypeError, ValueError, PermissionError):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="No fue posible asignar el lead.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    if not assigned:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=True,
            error_message="No encontramos el lead solicitado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=404,
        )

    return_to = str(form.get("return_to") or "")
    _set_flash(request, "Lead asignado correctamente.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to),
        status_code=303,
    )


@router.post("/leads/{lead_id}/status", response_class=HTMLResponse)
async def lead_status_update(request: Request, lead_id: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    user = _require_web_user(request)
    if not user or not _can_write(user):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Esta accion no esta disponible para este usuario.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La sesion de seguridad ha expirado. Recarga la pagina e intenta nuevamente.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    estado_lead = str(form.get("estado_lead") or "").strip()
    if not estado_lead:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Debes seleccionar un estado valido.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    service = _resolve_service(request)
    try:
        updated = service.update_lead_status(lead_id, estado_lead, actor=user)
    except ValueError:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="No fue posible actualizar el estado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    if not updated:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=True,
            error_message="No encontramos el lead solicitado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=404,
        )

    return_to = str(form.get("return_to") or "")
    _set_flash(request, "Estado actualizado correctamente.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to),
        status_code=303,
    )


@router.post("/leads/{lead_id}/comments", response_class=HTMLResponse)
async def lead_comment_append(request: Request, lead_id: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    user = _require_web_user(request)
    if not user or not _can_write(user):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Esta accion no esta disponible para este usuario.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La sesion de seguridad ha expirado. Recarga la pagina e intenta nuevamente.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )

    comment_text = str(form.get("new_comment") or "").strip()
    if not comment_text:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Debes ingresar una nota de seguimiento.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    service = _resolve_service(request)
    try:
        updated = service.append_lead_comment(
            lead_id,
            comment_text,
            actor=user,
        )
    except ValueError:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La nota de seguimiento no es valida.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    if not updated:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=True,
            error_message="No encontramos el lead solicitado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=404,
        )

    return_to = str(form.get("return_to") or "")
    _set_flash(request, "Seguimiento agregado.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to),
        status_code=303,
    )


@router.post("/leads/{lead_id}/cleanup")
async def cleanup_lead(request: Request, lead_id: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    user = _require_web_user(request)
    if not _can_cleanup(user):
        return request.app.state.templates.TemplateResponse(
            request,
            "leads.html",
            {
                "request": request,
                **_resolve_board_data(request),
                "cleanup_message": "Esta accion no esta disponible para este usuario.",
            },
            status_code=403,
        )
    service = _resolve_service(request)
    if not service.is_test_lead_cleanup_enabled():
        return request.app.state.templates.TemplateResponse(
            request,
            "leads.html",
            {
                "request": request,
                **_resolve_board_data(request),
                "cleanup_message": "Cleanup no disponible.",
            },
            status_code=403,
        )

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        return request.app.state.templates.TemplateResponse(
            request,
            "leads.html",
            {
                "request": request,
                **_resolve_board_data(request),
                "cleanup_message": "La sesion de seguridad ha expirado. Recarga la pagina e intenta nuevamente.",
            },
            status_code=403,
        )

    result = service.delete_test_lead(lead_id)
    board_context = _resolve_board_data(request)
    return request.app.state.templates.TemplateResponse(
        request,
        "leads.html",
        {
            "request": request,
            **board_context,
            "cleanup_result": result,
        },
    )

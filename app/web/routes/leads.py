"""CRM leads routes for the web UX."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from app.attachments.validation import (
    ATTACHMENT_MIME_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_FILES_PER_NOTE,
    MAX_REQUEST_BYTES,
    AttachmentValidationError,
    ValidatedAttachment,
    validate_attachment_content,
)
from app.auth.models import AuthenticatedUser, UserRole, is_superuser
from app.models.crm_states import normalize_crm_state_for_display
from app.models.lead_assignment import (
    LeadAssignmentConflictError,
    LeadAssignmentValidationError,
)
from app.services.xlsx_export import ExportLimitExceededError
from app.web.agenda_presentation import build_lead_agenda_context, resolve_agenda_service
from app.web.dependencies import build_service_for_web
from app.web.presentation import (
    build_timeline_items,
    parse_lead_comments,
    state_history_cutover_notice,
)

router = APIRouter()
_WRITE_ROLES = {"tester", "advisor", "coordinator", "operations", "admin"}
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


_ATTACHMENT_EXTENSIONS = {"pdf": "pdf", "pdfe": "pdf", "png": "png", "jpg": "jpg"}


def _attachments_enabled(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    return bool(getattr(settings, "attachments_enabled", False))


def _attachments_allow_pdf_embedded_files(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    return bool(getattr(settings, "attachments_allow_pdf_embedded_files", True))


def _attachment_not_found() -> PlainTextResponse:
    """404 genérico para las causas de adjunto no disponible en el borrado."""
    return PlainTextResponse("No disponible", status_code=404)


def _attachment_unavailable_page() -> HTMLResponse:
    """Página amable para un adjunto no disponible (AC-6).

    La misma respuesta para un lead no visible, un uuid sin marca y un objeto
    no disponible: no revela cuál de las causas aplica.
    """
    return HTMLResponse(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Adjunto no disponible</title></head><body>"
        "<p>Este adjunto no esta disponible: puede estar escaneandose, "
        "bloqueado o eliminado.</p></body></html>",
        status_code=404,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


_ATTACHMENT_REJECTION_REASONS = {
    "empty_file": "el archivo esta vacio",
    "too_large": "supera el limite de 10 MB",
    "unsupported_type": "el tipo no esta permitido (solo PDF, PNG y JPEG)",
    "invalid_content": "el contenido esta danado o incompleto",
    "too_many_pixels": "la imagen tiene dimensiones excesivas",
    "pdf_encrypted": "PDF cifrado",
    "pdf_javascript": "PDF con JavaScript o acciones automaticas",
    "pdf_launch": "PDF con acciones automaticas",
    "pdf_embedded_files": "PDF con archivos incrustados",
}

_PDF_RESAVE_SUGGESTION = "vuelve a guardarlo con «Imprimir y Guardar como PDF»"


def _attachment_rejection_reason(code: str) -> str:
    reason = _ATTACHMENT_REJECTION_REASONS.get(code, "no es valido")
    if code in {"pdf_encrypted", "pdf_javascript", "pdf_launch"}:
        return f"{reason}; {_PDF_RESAVE_SUGGESTION}"
    return reason


def _build_attachment_rejection_message(rejections: list[tuple[int, int, str]]) -> str:
    """Arma el mensaje con la posición y el motivo de cada archivo rechazado (AC-1)."""
    parts = [
        f"Archivo {position} de {total}: {_attachment_rejection_reason(code)}"
        for position, total, code in rejections
    ]
    return "No se subio ningun archivo. " + "; ".join(parts) + "."


def _attachment_download_filename(verified_type: str) -> str:
    extension = _ATTACHMENT_EXTENSIONS.get(verified_type, "bin")
    return f"adjunto-{datetime.now(UTC).strftime('%Y%m%d')}.{extension}"


def _attachment_content_security_policy(verified_type: str) -> str:
    # El visor de PDF integrado del navegador no funciona con sandbox (AC-6);
    # la excepción queda documentada en docs/ADJUNTOS_COMENTARIOS_DISENO.md.
    if verified_type in ("pdf", "pdfe"):
        return "default-src 'none'"
    return "default-src 'none'; sandbox"


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


_SCAN_STATUS_WINDOW = timedelta(minutes=30)
_SCAN_STATUS_MAX_QUERIES = 20
_SCAN_STATUS_TZ = ZoneInfo("America/Santiago")


def _attach_attachment_scan_statuses(
    service: Any, lead_id: str, timeline_items: list[dict[str, Any]]
) -> None:
    """Lee la etiqueta de GuardDuty de los adjuntos recientes, con tope (AC-5).

    Solo los adjuntos de notas de los últimos 30 minutos (hora de la cabecera de
    la nota, America/Santiago) consultan S3; los más antiguos conservan la imagen
    o el enlace sin tocar S3. Nunca se superan 20 consultas por página.
    """
    now = datetime.now(_SCAN_STATUS_TZ)
    queries = 0
    for item in timeline_items:
        if item["kind"] != "note":
            continue
        note_ts = item["timestamp"]
        if now - note_ts > _SCAN_STATUS_WINDOW:
            continue
        for attachment in item["attachments"]:
            if queries >= _SCAN_STATUS_MAX_QUERIES:
                return
            getter = getattr(service, "get_attachment_scan_status", None)
            if getter is None:
                return
            attachment["scan_status"] = getter(lead_id, attachment["attachment_id"])
            queries += 1


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

    state_options = service.get_crm_estado_lead_options_for_update(actor=user)
    can_assign = bool(user and service.can_assign_lead(user))
    parsed_comments = parse_lead_comments(
        (selected_lead or {}).get("comentarios") if selected_lead else None
    )
    timeline_items: list[dict[str, Any]] = []
    if selected_lead is not None:
        events = service.get_lead_assignment_events(lead_id)
        state_changes = service.get_lead_state_change_events(lead_id)
        simulations = service.get_lead_simulation_events(lead_id)
        timeline_items = build_timeline_items(
            events, parsed_comments.notes, state_changes, simulations
        )
        if _attachments_enabled(request):
            _attach_attachment_scan_statuses(service, lead_id, timeline_items)

    app_settings = getattr(request.app.state, "settings", None)
    cutover = getattr(app_settings, "lead_state_history_cutover", None)
    context = {
        "request": request,
        "selected_user": user,
        "can_view_executive_dashboard": _can_view_executive_dashboard(user),
        "can_simulate": bool(user) and (is_superuser(user.role) or user.role in {"executive", "coordinator"}),  # type: ignore[union-attr]
        "active_nav": "leads",
        "can_write": _can_write(user),
        "can_assign": can_assign,
        "can_cleanup": _can_cleanup(user),
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "web_cleanup_enabled": bool(getattr(request.app.state, "web_cleanup_enabled", False)),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "mask_pii": not (user is not None and service.can_view_full_pii(user)),
        "attachments_enabled": _attachments_enabled(request),
        "can_delete_attachments": user is not None and service.can_view_full_pii(user),
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
    if selected_lead is not None and user is not None:
        context["agenda"] = build_lead_agenda_context(
            resolve_agenda_service(request), lead_id, user
        )
    else:
        context["agenda"] = None
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
    except PermissionError:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Este perfil no puede fijar el estado seleccionado.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=403,
        )
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

    service = _resolve_service(request)
    attachments_enabled = _attachments_enabled(request)

    # Límites de tamaño de la petición (AC-4). El Content-Length declarado corta
    # la subida en 413 antes de leer el cuerpo.
    content_length_raw = request.headers.get("content-length")
    try:
        content_length = int(content_length_raw) if content_length_raw else None
    except ValueError:
        content_length = None

    if content_length is not None and content_length > MAX_REQUEST_BYTES:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La peticion excede el limite de tamano permitido.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=413,
        )

    # Sin Content-Length válido, max_part_size de Starlette solo limita los campos
    # de texto, no las partes de archivo (MultiPartParser.on_part_data): una
    # petición con Transfer-Encoding: chunked escribiría todo el cuerpo a un
    # temporal en disco antes de que la validación por contenido la rechace. Con
    # adjuntos activos se rechaza con 411 antes de leer el cuerpo (hallazgo F-1).
    if attachments_enabled and content_length is None:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="La peticion no declara su tamano; recarga la pagina e intenta nuevamente.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=411,
        )

    try:
        form = await request.form(
            # +1: la parte `files` vacía que el navegador envía cuando no se elige
            # archivo (filename="") también cuenta para el límite de Starlette; la
            # descartamos después y aplicamos abajo el límite real de 5 archivos.
            max_files=MAX_FILES_PER_NOTE + 1,
            max_fields=30,
            max_part_size=MAX_ATTACHMENT_BYTES + 1,
        )
    except MultiPartException as exc:
        if "Too many files" in str(getattr(exc, "message", "")):
            error_message = "Superaste el maximo de 5 archivos."
        else:
            error_message = "Un archivo excede el limite de 10 MB."
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message=error_message,
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

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

    # La parte `files` vacía del navegador (filename="") no es un archivo real:
    # se descarta para que la nota siga la ruta de solo texto. Un archivo con
    # nombre y 0 bytes sigue teniendo filename y se rechaza como empty_file.
    files = (
        [item for item in form.getlist("files") if isinstance(item, UploadFile) and item.filename]
        if attachments_enabled
        else []
    )

    if len(files) > MAX_FILES_PER_NOTE:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message="Superaste el maximo de 5 archivos.",
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    if not files:
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

    # Ruta con adjuntos: el alcance del asesor se comprueba antes de leer o subir
    # ningún archivo (AC-4), con la misma respuesta 404 que la nota de hoy.
    if not service.can_append_comment_to_lead(lead_id, user):
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

    limiter = getattr(request.app.state, "attachment_rate_limiter", None)
    if limiter is not None:
        for _upload in files:
            if not limiter.allow(user.subject):
                context, _ = _resolve_detail_context(
                    request,
                    lead_id,
                    lead_not_found=False,
                    error_message="Demasiados adjuntos. Intenta nuevamente mas tarde.",
                )
                return request.app.state.templates.TemplateResponse(
                    request,
                    "lead_detail.html",
                    context,
                    status_code=429,
                )

    attachments: list[ValidatedAttachment] = []
    rejections: list[tuple[int, int, str]] = []
    total_files = len(files)
    for position, upload in enumerate(files, start=1):
        content = await upload.read()
        try:
            attachments.append(
                validate_attachment_content(
                    content,
                    allow_pdf_embedded_files=_attachments_allow_pdf_embedded_files(request),
                )
            )
        except AttachmentValidationError as exc:
            rejections.append((position, total_files, exc.code))

    # Todo o nada: si falla uno, no se sube ninguno y se informan todos los
    # fallos juntos, cada uno con su posición y su motivo concreto (AC-1).
    if rejections:
        for _position, _total, code in rejections:
            service.audit_attachment_rejection(lead_id, actor=user, rejection_code=code)
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message=_build_attachment_rejection_message(rejections),
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
        )

    try:
        updated = service.append_lead_comment_with_attachments(
            lead_id,
            comment_text,
            attachments,
            actor=user,
        )
    except AttachmentValidationError as exc:
        context, _ = _resolve_detail_context(
            request,
            lead_id,
            lead_not_found=False,
            error_message=_attachment_rejection_reason(exc.code),
        )
        return request.app.state.templates.TemplateResponse(
            request,
            "lead_detail.html",
            context,
            status_code=400,
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


@router.get("/leads/{lead_id}/adjuntos/{attachment_uuid}")
def attachment_view_or_download(request: Request, lead_id: str, attachment_uuid: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    if not _attachments_enabled(request):
        return _attachment_unavailable_page()

    try:
        parsed_uuid = UUID(str(attachment_uuid).strip())
    except (ValueError, AttributeError):
        return _attachment_unavailable_page()

    user = _require_web_user(request)
    service = _resolve_service(request)
    as_download = _parse_flag(request.query_params.get("descargar"))
    stored = service.get_attachment(lead_id, parsed_uuid, actor=user, as_download=as_download)
    if stored is None:
        return _attachment_unavailable_page()

    verified_type = stored.metadata.get("verified_type")
    if verified_type not in ATTACHMENT_MIME_TYPES:
        return _attachment_unavailable_page()

    disposition_type = "attachment" if as_download else "inline"
    return Response(
        content=stored.content,
        media_type=ATTACHMENT_MIME_TYPES[verified_type],
        headers={
            "Content-Disposition": (
                f'{disposition_type}; filename="{_attachment_download_filename(verified_type)}"'
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": _attachment_content_security_policy(verified_type),
            "Referrer-Policy": "no-referrer",
        },
    )


@router.post("/leads/{lead_id}/adjuntos/{attachment_uuid}/eliminar")
async def attachment_delete(request: Request, lead_id: str, attachment_uuid: str):
    if not _require_web_user(request):
        return RedirectResponse(url="/login", status_code=307)
    if not _attachments_enabled(request):
        return _attachment_not_found()
    user = _require_web_user(request)
    if not user or not is_superuser(user.role):
        return PlainTextResponse("No autorizado", status_code=403)

    try:
        parsed_uuid = UUID(str(attachment_uuid).strip())
    except (ValueError, AttributeError):
        return _attachment_not_found()

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        return PlainTextResponse("No autorizado", status_code=403)

    service = _resolve_service(request)
    deleted = service.delete_attachment(lead_id, parsed_uuid, actor=user)
    if not deleted:
        return _attachment_not_found()

    _set_flash(request, "Adjunto eliminado.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, str(form.get("return_to") or "")),
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

"""Rutas web de la agenda de reuniones (CRM-AGENDA-2-CALENDARIO).

GET /agenda muestra la vista de semana (con navegacion anterior/siguiente/hoy) y la
vista de lista de proximas reuniones, con filtro por responsable. Las acciones de
agendar, reagendar, cancelar, marcar realizada y marcar no asistio viven bajo
``/leads/{lead_id}/agenda/*`` y comparten el token CSRF, la autorizacion server-side y
el fallo cerrado del resto del CRM. La autorizacion la resuelve el servicio con la base;
la interfaz solo guia (AC-2, AC-3, AC-6).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.models import AuthenticatedUser
from app.database.errors import DatabaseAppError
from app.models.agenda import (
    AGENDA_TZ,
    AgendaConflictError,
    AgendaNotFoundError,
    AgendaPermissionError,
    AgendaValidationError,
)
from app.web.agenda_presentation import (
    HORA_FIN,
    HORA_INI,
    agrupar_por_dia,
    build_week_grid,
    color_map,
    rango_label,
    resolve_agenda_service,
    resumen_semana,
)
from app.web.routes.leads import (
    _build_detail_redirect_url_from_value,
    _build_query_url,
    _can_view_executive_dashboard,
    _get_csrf_token,
    _parse_date,
    _parse_uuid,
    _pop_flash,
    _require_web_user,
    _resolve_detail_context,
    _set_flash,
    _validate_csrf_token,
)

router = APIRouter()

_DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _render_detail_error(request: Request, lead_id: str, message: str, status_code: int) -> Any:
    context, _ = _resolve_detail_context(
        request,
        lead_id,
        lead_not_found=(status_code == 404),
        error_message=message,
    )
    return request.app.state.templates.TemplateResponse(
        request, "lead_detail.html", context, status_code=status_code
    )


def _handle_agenda_error(request: Request, lead_id: str, exc: Exception) -> Any:
    if isinstance(exc, AgendaNotFoundError):
        return _render_detail_error(request, lead_id, str(exc), 404)
    if isinstance(exc, AgendaPermissionError):
        return _render_detail_error(request, lead_id, str(exc), 403)
    if isinstance(exc, AgendaConflictError):
        return _render_detail_error(request, lead_id, str(exc), 409)
    if isinstance(exc, (AgendaValidationError, ValueError, TypeError)):
        return _render_detail_error(request, lead_id, str(exc), 400)
    if isinstance(exc, DatabaseAppError):
        return _render_detail_error(
            request, lead_id, "No fue posible completar la operación de la agenda.", 400
        )
    raise exc


def _monday_of(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


@router.get("/agenda", response_class=HTMLResponse)
def agenda_page(request: Request):
    user = _require_web_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=307)

    agenda = resolve_agenda_service(request)
    now = datetime.now(AGENDA_TZ)
    hoy = now.date()
    fecha_ref = _parse_date(request.query_params.get("fecha")) or hoy
    monday = _monday_of(fecha_ref)
    desde = datetime.combine(monday, time(0, 0), tzinfo=AGENDA_TZ)
    hasta = desde + timedelta(days=7)
    responsable_id = _parse_uuid(request.query_params.get("responsable"))
    vista = request.query_params.get("vista") or "semana"

    try:
        responsables = agenda.list_responsables()
        citas_semana = agenda.get_agenda(
            desde=desde, hasta=hasta, responsable_id=responsable_id, user=user
        )
        proximas = agenda.get_proximas_citas(desde=now, responsable_id=responsable_id, user=user)
        unavailable = False
    except (DatabaseAppError, ValueError, TypeError):
        responsables = []
        citas_semana = []
        proximas = []
        unavailable = True

    colores = color_map(responsables)
    dias_semana = build_week_grid(citas_semana, monday, hoy, now, colores)
    grupos_proximas = agrupar_por_dia(proximas, hoy, colores)
    vista_actual = "lista" if vista == "lista" else "semana"
    base = {"fecha": monday.isoformat(), "responsable": str(responsable_id) if responsable_id else None}
    chips_responsable = [
        {
            "label": "Todos",
            "color": None,
            "activo": responsable_id is None,
            "url": _build_query_url("/agenda", {**base, "responsable": None, "vista": vista_actual}),
        }
    ] + [
        {
            "label": r.get("nombre"),
            "color": colores.get(str(r.get("nombre")), "slate"),
            "activo": responsable_id is not None and str(r.get("id_asesor")) == str(responsable_id),
            "url": _build_query_url(
                "/agenda", {**base, "responsable": str(r.get("id_asesor")), "vista": vista_actual}
            ),
        }
        for r in responsables
    ]

    context: dict[str, Any] = {
        "request": request,
        "selected_user": user,
        "active_nav": "agenda",
        "can_view_executive_dashboard": _can_view_executive_dashboard(user),
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "csrf_token": _get_csrf_token(request),
        "page_title": "Agenda",
        "vista": vista,
        "dias_semana": dias_semana,
        "proximas": proximas,
        "responsables": responsables,
        "responsable_id": str(responsable_id) if responsable_id else None,
        "semana_label": f"{monday:%d/%m/%Y}",
        "rango_label": rango_label(monday),
        "vista_actual": vista_actual,
        "grupos_proximas": grupos_proximas,
        "resumen": resumen_semana(citas_semana),
        "chips_responsable": chips_responsable,
        "horas": list(range(HORA_INI, HORA_FIN)),
        "hora_ini": HORA_INI,
        "vista_urls": {
            "semana": _build_query_url("/agenda", {**base, "vista": "semana"}),
            "lista": _build_query_url("/agenda", {**base, "vista": "lista"}),
        },
        "semana_anterior": _build_query_url(
            "/agenda",
            {**base, "fecha": (monday - timedelta(days=7)).isoformat(), "vista": vista_actual},
        ),
        "semana_siguiente": _build_query_url(
            "/agenda",
            {**base, "fecha": (monday + timedelta(days=7)).isoformat(), "vista": vista_actual},
        ),
        "semana_hoy": _build_query_url(
            "/agenda", {**base, "fecha": hoy.isoformat(), "vista": vista_actual}
        ),
        "unavailable": unavailable,
        "flash_message": _pop_flash(request),
    }
    return request.app.state.templates.TemplateResponse(request, "agenda.html", context)


def _parse_duracion(value: str | None) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError as exc:
        raise AgendaValidationError("La duración no es válida") from exc


def _parse_agendar_form(form: Any) -> dict[str, Any]:
    return {
        "responsable_id": _parse_uuid(str(form.get("responsable_id") or "")),
        "fecha": str(form.get("fecha") or "").strip(),
        "hora": str(form.get("hora") or "").strip(),
        "duracion": _parse_duracion(str(form.get("duracion") or "")),
        "modalidad": str(form.get("modalidad") or "").strip(),
        "enlace": str(form.get("enlace") or "").strip() or None,
        "nota": str(form.get("nota") or "").strip() or None,
    }


def _guard_form(request: Request, lead_id: str, form: Any) -> Any:
    user = _require_web_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=307)
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        return _render_detail_error(
            request,
            lead_id,
            "La sesión de seguridad ha expirado. Recarga la página e intenta nuevamente.",
            403,
        )
    return user


@router.post("/leads/{lead_id}/agenda/agendar", response_class=HTMLResponse)
async def agenda_agendar(request: Request, lead_id: str):
    form = await request.form()
    guarded = _guard_form(request, lead_id, form)
    if isinstance(guarded, HTMLResponse) or isinstance(guarded, RedirectResponse):
        return guarded
    user: AuthenticatedUser = guarded
    return_to = str(form.get("return_to") or "")
    try:
        data = _parse_agendar_form(form)
        if data["responsable_id"] is None or not data["fecha"] or not data["hora"]:
            raise AgendaValidationError("Completa fecha, hora y responsable")
        agenda = resolve_agenda_service(request)
        agenda.agendar(
            lead_id=UUID(lead_id),
            responsable_id=data["responsable_id"],
            fecha=data["fecha"],
            hora=data["hora"],
            duracion=data["duracion"],
            modalidad=data["modalidad"],
            link=data["enlace"],
            nota=data["nota"],
            actor=user,
        )
    except (
        AgendaNotFoundError,
        AgendaPermissionError,
        AgendaConflictError,
        AgendaValidationError,
        DatabaseAppError,
        ValueError,
        TypeError,
    ) as exc:
        return _handle_agenda_error(request, lead_id, exc)
    _set_flash(request, "Reunión agendada correctamente.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to), status_code=303
    )


@router.post("/leads/{lead_id}/agenda/reagendar", response_class=HTMLResponse)
async def agenda_reagendar(request: Request, lead_id: str):
    form = await request.form()
    guarded = _guard_form(request, lead_id, form)
    if isinstance(guarded, HTMLResponse) or isinstance(guarded, RedirectResponse):
        return guarded
    user: AuthenticatedUser = guarded
    return_to = str(form.get("return_to") or "")
    try:
        data = _parse_agendar_form(form)
        cita_id = _parse_uuid(str(form.get("cita_id") or ""))
        if cita_id is None:
            raise AgendaValidationError("Falta la reunión a reagendar")
        if data["responsable_id"] is None or not data["fecha"] or not data["hora"]:
            raise AgendaValidationError("Completa fecha, hora y responsable")
        agenda = resolve_agenda_service(request)
        agenda.reagendar(
            cita_id=cita_id,
            responsable_id=data["responsable_id"],
            fecha=data["fecha"],
            hora=data["hora"],
            duracion=data["duracion"],
            modalidad=data["modalidad"],
            link=data["enlace"],
            nota=data["nota"],
            actor=user,
        )
    except (
        AgendaNotFoundError,
        AgendaPermissionError,
        AgendaConflictError,
        AgendaValidationError,
        DatabaseAppError,
        ValueError,
        TypeError,
    ) as exc:
        return _handle_agenda_error(request, lead_id, exc)
    _set_flash(request, "Reunión reagendada correctamente.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to), status_code=303
    )


@router.post("/leads/{lead_id}/agenda/cancelar", response_class=HTMLResponse)
async def agenda_cancelar(request: Request, lead_id: str):
    form = await request.form()
    guarded = _guard_form(request, lead_id, form)
    if isinstance(guarded, HTMLResponse) or isinstance(guarded, RedirectResponse):
        return guarded
    user: AuthenticatedUser = guarded
    return_to = str(form.get("return_to") or "")
    try:
        cita_id = _parse_uuid(str(form.get("cita_id") or ""))
        if cita_id is None:
            raise AgendaValidationError("Falta la reunión a cancelar")
        motivo = str(form.get("motivo") or "").strip()
        agenda = resolve_agenda_service(request)
        agenda.cancelar(cita_id=cita_id, motivo=motivo, actor=user)
    except (
        AgendaNotFoundError,
        AgendaPermissionError,
        AgendaConflictError,
        AgendaValidationError,
        DatabaseAppError,
        ValueError,
        TypeError,
    ) as exc:
        return _handle_agenda_error(request, lead_id, exc)
    _set_flash(request, "Reunión cancelada.")
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to), status_code=303
    )


@router.post("/leads/{lead_id}/agenda/realizada", response_class=HTMLResponse)
async def agenda_realizada(request: Request, lead_id: str):
    return await _agenda_outcome(request, lead_id, realizada=True)


@router.post("/leads/{lead_id}/agenda/no-asistio", response_class=HTMLResponse)
async def agenda_no_asistio(request: Request, lead_id: str):
    return await _agenda_outcome(request, lead_id, realizada=False)


async def _agenda_outcome(request: Request, lead_id: str, *, realizada: bool) -> Any:
    form = await request.form()
    guarded = _guard_form(request, lead_id, form)
    if isinstance(guarded, HTMLResponse) or isinstance(guarded, RedirectResponse):
        return guarded
    user: AuthenticatedUser = guarded
    return_to = str(form.get("return_to") or "")
    try:
        cita_id = _parse_uuid(str(form.get("cita_id") or ""))
        if cita_id is None:
            raise AgendaValidationError("Falta la reunión a actualizar")
        agenda = resolve_agenda_service(request)
        if realizada:
            agenda.marcar_realizada(cita_id=cita_id, actor=user)
        else:
            agenda.marcar_no_asistio(cita_id=cita_id, actor=user)
    except (
        AgendaNotFoundError,
        AgendaPermissionError,
        AgendaConflictError,
        AgendaValidationError,
        DatabaseAppError,
        ValueError,
        TypeError,
    ) as exc:
        return _handle_agenda_error(request, lead_id, exc)
    _set_flash(
        request,
        "Reunión marcada como realizada." if realizada else "Reunión marcada como no asistida.",
    )
    return RedirectResponse(
        url=_build_detail_redirect_url_from_value(lead_id, return_to), status_code=303
    )

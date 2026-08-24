"""Authentication routes for the CRM Lite web UX."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.models import AuthenticationResult

router = APIRouter()


def _resolve_auth_provider(request: Request):
    provider = getattr(request.app.state, "auth_provider", None)
    return provider


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("web_user"):
        return RedirectResponse(url="/leads", status_code=307)
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "page_title": "Acceso CRM Lite",
            "error": None,
            "provisional_mode": True,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()

    provider = _resolve_auth_provider(request)
    if provider is None:
        error = "Autenticacion no disponible. Revisa la configuracion del ambiente."
        return request.app.state.templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "page_title": "Acceso CRM Lite",
                "error": error,
                "provisional_mode": False,
            },
            status_code=503,
        )

    result: AuthenticationResult = provider.authenticate(username, password)
    if result.status == "authenticated" and result.user is not None:
        request.session["web_user"] = {
            "subject": result.user.subject,
            "username": result.user.username,
            "display_name": result.user.display_name,
            "role": result.user.role,
        }
        return RedirectResponse(url="/leads", status_code=303)

    if result.status == "unavailable":
        error = "Autenticacion no disponible. Revisa la configuracion del ambiente."
        status_code = 503
    else:
        error = "Credenciales invalidas."
        status_code = 401

    return request.app.state.templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "page_title": "Acceso CRM Lite",
            "error": error,
            "provisional_mode": False,
        },
        status_code=status_code,
    )


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

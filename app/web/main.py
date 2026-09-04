"""FastAPI application for the CRM Lite web UX."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from app.auth import build_auth_provider
from app.components.ui import format_currency_clp
from app.config import get_settings
from app.models.crm_states import crm_state_label, normalize_crm_state_for_display
from app.web.dependencies import resolve_web_simulator_url
from app.web.routes.auth import router as auth_router
from app.web.routes.leads import router as leads_router

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_web_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TPI Backoffice Web", docs_url=None, redoc_url=None)
    session_secret = (
        settings.web_session_secret.get_secret_value()
        if settings.web_session_secret is not None
        else secrets.token_urlsafe(32)
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        https_only=settings.normalized_app_env in {"aws-dev", "production"},
        same_site="lax",
        max_age=settings.web_session_max_age_seconds,
    )
    app.state.settings = settings
    app.state.web_service = None
    try:
        app.state.auth_provider = build_auth_provider(settings)
    except Exception:
        app.state.auth_provider = None
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates.env.filters["crm_state_label"] = crm_state_label
    app.state.templates.env.filters["crm_state_canonical"] = normalize_crm_state_for_display
    app.state.templates.env.filters["format_currency_clp"] = format_currency_clp
    app.state.web_env_label = "Ambiente DEV"
    app.state.web_cleanup_enabled = settings.is_test_lead_cleanup_enabled
    app.state.web_simulator_url = resolve_web_simulator_url()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(auth_router)
    app.include_router(leads_router)

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=307)

    return app


app = create_web_app()

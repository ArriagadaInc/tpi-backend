"""Application factory for the public FastAPI adapter."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.abuse import InMemoryRateLimiter
from app.api.middleware import RequestMetadataMiddleware
from app.api.routes import router
from app.config import Settings, get_settings
from app.services import SolicitudService

logger = logging.getLogger(__name__)


def create_api_app(
    *,
    settings: Settings | None = None,
    service_factory: Callable[[], SolicitudService] = SolicitudService,
) -> FastAPI:
    """Build the public adapter without coupling it to deployment concerns."""
    resolved_settings = settings or get_settings()
    resolved_settings.validate_public_api_configuration()
    app = FastAPI(title="TPI Public API", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.settings = resolved_settings
    app.state.service_factory = service_factory
    app.state.rate_limiter = InMemoryRateLimiter(
        max_requests=resolved_settings.api_rate_limit_requests,
        window_seconds=resolved_settings.api_rate_limit_window_seconds,
    )
    app.add_middleware(RequestMetadataMiddleware)
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        status_code = 400 if any(error["type"] == "json_invalid" for error in exc.errors()) else 422
        return JSONResponse(
            status_code=status_code,
            content={"detail": "Los datos enviados no son validos."},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "event=public_api_unexpected_error request_id=%s", request.state.request_id
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "No fue posible procesar la solicitud. Intenta nuevamente."},
        )

    return app

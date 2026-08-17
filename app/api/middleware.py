"""HTTP hardening middleware for the public API."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestMetadataMiddleware(BaseHTTPMiddleware):
    """Generate a server request id and apply safe response headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.request_id = uuid4()
        content_length = request.headers.get("content-length")
        max_request_bytes: int = request.app.state.settings.api_max_request_bytes
        if content_length and content_length.isdigit() and int(content_length) > max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "La solicitud excede el tamano permitido."},
            )

        response = cast(Response, await call_next(request))
        response.headers["X-Request-ID"] = str(request.state.request_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

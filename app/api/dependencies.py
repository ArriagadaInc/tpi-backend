"""Dependencies shared by public API routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

from fastapi import Header, HTTPException, Request, status

from app.services import SolicitudService


def get_solicitud_service(request: Request) -> SolicitudService:
    service_factory = cast(Callable[[], SolicitudService], request.app.state.service_factory)
    return service_factory()


def require_json_content_type(content_type: str | None = Header(default=None)) -> None:
    if content_type is None or not content_type.lower().startswith("application/json"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El contenido debe enviarse como application/json.",
        )


def require_idempotency_key(idempotency_key: str | None = Header(default=None)) -> UUID:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Falta Idempotency-Key."
        )
    try:
        return UUID(idempotency_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key no es valido.",
        ) from exc

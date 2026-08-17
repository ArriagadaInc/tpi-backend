"""FastAPI routes delegating exclusively to the application service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.abuse import enforce_rate_limit
from app.api.dependencies import (
    get_solicitud_service,
    require_idempotency_key,
    require_json_content_type,
)
from app.api.fingerprint import build_payload_fingerprint
from app.api.schemas import (
    CatalogItem,
    PublicCatalogsResponse,
    PublicLeadCreateRequest,
    PublicLeadCreateResponse,
)
from app.models import IdempotencyConflictError
from app.services import SolicitudService

router = APIRouter(prefix="/api/v1", tags=["public-leads"])


@router.get("/catalogs", response_model=PublicCatalogsResponse)
def get_catalogs(
    service: SolicitudService = Depends(get_solicitud_service),
) -> PublicCatalogsResponse:
    """Return only active catalog values authorized by the application backend."""
    return PublicCatalogsResponse(
        generos=[CatalogItem.model_validate(item) for item in service.get_catalogo_genero()],
        estados_civiles=[
            CatalogItem.model_validate(item) for item in service.get_catalogo_estado_civil()
        ],
        afps=[CatalogItem.model_validate(item) for item in service.get_catalogo_afp()],
    )


@router.post(
    "/leads",
    response_model=PublicLeadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_json_content_type), Depends(enforce_rate_limit)],
)
def create_lead(
    payload: PublicLeadCreateRequest,
    request: Request,
    idempotency_key=Depends(require_idempotency_key),
    service: SolicitudService = Depends(get_solicitud_service),
) -> PublicLeadCreateResponse:
    """Create a public lead through the shared service, never directly through SQL."""
    request_id = request.state.request_id
    if payload.honeypot:
        # Return the same shape as success without identifying the anti-bot control.
        return PublicLeadCreateResponse(lead_id=idempotency_key, request_id=request_id)

    secret = request.app.state.settings.api_idempotency_hmac_secret
    if secret is None or not secret.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El formulario esta temporalmente no disponible.",
        )

    try:
        result = service.registrar_solicitud_idempotente(
            payload.to_application_request(),
            idempotency_key=idempotency_key,
            payload_fingerprint=build_payload_fingerprint(payload, secret.get_secret_value()),
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya fue enviada con datos diferentes.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los datos enviados no son validos.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la solicitud. Intenta nuevamente.",
        ) from exc

    return PublicLeadCreateResponse(lead_id=result.lead_id, request_id=request_id)

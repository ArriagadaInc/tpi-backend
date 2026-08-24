"""Módulo de modelos de datos."""

from app.models.crm_states import (
    CRM_STATE_CONTRACT,
    CRM_STATE_LABELS,
    CRM_STATE_OPTIONS,
    CRM_STATE_TONES,
    CrmStateOption,
    crm_state_filter_terms,
    crm_state_label,
    crm_state_tone,
    iter_crm_state_options,
    normalize_crm_state_for_display,
    normalize_crm_state_for_filter,
    normalize_crm_state_for_write,
)
from app.models.idempotency import IdempotencyConflictError, IdempotentSolicitudResult
from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
    SolicitudResponse,
)
from app.models.test_lead_cleanup import TestLeadCleanupResult
from app.notifications.events import LeadCreatedEvent

__all__ = [
    "PersonaData",
    "SolicitudData",
    "ConsentimientosData",
    "RegistrarSolicitudRequest",
    "SolicitudResponse",
    "TestLeadCleanupResult",
    "LeadCreatedEvent",
    "IdempotencyConflictError",
    "IdempotentSolicitudResult",
    "CrmStateOption",
    "CRM_STATE_CONTRACT",
    "CRM_STATE_LABELS",
    "CRM_STATE_OPTIONS",
    "CRM_STATE_TONES",
    "crm_state_filter_terms",
    "crm_state_label",
    "crm_state_tone",
    "iter_crm_state_options",
    "normalize_crm_state_for_display",
    "normalize_crm_state_for_filter",
    "normalize_crm_state_for_write",
]

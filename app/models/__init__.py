"""Módulo de modelos de datos."""

from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
    SolicitudResponse,
)
from app.models.test_lead_cleanup import TestLeadCleanupResult

__all__ = [
    "PersonaData",
    "SolicitudData",
    "ConsentimientosData",
    "RegistrarSolicitudRequest",
    "SolicitudResponse",
    "TestLeadCleanupResult",
]

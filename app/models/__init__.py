"""Módulo de modelos de datos."""

from app.models.solicitud import (
    PersonaData,
    SolicitudData,
    ConsentimientosData,
    RegistrarSolicitudRequest,
    SolicitudResponse,
)

__all__ = [
    "PersonaData",
    "SolicitudData",
    "ConsentimientosData",
    "RegistrarSolicitudRequest",
    "SolicitudResponse",
]

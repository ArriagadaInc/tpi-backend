"""Módulo de modelos de datos."""

from app.models.solicitud import (
    ConsentimientosData,
    PersonaData,
    RegistrarSolicitudRequest,
    SolicitudData,
    SolicitudResponse,
)

__all__ = [
    "PersonaData",
    "SolicitudData",
    "ConsentimientosData",
    "RegistrarSolicitudRequest",
    "SolicitudResponse",
]

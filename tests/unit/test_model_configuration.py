"""Regression tests for Pydantic model metadata configuration."""

from app.models.solicitud import PersonaData, RegistrarSolicitudRequest, SolicitudResponse


def test_models_expose_json_schema_metadata_with_config_dict() -> None:
    """Keep examples and request metadata after removing Pydantic's deprecated Config class."""
    assert PersonaData.model_json_schema()["example"]["rut"] == "12345678-5"
    assert "description" in RegistrarSolicitudRequest.model_json_schema()
    assert SolicitudResponse.model_json_schema()["example"]["estado_lead"] == "recibida"

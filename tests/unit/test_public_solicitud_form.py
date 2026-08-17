"""Unit coverage for the public presentation-to-service request mapping."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.presentation.public.solicitud_form import (
    PublicSolicitudFormData,
    build_solicitud_request,
)


def _form_data(**overrides: object) -> PublicSolicitudFormData:
    values: dict[str, object] = {
        "rut": "12345678-5",
        "nombre_completo": "Persona Prueba",
        "email": "persona@example.test",
        "telefono": "+56912345678",
        "fecha_nacimiento": date(1990, 1, 1),
        "genero_id": "00000000-0000-0000-0000-000000000001",
        "estado_civil_id": "00000000-0000-0000-0000-000000000002",
        "afp_id": "00000000-0000-0000-0000-000000000003",
        "saldo_afp": 100000,
        "comentarios": "",
        "acepta_terminos": True,
        "acepta_politica_privacidad": True,
        "finalidad_contacto": True,
    }
    values.update(overrides)
    return PublicSolicitudFormData(**values)  # type: ignore[arg-type]


def test_public_form_builds_the_existing_application_request() -> None:
    request = build_solicitud_request(_form_data())

    assert request.persona.rut == "12345678-5"
    assert request.solicitud.genero_id == UUID("00000000-0000-0000-0000-000000000001")
    assert request.consentimientos.finalidad_contacto is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"rut": ""},
        {"email": ""},
        {"acepta_terminos": False},
        {"acepta_politica_privacidad": False},
        {"finalidad_contacto": False},
    ],
)
def test_public_form_rejects_incomplete_or_unconsented_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        build_solicitud_request(_form_data(**overrides))

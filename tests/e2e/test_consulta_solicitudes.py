"""E2E tests for the CRM Lite lead board."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from app.models.test_lead_cleanup import TestLeadCleanupResult
from app.services.solicitud_service import SolicitudService


@pytest.fixture
def synthetic_board_records() -> list[dict[str, object]]:
    return [
        {
            "id_lead": "11111111-1111-1111-1111-111111111111",
            "id_persona": "22222222-2222-2222-2222-222222222222",
            "rut": "12.345.678-5",
            "nombre_completo": "Lead Sintetico Alpha",
            "email": "alpha@example.test",
            "telefono": "+56911112222",
            "afp": "Habitat",
            "genero": "Masculino",
            "estado_civil": "Soltero/a",
            "saldo_afp": 100000,
            "estado_lead": "pendiente",
            "created_at": datetime(2026, 8, 21, 9, 0, 0),
            "acepta_terminos": True,
            "acepta_politica_privacidad": True,
            "finalidad_contacto": True,
            "comentarios": "Registro sintetico para regresion",
        },
        {
            "id_lead": "33333333-3333-3333-3333-333333333333",
            "id_persona": "44444444-4444-4444-4444-444444444444",
            "rut": "20.123.456-7",
            "nombre_completo": "Lead Sintetico Beta",
            "email": "beta@example.test",
            "telefono": "+56933334444",
            "afp": "Provida",
            "genero": "Femenino",
            "estado_civil": "Casado/a",
            "saldo_afp": 3000000,
            "estado_lead": "aprobada",
            "created_at": datetime(2026, 8, 20, 10, 0, 0),
            "acepta_terminos": True,
            "acepta_politica_privacidad": True,
            "finalidad_contacto": True,
            "comentarios": "Segundo registro sintetico",
        },
    ]


@pytest.fixture
def synthetic_board(
    monkeypatch: pytest.MonkeyPatch, synthetic_board_records: list[dict[str, object]]
) -> list[dict[str, object]]:
    records = synthetic_board_records

    def get_crm_bandeja(self, page=1, page_size=10, masked=True, **kwargs):
        return {
            "solicitudes": records,
            "total": len(records),
            "page": page,
            "page_size": page_size,
            "total_pages": 2,
        }

    def get_solicitud_detalle_masked(self, id_lead):
        return next((row for row in records if row["id_lead"] == str(id_lead)), None)

    def delete_test_lead(self, id_lead):
        records[:] = [row for row in records if row["id_lead"] != str(id_lead)]
        return TestLeadCleanupResult(
            status="deleted",
            message="Lead de prueba eliminado correctamente.",
            lead_id=UUID(str(id_lead)),
        )

    monkeypatch.setattr(SolicitudService, "get_crm_bandeja", get_crm_bandeja)
    monkeypatch.setattr(
        SolicitudService, "get_solicitud_detalle_masked", get_solicitud_detalle_masked
    )
    monkeypatch.setattr(SolicitudService, "delete_test_lead", delete_test_lead)
    monkeypatch.setattr(SolicitudService, "is_test_lead_cleanup_enabled", lambda self: True)
    monkeypatch.setattr(
        SolicitudService,
        "get_crm_estado_lead_options",
        lambda self: ["pendiente", "aprobada", "descartado"],
    )
    return records


@pytest.fixture
def app(streamlit_app_factory, synthetic_board):
    return streamlit_app_factory("app/pages/2_solicitudes_registradas.py")


def _login(app) -> None:
    app.text_input[0].set_value("h2-5d-smoke")
    app.text_input[1].set_value("HT4*q80QKy^YI6f-pI")
    app.button[2].click()
    app.run()


def test_page_loads_and_exposes_primary_filters(app):
    app.run()

    assert not app.exception
    text_labels = {element.label for element in app.text_input}
    select_labels = {element.label for element in app.selectbox}

    assert "Buscar nombre o RUT" in text_labels
    assert "Desde" in text_labels
    assert "Hasta" in text_labels
    assert "AFP" in select_labels
    assert "Estado" in select_labels
    assert "Ordenar" in select_labels
    assert "Registros por página" in select_labels


def test_board_renders_pagination_and_detail_controls(app):
    app.run()

    assert not app.exception
    assert any(button.label == "Siguiente ➡️" for button in app.button)
    assert any(button.label == "Abrir" for button in app.button)


def test_board_can_open_detail_and_show_simulator_link(app):
    app.run()
    next(button for button in app.button if button.label == "Abrir").click()
    app.run()

    body = "\n".join(
        [*(element.value for element in app.markdown), *(element.value for element in app.caption)]
    )
    assert "Detalle del lead" in body or "Flujo operativo" in body
    assert "simulador" in body.lower()


def test_dev_cleanup_controls_remain_available_when_enabled(app):
    app.run()
    next(button for button in app.button if button.label == "Abrir").click()
    app.run()

    assert any(
        checkbox.label == "Confirmo que este es un dato de prueba" for checkbox in app.checkbox
    )
    assert any(text.label == "Escribe ELIMINAR para confirmar" for text in app.text_input)


def test_dev_cleanup_flow_is_stable(app, synthetic_board_records):
    app.run()
    next(button for button in app.button if button.label == "Abrir").click()
    app.run()

    checkbox = next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label == "Confirmo que este es un dato de prueba"
    )
    confirmation_text = next(
        text for text in app.text_input if text.label == "Escribe ELIMINAR para confirmar"
    )
    delete_button = next(
        button for button in app.button if button.label == "ELIMINAR LEAD DE PRUEBA"
    )

    checkbox.set_value(True)
    confirmation_text.set_value("ELIMINAR")
    app.run()

    delete_button = next(
        button for button in app.button if button.label == "ELIMINAR LEAD DE PRUEBA"
    )
    assert delete_button.disabled is False

    delete_button.click()
    app.run()

    body = "\n".join(
        [*(element.value for element in app.success), *(element.value for element in app.markdown)]
    )
    assert "Lead de prueba eliminado correctamente" in body
    app.run()
    assert all(
        lead["nombre_completo"] != "Lead Sintetico Alpha" for lead in synthetic_board_records
    )

"""Unit tests for CRM Lite presentation helpers."""

from datetime import datetime

from app.components import (
    format_currency_clp,
    format_datetime_short,
    lead_stage_label,
    lead_stage_tone,
)


def test_format_currency_clp_formats_chilean_pesos() -> None:
    assert format_currency_clp(1234567) == "$ 1.234.567"


def test_format_datetime_short_prefers_dense_iso_style() -> None:
    assert format_datetime_short(datetime(2026, 8, 21, 14, 30)) == "2026-08-21 14:30"


def test_lead_stage_label_normalizes_readable_text() -> None:
    assert lead_stage_label("pendiente") == "Pendiente"
    assert lead_stage_label("simulacion_generada") == "Simulacion Generada"


def test_lead_stage_tone_maps_known_states() -> None:
    assert lead_stage_tone("pendiente") == "info"
    assert lead_stage_tone("aprobada") == "success"
    assert lead_stage_tone("descartado") == "error"

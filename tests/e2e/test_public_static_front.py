"""End-to-end static contracts for the public landing and API form wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


def test_landing_and_simulator_are_public_static_pages_with_dev_banner() -> None:
    landing = (PROJECT_ROOT / "front/index.html").read_text(encoding="utf-8")
    simulator = (PROJECT_ROOT / "front/simulador.html").read_text(encoding="utf-8")

    for page in (landing, simulator):
        assert "AMBIENTE DE DESARROLLO" in page
        assert "NO INGRESAR DATOS PERSONALES REALES" in page
    assert 'id="lead-form"' in simulator


def test_public_form_loads_catalogs_and_submits_same_origin_api_with_idempotency() -> None:
    script = (PROJECT_ROOT / "front/js/contacto.js").read_text(encoding="utf-8")

    assert "fetch('/api/v1/catalogs'" in script
    assert "fetch('/api/v1/leads'" in script
    assert "Idempotency-Key" in script
    assert "crypto.randomUUID()" in script
    assert "AbortController" in script
    payload_builder = script.split("const buildPayload", maxsplit=1)[1].split(
        "form.addEventListener('input'", maxsplit=1
    )[0]
    assert "simSnapshot" not in payload_builder


def test_public_form_no_longer_transports_lead_pii_to_whatsapp() -> None:
    script = (PROJECT_ROOT / "front/js/contacto.js").read_text(encoding="utf-8")

    assert "wa.me" not in script
    assert "window.open" not in script

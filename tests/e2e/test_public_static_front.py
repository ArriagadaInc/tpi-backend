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


def test_backoffice_access_is_limited_to_approved_dev_hosts() -> None:
    landing = (PROJECT_ROOT / "front/index.html").read_text(encoding="utf-8")
    simulator = (PROJECT_ROOT / "front/simulador.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "front/js/backoffice-access.js").read_text(encoding="utf-8")

    for page in (landing, simulator):
        assert "Acceso Backoffice" in page
        assert "data-backoffice-access hidden" in page
        assert 'src="js/backoffice-access.js"' in page

    assert "['tpi.localhost', 'backoffice.tpi.localhost']" in script
    assert "['dev.genialabs.cl', 'backoffice.dev.genialabs.cl']" in script
    assert "destination.port = window.location.port" in script
    assert "link?.remove()" in script
    assert "destination.search = ''" in script
    assert "destination.hash = ''" in script


def test_public_dev_pages_are_not_indexable() -> None:
    for filename in ("index.html", "simulador.html"):
        page = (PROJECT_ROOT / "front" / filename).read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex,nofollow">' in page


def test_public_form_loads_catalogs_and_submits_same_origin_api_with_idempotency() -> None:
    script = (PROJECT_ROOT / "front/js/contacto.js").read_text(encoding="utf-8")
    simulator = (PROJECT_ROOT / "front/simulador.html").read_text(encoding="utf-8")
    styles = (PROJECT_ROOT / "front/css/styles.css").read_text(encoding="utf-8")

    assert "fetch('/api/v1/catalogs'" in script
    assert "fetch('/api/v1/leads'" in script
    assert "Idempotency-Key" in script
    assert "crypto.randomUUID()" in script
    assert "AbortController" in script
    assert "[data-honeypot]" in script
    assert "data-honeypot" in simulator
    assert 'name="empresa"' not in simulator
    assert 'name="tpi_contact_confirmation"' in simulator
    assert 'tabindex="-1"' in simulator
    assert 'autocomplete="off"' in simulator
    assert 'aria-hidden="true"' in simulator
    honeypot_styles = styles.split(".lead-hp", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assert "left: -9999px" in honeypot_styles
    assert "pointer-events: none" in honeypot_styles
    payload_builder = script.split("const buildPayload", maxsplit=1)[1].split(
        "form.addEventListener('input'", maxsplit=1
    )[0]
    assert "simSnapshot" not in payload_builder


def test_public_form_no_longer_transports_lead_pii_to_whatsapp() -> None:
    script = (PROJECT_ROOT / "front/js/contacto.js").read_text(encoding="utf-8")

    assert "wa.me" not in script
    assert "window.open" not in script

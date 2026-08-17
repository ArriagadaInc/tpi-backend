"""Security regression tests for the public static frontend and API boundary."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_public_front_has_no_lead_transport_to_whatsapp_or_hardcoded_api_secret() -> None:
    source = (PROJECT_ROOT / "front/js/contacto.js").read_text(encoding="utf-8")

    assert "wa.me" not in source
    assert "WHATSAPP_LEADS" not in source
    assert "API_IDEMPOTENCY_HMAC_SECRET" not in source


def test_front_assets_use_jpeg_extensions_for_jpeg_content() -> None:
    assets = PROJECT_ROOT / "front/assets"

    assert not list(assets.glob("*.png"))
    assert not list(assets.glob("*.webp"))
    for path in assets.glob("*.jpg"):
        assert path.read_bytes().startswith(b"\xff\xd8\xff")


def test_public_api_has_no_database_or_sns_implementation_in_routes() -> None:
    routes = (PROJECT_ROOT / "app/api/routes.py").read_text(encoding="utf-8")

    forbidden = ("SELECT ", "INSERT ", "boto3", "SnsLeadEventPublisher", "streamlit")
    assert not any(value in routes for value in forbidden)


def test_caddy_keeps_api_and_streamlit_ports_internal() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    caddyfile = (PROJECT_ROOT / "deployment/caddy/Caddyfile").read_text(encoding="utf-8")

    assert '"8000:8000"' not in compose
    assert '"8501:8501"' not in compose
    assert "reverse_proxy api:8000" in caddyfile
    assert "reverse_proxy backoffice:8501" in caddyfile


def test_idempotency_migration_is_minimal_and_cleanup_safe() -> None:
    migration = (PROJECT_ROOT / "scripts/sql/003_create_api_idempotency.sql").read_text(
        encoding="utf-8"
    )
    rollback = (PROJECT_ROOT / "scripts/sql/003_drop_api_idempotency.sql").read_text(
        encoding="utf-8"
    )

    assert "idempotency_key UUID PRIMARY KEY" in migration
    assert "payload_fingerprint CHAR(64) NOT NULL" in migration
    assert "ON DELETE SET NULL" in migration
    assert "api_idempotency_expires_at_idx" in migration
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON tpi.api_idempotency TO tpi_app" in migration
    assert "REVOKE SELECT, INSERT, UPDATE, DELETE ON tpi.api_idempotency FROM tpi_app" in rollback

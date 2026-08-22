"""E2E coverage for the fail-closed login boundary."""

from __future__ import annotations

import streamlit as st

from app.config import clear_settings_cache


def test_aws_dev_without_auth_secret_renders_only_safe_access_message(
    streamlit_app_factory, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "aws-dev")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_MODE", "simple-dev")
    monkeypatch.delenv("AUTH_USERS_JSON", raising=False)
    clear_settings_cache()
    st.cache_resource.clear()
    try:
        # Match the public landing's explicit cold-start allowance.
        app = streamlit_app_factory("app/backoffice_app.py", default_timeout=15)
        app.run()

        assert any("Acceso temporalmente no disponible" in str(item.value) for item in app.error)
        assert not app.get("metric")
    finally:
        clear_settings_cache()
        st.cache_resource.clear()


def test_invalid_auth_configuration_does_not_block_public_landing(
    streamlit_app_factory, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "aws-dev")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_MODE", "unsupported")
    monkeypatch.delenv("AUTH_USERS_JSON", raising=False)
    clear_settings_cache()
    st.cache_resource.clear()
    try:
        # The public landing imports the complete shared application boundary;
        # its cold Streamlit start can exceed AppTest's three-second default.
        app = streamlit_app_factory("app/streamlit_app.py", default_timeout=15)
        app.run()

        assert any("Tu Pension Inteligente" in str(item.value) for item in app.title)
        assert not any(
            "Acceso temporalmente no disponible" in str(item.value) for item in app.error
        )
    finally:
        clear_settings_cache()
        st.cache_resource.clear()

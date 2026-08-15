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
        app = streamlit_app_factory("app/streamlit_app.py")
        app.run()

        assert any("Acceso temporalmente no disponible" in str(item.value) for item in app.error)
        assert not app.get("metric")
    finally:
        clear_settings_cache()
        st.cache_resource.clear()

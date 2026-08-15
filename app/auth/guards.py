"""Streamlit session guard for the DEV-only authentication boundary."""

from __future__ import annotations

import logging
import time
from typing import Any

import streamlit as st

from app.auth.models import AuthenticatedUser
from app.auth.provider import AuthProvider
from app.auth.simple_dev import AuthConfigurationError, build_auth_provider
from app.config import Settings, get_settings

_USER_KEY = "_tpi_auth_user"
_FAILED_ATTEMPTS_KEY = "_tpi_auth_failed_attempts"
_BLOCKED_UNTIL_KEY = "_tpi_auth_blocked_until"
_MAX_FAILED_ATTEMPTS = 5
_MAX_BLOCK_SECONDS = 60

logger = logging.getLogger("tpi.auth")


def get_current_user() -> AuthenticatedUser | None:
    """Return the validated session user, never credentials or password hashes."""
    user = st.session_state.get(_USER_KEY)
    return user if isinstance(user, AuthenticatedUser) else None


def require_authenticated_user(
    settings: Settings | None = None,
    provider: AuthProvider | None = None,
) -> AuthenticatedUser | None:
    """Stop protected rendering unless the request has a valid authenticated session."""
    active_settings = settings or get_settings()
    if not active_settings.authentication_required:
        return None

    user = get_current_user()
    if user is not None:
        return user

    _hide_unauthenticated_navigation()
    try:
        active_settings.validate_auth_configuration()
        active_provider = provider or build_auth_provider(active_settings)
    except (AuthConfigurationError, ValueError):
        logger.error(
            "event=user_login_failed environment=%s result=unavailable",
            active_settings.normalized_app_env,
        )
        _render_unavailable_login()
        st.stop()
        return None

    _render_login(active_provider, active_settings)
    logger.warning(
        "event=unauthorized_access environment=%s result=denied",
        active_settings.normalized_app_env,
    )
    st.stop()
    return None


def logout() -> None:
    """Clear all authentication state and return the browser session to login."""
    user = get_current_user()
    if user is not None:
        logger.info(
            "event=user_logout user_subject=%s environment=%s",
            user.subject,
            get_settings().normalized_app_env,
        )

    for key in tuple(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("_tpi_auth_"):
            del st.session_state[key]
    st.rerun()


def render_logout_control() -> None:
    """Render one common logout control after the page guard has admitted a user."""
    user = get_current_user()
    if user is None:
        return

    st.sidebar.caption(f"Sesion: {user.display_name}")
    if st.sidebar.button("Cerrar sesion", key="tpi_auth_logout"):
        logout()


def _render_login(provider: AuthProvider, settings: Settings) -> None:
    blocked_seconds = _blocked_seconds_remaining()
    st.title("Tu Pension Inteligente")
    st.caption("Ambiente de Desarrollo")

    if blocked_seconds > 0:
        st.error("Demasiados intentos. Intenta nuevamente en unos segundos.")
        return

    with st.form("tpi_auth_login_form", clear_on_submit=True):
        username = st.text_input("Usuario", autocomplete="username")
        password = st.text_input("Contrasena", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Ingresar")

    if not submitted:
        return

    try:
        result = provider.authenticate(username, password)
    except AuthConfigurationError:
        logger.error(
            "event=user_login_failed environment=%s result=unavailable",
            settings.normalized_app_env,
        )
        st.error("Acceso temporalmente no disponible.")
        return
    if result.status == "authenticated" and result.user is not None:
        st.session_state[_USER_KEY] = result.user
        st.session_state[_FAILED_ATTEMPTS_KEY] = 0
        st.session_state.pop(_BLOCKED_UNTIL_KEY, None)
        logger.info(
            "event=user_login_success user_subject=%s environment=%s",
            result.user.subject,
            settings.normalized_app_env,
        )
        st.rerun()
        return

    if result.status == "unavailable":
        logger.error(
            "event=user_login_failed environment=%s result=unavailable",
            settings.normalized_app_env,
        )
        st.error("Acceso temporalmente no disponible.")
        return

    _record_failed_attempt()
    logger.warning(
        "event=user_login_failed environment=%s result=invalid_credentials",
        settings.normalized_app_env,
    )
    st.error("Usuario o contrasena invalidos.")


def _render_unavailable_login() -> None:
    st.title("Tu Pension Inteligente")
    st.caption("Ambiente de Desarrollo")
    st.error("Acceso temporalmente no disponible.")


def _hide_unauthenticated_navigation() -> None:
    """Hide automatic multipage navigation; guards still protect direct URLs."""
    st.markdown(
        "<style>[data-testid='stSidebarNav'] { display: none; }</style>",
        unsafe_allow_html=True,
    )


def _blocked_seconds_remaining(now: float | None = None) -> int:
    current_time = time.time() if now is None else now
    blocked_until = st.session_state.get(_BLOCKED_UNTIL_KEY, 0.0)
    if not isinstance(blocked_until, (int, float)):
        return 0
    return max(0, int(blocked_until - current_time))


def _record_failed_attempt(now: float | None = None) -> None:
    current_time = time.time() if now is None else now
    attempts = st.session_state.get(_FAILED_ATTEMPTS_KEY, 0)
    attempts = int(attempts) + 1 if isinstance(attempts, int) else 1
    st.session_state[_FAILED_ATTEMPTS_KEY] = attempts

    if attempts >= _MAX_FAILED_ATTEMPTS:
        exponent = min(attempts - _MAX_FAILED_ATTEMPTS, 3)
        block_seconds = min(_MAX_BLOCK_SECONDS, 5 * (2**exponent))
        st.session_state[_BLOCKED_UNTIL_KEY] = current_time + block_seconds


def _auth_session_snapshot() -> dict[str, Any]:
    """Expose only test-safe auth state metadata for unit tests."""
    return {
        "authenticated": get_current_user() is not None,
        "failed_attempts": st.session_state.get(_FAILED_ATTEMPTS_KEY, 0),
        "blocked_seconds": _blocked_seconds_remaining(),
    }

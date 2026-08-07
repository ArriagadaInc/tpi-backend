"""Unit tests for database error classification and safe messages."""

from __future__ import annotations

import psycopg
from psycopg_pool import PoolTimeout

from app.database.errors import (
    DatabaseAuthenticationError,
    DatabasePoolExhaustedError,
    DatabaseTimeoutError,
    classify_database_exception,
    get_safe_error_message,
    sanitize_exception_message,
)


def test_invalid_credentials_are_classified() -> None:
    exc = psycopg.OperationalError('password authentication failed for user "tpi_app"')
    error = classify_database_exception(exc, operation="connect", app_env="aws-dev")

    assert isinstance(error, DatabaseAuthenticationError)
    assert error.code == "database_authentication_error"
    assert "credenciales" in error.user_message.lower()


def test_timeout_is_classified() -> None:
    exc = psycopg.OperationalError("connection timeout expired")
    error = classify_database_exception(exc, operation="connect", app_env="aws-dev")

    assert isinstance(error, DatabaseTimeoutError)
    assert error.retryable is True


def test_pool_timeout_is_classified() -> None:
    exc = PoolTimeout("pool exhausted")
    error = classify_database_exception(exc, operation="get_connection", app_env="testing")

    assert isinstance(error, DatabasePoolExhaustedError)
    assert error.retryable is True


def test_dsn_password_is_redacted() -> None:
    message = "could not connect using postgresql://user:top-secret@db-host:5432/tpi"
    sanitized = sanitize_exception_message(message)

    assert "top-secret" not in sanitized
    assert "postgresql://user:***@db-host:5432/tpi" in sanitized


def test_safe_streamlit_message_prefers_public_text() -> None:
    exc = psycopg.OperationalError('password authentication failed for user "tpi_app"')
    error = classify_database_exception(exc, operation="connect", app_env="aws-dev")

    assert get_safe_error_message(error) == error.user_message
    assert (
        get_safe_error_message(RuntimeError("boom"))
        == "Ocurrio un error inesperado. Intenta nuevamente."
    )

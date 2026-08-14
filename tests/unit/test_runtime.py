"""Unit tests for runtime helpers."""

from __future__ import annotations

import logging

import pytest

from app.database.errors import DatabaseAppError
from app.runtime import log_health_status, run_guarded


def test_log_health_status_reports_success_without_sensitive_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tpi.backoffice.test")

    with caplog.at_level(logging.INFO, logger="tpi.backoffice.test"):
        log_health_status(
            {
                "all_ready": True,
                "connected": True,
                "connection": {
                    "schema_accessible": True,
                    "leads_accessible": True,
                    "message": "Base de datos conectada correctamente",
                    "error_code": None,
                },
            },
            logger,
        )

    assert "Health check completed" in caplog.text
    assert "password" not in caplog.text.lower()
    assert "postgresql://" not in caplog.text.lower()


def test_run_guarded_handles_database_error(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_messages: list[str] = []
    monkeypatch.setattr("app.runtime.st.error", lambda message: captured_messages.append(message))

    def boom() -> None:
        raise DatabaseAppError(
            "password=super-secret",
            operation="test.operation",
            app_env="testing",
            user_message="Mensaje seguro",
        )

    run_guarded(boom, page_name="unit-test")

    assert captured_messages == ["Mensaje seguro"]


def test_log_health_status_does_not_report_connection_success_when_not_ready(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("tpi.backoffice.test")

    with caplog.at_level(logging.WARNING, logger="tpi.backoffice.test"):
        log_health_status(
            {
                "all_ready": False,
                "connected": True,
                "connection": {"schema_accessible": False, "leads_accessible": False},
                "schema": {"exists": False},
                "tables": {"all_present": False},
                "catalogs": {"all_ready": False},
            },
            logger,
        )

    assert "Health check failed" in caplog.text
    assert "Base de datos conectada correctamente" not in caplog.text

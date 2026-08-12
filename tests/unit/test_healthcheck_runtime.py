"""Unit tests for the container readiness script."""

from __future__ import annotations

from scripts import healthcheck_runtime


class FakeLogger:
    def info(self, *_: object, **__: object) -> None:
        return None


def test_main_returns_true_when_health_is_ready(monkeypatch) -> None:
    monkeypatch.setattr(healthcheck_runtime, "configure_logging", lambda: FakeLogger())
    monkeypatch.setattr(
        healthcheck_runtime,
        "full_health_check",
        lambda: {
            "all_ready": True,
            "connected": True,
            "connection": {
                "schema_accessible": True,
                "leads_accessible": True,
                "message": "ok",
                "error_code": None,
            },
        },
    )
    monkeypatch.setattr(healthcheck_runtime, "log_health_status", lambda health, logger: None)

    assert healthcheck_runtime.main() is True


def test_main_returns_false_when_health_is_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(healthcheck_runtime, "configure_logging", lambda: FakeLogger())
    monkeypatch.setattr(
        healthcheck_runtime,
        "full_health_check",
        lambda: {
            "all_ready": False,
            "connected": False,
            "connection": {
                "schema_accessible": False,
                "leads_accessible": False,
                "message": "No fue posible conectar con la base de datos.",
                "error_code": "database_unavailable",
            },
        },
    )
    monkeypatch.setattr(healthcheck_runtime, "log_health_status", lambda health, logger: None)

    assert healthcheck_runtime.main() is False

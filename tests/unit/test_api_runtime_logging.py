"""Tests for public API process logging configuration."""

from __future__ import annotations

import logging

from app.api import logging as api_logging


class _Settings:
    log_level = "INFO"


def test_configure_api_logging_targets_stdout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(api_logging, "get_settings", lambda: _Settings())
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: captured.update(kwargs))

    api_logging.configure_api_logging()

    assert captured["level"] == logging.INFO
    assert captured["force"] is True
    assert captured["handlers"]

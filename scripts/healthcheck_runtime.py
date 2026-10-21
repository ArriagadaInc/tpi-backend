"""Readiness check for the backoffice web application container."""

from __future__ import annotations

import logging
import sys

from app.config import get_settings
from app.database.healthcheck import full_health_check, log_health_status

_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def _configure_logging() -> logging.Logger:
    """Configure process logging to stdout using the app log level."""
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    return logging.getLogger("tpi.backoffice")


def main() -> bool:
    """Return True when the app and its database dependency are ready."""
    logger = _configure_logging()
    logger.info("Readiness check started | component=scripts.healthcheck_runtime")
    health = full_health_check()
    log_health_status(health, logger)
    return bool(health.get("all_ready"))


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)

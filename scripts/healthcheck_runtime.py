"""Readiness check for the Streamlit application container."""

from __future__ import annotations

from app.database.healthcheck import full_health_check
from app.runtime import configure_logging, log_health_status


def main() -> bool:
    """Return True when the app and its database dependency are ready."""
    logger = configure_logging()
    logger.info("Readiness check started | component=scripts.healthcheck_runtime")
    health = full_health_check()
    log_health_status(health, logger)
    return bool(health.get("all_ready"))


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)

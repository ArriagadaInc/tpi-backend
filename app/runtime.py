"""Runtime helpers for Streamlit execution and logging."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any, cast

import streamlit as st

from app.config import get_settings
from app.database.errors import DatabaseAppError, get_safe_error_message

_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def configure_logging() -> logging.Logger:
    """Configure process logging to stdout using the app log level."""
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logging.getLogger("streamlit").setLevel(level)
    return logging.getLogger("tpi.backoffice")


def initialize_runtime(page_name: str) -> logging.Logger:
    """Configure logging and record a compact startup message."""
    logger = configure_logging()
    settings = get_settings()
    logger.info(
        "Application startup | page=%s | env=%s | app=%s | log_level=%s",
        page_name,
        settings.normalized_app_env,
        settings.app_name,
        settings.log_level,
    )
    return logger


def log_health_status(health: dict[str, Any], logger: logging.Logger | None = None) -> None:
    """Log a compact health summary without sensitive data."""
    active_logger = logger or logging.getLogger("tpi.backoffice")
    connection = health.get("connection")
    connection_data = cast(dict[str, Any], connection) if isinstance(connection, dict) else {}

    active_logger.info(
        "Health check completed | all_ready=%s | connected=%s | schema_accessible=%s | leads_accessible=%s",
        health.get("all_ready"),
        health.get("connected"),
        connection_data.get("schema_accessible"),
        connection_data.get("leads_accessible"),
    )

    if not health.get("all_ready"):
        active_logger.warning(
            "Health check failed | connected=%s | schema_exists=%s | required_tables=%s | catalogs_ready=%s",
            health.get("connected"),
            health.get("schema", {}).get("exists"),
            health.get("tables", {}).get("all_present"),
            health.get("catalogs", {}).get("all_ready"),
        )


def run_guarded(main: Callable[[], None], *, page_name: str) -> None:
    """Run a Streamlit entrypoint without leaking stack traces to the UI."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format=_LOG_FORMAT,
            handlers=[logging.StreamHandler(sys.stdout)],
        )

    try:
        main()
    except DatabaseAppError as exc:
        logging.getLogger("tpi.backoffice").error(
            "Database error | page=%s | operation=%s | code=%s | message=%s",
            page_name,
            exc.operation,
            exc.code,
            exc.user_message,
        )
        st.error(get_safe_error_message(exc))
    except Exception:
        logging.getLogger("tpi.backoffice").exception("Unexpected error | page=%s", page_name)
        st.error("Ocurrio un error inesperado. Intenta nuevamente.")

"""Logging bootstrap for the standalone public API process."""

from __future__ import annotations

import logging
import sys

from app.config import get_settings

_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def configure_api_logging() -> None:
    """Send API and service events to the container standard output."""
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

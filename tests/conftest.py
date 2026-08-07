# ruff: noqa: E402
"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault("APP_ENV", "testing")

from app.config import clear_settings_cache
from app.database import reset_pool


@pytest.fixture(autouse=True)
def reset_runtime_state() -> None:
    """Ensure settings and pooled connections do not leak between tests."""
    clear_settings_cache()
    reset_pool()
    yield
    reset_pool()
    clear_settings_cache()

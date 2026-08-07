# ruff: noqa: E402
"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import os
import sys

import pytest

from tests.streamlit_test_utils import PROJECT_ROOT, build_app_test

project_root = PROJECT_ROOT
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


@pytest.fixture(scope="session")
def streamlit_app_factory():
    """Build AppTest instances from repository-relative paths."""
    return build_app_test

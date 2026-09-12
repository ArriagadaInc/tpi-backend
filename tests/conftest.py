# ruff: noqa: E402
"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from tests.streamlit_test_utils import PROJECT_ROOT, build_app_test

project_root = PROJECT_ROOT
sys.path.insert(0, str(project_root))

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("PYTEST_ADDOPTS", "--basetemp=.pytest-tmp")
os.environ.setdefault("TMPDIR", str(Path(project_root) / ".pytest-tmp"))
os.environ.setdefault("TEMP", str(Path(project_root) / ".pytest-tmp"))
os.environ.setdefault("TMP", str(Path(project_root) / ".pytest-tmp"))
tempfile.tempdir = str(Path(project_root) / ".pytest-tmp")

if os.name == "nt":
    _temporary_directory_init = tempfile.TemporaryDirectory.__init__

    def _temporary_directory_init_windows(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = False,
        *,
        delete: bool = True,
    ) -> None:
        _temporary_directory_init(
            self,
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            ignore_cleanup_errors=True,
            delete=False,
        )

    tempfile.TemporaryDirectory.__init__ = _temporary_directory_init_windows

from app.config import clear_settings_cache
from app.database import reset_pool


def pytest_configure(config: pytest.Config) -> None:
    """Disable pytest dead-symlink cleanup on Windows temp roots.

    The Windows runner in this repository can leave `basetemp` paths in a state
    where pytest's dead-symlink cleanup raises `PermissionError` during session
    teardown even when the tests themselves passed. Linux CI keeps the default
    behavior.
    """
    if os.name != "nt":
        return

    try:
        import _pytest.pathlib as pytest_pathlib
        import _pytest.tmpdir as pytest_tmpdir
    except Exception:
        return

    if hasattr(pytest_pathlib, "cleanup_dead_symlinks"):
        pytest_pathlib.cleanup_dead_symlinks = lambda *_args, **_kwargs: None  # type: ignore[assignment]
    if hasattr(pytest_tmpdir, "cleanup_dead_symlinks"):
        pytest_tmpdir.cleanup_dead_symlinks = lambda *_args, **_kwargs: None  # type: ignore[assignment]


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

"""Helpers for loading Streamlit apps from repository-root paths in tests."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_repo_path(relative_path: str | Path) -> Path:
    """Resolve a repository-relative file path to an absolute path."""
    resolved_path = (PROJECT_ROOT / Path(relative_path)).resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"Streamlit test script not found: {resolved_path}. "
            "Pass a path relative to the repository root."
        )
    return resolved_path


def build_app_test(relative_path: str | Path, *, default_timeout: int | None = None) -> AppTest:
    """Create an AppTest using an absolute path that works across environments."""
    app = AppTest.from_file(str(resolve_repo_path(relative_path)))
    if default_timeout is not None:
        app.default_timeout = default_timeout
    return app

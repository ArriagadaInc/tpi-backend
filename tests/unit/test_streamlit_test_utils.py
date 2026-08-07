"""Tests for portable Streamlit AppTest path resolution."""

from __future__ import annotations

import pytest

from tests.streamlit_test_utils import PROJECT_ROOT, resolve_repo_path


def test_project_root_points_to_repository_root() -> None:
    assert PROJECT_ROOT.is_absolute()
    assert (PROJECT_ROOT / "app").is_dir()


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/streamlit_app.py",
        "app/pages/1_registrar_solicitud.py",
        "app/pages/2_solicitudes_registradas.py",
        "app/pages/3_trazabilidad.py",
    ],
)
def test_resolve_repo_path_returns_existing_absolute_file(relative_path: str) -> None:
    resolved_path = resolve_repo_path(relative_path)

    assert resolved_path.is_absolute()
    assert resolved_path.is_file()
    assert resolved_path.is_relative_to(PROJECT_ROOT)


def test_resolve_repo_path_raises_for_missing_file() -> None:
    with pytest.raises(FileNotFoundError, match="Streamlit test script not found"):
        resolve_repo_path("app/pages/does_not_exist.py")

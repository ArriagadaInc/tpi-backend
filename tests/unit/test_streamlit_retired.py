"""Regression tests: Streamlit is fully retired from the application runtime.

These tests guard acceptance criterion AC-1 of SEG-DESACOPLAR-STREAMLIT: the
web and API entrypoints import without Streamlit installed, and no module under
``app/`` imports it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"

_BLOCK_STREAMLIT = """
import sys


class _BlockStreamlit:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "streamlit" or fullname.startswith("streamlit."):
            raise ImportError("streamlit is retired and must not be importable")
        return None


sys.meta_path.insert(0, _BlockStreamlit())
"""


def test_no_app_module_imports_streamlit() -> None:
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = raw.strip()
            if stripped.startswith("import streamlit") or stripped.startswith("from streamlit"):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{line_no}: {stripped}")
    assert offenders == []


def test_web_and_api_entrypoints_import_without_streamlit() -> None:
    script = _BLOCK_STREAMLIT + """
import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("API_IDEMPOTENCY_HMAC_SECRET", "unit-test-hmac-not-for-runtime")

import app.web.main  # noqa: F401
import app.api.main  # noqa: F401

print("IMPORT_OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout

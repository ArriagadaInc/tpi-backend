"""Regression contract for the minimal Alpine runtime remediation."""

from pathlib import Path

DOCKERFILE = Path("Dockerfile")
PINNED_BASE = (
    "python:3.12.14-alpine3.24@"
    "sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a"
)
EXPECTED_PACKAGE = "libuuid=2.42.3-r1"


def test_app_image_keeps_the_pinned_python_31214_alpine324_base() -> None:
    assert f"FROM {PINNED_BASE}" in DOCKERFILE.read_text(encoding="utf-8")


def test_app_image_updates_only_the_explicit_util_linux_origin_fix() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert f"RUN apk add --no-cache {EXPECTED_PACKAGE}" in dockerfile
    assert "apk upgrade --no-cache" not in dockerfile
    assert dockerfile.count("apk add --no-cache") == 1

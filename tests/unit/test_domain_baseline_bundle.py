"""Regression tests for the hybrid domain-baseline Elastic Beanstalk bundle."""

from __future__ import annotations

import importlib.util
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

APP_IMAGE = (
    "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@"
    "sha256:45331812c93bcf905b2ae8ad9eedff9eba5f63bc4afbfd5639af85c78bb3b6ce"
)
CADDY_IMAGE = (
    "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@"
    "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf"
)
APP_GIT_SHA = "28cf009137ada707540d9ee7eba01dc45a9a260e"
CADDY_GIT_SHA = "43101be7835088f93267bee85b0f11c8bc879867"
BUNDLE_NAME = "tpi-dev-domain-baseline-28cf009-caddy43101be.zip"
EXPECTED_BUNDLE_SHA256 = "6e4bb205e996f11a12ade0070e189d44157314cf69ef414cd5de6e24a9ef6af5"


def _load_bundle_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_eb_ecr_bundle", "deployment/build_eb_ecr_bundle.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle_builder = _load_bundle_module()


def _build(tmp_path: Path) -> tuple[Path, dict[str, Any], str]:
    output = tmp_path / BUNDLE_NAME
    bundle, manifest_path = bundle_builder.build_domain_baseline_bundle(
        template=Path("deployment/aws/docker-compose.ecr.yml"),
        output=output,
        app_image=APP_IMAGE,
        caddy_image=CADDY_IMAGE,
        app_git_sha=APP_GIT_SHA,
        caddy_git_sha=CADDY_GIT_SHA,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(bundle) as archive:
        compose = archive.read("docker-compose.yml").decode("utf-8")
    return bundle, manifest, compose


def test_domain_baseline_bundle_is_hybrid_digest_pinned_and_minimal(tmp_path: Path) -> None:
    bundle, _, compose = _build(tmp_path)

    # app (28cf009) exactly twice; Caddy (43101be) exactly once.
    assert compose.count(APP_IMAGE) == 2
    assert compose.count(CADDY_IMAGE) == 1

    # No mutable image tag: every image reference is pinned by @sha256:<64hex>.
    image_lines = re.findall(r"^\s*image:\s*(\S+)\s*$", compose, re.MULTILINE)
    assert image_lines
    assert all(re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image) for image in image_lines)

    # The compose passes the env-driven hosted zone id to Caddy.
    assert (
        "TPI_ROUTE53_HOSTED_ZONE_ID: "
        "${TPI_ROUTE53_HOSTED_ZONE_ID:?TPI_ROUTE53_HOSTED_ZONE_ID is required}" in compose
    )

    # Only Caddy publishes the public 80/443 ports; app/backoffice never publish.
    assert '      - "80:80"' in compose
    assert '      - "443:443"' in compose
    assert "api:\n" in compose and "backoffice:\n" in compose and "caddy:\n" in compose
    assert "build:" not in compose

    # Bundle contains only docker-compose.yml at its root.
    with zipfile.ZipFile(bundle) as archive:
        assert archive.namelist() == ["docker-compose.yml"]
        assert archive.getinfo("docker-compose.yml").date_time == (1980, 1, 1, 0, 0, 0)


def test_domain_baseline_manifest_identifies_app_and_caddy_separately(tmp_path: Path) -> None:
    _, manifest, _ = _build(tmp_path)

    assert manifest["artifact_type"] == "domain-baseline"
    assert manifest["app_git_sha"] == APP_GIT_SHA
    assert manifest["app_image"] == APP_IMAGE
    assert manifest["app_image_digest"] == (
        "sha256:45331812c93bcf905b2ae8ad9eedff9eba5f63bc4afbfd5639af85c78bb3b6ce"
    )
    assert manifest["caddy_git_sha"] == CADDY_GIT_SHA
    assert manifest["caddy_image"] == CADDY_IMAGE
    assert manifest["caddy_image_digest"] == (
        "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf"
    )
    assert manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256

    # The baseline must never carry a misleading single runtime_git_sha.
    assert "runtime_git_sha" not in manifest


def test_domain_baseline_bundle_is_reproducible_and_pinned(tmp_path: Path) -> None:
    first, first_manifest, _ = _build(tmp_path)
    second, second_manifest, _ = _build(tmp_path / "second")

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256
    assert second_manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256


def test_domain_baseline_builder_rejects_missing_or_invalid_shas(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="app git SHA"):
        bundle_builder.build_domain_baseline_bundle(
            template=Path("deployment/aws/docker-compose.ecr.yml"),
            output=tmp_path / BUNDLE_NAME,
            app_image=APP_IMAGE,
            caddy_image=CADDY_IMAGE,
            app_git_sha="short",
            caddy_git_sha=CADDY_GIT_SHA,
        )
    with pytest.raises(ValueError, match="Caddy git SHA"):
        bundle_builder.build_domain_baseline_bundle(
            template=Path("deployment/aws/docker-compose.ecr.yml"),
            output=tmp_path / BUNDLE_NAME,
            app_image=APP_IMAGE,
            caddy_image=CADDY_IMAGE,
            app_git_sha=APP_GIT_SHA,
            caddy_git_sha="short",
        )

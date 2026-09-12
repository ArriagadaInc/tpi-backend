"""Regression tests for the domain-locked DEV H3.3 bundle."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path
from typing import Any

APP_IMAGE = (
    "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@"
    "sha256:79737222a5901871857f59143c8dc696879b2e88aa740eb7304225ffa4cd9631"
)
CADDY_IMAGE = (
    "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@"
    "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf"
)
RUNTIME_SHA = "43101be7835088f93267bee85b0f11c8bc879867"
EXPECTED_BUNDLE_SHA256 = "007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f"

DOMAIN_LOCK = {
    "TPI_PUBLIC_SITE_URL": "https://dev.tupensioninteligente.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.tupensioninteligente.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.tupensioninteligente.cl",
    "TPI_ROUTE53_HOSTED_ZONE_ID": "Z07053592LX0W8GJXNI1C",
}


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
    output = tmp_path / "tpi-dev-ecr-43101be-domainlocked.zip"
    bundle, manifest_path = bundle_builder.build_domain_locked_bundle(
        template=Path("deployment/aws/docker-compose.domainlocked.yml"),
        output=output,
        app_image=APP_IMAGE,
        caddy_image=CADDY_IMAGE,
        runtime_git_sha=RUNTIME_SHA,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(bundle) as archive:
        compose = archive.read("docker-compose.yml").decode("utf-8")
    return bundle, manifest, compose


def test_domain_locked_bundle_has_literal_tpi_values_and_exact_images(tmp_path: Path) -> None:
    bundle, manifest, compose = _build(tmp_path)

    for name, value in DOMAIN_LOCK.items():
        assert f'{name}: "{value}"' in compose

    assert "genialabs.cl" not in compose
    assert compose.count(APP_IMAGE) == 2
    assert compose.count(CADDY_IMAGE) == 1
    assert "build:" not in compose
    assert "${TPI_ROUTE53_HOSTED_ZONE_ID" not in compose
    assert "${TPI_PUBLIC_SITE_ADDRESS" not in compose
    assert "${TPI_BACKOFFICE_SITE_ADDRESS" not in compose
    assert "${TPI_PUBLIC_SITE_URL" not in compose

    with zipfile.ZipFile(bundle) as archive:
        assert archive.namelist() == ["docker-compose.yml"]


def test_domain_locked_bundle_manifest_and_reproducibility(tmp_path: Path) -> None:
    first, first_manifest, _ = _build(tmp_path)
    second, second_manifest, _ = _build(tmp_path / "second")

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest["artifact_type"] == "domain-locked"
    assert first_manifest["runtime_git_sha"] == RUNTIME_SHA
    assert first_manifest["app_image_digest"] == (
        "sha256:79737222a5901871857f59143c8dc696879b2e88aa740eb7304225ffa4cd9631"
    )
    assert first_manifest["caddy_image_digest"] == (
        "sha256:30ace9145a21209f41799d345f4d6f641f0b882478fede76d0e19a575656aaaf"
    )
    assert first_manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256
    assert second_manifest["bundle_sha256"] == EXPECTED_BUNDLE_SHA256

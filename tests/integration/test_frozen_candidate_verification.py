"""Integration tests for the immutable EB candidate artifact contract."""

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/release/verify_frozen_candidate.sh"
APP_IMAGE = "registry.example.test/tpi-dev-app@sha256:" + "a" * 64
CADDY_IMAGE = "registry.example.test/tpi-dev-caddy@sha256:" + "b" * 64
SOURCE_SHA = "c" * 40
BUNDLE_NAME = "tpi-dev-ecr-ccccccc.zip"
MANIFEST_NAME = "tpi-dev-ecr-ccccccc.manifest.json"


def _build_artifact(artifact_dir: Path) -> str:
    compose = f"""services:\n  api:\n    image: {APP_IMAGE}\n  backoffice:\n    image: {APP_IMAGE}\n  caddy:\n    image: {CADDY_IMAGE}\n"""
    bundle = artifact_dir / BUNDLE_NAME
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("docker-compose.yml", compose)

    bundle_sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (artifact_dir / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "runtime_git_sha": SOURCE_SHA,
                "app_image": APP_IMAGE,
                "caddy_image": CADDY_IMAGE,
                "bundle_sha256": bundle_sha,
            }
        ),
        encoding="utf-8",
    )
    return bundle_sha


def _run_verifier(artifact_dir: Path, bundle_sha: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "ARTIFACT_DIR": str(artifact_dir),
            "BUNDLE_NAME": BUNDLE_NAME,
            "MANIFEST_NAME": MANIFEST_NAME,
            "BUNDLE_SHA256": bundle_sha,
            "SOURCE_SHA": SOURCE_SHA,
            "APP_IMAGE": APP_IMAGE,
            "CADDY_IMAGE": CADDY_IMAGE,
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_verifier_accepts_flat_downloaded_artifact(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.fail("bash is required to execute the release verifier")
    if shutil.which("docker") is None:
        pytest.fail("docker is required to validate the Compose contract")

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    bundle_sha = _build_artifact(artifact_dir)

    result = _run_verifier(artifact_dir, bundle_sha)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Artifact verification passed." in result.stdout


def test_verifier_rejects_nested_download_layout(tmp_path: Path) -> None:
    if shutil.which("bash") is None:
        pytest.fail("bash is required to execute the release verifier")
    if shutil.which("docker") is None:
        pytest.fail("docker is required to validate the Compose contract")

    artifact_dir = tmp_path / "artifact"
    nested_dir = artifact_dir / "downloaded-artifact"
    nested_dir.mkdir(parents=True)
    bundle_sha = _build_artifact(nested_dir)

    result = _run_verifier(artifact_dir, bundle_sha)

    assert result.returncode != 0
    assert "expected bundle not found" in result.stdout

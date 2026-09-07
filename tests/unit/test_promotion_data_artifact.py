"""Tests for the non-executable CodePipeline release input."""

import json
import zipfile
from pathlib import Path

from deployment.aws.build_promotion_data import build_data_archive


def _release_files(directory: Path) -> tuple[str, str]:
    bundle_name = "tpi-dev-ecr-28cf009.zip"
    manifest_name = "tpi-dev-ecr-28cf009.manifest.json"
    (directory / bundle_name).write_bytes(b"immutable bundle")
    (directory / manifest_name).write_text(
        json.dumps({"bundle_sha256": "approved"}), encoding="utf-8"
    )
    return bundle_name, manifest_name


def test_promotion_source_contains_data_only_even_with_malicious_scripts(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    bundle_name, manifest_name = _release_files(artifact)
    (artifact / "promote_eb_candidate.py").write_text("raise SystemExit('owned')", encoding="utf-8")
    (artifact / "verify_frozen_candidate.sh").write_text("exit 0", encoding="utf-8")
    output = tmp_path / "candidate-data.zip"

    build_data_archive(artifact, bundle_name, manifest_name, output)

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [
            f"artifact/{bundle_name}",
            f"artifact/{manifest_name}",
        ]


def test_same_name_with_different_content_produces_different_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    bundle_name, manifest_name = _release_files(artifact)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    build_data_archive(artifact, bundle_name, manifest_name, first)

    (artifact / bundle_name).write_bytes(b"modified bundle")
    build_data_archive(artifact, bundle_name, manifest_name, second)

    assert first.read_bytes() != second.read_bytes()

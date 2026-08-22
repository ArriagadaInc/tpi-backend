"""Unit tests for the H3.2 automated preflight."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from deployment import preflight
from deployment.build_eb_ecr_bundle import build_bundle

APP_IMAGE = "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@sha256:" + "a" * 64
CADDY_IMAGE = "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@sha256:" + "b" * 64
GIT_SHA = "c" * 40
TREE_SHA = "d" * 40


def _write_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo_root, check=True, capture_output=True
    )


def _temp_workspace(name: str) -> Path:
    base = Path(".tmp") / f"preflight-{name}"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _build_release(workspace: Path) -> tuple[Path, Path]:
    output = workspace / "h2-5d-ecr-ccccccc.zip"
    bundle, manifest = build_bundle(
        template=Path("deployment/aws/docker-compose.ecr.yml"),
        output=output,
        app_image=APP_IMAGE,
        caddy_image=CADDY_IMAGE,
        runtime_git_sha=GIT_SHA,
        git_tree_sha=TREE_SHA,
        environment="aws-dev",
        eb_version="tpi-ccccccc",
        repository="ArriagadaInc/tpi-backend",
        run_id="123",
        run_attempt=1,
    )
    return bundle, manifest


def _stub_common_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight, "_current_branch", lambda _repo_root: "feat/h3-2-reproducible-deployment"
    )
    monkeypatch.setattr(preflight, "get_git_sha", lambda _repo_root: GIT_SHA)
    monkeypatch.setattr(preflight, "get_git_tree_sha", lambda _repo_root: TREE_SHA)


def test_preflight_valid_release_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("valid")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert report["status"] == "PASS"
        assert all(check["status"] == "PASS" for check in report["checks"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_dirty_repository_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("dirty")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        (repo_root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        bundle, manifest = _build_release(workspace)
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert report["status"] == "FAIL"
        assert any(
            check["name"] == "working_tree_clean" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_expected_sha_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("sha")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        monkeypatch.setattr(
            preflight, "_current_branch", lambda _repo_root: "feat/h3-2-reproducible-deployment"
        )
        monkeypatch.setattr(preflight, "get_git_sha", lambda _repo_root: "e" * 40)
        monkeypatch.setattr(preflight, "get_git_tree_sha", lambda _repo_root: TREE_SHA)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "expected_sha_equals_head" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_tree_sha_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("tree")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        monkeypatch.setattr(
            preflight, "_current_branch", lambda _repo_root: "feat/h3-2-reproducible-deployment"
        )
        monkeypatch.setattr(preflight, "get_git_sha", lambda _repo_root: GIT_SHA)
        monkeypatch.setattr(preflight, "get_git_tree_sha", lambda _repo_root: "f" * 40)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "expected_tree_sha_equals_actual" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_missing_manifest_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("missing-manifest")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, _manifest = _build_release(workspace)
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=workspace / "missing.json",
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "manifest_exists" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_invalid_manifest_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("invalid-manifest")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        manifest.write_text("{not-json}", encoding="utf-8")
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "manifest_schema_valid" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_mutable_image_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("mutable-image")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_data["app_image"]["reference"] = "example.com/tpi-dev-app:latest"
        manifest.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "app_image_immutable_digest" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_app_provenance_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("app-provenance")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_data["app_image"]["source_git_sha"] = "e" * 40
        manifest.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "app_source_git_sha_equals_release_git_sha"
            and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_missing_bundle_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("missing-bundle")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        _bundle, manifest = _build_release(workspace)
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=workspace / "missing.zip",
        )

        assert any(
            check["name"] == "bundle_exists" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_bundle_tampering_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("tamper")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        bundle.write_bytes(bundle.read_bytes() + b"tamper")
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert any(
            check["name"] == "bundle_sha256_matches_manifest" and check["status"] == "FAIL"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_preflight_deterministic_valid_release_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _temp_workspace("deterministic")
    try:
        repo_root = workspace / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)
        _write_git_repo(repo_root)
        bundle, manifest = _build_release(workspace)
        _stub_common_success(monkeypatch)

        report = preflight.run_preflight(
            repo_root=repo_root,
            expected_branch="feat/h3-2-reproducible-deployment",
            expected_git_sha=GIT_SHA,
            expected_tree_sha=TREE_SHA,
            manifest_path=manifest,
            bundle_path=bundle,
        )

        assert report["status"] == "PASS"
        assert any(
            check["name"] == "deterministic_release_bundle_naming" and check["status"] == "PASS"
            for check in report["checks"]
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

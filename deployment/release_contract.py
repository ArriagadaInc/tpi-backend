"""Release contract helpers for H3.2 reproducible deployments."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def get_git_sha(cwd: Path | None = None) -> str:
    return _run_git(["rev-parse", "HEAD"], cwd=cwd)


def get_git_tree_sha(cwd: Path | None = None) -> str:
    return _run_git(["rev-parse", "HEAD^{tree}"], cwd=cwd)


def build_release_id(git_sha: str) -> str:
    if len(git_sha) < 7:
        raise ValueError("git_sha must be at least 7 characters.")
    return f"tpi-{git_sha[:7]}"


def expected_bundle_filename(git_sha: str) -> str:
    if len(git_sha) < 7:
        raise ValueError("git_sha must be at least 7 characters.")
    return f"h2-5d-ecr-{git_sha[:7]}.zip"


@dataclass(frozen=True, slots=True)
class ReleaseImage:
    reference: str
    source_git_sha: str


@dataclass(frozen=True, slots=True)
class ReleaseTarget:
    environment: str
    eb_version: str


@dataclass(frozen=True, slots=True)
class ReleaseCI:
    repository: str
    run_id: str
    run_attempt: int


@dataclass(frozen=True, slots=True)
class ReleaseBundle:
    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    schema_version: str
    release_id: str
    git_sha: str
    git_tree_sha: str
    app_image: ReleaseImage
    caddy_image: ReleaseImage
    bundle: ReleaseBundle
    target: ReleaseTarget
    ci: ReleaseCI
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "git_sha": self.git_sha,
            "git_tree_sha": self.git_tree_sha,
            "app_image": {
                "reference": self.app_image.reference,
                "source_git_sha": self.app_image.source_git_sha,
            },
            "caddy_image": {
                "reference": self.caddy_image.reference,
                "source_git_sha": self.caddy_image.source_git_sha,
            },
            "bundle": {
                "filename": self.bundle.filename,
                "sha256": self.bundle.sha256,
            },
            "target": {
                "environment": self.target.environment,
                "eb_version": self.target.eb_version,
            },
            "ci": {
                "repository": self.ci.repository,
                "run_id": self.ci.run_id,
                "run_attempt": self.ci.run_attempt,
            },
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"


def build_release_manifest(
    *,
    git_sha: str,
    git_tree_sha: str,
    app_image: str,
    app_source_git_sha: str,
    caddy_image: str,
    caddy_source_git_sha: str,
    bundle_filename: str,
    bundle_sha256: str,
    environment: str,
    eb_version: str,
    repository: str,
    run_id: str,
    run_attempt: int,
    generated_at: str | None = None,
) -> ReleaseManifest:
    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha):
        raise ValueError("git_sha must be a full lowercase 40-character SHA.")
    if len(git_tree_sha) != 40 or any(char not in "0123456789abcdef" for char in git_tree_sha):
        raise ValueError("git_tree_sha must be a full lowercase 40-character tree SHA.")
    if len(bundle_sha256) != 64 or any(char not in "0123456789abcdef" for char in bundle_sha256):
        raise ValueError("bundle_sha256 must be a lowercase 64-character sha256 digest.")
    if not bundle_filename.endswith(".zip"):
        raise ValueError("bundle filename must end with .zip.")

    return ReleaseManifest(
        schema_version="1.0",
        release_id=build_release_id(git_sha),
        git_sha=git_sha,
        git_tree_sha=git_tree_sha,
        app_image=ReleaseImage(reference=app_image, source_git_sha=app_source_git_sha),
        caddy_image=ReleaseImage(reference=caddy_image, source_git_sha=caddy_source_git_sha),
        bundle=ReleaseBundle(filename=bundle_filename, sha256=bundle_sha256),
        target=ReleaseTarget(environment=environment, eb_version=eb_version),
        ci=ReleaseCI(repository=repository, run_id=run_id, run_attempt=run_attempt),
        generated_at=generated_at or datetime.now(UTC).isoformat(),
    )


def validate_release_manifest(manifest: dict[str, Any], *, expected_git_sha: str) -> None:
    required = {
        "schema_version",
        "release_id",
        "git_sha",
        "git_tree_sha",
        "app_image",
        "caddy_image",
        "bundle",
        "target",
        "ci",
        "generated_at",
    }
    missing = required.difference(manifest)
    if missing:
        raise ValueError(f"Release manifest is missing required fields: {sorted(missing)}")

    if manifest["schema_version"] != "1.0":
        raise ValueError("Unsupported release manifest schema version.")
    if manifest["git_sha"] != expected_git_sha:
        raise ValueError("Release manifest git_sha does not match the validated commit.")
    if manifest["release_id"] != build_release_id(expected_git_sha):
        raise ValueError("Release manifest release_id does not match the validated commit.")

    for key in ("app_image", "caddy_image"):
        image = manifest[key]
        if not isinstance(image, dict):
            raise ValueError(f"{key} must be a mapping.")
        if set(image) != {"reference", "source_git_sha"}:
            raise ValueError(f"{key} must contain reference and source_git_sha.")
        if "@sha256:" not in image["reference"]:
            raise ValueError(f"{key} reference must be immutable.")

    bundle = manifest["bundle"]
    if not isinstance(bundle, dict) or set(bundle) != {"filename", "sha256"}:
        raise ValueError("bundle must contain filename and sha256.")
    if not bundle["filename"].endswith(".zip"):
        raise ValueError("bundle filename must end with .zip.")


def validate_release_bundle_against_manifest(
    bundle_path: Path, manifest_path: Path, *, expected_git_sha: str
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_release_manifest(manifest, expected_git_sha=expected_git_sha)

    actual_bundle_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    if manifest["bundle"]["sha256"] != actual_bundle_sha:
        raise ValueError("Bundle SHA does not match the release manifest.")
    if manifest["bundle"]["filename"] != bundle_path.name:
        raise ValueError("Bundle filename does not match the release manifest.")

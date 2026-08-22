"""Fail-closed preflight checks for reproducible H3.2 releases."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deployment.release_contract import (
    expected_bundle_filename,
    get_git_sha,
    get_git_tree_sha,
    validate_release_bundle_against_manifest,
    validate_release_manifest,
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"name": self.name, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        return payload


def _ok(name: str, detail: str | None = None) -> CheckResult:
    return CheckResult(name=name, status="PASS", detail=detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status="FAIL", detail=detail)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Release manifest JSON must be an object.")
    return payload


def _is_full_sha(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _expected_bundle_name(git_sha: str) -> str:
    return expected_bundle_filename(git_sha)


def _check_repository_detected(repo_root: Path) -> CheckResult:
    git_dir = repo_root / ".git"
    if git_dir.exists():
        return _ok("repository_detected")
    return _fail("repository_detected", "Repository metadata not found.")


def _check_expected_branch(expected_branch: str | None, current_branch: str) -> CheckResult:
    if not expected_branch:
        return _fail("expected_branch", "Expected branch was not provided.")
    if current_branch != expected_branch:
        return _fail("expected_branch", f"Current branch is {current_branch!r}.")
    return _ok("expected_branch")


def _check_working_tree_clean(repo_root: Path) -> CheckResult:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip():
        return _fail("working_tree_clean", "Working tree contains uncommitted changes.")
    return _ok("working_tree_clean")


def _check_head_sha(repo_root: Path, expected_sha: str | None) -> tuple[CheckResult, str | None]:
    try:
        actual_sha = get_git_sha(repo_root)
    except Exception as exc:  # pragma: no cover - defensive, surfaced as fail-closed
        return _fail("head_is_full_sha", f"Unable to resolve HEAD: {exc}"), None
    if not _is_full_sha(actual_sha):
        return _fail("head_is_full_sha", "HEAD is not a full lowercase SHA."), actual_sha
    if expected_sha is None:
        return _fail("expected_sha_equals_head", "Expected SHA was not provided."), actual_sha
    if expected_sha != actual_sha:
        return _fail("expected_sha_equals_head", "Expected SHA does not match HEAD."), actual_sha
    return _ok("expected_sha_equals_head"), actual_sha


def _check_tree_sha(
    repo_root: Path, expected_tree_sha: str | None
) -> tuple[CheckResult, str | None]:
    try:
        actual_tree_sha = get_git_tree_sha(repo_root)
    except Exception as exc:  # pragma: no cover - defensive, surfaced as fail-closed
        return _fail("git_tree_sha_resolvable", f"Unable to resolve git tree: {exc}"), None
    if not _is_full_sha(actual_tree_sha):
        return (
            _fail("git_tree_sha_resolvable", "Git tree SHA is not a full lowercase SHA."),
            actual_tree_sha,
        )
    if expected_tree_sha is None:
        return (
            _fail("expected_tree_sha_equals_actual", "Expected tree SHA was not provided."),
            actual_tree_sha,
        )
    if expected_tree_sha != actual_tree_sha:
        return (
            _fail(
                "expected_tree_sha_equals_actual", "Expected tree SHA does not match actual tree."
            ),
            actual_tree_sha,
        )
    return _ok("expected_tree_sha_equals_actual"), actual_tree_sha


def _check_manifest(
    path: Path, expected_git_sha: str, actual_tree_sha: str
) -> tuple[list[CheckResult], dict[str, Any] | None]:
    if not path.exists():
        return [_fail("manifest_exists", "Release manifest not found.")], None

    try:
        manifest = _load_manifest(path)
    except Exception as exc:
        return [_fail("manifest_schema_valid", f"Invalid JSON manifest: {exc}")], None

    try:
        validate_release_manifest(manifest, expected_git_sha=expected_git_sha)
    except Exception as exc:
        return [_fail("manifest_schema_valid", str(exc))], manifest

    results = [
        _ok("manifest_schema_valid"),
        _ok("manifest_git_sha_equals_expected"),
        _ok("manifest_git_tree_sha_equals_actual"),
    ]

    if manifest["git_sha"] != expected_git_sha:
        results[1] = _fail(
            "manifest_git_sha_equals_expected", "Manifest git_sha does not match expected SHA."
        )
    if manifest["git_tree_sha"] != actual_tree_sha:
        results[2] = _fail(
            "manifest_git_tree_sha_equals_actual",
            "Manifest git_tree_sha does not match actual tree.",
        )
    return results, manifest


def _check_image_reference(
    name: str, reference: str, source_git_sha: str, expected_git_sha: str
) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(
        _ok(f"{name}_image_immutable_digest")
        if "@sha256:" in reference and reference.count("@sha256:") == 1
        else _fail(f"{name}_image_immutable_digest", f"{name} image reference is not immutable.")
    )
    results.append(
        _ok(f"{name}_source_git_sha_equals_release_git_sha")
        if source_git_sha == expected_git_sha
        else _fail(
            f"{name}_source_git_sha_equals_release_git_sha",
            f"{name} source_git_sha does not match release git_sha.",
        )
    )
    return results


def _check_bundle(path: Path, manifest_path: Path, expected_git_sha: str) -> list[CheckResult]:
    if not path.exists():
        return [_fail("bundle_exists", "Release bundle not found.")]
    try:
        validate_release_bundle_against_manifest(
            path, manifest_path, expected_git_sha=expected_git_sha
        )
    except Exception as exc:
        return [_fail("bundle_sha256_matches_manifest", str(exc))]
    expected_name = _expected_bundle_name(expected_git_sha)
    if path.name != expected_name:
        return [
            _fail(
                "deterministic_release_bundle_naming",
                f"Bundle name {path.name!r} does not match expected {expected_name!r}.",
            )
        ]
    return [
        _ok("bundle_exists"),
        _ok("bundle_sha256_matches_manifest"),
        _ok("deterministic_release_bundle_naming"),
    ]


def run_preflight(
    *,
    repo_root: Path,
    expected_branch: str,
    expected_git_sha: str,
    expected_tree_sha: str | None = None,
    manifest_path: Path | None = None,
    bundle_path: Path | None = None,
) -> dict[str, Any]:
    results: list[CheckResult] = []

    results.append(_check_repository_detected(repo_root))

    try:
        current_branch = _current_branch(repo_root)
    except Exception as exc:  # pragma: no cover - defensive fail-closed
        results.append(_fail("expected_branch", f"Unable to determine current branch: {exc}"))
        current_branch = ""
    else:
        results.append(_check_expected_branch(expected_branch, current_branch=current_branch))

    results.append(_check_working_tree_clean(repo_root))

    head_result, actual_git_sha = _check_head_sha(repo_root, expected_git_sha)
    results.append(head_result)

    tree_result, actual_tree_sha = _check_tree_sha(repo_root, expected_tree_sha)
    results.append(tree_result)

    manifest_data: dict[str, Any] | None = None
    if manifest_path is None:
        results.append(_fail("manifest_exists", "Release manifest path was not provided."))
    else:
        if actual_tree_sha is None:
            results.append(
                _fail("manifest_git_tree_sha_equals_actual", "Git tree SHA could not be resolved.")
            )
        manifest_results, manifest_data = _check_manifest(
            manifest_path, expected_git_sha, actual_tree_sha or ""
        )
        results.extend(manifest_results)

    if manifest_data is not None:
        results.extend(
            _check_image_reference(
                "app",
                manifest_data["app_image"]["reference"],
                manifest_data["app_image"]["source_git_sha"],
                expected_git_sha,
            )
        )
        results.extend(
            _check_image_reference(
                "caddy",
                manifest_data["caddy_image"]["reference"],
                manifest_data["caddy_image"]["source_git_sha"],
                expected_git_sha,
            )
        )

    if bundle_path is None or manifest_path is None:
        if bundle_path is None:
            results.append(_fail("bundle_exists", "Release bundle path was not provided."))
        if manifest_path is None:
            results.append(
                _fail("bundle_sha256_matches_manifest", "Release manifest path was not provided.")
            )
    else:
        results.extend(_check_bundle(bundle_path, manifest_path, expected_git_sha))

    status = "PASS" if all(result.status == "PASS" for result in results) else "FAIL"
    return {
        "status": status,
        "checks": [result.to_dict() for result in results],
        "repository": str(repo_root),
        "branch": expected_branch,
        "head_sha": actual_git_sha,
        "tree_sha": actual_tree_sha,
    }


def _current_branch(repo_root: Path) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )
    branch = completed.stdout.strip()
    if not branch:
        raise ValueError("Unable to determine current branch.")
    return branch


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-tree-sha")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = run_preflight(
        repo_root=args.repo_root,
        expected_branch=args.expected_branch,
        expected_git_sha=args.expected_git_sha,
        expected_tree_sha=args.expected_tree_sha,
        manifest_path=args.manifest,
        bundle_path=args.bundle,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

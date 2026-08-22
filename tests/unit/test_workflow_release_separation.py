"""Workflow checks for the reproducible release split."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workflow_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_on(workflow: dict) -> dict:
    return workflow.get("on") or workflow.get(True) or {}


def test_ci_workflow_uses_current_sha_and_no_hardcoded_release_artifact() -> None:
    path = Path(".github/workflows/ci.yml")
    workflow = _load_workflow(path)
    workflow_text = _workflow_text(path)
    docker_steps = workflow["jobs"]["docker-build"]["steps"]
    bundle_step = next(
        step for step in docker_steps if "Build CI validation EB bundle" in step.get("name", "")
    )
    bundle_run = bundle_step["run"]

    assert "${{ github.sha }}" in workflow_text
    assert "5c6a726423a7539daefb9bcb1c35748e928e7999" not in bundle_run
    assert "1446f299deb66f40b1eb50cf91d82447fba51ceed4c8adb23a138688571a7c66" not in bundle_run
    assert "0c72b8cb2f8b7281437d128ebc4b7669105e1df5693d1e026967b2c747a77449" not in bundle_run
    assert "h2-5d-ecr-5c6a726.zip" not in bundle_run


def test_release_workflow_requires_explicit_sha_checkout() -> None:
    workflow = _load_workflow(Path(".github/workflows/release.yml"))
    assert _workflow_on(workflow)["workflow_dispatch"]["inputs"]["source_sha"]["required"] is True

    checkout_step = workflow["jobs"]["build-release"]["steps"][0]
    assert checkout_step["uses"] == "actions/checkout@v5"
    assert checkout_step["with"]["ref"] == "${{ inputs.source_sha }}"


def test_release_workflow_has_preflight_and_no_direct_deploy() -> None:
    workflow = _load_workflow(Path(".github/workflows/release.yml"))
    step_names = [step.get("name", "") for step in workflow["jobs"]["build-release"]["steps"]]
    assert "Run preflight" in step_names
    assert all("elastic beanstalk" not in name.lower() for name in step_names)

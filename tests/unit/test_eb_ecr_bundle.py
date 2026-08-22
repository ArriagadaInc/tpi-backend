"""Regression tests for the minimal Elastic Beanstalk ECR source bundle."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


def _load_bundle_module() -> Any:
    path = Path("deployment/build_eb_ecr_bundle.py")
    spec = importlib.util.spec_from_file_location("build_eb_ecr_bundle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle_builder: Any = _load_bundle_module()
APP_IMAGE = "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-app@sha256:" + "a" * 64
CADDY_IMAGE = "821656895812.dkr.ecr.us-east-2.amazonaws.com/tpi-dev-caddy@sha256:" + "b" * 64
RUNTIME_SHA = "c" * 40


def test_build_bundle_is_minimal_posix_and_digest_pinned(tmp_path: Path) -> None:
    output = tmp_path / "h2-5d-ecr-ccccccc.zip"

    bundle, manifest = bundle_builder.build_bundle(
        template=Path("deployment/aws/docker-compose.ecr.yml"),
        output=output,
        app_image=APP_IMAGE,
        caddy_image=CADDY_IMAGE,
        runtime_git_sha=RUNTIME_SHA,
    )

    assert bundle == output
    assert manifest.exists()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["app_image"] == APP_IMAGE
    assert manifest_data["caddy_image"] == CADDY_IMAGE
    assert manifest_data["runtime_git_sha"] == RUNTIME_SHA
    assert len(manifest_data["bundle_sha256"]) == 64
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.namelist()
        assert entries == ["docker-compose.yml"]
        info = archive.getinfo("docker-compose.yml")
        compose = archive.read("docker-compose.yml").decode("utf-8")
    assert "\\" not in "".join(entries)
    assert info.date_time == (1980, 1, 1, 0, 0, 0)
    assert "build:" not in compose
    assert APP_IMAGE in compose
    assert CADDY_IMAGE in compose


def test_bundle_validation_rejects_windows_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "invalid.zip"
    with zipfile.ZipFile(bundle, mode="w") as archive:
        archive.writestr("deploy\\docker-compose.yml", "services: {}\n")

    with pytest.raises(ValueError, match="root"):
        bundle_builder.validate_bundle(bundle)


def test_bundle_validation_rejects_nested_posix_paths(tmp_path: Path) -> None:
    bundle = tmp_path / "invalid.zip"
    with zipfile.ZipFile(bundle, mode="w") as archive:
        archive.writestr("nested/docker-compose.yml", "services: {}\n")

    with pytest.raises(ValueError, match="root"):
        bundle_builder.validate_bundle(bundle)


@pytest.mark.parametrize(
    "forbidden_entry", [".env", ".ebextensions/01-runtime.config", "Dockerfile"]
)
def test_bundle_validation_rejects_non_compose_files(tmp_path: Path, forbidden_entry: str) -> None:
    bundle = tmp_path / "invalid.zip"
    with zipfile.ZipFile(bundle, mode="w") as archive:
        archive.writestr("docker-compose.yml", "services: {}\n")
        archive.writestr(forbidden_entry, "forbidden\n")

    with pytest.raises(ValueError, match="only docker-compose.yml"):
        bundle_builder.validate_bundle(bundle)


def test_bundle_builder_rejects_tag_reference(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="digest"):
        bundle_builder.build_bundle(
            template=Path("deployment/aws/docker-compose.ecr.yml"),
            output=tmp_path / "h2-5d-ecr-ccccccc.zip",
            app_image="example.com/tpi-dev-app:mutable",
            caddy_image=CADDY_IMAGE,
            runtime_git_sha=RUNTIME_SHA,
        )


def test_bundle_builder_rejects_invalid_runtime_sha(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="40-character"):
        bundle_builder.build_bundle(
            template=Path("deployment/aws/docker-compose.ecr.yml"),
            output=tmp_path / "h2-5d-ecr-ccccccc.zip",
            app_image=APP_IMAGE,
            caddy_image=CADDY_IMAGE,
            runtime_git_sha="short-sha",
        )


def test_bundle_builder_rejects_unexpected_output_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Bundle filename"):
        bundle_builder.build_bundle(
            template=Path("deployment/aws/docker-compose.ecr.yml"),
            output=tmp_path / "bundle.zip",
            app_image=APP_IMAGE,
            caddy_image=CADDY_IMAGE,
            runtime_git_sha=RUNTIME_SHA,
        )


def test_render_compose_rejects_missing_placeholders(tmp_path: Path) -> None:
    template = tmp_path / "docker-compose.ecr.yml"
    template.write_text("services:\n  api:\n    image: missing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected image placeholders"):
        bundle_builder.render_compose(template, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_unresolved_placeholder() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace(APP_IMAGE, bundle_builder.APP_PLACEHOLDER, 1)

    with pytest.raises(ValueError, match="unresolved image placeholder"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_build_directive() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace(
        '    command: ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]',
        '    build: .\n    command: ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]',
    )

    with pytest.raises(ValueError, match="must not contain build directives"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_wrong_image_counts() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace(APP_IMAGE, "other@sha256:" + "d" * 64, 1)

    with pytest.raises(ValueError, match="reference the app twice and Caddy once"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_missing_service() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    )
    compose = compose.replace("  backoffice:\n", "  removed-backoffice:\n", 1)

    with pytest.raises(ValueError, match="missing the backoffice service"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_api_published_port() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace('    expose:\n      - "8000"', '    ports:\n      - "8000:8000"')

    with pytest.raises(ValueError, match="api must not publish host ports"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_backoffice_published_port() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace('    expose:\n      - "8501"', '    ports:\n      - "8501:8501"')

    with pytest.raises(ValueError, match="backoffice must not publish host ports"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_rendered_compose_rejects_missing_public_caddy_ports() -> None:
    compose = bundle_builder.render_compose(
        Path("deployment/aws/docker-compose.ecr.yml"),
        APP_IMAGE,
        CADDY_IMAGE,
    ).replace('      - "443:443"\n', "")

    with pytest.raises(ValueError, match="ports 80 and 443"):
        bundle_builder._validate_rendered_compose(compose, APP_IMAGE, CADDY_IMAGE)


def test_validate_bundle_rejects_compose_without_digest_pinned_tpi_images(tmp_path: Path) -> None:
    bundle = tmp_path / "invalid.zip"
    compose = """
services:
    api:
        image: example.com/tpi-dev-app:latest
    backoffice:
        image: example.com/tpi-dev-app:latest
    caddy:
        image: example.com/tpi-dev-caddy:latest
""".strip() + "\n"
    with zipfile.ZipFile(bundle, mode="w") as archive:
        archive.writestr("docker-compose.yml", compose)

    with pytest.raises(ValueError, match="digest-pinned TPI ECR images"):
        bundle_builder.validate_bundle(bundle)


def test_main_prints_bundle_and_manifest_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "h2-5d-ecr-ccccccc.zip"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_eb_ecr_bundle.py",
            "--template",
            "deployment/aws/docker-compose.ecr.yml",
            "--output",
            str(output),
            "--app-image",
            APP_IMAGE,
            "--caddy-image",
            CADDY_IMAGE,
            "--runtime-git-sha",
            RUNTIME_SHA,
        ],
    )

    bundle_builder.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "bundle": str(output),
        "manifest": str(output.with_suffix(".manifest.json")),
    }

"""Build the minimal, digest-pinned Elastic Beanstalk source bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

APP_PLACEHOLDER: Final = "${TPI_APP_IMAGE:?TPI_APP_IMAGE must be an immutable digest reference}"
CADDY_PLACEHOLDER: Final = (
    "${TPI_CADDY_IMAGE:?TPI_CADDY_IMAGE must be an immutable digest reference}"
)
ARCHIVE_ENTRY: Final = "docker-compose.yml"
IMAGE_REFERENCE_PATTERN: Final = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")
BUILD_PATTERN: Final = re.compile(r"^\s*build\s*:", re.MULTILINE)


def _validate_image_reference(image: str, name: str) -> None:
    if not IMAGE_REFERENCE_PATTERN.fullmatch(image):
        raise ValueError(f"{name} must be an immutable image reference pinned by sha256 digest.")


def _validate_rendered_compose(compose: str, app_image: str, caddy_image: str) -> None:
    if APP_PLACEHOLDER in compose or CADDY_PLACEHOLDER in compose:
        raise ValueError("Compose still contains an unresolved image placeholder.")
    if BUILD_PATTERN.search(compose):
        raise ValueError("Elastic Beanstalk ECR compose must not contain build directives.")
    if compose.count(app_image) != 2 or compose.count(caddy_image) != 1:
        raise ValueError(
            "Compose must reference the app twice and Caddy once using the approved digests."
        )

    for service_name in ("api", "backoffice"):
        match = re.search(
            rf"^  {service_name}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|^volumes:|^networks:|\Z)",
            compose,
            re.MULTILINE | re.DOTALL,
        )
        if match is None:
            raise ValueError(f"Compose is missing the {service_name} service.")
        if re.search(r"^    ports:\n", match.group("body"), re.MULTILINE):
            raise ValueError(f"{service_name} must not publish host ports.")

    if '      - "80:80"' not in compose or '      - "443:443"' not in compose:
        raise ValueError("Caddy must be the only public entry point on ports 80 and 443.")


def render_compose(template: Path, app_image: str, caddy_image: str) -> str:
    """Render the deployment compose from approved immutable image references."""
    _validate_image_reference(app_image, "app image")
    _validate_image_reference(caddy_image, "Caddy image")

    source = template.read_text(encoding="utf-8")
    if source.count(APP_PLACEHOLDER) != 2 or source.count(CADDY_PLACEHOLDER) != 1:
        raise ValueError("Compose template does not contain the expected image placeholders.")

    compose = source.replace(APP_PLACEHOLDER, app_image).replace(CADDY_PLACEHOLDER, caddy_image)
    _validate_rendered_compose(compose, app_image, caddy_image)
    return compose


def validate_bundle(bundle: Path) -> str:
    """Validate archive contents and return the rendered compose text."""
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.namelist()
        if entries != [ARCHIVE_ENTRY]:
            raise ValueError(
                "Elastic Beanstalk bundle must contain only docker-compose.yml at its root."
            )
        for entry in entries:
            path = PurePosixPath(entry)
            if "\\" in entry or path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
                raise ValueError("Bundle contains an invalid archive path.")
        if archive.testzip() is not None:
            raise ValueError("Bundle ZIP integrity check failed.")
        compose = archive.read(ARCHIVE_ENTRY).decode("utf-8")

    app_images = re.findall(
        r"^\s*image:\s*([^\s]+tpi-dev-app@sha256:[0-9a-f]{64})\s*$", compose, re.MULTILINE
    )
    caddy_images = re.findall(
        r"^\s*image:\s*([^\s]+tpi-dev-caddy@sha256:[0-9a-f]{64})\s*$", compose, re.MULTILINE
    )
    if len(app_images) != 2 or len(caddy_images) != 1:
        raise ValueError("Bundle compose must contain digest-pinned TPI ECR images.")
    _validate_rendered_compose(compose, app_images[0], caddy_images[0])
    return compose


def build_bundle(
    *,
    template: Path,
    output: Path,
    app_image: str,
    caddy_image: str,
    runtime_git_sha: str,
) -> tuple[Path, Path]:
    """Create and validate a minimal POSIX-path ZIP plus an external manifest."""
    if not GIT_SHA_PATTERN.fullmatch(runtime_git_sha):
        raise ValueError("runtime git SHA must be a full 40-character lowercase SHA.")
    expected_name = f"h2-5d-ecr-{runtime_git_sha[:7]}.zip"
    if output.name != expected_name:
        raise ValueError(f"Bundle filename must be {expected_name}.")

    compose = render_compose(template, app_image, caddy_image)
    output.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo(filename=ARCHIVE_ENTRY, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(info, compose.encode("utf-8"))

    validate_bundle(output)
    manifest = {
        "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "caddy_image": caddy_image,
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_git_sha": runtime_git_sha,
        "app_image": app_image,
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--caddy-image", required=True)
    parser.add_argument("--runtime-git-sha", required=True)
    args = parser.parse_args()

    bundle, manifest = build_bundle(
        template=args.template,
        output=args.output,
        app_image=args.app_image,
        caddy_image=args.caddy_image,
        runtime_git_sha=args.runtime_git_sha,
    )
    print(json.dumps({"bundle": str(bundle), "manifest": str(manifest)}, sort_keys=True))


if __name__ == "__main__":
    main()

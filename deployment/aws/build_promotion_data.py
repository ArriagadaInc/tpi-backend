"""Build a data-only CodePipeline source from a verified release artifact."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def build_data_archive(
    artifact_dir: Path,
    bundle_name: str,
    manifest_name: str,
    output: Path,
) -> None:
    files = (artifact_dir / bundle_name, artifact_dir / manifest_name)
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing verified release files: {', '.join(missing)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(files[0], f"artifact/{bundle_name}")
        archive.write(files[1], f"artifact/{manifest_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--manifest-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build_data_archive(
        arguments.artifact_dir,
        arguments.bundle_name,
        arguments.manifest_name,
        arguments.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

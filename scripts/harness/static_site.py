"""Static-site deployment profile: the evidence checks that differ from Elastic Beanstalk.

The target is a private S3 bucket behind CloudFront. A release is a set of files:

  staged   ``<bundle_key_prefix>/<label>/<path>``   one object per file, SHA-256 checked by S3
  live     ``<live_prefix>/<path>``                 what CloudFront serves

PREPARING_DEPLOYMENT stages the files and records them in the candidate; the human approves exactly
that candidate; DEPLOYING copies each approved file from the staged prefix to the live prefix;
rollback copies the files of the last known good release back. Nothing here talks to AWS: these are
pure checks over evidence documents (aws_guard.py decides which operations may run, guards.py asks
this module whether the documents agree with each other and with the environment).

Every check returns a list of problems (empty = fine) so a caller can show all of them at once.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

try:
    from . import common, deploy_profile
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import deploy_profile  # type: ignore[no-redef]

LIVE_STATUS = "Live"
MARKER_RELEASE = "release"  # object metadata: which release the live object came from
MARKER_SHA256 = "sha256"  # object metadata: hex SHA-256 of the object's content


def site_healthy(state: Mapping[str, Any]) -> bool:
    """The live site answers with its release marker (the static counterpart of Ready/Green/Ok)."""
    return state.get("status") == LIVE_STATUS and state.get("http_status") == 200


def staged_prefix(artifacts: Mapping[str, Any], label: str) -> str:
    return f"{artifacts['bundle_key_prefix']}/{label}"


def live_key(artifacts: Mapping[str, Any], path: str) -> str:
    return f"{artifacts['live_prefix']}/{path}"


def _object_problems(
    objects: list[dict[str, Any]], prefix: str, expected: Mapping[str, str] | None, what: str
) -> list[str]:
    """Each staged object sits under ``prefix`` and (when known) carries its file's checksum."""
    problems: list[str] = []
    for obj in objects:
        path = obj["path"]
        if not deploy_profile.safe_site_path(path):
            problems.append(f"{what}: ruta no segura {path!r}")
            continue
        if obj["key"] != f"{prefix}/{path}":
            problems.append(f"{what}: key inesperada para {path}")
        if expected is not None and obj["checksum_sha256"] != expected.get(path):
            problems.append(f"{what}: checksum de {path} no corresponde al archivo")
    return problems


def candidate_errors(
    cand: Mapping[str, Any], merge: Mapping[str, Any], env: Mapping[str, Any]
) -> list[str]:
    """Problems of a candidate evidence document against its merge and the environment."""
    artifacts, target = env["artifacts"], env["deployment_target"]
    problems: list[str] = []

    def need(condition: object, message: str) -> None:
        if not condition:
            problems.append(message)

    label = cand["application_version"]["label"]
    need(cand["release_sha"] == merge["release_sha"], "release_sha del candidate != merge")
    need(cand["account_id"] == env["account_id"], "cuenta AWS distinta")
    need(cand["region"] == env["region"], "region AWS distinta")
    need(cand["environment"] == target["environment_name"], "environment distinto del target DEV")
    need(
        re.fullmatch(artifacts["version_label_pattern"], label),
        "version label fuera de patron",
    )
    need(cand["release_sha"][:7] in label, "version label no contiene el release SHA corto")

    bundle = cand["bundle"]
    files = bundle["files"]
    paths = [f["path"] for f in files]
    need(bundle["reproducible"] is True, "bundle no reproducible")
    need(len(set(paths)) == len(paths), "rutas repetidas en el bundle")
    need(len(paths) <= deploy_profile.MAX_SITE_FILES, "demasiados archivos en el bundle")
    for item in files:
        need(deploy_profile.safe_site_path(item["path"]), f"ruta no segura {item['path']!r}")
        need(
            deploy_profile.content_type_for(item["path"]) == item["content_type"],
            f"content type no permitido para {item['path']}",
        )
    need(target["index_document"] in paths, "el bundle no incluye el documento indice")
    need(
        bundle["sha256"] == deploy_profile.manifest_hash(files),
        "sha256 del bundle no corresponde a la lista de archivos",
    )

    s3 = cand["s3"]
    need(s3["bucket"] == artifacts["bundle_bucket"], "bucket de releases inesperado")
    need(s3["prefix"] == staged_prefix(artifacts, label), "prefijo de staging inesperado")
    expected = {f["path"]: common.hex_to_b64(f["sha256"]) for f in files}
    staged = {o["path"] for o in s3["files"]}
    need(staged == set(paths), "los archivos en S3 no son los del bundle")
    problems += _object_problems(s3["files"], s3["prefix"], expected, "staging")

    observed, lkg = cand["environment_observed"], cand["lkg"]
    need(site_healthy(observed), "el sitio no responde sano antes del release")
    need(
        observed["live_version_label"] == lkg["version_label"],
        "el LKG debe ser la version viva observada",
    )
    need(lkg["version_label"] != label, "LKG igual al candidate")
    need(lkg["status"] == "PRESENT" and lkg["files_present"] is True, "LKG no utilizable")
    problems += _object_problems(
        lkg["files"], staged_prefix(artifacts, lkg["version_label"]), None, "LKG"
    )
    need(
        cand["rollback_plan"]["version_label"] == lkg["version_label"],
        "plan de rollback != LKG",
    )
    commands = cand["deployment_plan"]["commands"]
    need(
        commands and all(str(c).startswith("s3api copy-object ") for c in commands),
        "el plan solo puede contener s3api copy-object",
    )
    return problems


def approval_errors(approval: Mapping[str, Any], cand: Mapping[str, Any]) -> list[str]:
    """Problems of the human approval against the candidate (profile-specific fields only)."""
    problems: list[str] = []
    if approval["s3_prefix"] != cand["s3"]["prefix"]:
        problems.append("prefijo S3 distinto del candidate")
    if approval["bundle_sha256"] != cand["bundle"]["sha256"]:
        problems.append("bundle SHA256 distinto")
    return problems


def deployment_errors(
    dep: Mapping[str, Any], approval: Mapping[str, Any], env: Mapping[str, Any]
) -> list[str]:
    """Problems of a deployment evidence document against the approval."""
    problems: list[str] = []
    if dep["update_accepted"] is not True:
        problems.append("copy-object no aceptado para todos los archivos")
    final = dep["final_state"]
    if not site_healthy(final):
        problems.append("el sitio final no responde sano")
    if final["live_version_label"] != approval["application_version"]:
        problems.append("version viva final != aprobada")
    if not all(value is True for value in dep["runtime_identity"].values()):
        problems.append("identidad de runtime no verificada")
    return problems


def rollback_errors(pre: Mapping[str, Any]) -> list[str]:
    """Problems of the rollback precheck that are specific to this profile."""
    return [] if pre["lkg_files_present"] is True else ["archivos del LKG ausentes en S3"]


def gate_package(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """The fields the human is shown and signs (the static counterpart of the image digests)."""
    return {
        "bundle_sha256": candidate["bundle"]["sha256"],
        "s3_prefix": candidate["s3"]["prefix"],
        "files": [
            {"path": f["path"], "sha256": f["sha256"], "bytes": f["bytes"]}
            for f in candidate["bundle"]["files"]
        ],
    }

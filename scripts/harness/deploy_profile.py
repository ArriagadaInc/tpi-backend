"""Deployment profiles: what kind of target an environment deploys to.

The core of the harness (develop -> review -> merge -> close) knows nothing about AWS. The
deployment states (PREPARING_DEPLOYMENT .. ROLLING_BACK) do, and they used to assume one target:
Elastic Beanstalk with two container images. A *profile* names the target; everything that is
specific to it (evidence shape, guards, AWS operations) is looked up by profile.

  elastic-beanstalk  the original target (default when ``deployment_target.type`` is absent)
  static-site        a private S3 bucket behind CloudFront: releases are staged under
                     ``<prefix>/<label>/`` and promoted by copying into ``<live_prefix>/``
  none               the project does not deploy (``deploy_required`` is always false)

Evidence carries ``deployment_profile`` (absent means elastic-beanstalk) so a document written for
one target can never be mistaken for another.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

ELASTIC_BEANSTALK = "elastic-beanstalk"
STATIC_SITE = "static-site"
NO_DEPLOYMENT = "none"
PROFILES = (ELASTIC_BEANSTALK, STATIC_SITE, NO_DEPLOYMENT)

# Content types the static profile may publish (a closed list: the Content-Type is what a browser
# trusts, so it is part of what the human approves).
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
MAX_SITE_FILES = 200


def profile_of(environment: Mapping[str, Any]) -> str:
    """Profile of an environment definition (environments/<name>.yaml)."""
    target = environment.get("deployment_target") or {}
    return str(target.get("type") or ELASTIC_BEANSTALK)


def evidence_profile(document: Mapping[str, Any]) -> str:
    """Profile an evidence document was written for (absent = the original target)."""
    return str(document.get("deployment_profile") or ELASTIC_BEANSTALK)


def safe_site_path(path: object) -> bool:
    """A relative path of plain segments: no ``..``, no absolute path, no backslash, no dotfiles."""
    if not isinstance(path, str) or not path or path != path.strip():
        return False
    segments = path.split("/")
    return all(_SAFE_SEGMENT.fullmatch(segment) for segment in segments) and not path.endswith("/")


def content_type_for(path: str) -> str | None:
    """Content type for the extension of ``path``, or None when the extension is not allowed."""
    dot = path.rfind(".")
    return CONTENT_TYPES.get(path[dot:].lower()) if dot >= 0 else None


def manifest_hash(files: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 binding a release to exactly its files (path, content hash, size), order-free.

    Canonical JSON (sorted keys, no spaces) of the files sorted by path: the same files always
    give the same hash, so a reviewer who rebuilds the release from git compares one value.
    """
    rows = sorted(
        ({"path": f["path"], "sha256": f["sha256"], "bytes": int(f["bytes"])} for f in files),
        key=lambda row: row["path"],
    )
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()

"""Shared helpers for the TPI repository-native agent harness.

Every harness script fails closed: an unexpected condition raises ``HarnessError``.
"""

from __future__ import annotations

import base64
import datetime as dt
import functools
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
AGENT_ROLES = ("developer", "reviewer", "deployer")
ROLE_EVIDENCE_DIR = {
    "developer": "developer",
    "reviewer": "reviewer",
    "deployer": "deployment",
    "human": "approvals",
}
STOP_BANNER = "STOP - DO NOT MODIFY THE REPOSITORY - REQUEST HUMAN ASSISTANCE"

_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"X-Amz-(Signature|Credential|Security-Token)=[^&\s\"']+"), "presigned-url"),
    (re.compile(r"https://[^\s\"']*amazonaws\.com[^\s\"']*\?[^\s\"']*"), "presigned-url"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "aws-access-key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private-key"),
    (re.compile(r"\$argon2id\$[^\s\"']+"), "password-hash"),
    (
        re.compile(
            r'"[A-Za-z_]*(password|secret|token|sessiontoken|secretaccesskey)[A-Za-z_]*"'
            r'\s*:\s*"(?!\[REDACTED\])[^"]+"',
            re.IGNORECASE,
        ),
        "secret-value",
    ),
    (re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b"), "rut"),
    (re.compile(r"\+569\d{8}\b"), "phone"),
)

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"X-Amz-(Signature|Credential|Security-Token)=[^&\s\"']+"), r"X-Amz-\1=[REDACTED]"),
    (re.compile(r"https://[^\s\"']*amazonaws\.com[^\s\"']*\?[^\s\"']*"), "[REDACTED_PRESIGNED_URL]"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_ACCESS_KEY]"),
    (
        re.compile(
            r'("[A-Za-z_]*(?:password|secret|token|sessiontoken|secretaccesskey|auth_users_json)'
            r'[A-Za-z_]*"\s*:\s*)"[^"]*"',
            re.IGNORECASE,
        ),
        r'\1"[REDACTED]"',
    ),
    (re.compile(r'("PhysicalResourceId"\s*:\s*)"[^"]*"'), r'\1"[REDACTED]"'),
    (re.compile(r"\$argon2id\$[^\s\"']+"), "[REDACTED_HASH]"),
)


class HarnessError(RuntimeError):
    """A harness invariant was violated; the caller must stop."""


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_yaml_atomic(path: Path, data: Any, header: str = "") -> None:
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    write_text_atomic(path, header + body)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hex_to_b64(hex_digest: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")


def load_state(root: Path) -> dict[str, Any]:
    return read_json(root / "harness" / "state.json")


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    errors = validate_schema(root, "state", state)
    if errors:
        raise HarnessError("state.json invalido: " + "; ".join(errors))
    write_json_atomic(root / "harness" / "state.json", state)


def load_workflow(root: Path) -> dict[str, Any]:
    return read_yaml(root / "harness" / "workflow.yaml")


def load_policies(root: Path) -> dict[str, Any]:
    return read_yaml(root / "harness" / "policies.yaml")


def load_profile(root: Path) -> dict[str, Any]:
    return read_yaml(root / "harness" / "project-profile.yaml")


def load_knowledge(root: Path) -> dict[str, Any]:
    return read_yaml(root / "harness" / "knowledge-sources.yaml")


def load_environment(root: Path, name: str = "dev") -> dict[str, Any]:
    return read_yaml(root / "environments" / f"{name}.yaml")


def load_current_task(root: Path) -> dict[str, Any] | None:
    data = read_yaml(root / "tasks" / "current.yaml") or {}
    return data.get("task")


def load_backlog(root: Path) -> dict[str, Any]:
    return read_yaml(root / "tasks" / "backlog.yaml")


def state_role(workflow: dict[str, Any], state_name: str) -> str:
    try:
        return str(workflow["states"][state_name]["role"])
    except KeyError as error:
        raise HarnessError(f"Estado desconocido en workflow: {state_name}") from error


def validate_schema(root: Path, schema_name: str, data: Any) -> list[str]:
    import jsonschema

    schema = read_json(root / "harness" / "schemas" / f"{schema_name}.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    messages = []
    for error in validator.iter_errors(data):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return sorted(messages)


def evidence_task_dir(root: Path, task_id: str) -> Path:
    if not task_id or not TASK_ID_RE.fullmatch(task_id):
        raise HarnessError("task_id invalido para evidencia")
    return root / "evidence" / task_id


def resolve_repo_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise HarnessError(f"Ruta fuera del repositorio: {relative}") from error
    return path


def to_repo_relative(root: Path, path: str | Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def load_ref(root: Path, state: dict[str, Any], key: str) -> dict[str, Any] | None:
    relative = (state.get("refs") or {}).get(key)
    if not relative:
        return None
    path = resolve_repo_path(root, relative)
    if not path.is_file():
        raise HarnessError(f"Evidencia referenciada no existe: {relative}")
    return read_json(path)


def git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False  # noqa: S607
    )
    if check and result.returncode != 0:
        raise HarnessError(f"git {' '.join(args)} fallo: {result.stderr.strip()}")
    return result.stdout.strip()


def git_tree(root: Path, sha: str) -> str | None:
    if not SHA_RE.fullmatch(sha or ""):
        return None
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{tree}}"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    tree = result.stdout.strip()
    return tree if result.returncode == 0 and SHA_RE.fullmatch(tree) else None


@functools.lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out))


def glob_match(relative: str, pattern: str) -> bool:
    return _glob_regex(pattern).fullmatch(relative.replace("\\", "/")) is not None


def matches_any(relative: str, patterns: Iterable[str]) -> bool:
    return any(glob_match(relative, pattern) for pattern in patterns)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def find_sensitive(text: str) -> list[str]:
    return sorted({label for pattern, label in _SENSITIVE_PATTERNS if pattern.search(text)})


def env_healthy(state: dict[str, Any]) -> bool:
    return (
        state.get("status") == "Ready"
        and state.get("health") == "Green"
        and state.get("health_status") == "Ok"
    )

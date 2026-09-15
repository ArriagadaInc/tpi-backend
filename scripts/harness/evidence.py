"""Write and validate structured harness evidence.

Usage:
  python scripts/harness/evidence.py write --kind <kind> --input <payload.json> --runtime <r> --session <id>
  python scripts/harness/evidence.py validate --file evidence/<task>/<dir>/<file>.json
  python scripts/harness/evidence.py hash --file <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

KIND_ROLES: dict[str, set[str]] = {
    "developer": {"developer"},
    "review": {"reviewer"},
    "candidate_review": {"reviewer"},
    "merge": {"deployer"},
    "candidate": {"deployer"},
    "deployment": {"deployer"},
    "verification": {"deployer"},
    "rollback": {"deployer"},
    "failure": {"developer", "reviewer", "deployer"},
    "approval": {"human"},
    "acceptance": {"human"},
    "resolution": {"human"},
}
HUMAN_KINDS = {"approval", "acceptance", "resolution"}
RESERVED = {"schema_version", "kind", "task_id", "created_at", "role", "created_by", "interactive"}


def _check_payload(root: Path, data: dict[str, Any]) -> None:
    errors = common.validate_schema(root, "evidence", data)
    if errors:
        raise common.HarnessError("evidencia invalida: " + "; ".join(errors[:8]))
    findings = common.find_sensitive(json.dumps({k: v for k, v in data.items() if k != "actor"}))
    if findings:
        raise common.HarnessError(f"evidencia con posible material sensible: {', '.join(findings)}")


def _next_path(directory: Path, kind: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    index = 1 + sum(1 for _ in directory.glob(f"{kind}-*.json"))
    while (directory / f"{kind}-{index:02d}.json").exists():
        index += 1
    return directory / f"{kind}-{index:02d}.json"


def _store(root: Path, task_id: str, role: str, kind: str, data: dict[str, Any]) -> Path:
    _check_payload(root, data)
    directory = common.evidence_task_dir(root, task_id) / common.ROLE_EVIDENCE_DIR[role]
    path = _next_path(directory, kind)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def write_evidence(
    root: Path, kind: str, payload: dict[str, Any], *, runtime: str, session: str
) -> Path:
    if kind in HUMAN_KINDS:
        raise common.HarnessError("la evidencia humana solo la crea scripts/harness/approve.py")
    if kind not in KIND_ROLES:
        raise common.HarnessError(f"tipo de evidencia desconocido: {kind}")
    state = common.load_state(root)
    task_id = state.get("task_id")
    if not task_id:
        raise common.HarnessError("no hay tarea activa")
    role = common.state_role(common.load_workflow(root), state["state"])
    if role not in KIND_ROLES[kind]:
        raise common.HarnessError(f"el rol activo '{role}' no puede registrar evidencia '{kind}'")
    if RESERVED & set(payload):
        raise common.HarnessError(f"campos reservados en payload: {sorted(RESERVED & set(payload))}")
    data = {
        "schema_version": 1,
        "kind": kind,
        "task_id": task_id,
        "created_at": common.now_iso(),
        "role": role,
        "runtime": runtime,
        "session_id": session,
        **payload,
    }
    return _store(root, task_id, role, kind, data)


def write_human_evidence(
    root: Path, kind: str, payload: dict[str, Any], *, actor: dict[str, str]
) -> Path:
    """Internal API for approve.py after its interactive TTY confirmation."""
    if kind not in HUMAN_KINDS:
        raise common.HarnessError("tipo de evidencia no humano")
    state = common.load_state(root)
    task_id = state.get("task_id")
    if not task_id:
        raise common.HarnessError("no hay tarea activa")
    data = {
        "schema_version": 1,
        "kind": kind,
        "task_id": task_id,
        "created_at": common.now_iso(),
        "role": "human",
        "created_by": "scripts/harness/approve.py",
        "interactive": True,
        "actor": actor,
        **payload,
    }
    return _store(root, task_id, "human", kind, data)


def validate_reference(
    root: Path, state: dict[str, Any], evidence_path: str, *, expected_kind: str, actor: str
) -> str:
    relative = common.to_repo_relative(root, evidence_path)
    task_id = state.get("task_id")
    if relative is None or not task_id:
        raise common.HarnessError("evidencia fuera del repositorio o sin tarea")
    expected_dir = f"evidence/{task_id}/{common.ROLE_EVIDENCE_DIR[actor]}/"
    if not relative.startswith(expected_dir):
        raise common.HarnessError(f"la evidencia debe estar en {expected_dir}")
    path = common.resolve_repo_path(root, relative)
    if not path.is_file():
        raise common.HarnessError(f"no existe la evidencia {relative}")
    data = common.read_json(path)
    if data.get("kind") != expected_kind:
        raise common.HarnessError(f"se esperaba evidencia '{expected_kind}' y llego '{data.get('kind')}'")
    if data.get("task_id") != task_id:
        raise common.HarnessError("evidencia de otra tarea")
    _check_payload(root, data)
    return relative


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--kind", required=True)
    write.add_argument("--input", required=True)
    write.add_argument("--runtime", required=True, choices=["claude", "codex", "deepseek", "other"])
    write.add_argument("--session", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--file", required=True)
    hashing = sub.add_parser("hash")
    hashing.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    root = common.ROOT
    try:
        if args.command == "write":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
            path = write_evidence(root, args.kind, payload, runtime=args.runtime, session=args.session)
            print(path.relative_to(root).as_posix())
        elif args.command == "validate":
            _check_payload(root, common.read_json(Path(args.file)))
            print("EVIDENCE VALID")
        else:
            print(common.sha256_file(Path(args.file)))
    except (common.HarnessError, json.JSONDecodeError, OSError) as error:
        print(f"EVIDENCE ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

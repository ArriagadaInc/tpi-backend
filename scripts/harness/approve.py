"""Human decisions of the harness. Run ONLY by a human in an interactive terminal.

Usage:
  python scripts/harness/approve.py activate --task <ID>
  python scripts/harness/approve.py gate --decision approve|reject [--reason <text>]
  python scripts/harness/approve.py accept --decision accept|reject --criteria AC-1,AC-2 [--notes <text>]
  python scripts/harness/approve.py resolve --to <STATE> --reason <text>
  python scripts/harness/approve.py maintenance-scope open --id <id> --worktree <path>
      --write-path <glob> [--write-path <glob> ...] --hours <h> --reason <text>
      [--allow-test-runs --test-basetemp-root <absolute dir outside the repo>]
  python scripts/harness/approve.py maintenance-scope close --id <id> --reason <text>

Agents must never run this script (Claude hooks deny it). Never type credentials here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import common, evidence, maintenance_scope, transition
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import maintenance_scope  # type: ignore[no-redef]
    import transition  # type: ignore[no-redef]

    import evidence  # type: ignore[no-redef]


def _require_tty() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise common.HarnessError("approve.py requiere una terminal interactiva humana")


def _confirm(prompt: str, expected: str) -> None:
    typed = input(prompt).strip()
    if typed != expected:
        raise common.HarnessError("confirmacion no coincide; no se registro ninguna decision")


def _actor(root: Path) -> dict[str, str]:
    name = common.git(root, "config", "user.name", check=False) or "unknown"
    email = common.git(root, "config", "user.email", check=False) or "unknown"
    return {"name": name, "email": email}


def _require_state(root: Path, expected: str) -> dict[str, Any]:
    state = common.load_state(root)
    if state["state"] != expected:
        raise common.HarnessError(f"estado actual {state['state']}; se requiere {expected}")
    return state


def activate(root: Path, task_id: str) -> dict[str, Any]:
    _require_tty()
    state = _require_state(root, "IDLE")
    if state.get("task_id") is not None:
        raise common.HarnessError("IDLE con tarea vinculada: estado inconsistente")
    backlog = common.load_backlog(root)
    item = next((i for i in backlog.get("items", []) if i.get("id") == task_id), None)
    if item is None or not item.get("task"):
        raise common.HarnessError(
            f"'{task_id}' no existe en backlog o no tiene definicion de tarea"
        )
    task = {**item["task"], "status": "active"}
    errors = common.validate_schema(root, "task", {"schema_version": 1, "task": task})
    if errors:
        raise common.HarnessError("tarea invalida: " + "; ".join(errors))
    print(f"Activar tarea {task['id']}: {task['title']}")
    print(f"Clase {task['change_class']} | deploy_required={task['deploy_required']}")
    _confirm("Escribe el ID de la tarea para confirmar: ", task["id"])
    common.write_yaml_atomic(
        root / "tasks" / "current.yaml",
        {"schema_version": 1, "task": task},
        header="# Tarea activa. Activada por approve.py.\n",
    )
    item["status"] = "active"
    common.write_yaml_atomic(root / "tasks" / "backlog.yaml", backlog)
    return transition.apply_transition(root, "activate_task", _human=True)


def gate_package(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    candidate = common.load_ref(root, state, "candidate_evidence")
    review = common.load_ref(root, state, "candidate_review_evidence")
    if not candidate or not review or review.get("decision") != "APPROVED":
        raise common.HarnessError("no hay candidate aprobado por CANDIDATE_REVIEW")
    policies = common.load_policies(root)
    return {
        "approved_commit": candidate["release_sha"],
        "app_digest": candidate["images"]["app"]["digest"],
        "caddy_digest": candidate["images"]["caddy"]["digest"],
        "bundle_sha256": candidate["bundle"]["sha256"],
        "s3_key": candidate["s3"]["key"],
        "application_version": candidate["application_version"]["label"],
        "environment": candidate["environment"],
        "lkg_version_label": candidate["lkg"]["version_label"],
        "candidate_evidence": {
            "path": state["refs"]["candidate_evidence"],
            "sha256": common.sha256_file(
                common.resolve_repo_path(root, state["refs"]["candidate_evidence"])
            ),
        },
        "rollback_authorization": {
            "scope": policies["rollback_authorization"]["scope"],
            "max_attempts": 1,
            "lkg_version_label": candidate["lkg"]["version_label"],
            "conditions": list(policies["rollback_authorization"]["conditions"]),
        },
        "smoke_plan": candidate["smoke_plan"],
        "environment_observed": candidate["environment_observed"],
    }


def gate(root: Path, decision: str, reason: str = "") -> dict[str, Any]:
    _require_tty()
    state = _require_state(root, "WAITING_HUMAN_APPROVAL")
    package = gate_package(root, state)
    print("=== AUTORIZAR DEPLOYMENT DEV ===")
    for key in (
        "approved_commit",
        "application_version",
        "environment",
        "app_digest",
        "caddy_digest",
        "bundle_sha256",
        "s3_key",
        "lkg_version_label",
    ):
        print(f"{key}: {package[key]}")
    print(f"environment_observed: {package['environment_observed']}")
    print("smoke_plan:", ", ".join(str(step) for step in package["smoke_plan"]))
    print("rollback condicionado (1 intento, version-only al LKG):")
    for condition in package["rollback_authorization"]["conditions"]:
        print(f"  - {condition}")
    payload = {k: v for k, v in package.items() if k not in ("smoke_plan", "environment_observed")}
    if decision == "approve":
        _confirm("Escribe el release SHA completo para aprobar: ", package["approved_commit"])
        _confirm("Escribe APROBAR para confirmar: ", "APROBAR")
        payload["decision"] = "approved"
        event = "human_approve"
    else:
        _confirm("Escribe RECHAZAR para confirmar: ", "RECHAZAR")
        payload["decision"] = "rejected"
        payload["reason"] = reason
        event = "human_reject"
    path = evidence.write_human_evidence(root, "approval", payload, actor=_actor(root))
    return transition.apply_transition(root, event, evidence_path=str(path), _human=True)


def accept(root: Path, decision: str, criteria: list[str], notes: str = "") -> dict[str, Any]:
    _require_tty()
    state = _require_state(root, "VERIFYING")
    task = common.load_current_task(root) or {}
    human_ids = {
        c["id"]
        for c in task.get("acceptance_criteria", [])
        if c["verification"] in ("human", "both")
    }
    unknown = set(criteria) - human_ids
    if not criteria or unknown:
        raise common.HarnessError(
            f"criterios invalidos para aceptacion humana: {sorted(unknown) or 'vacio'}"
        )
    status = "accepted" if decision == "accept" else "rejected"
    _confirm(f"Escribe {status.upper()} para confirmar: ", status.upper())
    payload = {
        "decision": "accepted" if decision == "accept" else "rejected",
        "criteria": [{"id": item, "status": status} for item in criteria],
        "notes": notes,
    }
    path = evidence.write_human_evidence(root, "acceptance", payload, actor=_actor(root))
    state["refs"]["acceptance"] = path.relative_to(root).as_posix()
    common.save_state(root, state)
    return state


def resolve(root: Path, to_state: str, reason: str) -> dict[str, Any]:
    _require_tty()
    _require_state(root, "BLOCKED_HUMAN")
    if len(reason.strip()) < 10:
        raise common.HarnessError("la resolucion requiere una razon explicita")
    _confirm(f"Escribe {to_state} para confirmar: ", to_state)
    payload = {"from_state": "BLOCKED_HUMAN", "to_state": to_state, "reason": reason}
    path = evidence.write_human_evidence(root, "resolution", payload, actor=_actor(root))
    return transition.apply_transition(root, "human_resolve", evidence_path=str(path), _human=True)


def _scope_event(root: Path, policies: dict[str, Any], payload: dict[str, Any]) -> None:
    """Append-only open/close log: ids, paths, commits and actor; never secrets."""
    path = maintenance_scope.registry_dir(root, policies) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"at": common.now_iso(), **payload}, ensure_ascii=False) + "\n")


def open_scope(
    root: Path,
    scope_id: str,
    worktree: str,
    write_paths: list[str],
    hours: float,
    reason: str,
    allow_test_runs: bool = False,
    test_basetemp_root: str | None = None,
) -> Path:
    _require_tty()
    policies = common.load_policies(root)
    cfg = maintenance_scope.config(policies)
    path = maintenance_scope.registry_path(root, policies, scope_id)
    if not 0 < hours <= cfg["max_hours"]:
        raise common.HarnessError(f"--hours debe estar entre 0 y {cfg['max_hours']}")
    if path.exists():
        raise common.HarnessError("ya existe un registro con ese identificador: usa uno nuevo")
    if allow_test_runs != (test_basetemp_root is not None):
        raise common.HarnessError("--allow-test-runs y --test-basetemp-root van juntos")
    worktree_path = Path(worktree).resolve()
    branch, head = maintenance_scope.worktree_identity(root, worktree_path)
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    record: dict[str, Any] = {
        "schema_version": 1,
        "id": scope_id,
        "status": "open",
        "reason": reason.strip(),
        "control_checkout": str(root.resolve()),
        "worktree": str(worktree_path),
        "branch": branch,
        "head": head,
        "write_paths": list(write_paths),
        "allow_test_runs": allow_test_runs,
        "test_basetemp_root": test_basetemp_root,
        "created_at": maintenance_scope.iso(now),
        "expires_at": maintenance_scope.iso(now + dt.timedelta(hours=hours)),
        "opened_by": _actor(root),
        "closed_at": None,
        "closed_by": None,
        "close_reason": None,
    }
    maintenance_scope.check_record(root, policies, scope_id, record, now=now)
    summary = {
        key: record[key]
        for key in ("id", "worktree", "branch", "head", "write_paths", "allow_test_runs")
    }
    print(json.dumps({**summary, "expires_at": record["expires_at"]}, indent=2))
    _confirm(f"Escribe ABRIR {scope_id} para confirmar: ", f"ABRIR {scope_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    common.write_json_atomic(path, record)
    _scope_event(root, policies, {"event": "opened", **summary, "actor": record["opened_by"]})
    return path


def close_scope(root: Path, scope_id: str, reason: str) -> Path:
    _require_tty()
    policies = common.load_policies(root)
    path = maintenance_scope.registry_path(root, policies, scope_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise common.HarnessError(f"registro de alcance ilegible: {error}") from error
    if not isinstance(record, dict) or record.get("status") != "open":
        raise common.HarnessError("el alcance no esta abierto")
    if len(reason.strip()) < 10:
        raise common.HarnessError("el cierre requiere una razon explicita")
    _confirm(f"Escribe CERRAR {scope_id} para confirmar: ", f"CERRAR {scope_id}")
    try:
        _branch, head_at_close = maintenance_scope.worktree_identity(
            root, Path(str(record.get("worktree", ""))).resolve()
        )
    except common.HarnessError:
        head_at_close = None  # closing must work even if the worktree is gone or changed
    record.update(
        status="closed",
        closed_at=common.now_iso(),
        closed_by=_actor(root),
        close_reason=reason.strip(),
        head_at_close=head_at_close,
    )
    common.write_json_atomic(path, record)
    _scope_event(
        root,
        policies,
        {
            "event": "closed",
            "id": scope_id,
            "head_at_close": head_at_close,
            "actor": record["closed_by"],
        },
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    act = sub.add_parser("activate")
    act.add_argument("--task", required=True)
    gt = sub.add_parser("gate")
    gt.add_argument("--decision", required=True, choices=["approve", "reject"])
    gt.add_argument("--reason", default="")
    ac = sub.add_parser("accept")
    ac.add_argument("--decision", required=True, choices=["accept", "reject"])
    ac.add_argument("--criteria", required=True)
    ac.add_argument("--notes", default="")
    rs = sub.add_parser("resolve")
    rs.add_argument("--to", required=True)
    rs.add_argument("--reason", required=True)
    ms = sub.add_parser("maintenance-scope")
    ms_sub = ms.add_subparsers(dest="action", required=True)
    mo = ms_sub.add_parser("open")
    mo.add_argument("--id", required=True)
    mo.add_argument("--worktree", required=True)
    mo.add_argument("--write-path", dest="write_paths", action="append", required=True)
    mo.add_argument("--hours", type=float, required=True)
    mo.add_argument("--reason", required=True)
    mo.add_argument("--allow-test-runs", action="store_true")
    mo.add_argument("--test-basetemp-root", default=None)
    mc = ms_sub.add_parser("close")
    mc.add_argument("--id", required=True)
    mc.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    root = common.ROOT
    if args.command == "maintenance-scope":
        try:
            if args.action == "open":
                path = open_scope(
                    root,
                    args.id,
                    args.worktree,
                    args.write_paths,
                    args.hours,
                    args.reason,
                    args.allow_test_runs,
                    args.test_basetemp_root,
                )
            else:
                path = close_scope(root, args.id, args.reason)
        except (common.HarnessError, EOFError, KeyboardInterrupt) as error:
            print(f"HUMAN DECISION NOT RECORDED: {error}", file=sys.stderr)
            return 1
        print(f"alcance {args.id}: {path}")
        return 0
    try:
        if args.command == "activate":
            state = activate(root, args.task)
        elif args.command == "gate":
            state = gate(root, args.decision, args.reason)
        elif args.command == "accept":
            state = accept(
                root,
                args.decision,
                [c.strip() for c in args.criteria.split(",") if c.strip()],
                args.notes,
            )
        else:
            state = resolve(root, args.to, args.reason)
    except (common.HarnessError, EOFError, KeyboardInterrupt) as error:
        print(f"HUMAN DECISION NOT RECORDED: {error}", file=sys.stderr)
        return 1
    print(transition.describe(root, state, None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

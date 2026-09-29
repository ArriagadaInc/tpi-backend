"""Managed git worktrees for harness roles.

Usage:
  python scripts/harness/worktree.py create --ref <sha|branch> [--branch harness/<task>-<slug>] --purpose <text>
  python scripts/harness/worktree.py list
  python scripts/harness/worktree.py remove --name <name>
  python scripts/harness/worktree.py prune

Names are deterministic: .harness-worktrees/<task>-<role>-<sha7>. Only registered harness
worktrees are ever removed; pre-existing worktrees are never touched. Removal is never forced.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

BASE = ".harness-worktrees"


def create(root: Path, *, ref: str, purpose: str, branch: str | None = None) -> dict[str, Any]:
    state = common.load_state(root)
    task_id = state.get("task_id")
    role = common.state_role(common.load_workflow(root), state["state"])
    if not task_id or role not in common.AGENT_ROLES:
        raise common.HarnessError("worktrees solo para un rol agente con tarea activa")
    sha = common.git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if branch is not None:
        if role != "developer" or not branch.startswith(f"harness/{task_id}"):
            raise common.HarnessError(f"solo el Developer crea ramas harness/{task_id}*")
    name = f"{task_id}-{role}-{sha[:7]}"
    path = root / BASE / name
    if path.exists():
        raise common.HarnessError(f"el worktree ya existe: {name}")
    args = ["worktree", "add"]
    args += ["-b", branch, str(path), sha] if branch else ["--detach", str(path), sha]
    common.git(root, *args)
    head = common.git(path, "rev-parse", "HEAD")
    if head != sha:
        raise common.HarnessError("el worktree no quedo en el SHA esperado")
    entry = {
        "path": f"{BASE}/{name}",
        "role": role,
        "sha": sha,
        "branch": branch,
        "purpose": purpose,
        "created_at": common.now_iso(),
    }
    state["worktrees"] = [*state.get("worktrees", []), entry]
    common.save_state(root, state)
    return entry


def _remove_path(root: Path, relative: str) -> str | None:
    path = root / relative
    if not relative.startswith(f"{BASE}/"):
        return f"ruta no administrada: {relative}"
    if path.exists():
        result = subprocess.run(  # noqa: S603
            ["git", "worktree", "remove", str(path)],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"no se removio {relative} (cambios locales?): {result.stderr.strip()}"
    return None


def cleanup_task(root: Path, state: dict[str, Any], task_id: str) -> list[str]:
    warnings = []
    for entry in state.get("worktrees", []):
        if Path(entry["path"]).name.startswith(f"{task_id}-"):
            problem = _remove_path(root, entry["path"])
            if problem:
                warnings.append(problem)
    common.git(root, "worktree", "prune", check=False)
    for warning in warnings:
        print(f"WORKTREE WARNING: {warning}", file=sys.stderr)
    return warnings


def remove(root: Path, name: str) -> None:
    state = common.load_state(root)
    entries = [e for e in state.get("worktrees", []) if Path(e["path"]).name == name]
    if not entries:
        raise common.HarnessError(f"worktree no registrado por el Harness: {name}")
    problem = _remove_path(root, entries[0]["path"])
    if problem:
        raise common.HarnessError(problem)
    state["worktrees"] = [e for e in state["worktrees"] if Path(e["path"]).name != name]
    common.save_state(root, state)
    common.git(root, "worktree", "prune", check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("create")
    make.add_argument("--ref", required=True)
    make.add_argument("--branch")
    make.add_argument("--purpose", required=True)
    sub.add_parser("list")
    drop = sub.add_parser("remove")
    drop.add_argument("--name", required=True)
    sub.add_parser("prune")
    args = parser.parse_args(argv)
    root = common.ROOT
    try:
        if args.command == "create":
            print(create(root, ref=args.ref, purpose=args.purpose, branch=args.branch)["path"])
        elif args.command == "list":
            for entry in common.load_state(root).get("worktrees", []):
                print(f"{entry['path']}  {entry['role']}  {entry['sha'][:12]}  {entry['purpose']}")
        elif args.command == "remove":
            remove(root, args.name)
        else:
            common.git(root, "worktree", "prune")
    except common.HarnessError as error:
        print(f"WORKTREE ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

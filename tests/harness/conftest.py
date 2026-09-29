"""Shared fixtures for the harness test suite (tests A-J, M1-M6, section 14/10).

Two testing strategies are used, chosen per-test for the cheapest honest coverage:

1. ``tmp_harness_repo``: a full, isolated copy of the harness skeleton in its own git
   repository under ``tmp_path``. Used whenever a test needs real file structure,
   real git history, or must mutate ``harness/state.json`` (init/validate_repo/
   transition/worktree tests). Never touches the real repository.
2. Direct calls against the real repository root (``REAL_ROOT``) with
   ``monkeypatch.setattr(common, "load_state", ...)`` to synthesize a role/state
   for a single decision function (guard.decide / aws_guard.evaluate). These are
   read-only against the real policies/workflow and never write outside
   ``.harness-runtime/`` (already gitignored).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REAL_ROOT = Path(__file__).resolve().parents[2]

_SKELETON_ITEMS = (
    "AGENTS.md",
    "CLAUDE.md",
    "init.sh",
    "init.ps1",
    ".mcp.json",
    ".claude",
    "harness",
    "agents",
    "scripts/harness",
    "environments",
    "tasks",
    "progress",
    "evidence",
    "runtime",
    "docs",
    ".github",
    "deployment",
    "scripts/release",
)


def _copy_skeleton(dest: Path) -> None:
    for item in _SKELETON_ITEMS:
        src = REAL_ROOT / item
        target = dest / item
        if src.is_dir():
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


def _git(dest: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=dest, check=True, capture_output=True, text=True
    )  # noqa: S603,S607


@pytest.fixture
def tmp_harness_repo(tmp_path: Path) -> Path:
    """A clean, isolated git repo containing a full copy of the harness skeleton."""
    dest = tmp_path / "repo"
    dest.mkdir()
    _copy_skeleton(dest)
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "config", "user.email", "harness-test@example.invalid")
    _git(dest, "config", "user.name", "harness-test")
    _git(dest, "remote", "add", "origin", "https://github.com/ArriagadaInc/tpi-backend.git")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "harness skeleton snapshot for tests")
    return dest


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_task(task_id: str = "TEST-1", **overrides: Any) -> dict[str, Any]:
    task = {
        "id": task_id,
        "title": "Tarea sintetica de test",
        "objective": "Ejercitar el Harness con datos sinteticos, sin AWS real.",
        "source": {"type": "backlog", "ref": "TEST-BACKLOG"},
        "change_class": "A",
        "deploy_required": True,
        "requires_human_acceptance": False,
        "acceptance_criteria": [
            {"id": "AC-1", "description": "criterio sintetico", "verification": "automated"}
        ],
        "constraints": [],
        "dependencies": [],
        "risk": {"level": "low", "notes": "test"},
        "status": "active",
    }
    task.update(overrides)
    return task


def bind_task(
    root: Path, task_id: str = "TEST-1", state_name: str = "NEW", **task_overrides: Any
) -> None:
    """Write tasks/current.yaml + harness/state.json consistently for a given state."""
    import yaml

    task = make_task(task_id, **task_overrides)
    (root / "tasks" / "current.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "task": task}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    state = json.loads((root / "harness" / "state.json").read_text(encoding="utf-8"))
    state.update(
        state=state_name,
        task_id=task_id,
        rework_round=0,
        candidate_rework_round=0,
        rollback_attempted=False,
        refs={},
        sessions={"developer": None, "reviewer": None, "deployer": None},
    )
    write_json(root / "harness" / "state.json", state)


def set_state(root: Path, **overrides: Any) -> None:
    state = json.loads((root / "harness" / "state.json").read_text(encoding="utf-8"))
    state.update(**overrides)
    write_json(root / "harness" / "state.json", state)

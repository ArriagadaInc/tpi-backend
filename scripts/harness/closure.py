"""Deterministic administrative closure of a task (DONE or cancelled)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from . import common, context_compact, worktree
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import context_compact  # type: ignore[no-redef]
    import worktree  # type: ignore[no-redef]


def _release_summary(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    merge = common.load_ref(root, state, "merge_evidence")
    candidate = common.load_ref(root, state, "candidate_evidence")
    deployment = common.load_ref(root, state, "deployment_evidence")
    verification = common.load_ref(root, state, "verification_evidence")
    if merge:
        summary["release_sha"] = merge["release_sha"]
        summary["pr_number"] = merge["pr_number"]
    if candidate:
        summary["application_version"] = candidate["application_version"]["label"]
        summary["bundle_sha256"] = candidate["bundle"]["sha256"]
        summary["lkg"] = candidate["lkg"]["version_label"]
    if deployment:
        summary["deployment"] = deployment["result"]
        summary["deployed_commit"] = deployment["deployed_commit"]
    if verification:
        summary["verification"] = verification["result"]
    return summary


def _bitacora_entry(task: dict[str, Any], summary: dict[str, Any], cancelled: bool) -> str:
    status = "cancelada" if cancelled else "cerrada (DONE)"
    lines = [
        f"### {common.today()} - Harness: tarea {task['id']} {status}",
        "",
        f"- Titulo: {task['title']}",
        f"- Evidencia: `evidence/{task['id']}/` y `tasks/completed/{task['id']}.yaml`.",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in summary.items())
    return "\n".join(lines) + "\n\n"


def _append_bitacora(root: Path, entry: str) -> bool:
    path = root / "docs" / "BITACORA.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    marker = text.find("\n### ")
    if marker < 0:
        return False
    common.write_text_atomic(path, text[: marker + 1] + entry + text[marker + 1 :])
    return True


def close_task(root: Path, state: dict[str, Any], *, cancelled: bool) -> dict[str, Any]:
    task = common.load_current_task(root)
    task_id = state.get("task_id")
    if task is None or task.get("id") != task_id:
        raise common.HarnessError("cierre sin tarea activa coherente")
    summary = _release_summary(root, state)
    final_task = {**task, "status": "cancelled" if cancelled else "closed"}
    record = {
        "schema_version": 1,
        "task": final_task,
        "closure": {
            "closed_at": common.now_iso(),
            "final_state": "CANCELLED" if cancelled else "DONE",
            "evidence_dir": f"evidence/{task_id}",
            "release": summary,
            "rework_rounds": state.get("rework_round", 0),
        },
    }
    common.write_yaml_atomic(root / "tasks" / "completed" / f"{task_id}.yaml", record)

    backlog = common.load_backlog(root)
    backlog["items"] = [item for item in backlog.get("items", []) if item.get("id") != task_id]
    common.write_yaml_atomic(
        root / "tasks" / "backlog.yaml",
        backlog,
        header="# Backlog del Harness. Ninguna tarea es current hasta que el humano la active.\n",
    )

    _append_bitacora(root, _bitacora_entry(task, summary, cancelled))
    worktree.cleanup_task(root, state, task_id)
    state["worktrees"] = [w for w in state.get("worktrees", []) if not Path(w["path"]).name.startswith(f"{task_id}-")]

    common.write_yaml_atomic(
        root / "tasks" / "current.yaml",
        {"schema_version": 1, "task": None},
        header="# Tarea activa. La elige el humano con: python scripts/harness/approve.py activate --task <ID>\n",
    )
    state.update(
        task_id=None,
        rework_round=0,
        candidate_rework_round=0,
        rollback_attempted=False,
        refs={},
        sessions={"developer": None, "reviewer": None, "deployer": None},
    )
    context_compact.compact(
        root,
        label=f"{task_id}-closure",
        note=f"Tarea {task_id} {'cancelada' if cancelled else 'cerrada'}; resumen en tasks/completed/{task_id}.yaml",
        state_override={"state": "IDLE", "task_id": None},
    )
    return state

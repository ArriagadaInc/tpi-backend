"""Deterministic projection of harness/state.json into progress/current.md (Harness v1.1).

state.json stays the only authority. progress/current.md is a human/LLM cache (AGENTS.md,
authority level 6); this module only keeps a small, clearly delimited block of it in sync:

  <!-- harness:projection:begin ... -->
  - Estado del Harness: <state> (rol: <role>)
  - Tarea: <task_id>
  - Proximo paso: <next_action>
  - Ultima transicion: <id> (<from> -> <to>)
  - Actualizado: <updated_at>
  <!-- harness:projection:end -->

transition.py (and therefore approve.py, which applies transitions through it) refreshes the
block AFTER state.json has been written, so the projection no longer depends on an LLM
remembering to update it, nor on the order context_compact.py / transition.py were run.
A failure here is only a warning: it can never undo or invalidate a correct transition.
Everything outside the block (free notes, DECISION:/BLOCKER: lines) is left untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

BEGIN = (
    "<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py;"
    " no editar a mano) -->"
)
END = "<!-- harness:projection:end -->"
_BEGIN_PREFIX = "<!-- harness:projection:begin"
_LEGACY_PREFIXES = ("- Estado del Harness:", "- Tarea:")


def render(state: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    spec = workflow["states"][state["state"]]
    last = state.get("last_transition") or {}
    transition = (
        f"{last.get('transition')} ({last.get('from')} -> {last.get('to')})" if last else "-"
    )
    return [
        BEGIN,
        f"- Estado del Harness: {state['state']} (rol: {spec['role']})",
        f"- Tarea: {state.get('task_id') or 'ninguna'}",
        f"- Proximo paso: {spec['next_action']}",
        f"- Ultima transicion: {transition}",
        f"- Actualizado: {state.get('updated_at')}",
        END,
    ]


def apply(text: str, block: list[str]) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(_BEGIN_PREFIX)), None)
    if start is not None:
        end = next((i for i in range(start, len(lines)) if lines[i].strip() == END), None)
        if end is None:
            raise common.HarnessError("bloque de proyeccion sin marcador de cierre")
        lines[start : end + 1] = block
        return "\n".join(lines) + "\n"
    # First sync of a legacy file: the projection replaces the stale state/task lines of the
    # "## Estado" section (they are exactly what the block now owns); nothing else is removed.
    heading = next((i for i, line in enumerate(lines) if line.strip() == "## Estado"), None)
    if heading is not None:
        stop = next(
            (i for i in range(heading + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
        )
        section = [
            line for line in lines[heading + 1 : stop] if not line.startswith(_LEGACY_PREFIXES)
        ]
        lines[heading + 1 : stop] = block + section
        return "\n".join(lines) + "\n"
    title = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    insert = [*block, ""] if title is None else ["", "## Estado", *block]
    position = 0 if title is None else title + 1
    lines[position:position] = insert
    return "\n".join(lines) + "\n"


def sync(root: Path, state: dict[str, Any] | None = None) -> str | None:
    """Refresh the block. Returns a warning (never raises): state.json keeps authority."""
    try:
        state = state if state is not None else common.load_state(root)
        workflow = common.load_workflow(root)
        path = root / "progress" / "current.md"
        text = path.read_text(encoding="utf-8") if path.is_file() else "# Progreso actual\n"
        updated = apply(text, render(state, workflow))
        if updated != text:
            common.write_text_atomic(path, updated)
    except Exception as error:  # noqa: BLE001 - secondary projection, never fatal
        return f"progress/current.md no sincronizado ({type(error).__name__}: {error})"
    return None


def in_sync(root: Path, state: dict[str, Any]) -> bool:
    """True if progress/current.md already shows exactly this state's projection."""
    try:
        text = (root / "progress" / "current.md").read_text(encoding="utf-8")
        block = render(state, common.load_workflow(root))
    except Exception:  # noqa: BLE001 - diagnostics only
        return False
    return "\n".join(block) in text

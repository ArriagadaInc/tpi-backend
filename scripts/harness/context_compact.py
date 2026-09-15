"""Non-destructive compaction of progress/current.md.

Usage: python scripts/harness/context_compact.py --label <etapa> [--note <texto>]

1. Archives the full current.md into progress/sessions/ (never deletes history).
2. Appends lines starting with "DECISION:" to progress/decisions.md.
3. Rebuilds a small current.md: state, task, recent status, next action, blockers.
4. Verifies every original line exists in the archive before replacing current.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

KEEP_RECENT = 5


def _section(text: str, title: str) -> list[str]:
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return [line for line in match.group(1).splitlines() if line.strip()]


def _unique_session_path(root: Path, label: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-") or "session"
    directory = root / "progress" / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    base = directory / f"{common.today()}-{safe}.md"
    index = 2
    path = base
    while path.exists():
        path = directory / f"{common.today()}-{safe}-{index}.md"
        index += 1
    return path


def _append_decisions(root: Path, decisions: list[str], session_rel: str) -> int:
    path = root / "progress" / "decisions.md"
    text = path.read_text(encoding="utf-8")
    ids = [int(n) for n in re.findall(r"\| D-(\d+) \|", text)]
    next_id = max(ids, default=0) + 1
    added = 0
    lines = []
    for decision in decisions:
        body = decision.split(":", 1)[1].strip().replace("|", "/")
        if body and body not in text:
            lines.append(f"| D-{next_id:03d} | {common.today()} | {body} | {session_rel} |")
            next_id += 1
            added += 1
    if lines:
        common.write_text_atomic(path, text.rstrip("\n") + "\n" + "\n".join(lines) + "\n")
    return added


def compact(
    root: Path,
    *,
    label: str,
    note: str | None = None,
    state_override: dict[str, Any] | None = None,
) -> Path:
    current_path = root / "progress" / "current.md"
    original = current_path.read_text(encoding="utf-8") if current_path.is_file() else ""
    state = {**common.load_state(root), **(state_override or {})}
    workflow = common.load_workflow(root)
    spec = workflow["states"][state["state"]]
    limit = int(common.load_policies(root)["harness"]["progress_current_max_lines"])

    session_path = _unique_session_path(root, label)
    session_rel = session_path.relative_to(root).as_posix()
    archive = f"# Sesion archivada: {label}\n\n- Archivada: {common.now_iso()}\n- Estado: {state['state']}\n\n{original}"
    common.write_text_atomic(session_path, archive)
    archived = session_path.read_text(encoding="utf-8")
    missing = [line for line in original.splitlines() if line.strip() and line not in archived]
    if missing:
        raise common.HarnessError("compactacion abortada: el archivo de sesion no preserva el contenido")

    decisions = [line.strip() for line in original.splitlines() if line.strip().startswith("DECISION:")]
    _append_decisions(root, decisions, session_rel)

    blockers = [line for line in original.splitlines() if line.strip().startswith(("BLOCKER:", "- BLOCKER:"))]
    recent = [line for line in _section(original, "Estado reciente") if not line.startswith("DECISION:")]
    if note:
        recent.append(f"- {common.today()}: {note}")
    recent = recent[-KEEP_RECENT:]

    lines = [
        "# Progreso actual",
        "",
        "## Estado",
        f"- Estado del Harness: {state['state']} (rol: {spec['role']})",
        f"- Tarea: {state.get('task_id') or 'ninguna'}",
        f"- Ultima sesion archivada: {session_rel}",
        "",
        "## Estado reciente",
        *(recent or ["- (sin novedades)"]),
        "",
        "## Proximo paso",
        f"- {spec['next_action']}",
        "",
        "## Bloqueos",
        *(blockers or ["- Ninguno."]),
        "",
    ]
    if len(lines) > limit:
        raise common.HarnessError("current.md compactado supera el limite; revisar bloqueos")
    common.write_text_atomic(current_path, "\n".join(lines))
    return session_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True)
    parser.add_argument("--note")
    args = parser.parse_args(argv)
    try:
        path = compact(common.ROOT, label=args.label, note=args.note)
    except common.HarnessError as error:
        print(f"COMPACT ERROR: {error}", file=sys.stderr)
        return 1
    print(f"archivado en {path.relative_to(common.ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

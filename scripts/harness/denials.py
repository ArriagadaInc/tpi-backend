"""Session-scoped DENIED latch shared by guard.py / aws_guard.py and the Supervisor (v1.1).

The Supervisor launches each worker with ``TPI_SUPERVISOR_TURN=<session_id>`` in its
environment. When a guard denies an operation inside that process tree it appends one record
to ``.harness-runtime/supervisor/denials/<session_id>.jsonl``; after the worker exits the
Supervisor reads ONLY the file of the turn it launched and stops if it is not empty.

- Not a source of truth: never read by transition.py/approve.py, never touches state.json.
- Manual mode (variable absent): nothing is written.
- Session scoped: the file name is the unique session id of one turn, so a later session can
  never inherit or reinterpret an earlier block.
- No secrets: only the source, the guard's fixed reason (redacted, truncated) and a label.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

ENV_VAR = "TPI_SUPERVISOR_TURN"
DENIALS_DIR = Path(".harness-runtime") / "supervisor" / "denials"
_TURN_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def turn_id(env: Mapping[str, str] | None = None) -> str | None:
    value = (os.environ if env is None else env).get(ENV_VAR, "")
    return value if _TURN_RE.fullmatch(value) else None


def path_for(root: Path, turn: str) -> Path:
    if not _TURN_RE.fullmatch(turn):
        raise ValueError("turn id invalido")
    return root / DENIALS_DIR / f"{turn}.jsonl"


def record(
    root: Path,
    source: str,
    reason: str,
    *,
    label: str = "",
    env: Mapping[str, str] | None = None,
) -> bool:
    """Append a DENIED record for the current Supervisor turn. Never raises."""
    turn = turn_id(env)
    if turn is None:
        return False
    entry = {
        "at": common.now_iso(),
        "turn": turn,
        "source": source,
        "reason": common.redact(str(reason))[:300],
        "label": common.redact(str(label))[:80],
    }
    with contextlib.suppress(OSError, ValueError):
        target = path_for(root, turn)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    return False


def read(root: Path, turn: str) -> list[dict[str, Any]]:
    """Records of exactly one turn. Unreadable lines still count as a denial (fail closed)."""
    try:
        text = path_for(root, turn).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            item = {"source": "unknown", "reason": "registro ilegible"}
        records.append(item if isinstance(item, dict) else {"source": "unknown"})
    return records

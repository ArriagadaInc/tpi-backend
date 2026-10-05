"""Prove the EFFECTIVE tool configuration of a maintenance-scope runtime (Harness v1.2).

The scope guard judges only the tool calls that Claude Code delivers to the PreToolUse hook: the
``matcher`` of .claude/settings.json. A tool outside that matcher never reaches guard.py and an
active scope does not restrict it. So the human launches the runtime with ``--tools`` limited to
``harness.maintenance_scope.runtime_tools`` and, before relying on the scope, proves what the
runtime really loaded. This script does that from the ``system``/``init`` event of the runtime's
stream-json transcript.

    claude ... --output-format stream-json --verbose | Out-File -Encoding utf8 init.jsonl
    python scripts/harness/check_scope_tools.py --init init.jsonl

It fails (exit 1) unless:

* exactly one ``system``/``init`` event is present (zero or several means the evidence is missing,
  foreign or spliced, so it is refused rather than trusting the first);
* every effective tool is in ``runtime_tools``, none is an MCP tool and no MCP server is loaded;
* every effective tool is delivered to the hook (full-name match, independent of the unanchored
  regex the runtime compiles).

Session identity. A ``claude -p`` probe is a different process from the interactive session that
does the work, so its init event alone proves nothing about that session. To bind the check to the
real session, pass ``--session-id <id>`` and ``--cwd <dir>`` (the values the working session must
report), and ``--guard-log <log> --scope-id <id>`` to cross-check that the init's session is one of
the sessions whose tool calls actually reached the guard. The field names read here (``session_id``
and ``cwd`` of the init event) are the same keys guard.py records for tool events, but their exact
spelling in a real init event must be confirmed against a runtime capture; if it differs, only
``init_session_id``/``init_cwd`` change.

Read-only. Never launches the runtime and never writes anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]


def hook_matchers(root: Path) -> list[str]:
    """The PreToolUse matchers configured in .claude/settings.json."""
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    entries = (settings.get("hooks") or {}).get("PreToolUse") or []
    return [str(entry["matcher"]) for entry in entries if entry.get("matcher")]


def reaches_hook(tool: str, matchers: Iterable[str]) -> bool:
    """True if the WHOLE tool name matches a PreToolUse matcher.

    Claude Code compiles a matcher that contains regex characters as an unanchored regex (so
    ``Write`` would also match ``TodoWrite``). Requiring a full match keeps this check
    independent of that detail: a tool passes only if the matcher names it unambiguously.
    """
    return any(re.fullmatch(matcher, tool) for matcher in matchers)


def runtime_tools(policies: Mapping[str, Any]) -> list[str]:
    return list(policies["harness"]["maintenance_scope"]["runtime_tools"])


def _read_text(path: Path) -> str:
    """Decode a transcript; Windows PowerShell 5.1 redirects (``>``) write UTF-16 with a BOM."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def init_events(path: Path) -> list[dict[str, Any]]:
    """Every ``system``/``init`` event of a stream-json transcript, in order.

    Non-JSON lines are skipped as noise (a stream transcript is JSON events, sometimes with other
    lines). An unreadable or undecodable file raises, and ``main`` reports that as ``CHECK: FAIL``.
    Whether the count (0, 1, or more) is acceptable is the caller's decision: ``assess`` requires
    exactly one.
    """
    events: list[dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(event, dict)
            and event.get("type") == "system"
            and event.get("subtype") == "init"
        ):
            events.append(event)
    return events


def read_init(path: Path) -> dict[str, Any] | None:
    """Exactly one ``system``/``init`` event, or None (zero or several are both refused)."""
    events = init_events(path)
    return events[0] if len(events) == 1 else None


def init_session_id(event: Mapping[str, Any]) -> str | None:
    """The session id the init event reports.

    Assumed key ``session_id`` (the key guard.py records in .harness-runtime/guard.log for tool
    events). Confirm the real spelling against a runtime capture; only this function and
    ``init_cwd`` need changing if it differs.
    """
    value = event.get("session_id")
    return str(value) if isinstance(value, str) and value else None


def init_cwd(event: Mapping[str, Any]) -> str | None:
    """The working directory the init event reports (assumed key ``cwd``; see init_session_id)."""
    value = event.get("cwd")
    return str(value) if isinstance(value, str) and value else None


def _same_dir(left: str | None, right: str | None) -> bool:
    """Case- and separator-insensitive directory comparison (Windows)."""
    if not left or not right:
        return False
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def logged_tools(guard_log: Path, scope_id: str) -> set[str]:
    """Tools that reached the guard under the given scope id, from .harness-runtime/guard.log."""
    tools: set[str] = set()
    for line in guard_log.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("maintenance_scope") == scope_id:
            tools.add(str(entry.get("tool")))
    return tools


def logged_sessions(guard_log: Path, scope_id: str) -> set[str]:
    """Session ids whose tool calls reached the guard under the scope, from guard.log."""
    sessions: set[str] = set()
    for line in guard_log.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("maintenance_scope") == scope_id:
            sid = entry.get("session_id")
            if isinstance(sid, str) and sid:
                sessions.add(sid)
    return sessions


def assess(
    root: Path,
    events: list[dict[str, Any]],
    session_id: str | None = None,
    cwd: str | None = None,
    guard_log: Path | None = None,
    scope_id: str | None = None,
) -> list[tuple[bool, str]]:
    """(ok, message) per check; the configuration is acceptable only if all are ok.

    ``events`` is every init event of a transcript. Exactly one is required: an old, foreign or
    spliced transcript (zero or several init events) is refused instead of trusting the first.
    """
    policies = common.load_policies(root)
    allowed = runtime_tools(policies)
    matchers = hook_matchers(root)
    results: list[tuple[bool, str]] = []

    def check(ok: bool, message: str) -> None:
        results.append((ok, message))

    check(bool(matchers), "el hook PreToolUse tiene un matcher en .claude/settings.json")
    if len(events) != 1:
        check(
            False,
            f"exactamente un evento system/init (hay {len(events)}): evidencia ajena, ambigua o "
            "malformada",
        )
        return results
    init = events[0]
    if session_id is not None:
        got = init_session_id(init)
        check(
            got == session_id,
            f"el init pertenece a la sesion esperada (session_id {got!r} != {session_id!r})",
        )
    if cwd is not None:
        got = init_cwd(init)
        check(
            _same_dir(got, cwd), f"el init se lanzo desde el cwd esperado (cwd {got!r} != {cwd!r})"
        )
    tools = init.get("tools")
    if not isinstance(tools, list) or not tools:
        check(False, "el evento system/init no trae la lista 'tools' del runtime")
        return results
    effective = [str(tool) for tool in tools]
    extra = sorted(set(effective) - set(allowed))
    check(not extra, f"herramientas efectivas dentro de runtime_tools (sobran: {extra})")
    mcp_tools = [tool for tool in effective if tool.startswith("mcp__")]
    servers = init.get("mcp_servers")
    check(
        not mcp_tools and not servers, f"sin MCP (herramientas: {mcp_tools}, servidores: {servers})"
    )
    unreached = sorted(tool for tool in effective if not reaches_hook(tool, matchers))
    check(not unreached, f"toda herramienta efectiva llega al hook (no llegan: {unreached})")
    missing = sorted(set(allowed) - set(effective))
    results.append((True, f"INFO herramientas de runtime_tools no cargadas: {missing}"))
    if guard_log is not None and scope_id:
        seen = logged_tools(guard_log, scope_id)
        outside = sorted(seen - set(allowed))
        check(not outside, f"guard.log: solo runtime_tools llegaron al guard (otras: {outside})")
        # Bind the init to the session that actually worked: its session_id must be one of the
        # sessions whose tool calls reached the guard under this scope (not a `claude -p` probe).
        init_sid = init_session_id(init)
        log_sids = logged_sessions(guard_log, scope_id)
        if init_sid and log_sids:
            check(
                init_sid in log_sids,
                f"el init es de la misma sesion que genero guard.log ({init_sid!r} no esta en "
                f"{sorted(log_sids)!r})",
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--init", required=True, type=Path, help="salida stream-json del runtime")
    parser.add_argument("--root", type=Path, default=common.ROOT)
    parser.add_argument("--session-id", default=None, help="session_id esperado del evento init")
    parser.add_argument(
        "--cwd", default=None, help="directorio de trabajo esperado del evento init"
    )
    parser.add_argument("--guard-log", type=Path, default=None)
    parser.add_argument("--scope-id", default=None)
    args = parser.parse_args(argv)
    try:
        events = init_events(args.init)
        results = assess(
            args.root, events, args.session_id, args.cwd, args.guard_log, args.scope_id
        )
    except (OSError, ValueError, KeyError, common.HarnessError) as error:
        print(f"CHECK: FAIL - no se pudo evaluar: {error}")
        return 1
    failed = 0
    for ok, message in results:
        failed += 0 if ok else 1
        print(("PASS " if ok else "FAIL ") + message)
    print("CHECK: PASS" if not failed else "CHECK: FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

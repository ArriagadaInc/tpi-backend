"""D2 regression test.

Bug: the previous hook command was
    python3 guard.py 2>/dev/null || python guard.py || exit 2
If python3 existed but guard.py legitimately DENIED (exit 2), bash's `||` treated the
non-zero exit as "python3 failed" and retried with `python guard.py` -- but stdin had
already been drained by the first invocation, so the retry parsed an empty JSON event
(tool_name == "") which falls through every guard.py branch to the default ALLOW. A
real DENY was silently converted into an ALLOW.

The fix resolves the interpreter once via `command -v` (never touches stdin, never
runs guard.py) and then execs guard.py exactly once, so its exit code is the hook's
exit code with no possibility of a fallback re-run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from tests.harness.conftest import REAL_ROOT

BASH = shutil.which("bash") or shutil.which("sh")
pytestmark = pytest.mark.skipif(BASH is None, reason="requires a POSIX shell (bash/sh) on PATH")


def _hook_command() -> str:
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_hook_command_has_no_stdin_fallback_chain():
    command = _hook_command()
    # The previous vulnerable shape ran guard.py, then `||` into a second guard.py
    # invocation. Assert guard.py appears in the resolved command exactly once.
    assert command.count("guard.py") == 1


def test_hook_invokes_guard_exactly_once_and_preserves_deny(tmp_path: Path):
    project_dir = tmp_path / "project"
    (project_dir / "scripts" / "harness").mkdir(parents=True)
    counter = tmp_path / "invocations.log"
    guard_stub = project_dir / "scripts" / "harness" / "guard.py"
    guard_stub.write_text(
        textwrap.dedent(f"""
            import sys
            sys.stdin.read()
            with open({str(counter)!r}, "a", encoding="utf-8") as fh:
                fh.write("call\\n")
            sys.stderr.write("TPI HARNESS GUARD: DENIED - simulated deny\\n")
            sys.exit(2)
            """),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", _hook_command()],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=30,
    )
    calls = counter.read_text(encoding="utf-8").count("call") if counter.exists() else 0
    assert calls == 1, "guard.py must run exactly once per tool call"
    assert (
        result.returncode == 2
    ), "a DENY from the sole invocation must propagate, never be overridden to ALLOW"


def test_hook_fails_closed_when_no_python_interpreter_available(tmp_path: Path):
    project_dir = tmp_path / "project"
    (project_dir / "scripts" / "harness").mkdir(parents=True)
    counter = tmp_path / "invocations.log"
    guard_stub = project_dir / "scripts" / "harness" / "guard.py"
    guard_stub.write_text(
        f'import sys\nopen({str(counter)!r}, "a").write("call\\n")\nsys.exit(0)\n', encoding="utf-8"
    )
    empty_path_dir = tmp_path / "empty-path"
    empty_path_dir.mkdir()
    env = {"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": str(empty_path_dir)}
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", _hook_command()],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=30,
    )
    assert result.returncode == 2
    assert not counter.exists(), "guard.py must never run when no canonical interpreter resolves"

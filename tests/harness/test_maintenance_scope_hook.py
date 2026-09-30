"""Harness v1.2: the maintenance scope exercised the way the runtime does, not through decide().

Claude Code runs `.claude/settings.json` -> `guard.py` as a subprocess: the event is JSON on stdin,
the verdict is the EXIT CODE and only exit 2 blocks; any other non-zero exit is a non-blocking
hook error and the tool call runs. These tests launch guard.py exactly like that, in isolated
copies of the harness skeleton (and a real git worktree), with fictitious data: nothing touches
the real repository, AWS or the network.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.harness import check_scope_tools, common, maintenance_scope, validate_repo
from tests.harness.conftest import REAL_ROOT, _copy_skeleton, _git

GUARD = Path("scripts") / "harness" / "guard.py"
SID = "hook-scope-01"
GIT = shutil.which("git")


def _posix_bash() -> str | None:
    """A usable POSIX bash. On Windows `shutil.which("bash")` returns WSL's system32 bash, which is
    not usable here; prefer Git for Windows bash."""
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        "/usr/bin/bash",
        "/bin/bash",
    ):
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("bash") or shutil.which("sh")
    if found and "system32" not in found.lower():
        return found
    return None


BASH = _posix_bash()


def _bash_works(bash: str | None) -> bool:
    """True if the found bash can actually run here (MSYS2 bash is denied in some sandboxes)."""
    if not bash:
        return False
    try:
        return (
            subprocess.run(  # noqa: S603
                [bash, "-c", "exit 0"], capture_output=True, timeout=30, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


BASH_OK = _bash_works(BASH)


def _run_hook_command(bash: str, command: str, root: Path, event: dict) -> tuple[int, str]:
    """Run the settings.json hook command exactly as Claude Code would (exit code, stderr)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TPI_HARNESS")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(  # noqa: S603
        [bash, "-c", command],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    return result.returncode, result.stderr


def _fail_closed_command(settings: dict) -> str:
    """The F-E fix for the settings.json hook command (delivered as a diff, installed by a human).

    The current command `exec`s guard.py, so a SyntaxError in guard.py itself (or the interpreter
    failing) exits 1, which Claude Code treats as a NON-blocking hook error. This wrapper runs
    guard.py, lets allow (0) and deny (2) through unchanged, and maps any other exit to 2.
    """
    base = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    marker = 'exec "$PY" "$CLAUDE_PROJECT_DIR/scripts/harness/guard.py"'
    tail = (
        '"$PY" "$CLAUDE_PROJECT_DIR/scripts/harness/guard.py"; rc=$?; '
        'if [ "$rc" -eq 0 ]; then exit 0; fi; '
        'if [ "$rc" -ne 2 ]; then echo "TPI HARNESS GUARD: DENIED - el guard termino con '
        'codigo $rc (fail-closed)" >&2; fi; exit 2'
    )
    assert marker in base, "the settings.json hook command changed; update the F-E wrapper"
    return base.replace(marker, tail)


def run_hook(
    root: Path,
    tool: str,
    tool_input: dict,
    env_extra: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, str]:
    """guard.py as a hook subprocess: (exit code, stderr)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TPI_HARNESS")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})})
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(cwd or root),
        "session_id": "pytest-hook",
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(root / GUARD)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
        timeout=120,
        check=False,
    )
    return result.returncode, result.stderr


def _scripts_only(tmp_path: Path, skip: str | None = None, replace: dict[str, str] | None = None):
    """A root that holds only scripts/harness: enough to start guard.py and fail to import."""
    target = tmp_path / "scripts" / "harness"
    target.mkdir(parents=True)
    for source in (REAL_ROOT / "scripts" / "harness").glob("*.py"):
        if source.name != skip:
            shutil.copy2(source, target / source.name)
    for name, text in (replace or {}).items():
        (target / name).write_text(text, encoding="utf-8")
    return tmp_path


# --- blocker 1: a module the hook needs is missing -> the hook must BLOCK (exit 2) --------------
@pytest.mark.parametrize("missing", ["maintenance_scope", "common", "command_analysis", "denials"])
def test_hook_blocks_with_exit_2_when_a_module_it_imports_is_missing(tmp_path, missing):
    root = _scripts_only(tmp_path, skip=f"{missing}.py")
    code, stderr = run_hook(root, "Read", {"file_path": "README.md"})
    assert code == 2, f"exit {code} would NOT block in Claude Code:\n{stderr}"
    assert "DENIED" in stderr and "no pudo cargar sus modulos" in stderr


def test_hook_blocks_with_exit_2_when_a_module_is_broken(tmp_path):
    root = _scripts_only(tmp_path, replace={"maintenance_scope.py": "def roto(:\n"})
    code, stderr = run_hook(root, "Write", {"file_path": "x.py"})
    assert code == 2 and "DENIED" in stderr, stderr


@pytest.mark.skipif(not BASH_OK, reason="needs a working POSIX bash")
def test_hook_blocks_through_the_settings_json_command_when_a_module_is_missing(tmp_path):
    """The command Claude Code really runs (settings.json), not just `python guard.py`."""
    root = _scripts_only(tmp_path, skip="maintenance_scope.py")
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    code, stderr = _run_hook_command(
        BASH, command, root, {"tool_name": "Write", "tool_input": {"file_path": "x.py"}}
    )
    assert code == 2, stderr
    assert "DENIED" in stderr


# --- F-E: a failure of guard.py itself must still BLOCK (exit 2), not leak as a non-blocking 1 --
@pytest.mark.skipif(not BASH_OK, reason="needs a working POSIX bash")
def test_guard_own_syntax_error_exits_1_with_the_current_command(tmp_path):
    """The defect: a SyntaxError in guard.py itself exits 1 (a NON-blocking hook error)."""
    root = _scripts_only(tmp_path, replace={"guard.py": "def roto(:\n"})
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    code, _stderr = _run_hook_command(
        BASH, command, root, {"tool_name": "Write", "tool_input": {"file_path": "x.py"}}
    )
    assert code == 1


@pytest.mark.skipif(not BASH_OK, reason="needs a working POSIX bash")
def test_guard_own_syntax_error_blocks_with_the_fail_closed_command(tmp_path):
    """The fix: the fail-closed wrapper turns that exit 1 into the blocking exit 2."""
    root = _scripts_only(tmp_path, replace={"guard.py": "def roto(:\n"})
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    code, stderr = _run_hook_command(
        BASH,
        _fail_closed_command(settings),
        root,
        {"tool_name": "Write", "tool_input": {"file_path": "x.py"}},
    )
    assert code == 2, stderr
    assert "DENIED" in stderr


@pytest.mark.skipif(not BASH_OK, reason="needs a working POSIX bash")
def test_fail_closed_command_preserves_allow_and_deny(tmp_harness_repo):
    """Allow (0) and a normal deny (2 with the guard's reason) must be unchanged."""
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = _fail_closed_command(settings)
    allow, _ = _run_hook_command(
        BASH,
        command,
        tmp_harness_repo,
        {"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}},
    )
    assert allow == 0
    deny, stderr = _run_hook_command(
        BASH,
        command,
        tmp_harness_repo,
        {"tool_name": "Edit", "tool_input": {"file_path": "harness/state.json"}},
    )
    assert deny == 2 and "DENIED" in stderr


def test_guard_own_syntax_error_exits_1_as_a_python_subprocess(tmp_path):
    """Without the settings.json wrapper, a SyntaxError in guard.py ITSELF exits 1 (non-blocking).

    This is the exit code the F-E wrapper maps to 2; the wrapper itself is exercised by the
    bash-based tests above (skipped when this sandbox cannot run MSYS2 bash).
    """
    root = _scripts_only(tmp_path, replace={"guard.py": "def roto(:\n"})
    code, _stderr = run_hook(root, "Write", {"file_path": "x.py"})
    assert code == 1


def test_fail_closed_command_maps_nonzero_to_2_and_keeps_allow_deny():
    """The delivered diff replaces the `exec` with a wrapper: allow -> 0, deny -> 2, else -> 2."""
    settings = json.loads((REAL_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    base = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    command = _fail_closed_command(settings)
    assert 'exec "$PY" "$CLAUDE_PROJECT_DIR/scripts/harness/guard.py"' in base
    assert 'exec "$PY" "$CLAUDE_PROJECT_DIR/scripts/harness/guard.py"' not in command
    assert "rc=$?" in command
    assert 'if [ "$rc" -eq 0 ]; then exit 0; fi' in command
    assert 'if [ "$rc" -ne 2 ]; then' in command
    assert command.rstrip().endswith("exit 2")


# --- blocker 1 (other half): validate_repo must fail ---------------------------------------------
def test_validate_repo_passes_on_an_intact_skeleton(tmp_harness_repo):
    errors, _warnings = validate_repo.validate(tmp_harness_repo)
    assert errors == []


def _run_validate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(root / "scripts" / "harness" / "validate_repo.py")],
        capture_output=True,
        text=True,
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )


def test_validate_repo_fails_when_maintenance_scope_is_missing(tmp_harness_repo):
    (tmp_harness_repo / "scripts" / "harness" / "maintenance_scope.py").unlink()
    result = _run_validate(tmp_harness_repo)
    assert result.returncode == 1, result.stdout
    assert "falta ruta obligatoria: scripts/harness/maintenance_scope.py" in result.stdout
    assert "VALIDATE: FAIL" in result.stdout


@pytest.mark.parametrize("missing", ["common.py", "check_scope_tools.py"])
def test_validate_repo_fails_when_a_module_it_imports_is_missing(tmp_harness_repo, missing):
    (tmp_harness_repo / "scripts" / "harness" / missing).unlink()
    assert _run_validate(tmp_harness_repo).returncode != 0


def test_hook_closure_is_exactly_what_required_paths_demands():
    needed = validate_repo.hook_modules(REAL_ROOT)
    assert {"guard", "common", "command_analysis", "denials", "maintenance_scope"} <= needed
    for module in needed:
        assert f"scripts/harness/{module}.py" in validate_repo.REQUIRED_PATHS, module


def test_validate_repo_notices_a_hook_module_dropped_from_required_paths(
    tmp_harness_repo, monkeypatch
):
    trimmed = tuple(
        path for path in validate_repo.REQUIRED_PATHS if not path.endswith("maintenance_scope.py")
    )
    monkeypatch.setattr(validate_repo, "REQUIRED_PATHS", trimmed)
    errors, _warnings = validate_repo.validate(tmp_harness_repo)
    assert any("maintenance_scope.py pero REQUIRED_PATHS no lo exige" in e for e in errors), errors


# --- the scope through the real hook, with a real git worktree ----------------------------------
@pytest.fixture(scope="module")
def control(tmp_path_factory):
    if GIT is None:
        pytest.skip("git no disponible")
    root = tmp_path_factory.mktemp("hookctl") / "repo"
    root.mkdir()
    _copy_skeleton(root)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "hook@example.invalid"),
        ("config", "user.name", "hook"),
        ("add", "-A"),
        ("commit", "-q", "-m", "base ficticia"),
    ):
        _git(root, *args)
    worktree = root / ".harness-worktrees" / "wt"
    _git(root, "worktree", "add", "-q", "-b", "fix/hook", str(worktree))
    head = subprocess.run(  # noqa: S603
        [GIT, "rev-parse", "HEAD"], cwd=worktree, capture_output=True, text=True, check=True
    ).stdout.strip()
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    record = {
        "schema_version": 1,
        "id": SID,
        "status": "open",
        "reason": "prueba del hook real con datos ficticios",
        "control_checkout": str(root),
        "worktree": str(worktree),
        "branch": "fix/hook",
        "head": head,
        "write_paths": ["scripts/harness/**", "tests/harness/**"],
        "allow_test_runs": False,
        "test_basetemp_root": None,
        "created_at": maintenance_scope.iso(now - dt.timedelta(minutes=1)),
        "expires_at": maintenance_scope.iso(now + dt.timedelta(hours=2)),
        "opened_by": {"name": "humano", "email": "humano@example.invalid"},
        "closed_at": None,
        "closed_by": None,
        "close_reason": None,
    }
    path = root / ".harness-runtime" / "maintenance" / f"{SID}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    maintenance_scope.load(root, common.load_policies(root), SID)  # the record must validate
    return root, worktree


SCOPED = {"TPI_HARNESS_MAINTENANCE": "1", "TPI_HARNESS_MAINTENANCE_SCOPE": SID}


def _cases(root: Path, wt: Path):
    cd = f"cd {wt.as_posix()} && "
    return [
        # (label, tool, input, expected exit)
        ("edit inside write_paths", "Edit", {"file_path": str(wt / "scripts/harness/x.py")}, 0),
        ("write inside write_paths", "Write", {"file_path": str(wt / "tests/harness/t.py")}, 0),
        ("edit outside write_paths", "Edit", {"file_path": str(wt / "app/x.py")}, 2),
        ("edit the control checkout", "Edit", {"file_path": str(root / "scripts/harness/x.py")}, 2),
        (
            "edit the registry",
            "Edit",
            {"file_path": str(root / f".harness-runtime/maintenance/{SID}.json")},
            2,
        ),
        ("edit control settings", "Edit", {"file_path": str(root / ".claude/settings.json")}, 2),
        ("edit worktree state.json", "Edit", {"file_path": str(wt / "harness/state.json")}, 2),
        ("edit worktree .git", "Edit", {"file_path": str(wt / ".git")}, 2),
        ("shell: git status", "Bash", {"command": "git status"}, 0),
        (
            "shell: cd wt && ruff",
            "Bash",
            {"command": cd + "python -m ruff check scripts/harness"},
            0,
        ),
        (
            "shell: cd in a pipeline",
            "Bash",
            {"command": f"cd {wt.as_posix()} | python -m ruff check ."},
            2,
        ),
        ("shell: python -c", "Bash", {"command": 'python -c "print(1)"'}, 2),
        ("shell: git commit", "Bash", {"command": "git commit -m x"}, 2),
        (
            "shell: approve.py",
            "Bash",
            {"command": "python scripts/harness/approve.py maintenance-scope close --id x"},
            2,
        ),
        (
            "shell: change scope variable",
            "Bash",
            {"command": "export TPI_HARNESS_MAINTENANCE_SCOPE=x"},
            2,
        ),
        (
            "shell: registry via redirect",
            "Bash",
            {"command": "echo x > .harness-runtime/maintenance/y.json"},
            2,
        ),
        ("powershell", "PowerShell", {"command": "Get-ChildItem"}, 2),
        ("mcp filesystem", "mcp__filesystem__write_file", {}, 2),
        ("mcp aws", "mcp__aws__aws___call_aws", {}, 2),
        ("read", "Read", {"file_path": str(root / "README.md")}, 0),
        ("read .env", "Read", {"file_path": str(root / ".env")}, 2),
    ]


def test_scope_verdicts_through_the_real_hook(control):
    root, wt = control
    wrong = []
    for label, tool, tool_input, expected in _cases(root, wt):
        code, stderr = run_hook(root, tool, tool_input, SCOPED)
        if code != expected:
            wrong.append((label, code, expected, stderr.strip().splitlines()[:1]))
    assert not wrong, wrong


def test_scope_fails_closed_through_the_real_hook(control):
    root, wt = control
    target = {"file_path": str(wt / "scripts/harness/x.py")}
    scope_only = {"TPI_HARNESS_MAINTENANCE_SCOPE": SID}
    other_id = {**SCOPED, "TPI_HARNESS_MAINTENANCE_SCOPE": "no-existe-99"}
    plain = {"TPI_HARNESS_MAINTENANCE": "1"}
    for label, env in (
        ("scope without maintenance", scope_only),
        ("unknown id", other_id),
        ("plain maintenance while a registry is open", plain),
    ):
        code, stderr = run_hook(root, "Edit", target, env)
        assert code == 2, (label, stderr)
    code, _ = run_hook(root, "Edit", target, SCOPED)
    assert code == 0


def test_scope_follows_the_event_cwd_through_the_real_hook(control):
    root, wt = control
    ruff = {"command": "python -m ruff check scripts/harness"}
    assert run_hook(root, "Bash", ruff, SCOPED, cwd=root)[0] == 2  # no cd: control checkout
    assert run_hook(root, "Bash", ruff, SCOPED, cwd=wt)[0] == 0  # a previous cd already moved


@pytest.mark.parametrize(
    "name",
    [
        "scripts/harness/zz/.GitAttributes",
        "scripts/harness/zz/.gitattributes.",
        "scripts/harness/zz/.GIT",
        "scripts/harness/zz/.git.",
        "scripts/harness/CoN ",
        "scripts/harness/CONOUT$",
        "Tasks/new.yaml",
        "scripts/harness/x.py:stream",
    ],
)
def test_windows_name_variants_are_blocked_through_the_real_hook(control, name):
    root, wt = control
    code, stderr = run_hook(root, "Edit", {"file_path": str(wt / name)}, SCOPED)
    assert code == 2, (name, stderr)


# --- what the hook never receives: the launch must exclude it -----------------------------------
def test_runtime_tools_all_reach_the_hook_and_the_gap_is_documented():
    policies = common.load_policies(REAL_ROOT)
    matchers = check_scope_tools.hook_matchers(REAL_ROOT)
    tools = check_scope_tools.runtime_tools(policies)
    assert all(check_scope_tools.reaches_hook(tool, matchers) for tool in tools), tools
    # Tools the matcher does NOT deliver: the scope cannot restrict them, so the launch excludes
    # them with --tools. If you widen the matcher, update runtime/claude/README.md and this test.
    outside = ["Monitor", "Agent", "Task", "Skill", "EnterWorktree", "WebFetch", "WebSearch"]
    assert not [t for t in outside if check_scope_tools.reaches_hook(t, matchers)]
    readme = (REAL_ROOT / "runtime" / "claude" / "README.md").read_text(encoding="utf-8")
    for tool in outside:
        assert (
            tool in readme
        ), f"{tool} no aparece en la seccion de alcance de runtime/claude/README.md"

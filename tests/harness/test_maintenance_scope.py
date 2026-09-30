"""Harness v1.2: alcance de mantencion abierto por el humano, acotado en tiempo, rutas y shell.

Todos los comandos son cadenas entregadas a guard.decide: nada se ejecuta. Repositorios,
metadatos git de worktrees, registros y directorios son fixtures temporales ficticios; la unica
excepcion es test_identity_matches_real_git_worktrees, que crea repositorios git desechables
en tmp_path (sin red, sin configuracion global) para contrastar los fixtures con git real.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.harness import approve, common, guard, maintenance_scope
from tests.harness.conftest import REAL_ROOT
from tests.harness.test_guard_headless import _fake_state, _fake_task

MAINT = "TPI_HARNESS_MAINTENANCE"
SCOPE_VAR = "TPI_HARNESS_MAINTENANCE_SCOPE"
SCOPE_ID = "guard-repair-01"
BRANCH = "fix/ficticia"
SHA = "a" * 40
OTHER_SHA = "b" * 40
ENV = {MAINT: "1", SCOPE_VAR: SCOPE_ID}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _iso(value: dt.datetime) -> str:
    return maintenance_scope.iso(value)


def _add_worktree(
    root: Path,
    name: str,
    *,
    repo_git: Path | None = None,
    branch: str = BRANCH,
    relative: bool = False,
) -> Path:
    """Linked-worktree metadata as git writes it: <wt>/.git -> <repo>/.git/worktrees/<name>.

    `relative` mimics `git worktree add --relative-paths` (git >= 2.48): both pointers are
    relative, the back-pointer to the directory that holds it.
    """
    repo_git = repo_git or root / ".git"
    worktree = root / ".harness-worktrees" / name
    (worktree / "scripts" / "harness").mkdir(parents=True)
    (worktree / "tests" / "harness").mkdir(parents=True)
    meta = repo_git / "worktrees" / name
    meta.mkdir(parents=True)
    forward = Path(os.path.relpath(meta, worktree)).as_posix() if relative else meta.as_posix()
    back = (
        Path(os.path.relpath(worktree / ".git", meta)).as_posix()
        if relative
        else (worktree / ".git").as_posix()
    )
    (worktree / ".git").write_text(f"gitdir: {forward}\n", encoding="utf-8")
    (meta / "commondir").write_text("../..\n", encoding="utf-8")
    (meta / "gitdir").write_text(f"{back}\n", encoding="utf-8")
    (meta / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    ref = repo_git / "refs" / "heads" / branch
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(SHA + "\n", encoding="utf-8")
    return worktree


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "r"
    (root / "harness" / "schemas").mkdir(parents=True)
    for name in ("policies.yaml", "workflow.yaml"):
        shutil.copy(REAL_ROOT / "harness" / name, root / "harness" / name)
    for schema in (REAL_ROOT / "harness" / "schemas").glob("*.json"):
        shutil.copy(schema, root / "harness" / "schemas" / schema.name)
    (root / ".git" / "worktrees").mkdir(parents=True)
    (root / "scripts" / "harness").mkdir(parents=True)
    _add_worktree(root, "wt")
    _add_worktree(root, "other", branch="fix/otra")
    (tmp_path / "bt").mkdir()
    monkeypatch.setattr(common, "load_state", lambda r: _fake_state("CANDIDATE_REVIEW", "TEST-1"))
    monkeypatch.setattr(common, "load_current_task", lambda r: _fake_task())
    return root


def _wt(root: Path, name: str = "wt") -> Path:
    return root / ".harness-worktrees" / name


def _bt(root: Path) -> Path:
    return root.parent / "bt"


def _record(root: Path, **overrides: Any) -> dict[str, Any]:
    now = _now()
    record: dict[str, Any] = {
        "schema_version": 1,
        "id": SCOPE_ID,
        "status": "open",
        "reason": "reparar guard con datos ficticios",
        "control_checkout": str(root),
        "worktree": str(_wt(root)),
        "branch": BRANCH,
        "head": SHA,
        "write_paths": ["scripts/harness/**", "tests/harness/**"],
        "allow_test_runs": True,
        "test_basetemp_root": str(_bt(root)),
        "created_at": _iso(now - dt.timedelta(minutes=1)),
        "expires_at": _iso(now + dt.timedelta(hours=2)),
        "opened_by": {"name": "humano", "email": "humano@example.invalid"},
        "closed_at": None,
        "closed_by": None,
        "close_reason": None,
    }
    record.update(overrides)
    return record


def _register(root: Path, record: dict[str, Any] | None = None, *, text: str | None = None) -> Path:
    path = root / ".harness-runtime" / "maintenance" / f"{SCOPE_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = text if text is not None else json.dumps(record or _record(root))
    path.write_text(body, encoding="utf-8")
    return path


def _decide(root: Path, tool: str, env: dict[str, str] | None = None, **tool_input: Any):
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(root)}
    return guard.decide(root, event, ENV if env is None else env)


def _edit(root: Path, path: Path | str, env: dict[str, str] | None = None):
    return _decide(root, "Edit", env, file_path=str(path))


def _bash(root: Path, command: str, env: dict[str, str] | None = None, tool: str = "Bash"):
    return _decide(root, tool, env, command=command)


# --- alcance valido: escrituras -----------------------------------------------------------------
def test_valid_scope_allows_only_authorized_writes(repo):
    _register(repo)
    wt = _wt(repo)
    assert _edit(repo, wt / "scripts/harness/guard.py")[0]
    assert _edit(repo, wt / "tests/harness/test_x.py")[0]
    for target in (
        wt / "app/main.py",
        wt / "harness/policies.yaml",
        wt / "harness/state.json",
        wt / "tasks/current.yaml",
        wt / "evidence/X/y.json",
        wt / "pyproject.toml",
        wt / ".git",
        wt,
    ):
        assert not _edit(repo, target)[0], target


def test_valid_scope_denies_sibling_worktree_control_checkout_and_outside_root(repo, tmp_path):
    _register(repo)
    for target in (
        _wt(repo, "other") / "scripts/harness/guard.py",
        repo / "scripts/harness/guard.py",  # plain maintenance would allow this one
        repo / "harness/policies.yaml",
        repo / ".harness-runtime/maintenance" / f"{SCOPE_ID}.json",
        tmp_path / "hermano" / "scripts/harness/guard.py",  # outside ROOT: V4 closed
    ):
        assert not _edit(repo, target)[0], target


def test_canonical_resolution_blocks_dotdot_and_relative_paths(repo):
    _register(repo)
    base = str(_wt(repo) / "scripts" / "harness")
    assert not _edit(repo, base + "/../../../../scripts/harness/guard.py")[0]
    assert not _edit(repo, base + "/../../.git")[0]
    assert not _edit(repo, "scripts/harness/guard.py")[0]  # relative => control checkout
    assert _edit(repo, str(_wt(repo) / "tests" / "harness") + "/../harness/test_y.py")[0]


def _make_link(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    try:
        import _winapi  # type: ignore[import-not-found]

        _winapi.CreateJunction(str(target), str(link))
        return True
    except (ImportError, OSError, AttributeError):
        return False


def test_links_or_junctions_out_of_scope_are_denied(repo, tmp_path):
    _register(repo)
    outside = tmp_path / "fuera"
    outside.mkdir()
    to_outside = _wt(repo) / "scripts/harness/enlace-fuera"
    to_control = _wt(repo) / "scripts/harness/enlace-control"
    if not (_make_link(to_outside, outside) and _make_link(to_control, repo / "scripts/harness")):
        pytest.skip("el entorno no permite crear symlinks ni junctions")
    assert not _edit(repo, to_outside / "x.py")[0]
    assert not _edit(repo, to_control / "guard.py")[0]


def test_identity_accepts_relative_worktree_pointers(repo):
    """git >= 2.48 (`worktree.useRelativePaths`) writes relative pointers: not a foreign worktree."""
    _add_worktree(repo, "rel", relative=True)
    assert maintenance_scope.worktree_identity(repo, _wt(repo, "rel")) == (BRANCH, SHA)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=check, capture_output=True, text=True
    )


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_identity_matches_real_git_worktrees(tmp_path, relative):
    """The fixtures above imitate git's files; this checks the real thing (scratch repos only)."""
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    repo = tmp_path / "real"
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    worktrees = repo / ".harness-worktrees"
    worktrees.mkdir()
    flags = ["--relative-paths"] if relative else []
    added = _git(
        repo, "worktree", "add", "-q", *flags, "-b", "fix/real", str(worktrees / "wt"), check=False
    )
    if added.returncode != 0 and relative:
        pytest.skip("este git no admite worktree add --relative-paths")
    assert added.returncode == 0, added.stderr
    head = _git(repo, "rev-parse", "fix/real").stdout.strip()
    assert maintenance_scope.worktree_identity(repo, worktrees / "wt") == ("fix/real", head)
    _git(repo, "pack-refs", "--all")  # branch ref now only in packed-refs
    assert maintenance_scope.worktree_identity(repo, worktrees / "wt") == ("fix/real", head)
    _git(worktrees / "wt", "commit", "-q", "--allow-empty", "-m", "mueve HEAD")
    assert maintenance_scope.worktree_identity(repo, worktrees / "wt")[1] != head
    # a worktree that belongs to another repository is not this repository's worktree
    other = tmp_path / "otro"
    _git(tmp_path, "init", "-q", "-b", "main", str(other))
    _git(other, "commit", "-q", "--allow-empty", "-m", "base")
    _git(other, "worktree", "add", "-q", "-b", "ajeno", str(worktrees / "ajeno"))
    with pytest.raises(maintenance_scope.ScopeError):
        maintenance_scope.worktree_identity(repo, worktrees / "ajeno")


def test_root_reaching_write_paths_fail_closed(repo):
    """`**`, `*`, `*.py` reach the worktree root where `python -m black|ruff|pytest` would import
    a shadowing module; the scope must fail closed instead of activating (F-B)."""
    wt = _wt(repo)
    target = wt / "scripts/harness/guard.py"
    for bad in ("**", "*", "*.py", "**/*.py", "*.*", "black.py"):
        _register(repo, _record(repo, write_paths=[bad]))
        allowed, reason = _edit(repo, target)
        assert not allowed and "no activable" in reason, bad
        assert _decide(repo, "Read", file_path=str(target))[0]  # reads stay allowed


@pytest.mark.parametrize(
    "pattern", ["**", "*", "*.py", "**/*.py", "*.*", "black.py", "conftest.py"]
)
def test_write_path_reaches_root_detects_dangerous_patterns(pattern):
    assert maintenance_scope.write_path_reaches_root(pattern)


@pytest.mark.parametrize(
    "pattern", ["scripts/harness/**", "scripts/*.py", "docs/notas.md", "tests/**"]
)
def test_write_path_reaches_root_accepts_directory_patterns(pattern):
    assert not maintenance_scope.write_path_reaches_root(pattern)


def test_python_m_is_denied_when_shadowed_at_the_worktree_root(repo):
    _register(repo)
    wt = _wt(repo)
    (wt / "black.py").write_text("print('shadow')\n", encoding="utf-8")
    allowed, reason = _bash(
        repo, "cd .harness-worktrees/wt && python -m black --check scripts/harness"
    )
    assert not allowed and "sustituiria" in reason
    (wt / "black.py").unlink()
    (wt / "ruff").mkdir()
    allowed, reason = _bash(
        repo, "cd .harness-worktrees/wt && python -m ruff check scripts/harness"
    )
    assert not allowed and "sustituiria" in reason


# Windows spells one file many ways, and the never_writable globs are lexical and case-sensitive.
# None of these names exists in the worktree: Path.resolve() cannot canonicalise what is not there.
PROTECTED_NAME_VARIANTS = [
    # case
    "scripts/harness/zz/.GitAttributes",
    "scripts/harness/zz/.GIT",
    "scripts/harness/zz/.Git/config",
    "Tasks/new.yaml",
    "TASKS/new.yaml",
    "Evidence/X/y.json",
    "PROGRESS/notas.md",
    ".CLAUDE/x.json",
    "Harness/State.json",
    "PyProject.TOML",
    ".MCP.JSON",
    # trailing dot or space: Win32 strips them, so `.git.` creates `.git`
    "scripts/harness/zz/.gitattributes.",
    "scripts/harness/zz/.gitattributes ",
    "scripts/harness/zz/.git.",
    "scripts/harness/zz/.git ",
    "pyproject.toml.",
    "tasks./new.yaml",
    "tasks /new.yaml",
    "scripts/harness/x.py.",
    "scripts/harness/x.py ",
    # reserved devices, with trailing dots/spaces, extensions and unusual digits
    "scripts/harness/CoN ",
    "scripts/harness/con .txt",
    "scripts/harness/NUL.",
    "scripts/harness/aux .py",
    "scripts/harness/prn",
    "scripts/harness/COM\u00b9",
    "scripts/harness/lpt\u00b2.log",
    "scripts/harness/CONIN$",
    "scripts/harness/CONOUT$",
    # characters Win32 rejects or reinterprets
    "scripts/harness/a<b.py",
    "scripts/harness/a|b.py",
    "scripts/harness/a?b.py",
    "scripts/harness/a*b.py",
    'scripts/harness/a"b.py',
    "scripts/harness/a\x01b.py",
    "scripts/harness/x.py:stream",
]
ORDINARY_NAMES = [
    "docs/notas.md",
    "scripts/harness/.gitignore",
    "scripts/harness/file.tar.gz",
    "scripts/harness/auxiliary.py",
    "scripts/harness/com10.txt",
    "scripts/harness/Makefile",
]


@pytest.mark.parametrize("name", PROTECTED_NAME_VARIANTS)
def test_protected_and_reserved_name_variants_are_refused_even_if_absent(repo, name):
    # F-B: `**` is refused at load, so these names are exercised under the directory write paths.
    _register(repo, _record(repo, write_paths=["scripts/harness/**", "tests/harness/**"]))
    allowed, _reason = _edit(repo, _wt(repo) / name)  # must return a verdict, never raise
    assert not allowed, name


# The broadest write paths that do NOT reach the worktree root (F-B): a concrete directory tree.
_DIRECTORY_PATHS = ["docs/**", "scripts/**", "tests/**"]


def test_ordinary_names_are_still_writable(repo):
    """The hardening must not turn the scope into a scope that writes nothing."""
    _register(repo, _record(repo, write_paths=_DIRECTORY_PATHS))
    for name in ORDINARY_NAMES:
        assert _edit(repo, _wt(repo) / name)[0], name


def test_allowed_names_never_materialise_as_protected_names(repo):
    """Oracle: create what the guard allows and look at what the filesystem really made.

    Whatever the platform does with a name (strip a trailing dot, fold case, ...) must not leave a
    `.git` or `.gitattributes` behind: those are exactly the entries never_writable protects.
    """
    _register(repo, _record(repo, write_paths=_DIRECTORY_PATHS))
    wt = _wt(repo)
    protected = {".git", ".gitattributes"}
    for name in PROTECTED_NAME_VARIANTS + ORDINARY_NAMES:
        if not _edit(repo, wt / name)[0]:
            continue
        target = wt / name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text("x", encoding="utf-8")
        except OSError:
            continue  # the platform refuses the name: nothing materialised
        created = {entry.name.lower() for entry in target.parent.iterdir()}
        assert (
            not created & protected
        ), f"{name!r} allowed and created {sorted(created & protected)}"


# --- solicitado pero no activable: fail closed --------------------------------------------------
def _foreign_worktree(root: Path, tmp: Path) -> None:
    _add_worktree(root, "ajeno", repo_git=tmp / "otro-repo" / ".git")
    _register(root, _record(root, worktree=str(_wt(root, "ajeno"))))


def _broken_backlink(root: Path, tmp: Path) -> None:
    (root / ".git" / "worktrees" / "wt" / "gitdir").write_text("C:/otro/.git\n", encoding="utf-8")
    _register(root)


def _broken_commondir(root: Path, tmp: Path) -> None:
    (tmp / "otro-git").mkdir()
    commondir = root / ".git" / "worktrees" / "wt" / "commondir"
    commondir.write_text(f"{(tmp / 'otro-git').as_posix()}\n", encoding="utf-8")
    _register(root)


def _branch_changed(root: Path, tmp: Path) -> None:
    _register(root)
    head = root / ".git" / "worktrees" / "wt" / "HEAD"
    head.write_text("ref: refs/heads/fix/otra\n", encoding="utf-8")


def _head_moved(root: Path, tmp: Path) -> None:
    _register(root)
    (root / ".git" / "refs" / "heads" / "fix" / "ficticia").write_text(OTHER_SHA + "\n")


def _detached(root: Path, tmp: Path) -> None:
    _register(root)
    (root / ".git" / "worktrees" / "wt" / "HEAD").write_text(SHA + "\n", encoding="utf-8")


def _timed(created: dt.timedelta, expires: dt.timedelta) -> Callable[[Path, Path], object]:
    def build(root: Path, tmp: Path) -> object:
        now = _now()
        return _register(
            root, _record(root, created_at=_iso(now + created), expires_at=_iso(now + expires))
        )

    return build


INVALID: list[tuple[str, Callable[[Path, Path], object]]] = [
    ("ausente", lambda root, tmp: None),
    ("corrupto", lambda root, tmp: _register(root, text="{no es json")),
    ("vacio", lambda root, tmp: _register(root, text="")),
    ("vencido", _timed(-dt.timedelta(hours=3), -dt.timedelta(hours=1))),
    ("inicio_futuro", _timed(dt.timedelta(hours=1), dt.timedelta(hours=2))),
    ("vigencia_excesiva", _timed(-dt.timedelta(minutes=1), dt.timedelta(hours=13))),
    (
        "cerrado",
        lambda root, tmp: _register(
            root,
            _record(
                root,
                status="closed",
                closed_at=_iso(_now()),
                closed_by={"name": "humano", "email": "humano@example.invalid"},
                close_reason="cierre por el humano",
            ),
        ),
    ),
    ("id_distinto", lambda root, tmp: _register(root, _record(root, id="otro-alcance"))),
    (
        "otro_checkout",
        lambda root, tmp: _register(root, _record(root, control_checkout=str(tmp / "otro"))),
    ),
    (
        "worktree_fuera_de_root",
        lambda root, tmp: _register(root, _record(root, worktree=str(tmp / "hermano"))),
    ),
    (
        "worktree_es_el_directorio_base",
        lambda root, tmp: _register(root, _record(root, worktree=str(root / ".harness-worktrees"))),
    ),
    (
        "worktree_sin_git",
        lambda root, tmp: _register(
            root, _record(root, worktree=str(root / ".harness-worktrees" / "sin-git"))
        ),
    ),
    ("worktree_de_otro_repositorio", _foreign_worktree),
    ("repositorio_no_reconoce_worktree", _broken_backlink),
    ("commondir_ajeno", _broken_commondir),
    ("rama_cambiada", _branch_changed),
    ("head_movido", _head_moved),
    ("head_desacoplado", _detached),
    ("rama_distinta_al_registro", lambda root, tmp: _register(root, _record(root, branch="main"))),
    ("head_distinto_al_registro", lambda root, tmp: _register(root, _record(root, head=OTHER_SHA))),
    ("campo_extra", lambda root, tmp: _register(root, _record(root, grant="all"))),
    (
        "ruta_con_punto_punto",
        lambda root, tmp: _register(root, _record(root, write_paths=["../scripts/**"])),
    ),
    ("ruta_absoluta", lambda root, tmp: _register(root, _record(root, write_paths=["C:/x/**"]))),
    (
        "pruebas_sin_basetemp",
        lambda root, tmp: _register(root, _record(root, test_basetemp_root=None)),
    ),
    (
        "basetemp_dentro_del_repo",
        lambda root, tmp: _register(root, _record(root, test_basetemp_root=str(root / "tmp"))),
    ),
    (
        "basetemp_contiene_el_repo",
        lambda root, tmp: _register(root, _record(root, test_basetemp_root=str(tmp))),
    ),
]


@pytest.mark.parametrize("label,build", INVALID, ids=[case[0] for case in INVALID])
def test_requested_but_invalid_scope_fails_closed(repo, tmp_path, label, build):
    build(repo, tmp_path)
    target = _wt(repo) / "scripts/harness/guard.py"
    for allowed, reason in (
        _edit(repo, target),
        _edit(repo, repo / "scripts/harness/guard.py"),  # never falls back to plain maintenance
        _bash(repo, "git status"),
    ):
        assert not allowed
        assert "no activable" in reason
    assert _decide(repo, "Read", file_path=str(target))[0]


@pytest.mark.parametrize(
    "env",
    [
        {SCOPE_VAR: SCOPE_ID},
        {MAINT: "0", SCOPE_VAR: SCOPE_ID},
        {MAINT: "1", SCOPE_VAR: ""},
        {MAINT: "1", SCOPE_VAR: "../escape"},
    ],
)
def test_scope_variable_without_maintenance_or_invalid_fails_closed(repo, env):
    _register(repo)
    allowed, reason = _edit(repo, _wt(repo) / "scripts/harness/guard.py", env)
    assert not allowed and "no activable" in reason


# --- quitar la variable no amplia permisos ------------------------------------------------------
def test_open_registry_blocks_plain_maintenance(repo):
    path = _register(repo)
    control = repo / "scripts/harness/guard.py"
    for allowed, reason in (
        _edit(repo, control, {MAINT: "1"}),
        _bash(repo, "git status", {MAINT: "1"}),
    ):
        assert not allowed and "alcances de mantencion abiertos" in reason
    assert _decide(repo, "Read", {MAINT: "1"}, file_path=str(control))[0]
    closed = _record(
        repo,
        status="closed",
        closed_at=_iso(_now()),
        closed_by={"name": "humano", "email": "humano@example.invalid"},
        close_reason="cierre por el humano",
    )
    path.write_text(json.dumps(closed), encoding="utf-8")
    assert _edit(repo, control, {MAINT: "1"})[0]  # back to the unchanged plain maintenance


def test_expired_but_unclosed_or_unreadable_registry_still_blocks(repo):
    _timed(-dt.timedelta(hours=3), -dt.timedelta(hours=1))(repo, repo)
    assert not _edit(repo, repo / "scripts/harness/guard.py", {MAINT: "1"})[0]
    _register(repo, text="{corrupto")
    allowed, reason = _edit(repo, repo / "scripts/harness/guard.py", {MAINT: "1"})
    assert not allowed and "ilegible" in reason


# --- shell bajo alcance: allowlist explicita ----------------------------------------------------
def _allowed_shell(root: Path) -> list[str]:
    bt = _bt(root).as_posix()
    return [
        "git status",
        "git -C .harness-worktrees/wt diff --stat",
        "git -C .harness-worktrees/wt log --oneline -5",
        "git --no-pager -C .harness-worktrees/wt show --stat HEAD",
        "cat .harness-worktrees/wt/scripts/harness/x.py | head -n 20",
        "wc -l harness/policies.yaml",
        "ls -la .harness-worktrees/wt/scripts/harness",
        "cd .harness-worktrees/wt && python -m black --check scripts/harness tests/harness",
        "cd .harness-worktrees/wt && python -m ruff check scripts/harness tests/harness",
        "cd .harness-worktrees/wt && python -m pytest tests/harness/test_x.py -q "
        f"-p no:cacheprovider --basetemp={bt}/run1",
    ]


def _denied_shell(root: Path) -> list[tuple[str, str]]:
    bt = _bt(root).as_posix()
    wt = "cd .harness-worktrees/wt && "
    pytest_ok = f"-p no:cacheprovider --basetemp={bt}/run1"
    return [
        ("Bash", "echo hola > .harness-worktrees/wt/scripts/harness/x.py"),
        ("Bash", "cat harness/policies.yaml > .harness-worktrees/wt/out.txt"),
        ("Bash", "touch .harness-worktrees/wt/scripts/harness/x.py"),
        ("Bash", "cp harness/policies.yaml .harness-worktrees/wt/p.yaml"),
        ("Bash", "mv a b"),
        ("Bash", "sed -i s/a/b/ harness/policies.yaml"),
        ("Bash", "python -c 'print(1)'"),
        ("Bash", "python .harness-worktrees/wt/scripts/harness/x.py"),
        ("Bash", f"python -m pytest .harness-worktrees/wt/tests/harness {pytest_ok}"),
        ("Bash", wt + "python -m pytest tests/harness -q"),
        ("Bash", wt + f"python -m pytest tests/harness -p no:cacheprovider --basetemp={bt}"),
        (
            "Bash",
            wt + "python -m pytest tests/harness -p no:cacheprovider "
            f"--basetemp={root.as_posix()}/tmp",
        ),
        ("Bash", wt + f"python -m pytest tests/harness -p otro_plugin {pytest_ok}"),
        ("Bash", wt + f"python -m pytest tests/harness -o addopts= {pytest_ok}"),
        ("Bash", wt + f"python -m pytest tests/harness --rootdir=. {pytest_ok}"),
        ("Bash", wt + f"python -m pytest scripts/harness {pytest_ok}"),
        ("Bash", wt + "python -m ruff check --fix scripts/harness"),
        ("Bash", wt + "python -m black scripts/harness"),
        ("Bash", wt + "python -m pip install requests"),
        ("Bash", "git commit -m cambio"),
        ("Bash", "git push origin HEAD"),
        ("Bash", "git checkout main"),
        ("Bash", "git -c core.pager=less log"),
        ("Bash", "git config user.name x"),
        ("Bash", "git diff --output=x.txt"),
        ("Bash", "git grep patron"),
        ("Bash", "git -C .harness-worktrees/other status"),
        ("Bash", "cd .harness-worktrees/other"),
        ("Bash", "cd .."),
        ("Bash", "bash -c 'git status'"),
        ("Bash", "env X=1 git status"),
        ("Bash", "X=1 git status"),
        ("Bash", "cat $(echo harness/policies.yaml)"),
        ("Bash", "cat ${HOME}/x"),
        ("Bash", "ls *"),
        ("Bash", "cat ../fuera.txt"),
        ("Bash", "head -n 5 deploy/server.pem"),
        ("Bash", "cat certs/tls.key"),
        ("Bash", "python scripts/harness/transition.py start_review"),
        ("Bash", "python -m scripts.harness.supervisor"),
        ("Bash", "python scripts/harness/aws_guard.py sts get-caller-identity"),
        ("Bash", "aws sts get-caller-identity"),
        ("Bash", "gh pr create --fill"),
        ("Bash", "docker build ."),
        ("Bash", f"cat .harness-runtime/maintenance/{SCOPE_ID}.json"),
        ("PowerShell", "Get-ChildItem"),
        ("PowerShell", "Set-Content x.txt hola"),
    ]


def test_scope_shell_allows_only_listed_reads_and_entry_points(repo):
    _register(repo)
    for command in _allowed_shell(repo):
        allowed, reason = _bash(repo, command)
        assert allowed, (command, reason)


def test_scope_shell_denies_everything_else(repo):
    _register(repo)
    for tool, command in _denied_shell(repo):
        allowed, _reason = _bash(repo, command, tool=tool)
        assert not allowed, command


def test_cd_must_lead_the_line_and_bind_what_follows(repo):
    """A cd that a real shell would not apply to the next command must not be trusted."""
    _register(repo)
    wt = "cd .harness-worktrees/wt"
    check = "python -m ruff check scripts/harness"
    for command in (
        f"{wt} && {check}",
        f"{wt}; {check}",
        f"{wt}\n{check}",
        f"{wt} && git diff --stat | head -n 5",
        wt,
    ):
        assert _bash(repo, command)[0], command
    for command in (
        f"{wt} | {check}",  # cd runs in a pipeline subshell
        f"{wt} & {check}",  # background
        f"{wt} || {check}",  # check runs only when cd failed
        f"({wt}) && {check}",  # subshell
        f"{{ {wt}; }} | {check}",  # group in a pipeline
        f"git status && {wt} && {check}",  # not the first command
        f"git status; {wt}; {check}",
        f"git status || {wt} && {check}",  # cd may be skipped
        check,  # no cd at all: cwd is the control checkout
    ):
        assert not _bash(repo, command)[0], command


def test_scope_denies_every_mcp_tool(repo):
    """check_mcp allows unknown servers; under a scope a file or shell MCP tool would bypass it."""
    _register(repo)
    for tool in (
        "mcp__filesystem__write_file",
        "mcp__github__create_pull_request",
        "mcp__aws__aws___search_documentation",
        "mcp__aws__aws___call_aws",
    ):
        allowed, reason = _decide(repo, tool)
        assert not allowed and "MCP" in reason, tool


def test_test_runs_require_explicit_human_authorization(repo):
    _register(repo, _record(repo, allow_test_runs=False, test_basetemp_root=None))
    command = _allowed_shell(repo)[-1]
    allowed, reason = _bash(repo, command)
    assert not allowed and "allow_test_runs" in reason
    assert _bash(repo, _allowed_shell(repo)[-2])[0]  # ruff check stays available


def test_scope_denies_aws_mcp_and_unknown_tools(repo):
    _register(repo)
    assert not _decide(repo, "mcp__aws__aws___call_aws")[0]
    assert not _decide(repo, "HerramientaDesconocida")[0]


# --- el agente no controla su alcance -----------------------------------------------------------
@pytest.mark.parametrize("env", [{}, {MAINT: "1"}, ENV], ids=["normal", "mantencion", "alcance"])
def test_agent_cannot_create_modify_or_close_registry(repo, env):
    _register(repo)
    registry = repo / ".harness-runtime" / "maintenance"
    for target in (
        registry / f"{SCOPE_ID}.json",
        registry / "otro.json",
        registry / "events.jsonl",
    ):
        assert not _edit(repo, target, env)[0], target
    assert not _bash(repo, "echo {} > .harness-runtime/maintenance/otro.json", env)[0]
    assert not _bash(
        repo, "python scripts/harness/approve.py maintenance-scope open --id x-1", env
    )[0]
    assert not _bash(
        repo, "python scripts/harness/approve.py maintenance-scope close --id x-1", env
    )[0]


@pytest.mark.parametrize(
    "tool,command",
    [
        ("Bash", "export TPI_HARNESS_MAINTENANCE_SCOPE=otro-alcance"),
        ("Bash", "unset TPI_HARNESS_MAINTENANCE_SCOPE"),
        ("Bash", "TPI_HARNESS_MAINTENANCE_SCOPE=otro-alcance claude"),
        ("Bash", "env -u TPI_HARNESS_MAINTENANCE_SCOPE claude"),
        ("PowerShell", "$env:TPI_HARNESS_MAINTENANCE_SCOPE = 'otro-alcance'"),
    ],
)
@pytest.mark.parametrize("env", [{}, {MAINT: "1"}, ENV], ids=["normal", "mantencion", "alcance"])
def test_agent_cannot_set_or_drop_scope_variable(repo, tool, command, env):
    _register(repo)
    assert not _bash(repo, command, env, tool=tool)[0]


# --- secretos reales, registro y comportamiento sin mantencion ----------------------------------
def test_secret_read_protection_kept_under_scope(repo):
    _register(repo)
    for path in (repo / "deploy/server.pem", _wt(repo) / "certs/tls.key"):
        assert not _decide(repo, "Read", file_path=str(path))[0]


def test_behavior_without_scope_or_registry_is_unchanged(repo):
    control = repo / "scripts/harness/guard.py"
    in_worktree = _wt(repo) / "scripts/harness/guard.py"
    assert not _edit(repo, control, {})[0]
    assert _edit(repo, control, {MAINT: "1"})[0]
    assert not _edit(repo, in_worktree, {MAINT: "1"})[0]
    assert _bash(repo, "git status", {})[0]
    assert _decide(repo, "Read", {}, file_path=str(control))[0]
    assert maintenance_scope.requested_id(common.load_policies(repo), {}) is None


def test_guard_log_records_scope_id(repo):
    event = {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "session_id": "s"}
    guard._log(repo, event, True, "", True, SCOPE_ID)
    line = (repo / ".harness-runtime" / "guard.log").read_text(encoding="utf-8").splitlines()[-1]
    record = json.loads(line)
    assert record["maintenance_scope"] == SCOPE_ID and record["maintenance_mode"] is True


# --- mecanismo humano: approve.py maintenance-scope ---------------------------------------------
@pytest.fixture
def human(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    answers: list[str] = []
    monkeypatch.setattr(approve, "_require_tty", lambda: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    monkeypatch.setattr(common, "git", lambda root, *args, check=True: "humano-ficticio")
    return answers


def _open(repo: Path, **overrides: Any) -> Path:
    kwargs: dict[str, Any] = {
        "scope_id": SCOPE_ID,
        "worktree": str(_wt(repo)),
        "write_paths": ["scripts/harness/**"],
        "hours": 2.0,
        "reason": "reparar guard con datos ficticios",
    }
    kwargs.update(overrides)
    return approve.open_scope(repo, **kwargs)


def test_human_opens_and_closes_scope(repo, human):
    human.append(f"ABRIR {SCOPE_ID}")
    path = _open(repo)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert (record["branch"], record["head"]) == (BRANCH, SHA)  # read from git metadata
    target = _wt(repo) / "scripts/harness/guard.py"
    assert _edit(repo, target)[0]
    human.append(f"CERRAR {SCOPE_ID}")
    approve.close_scope(repo, SCOPE_ID, "reparacion terminada")
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "closed"
    allowed, reason = _edit(repo, target)
    assert not allowed and "cerrado" in reason
    events = (path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in events] == ["opened", "closed"]


def test_human_opens_scope_with_test_runs(repo, human):
    human.append(f"ABRIR {SCOPE_ID}")
    _open(repo, allow_test_runs=True, test_basetemp_root=str(_bt(repo)))
    assert _bash(repo, _allowed_shell(repo)[-1])[0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"hours": 13.0},
        {"hours": 0.0},
        {"write_paths": ["../x/**"]},
        {"write_paths": ["**"]},
        {"write_paths": ["*.py"]},
        {"write_paths": []},
        {"scope_id": "../escape"},
        {"reason": "corta"},
        {"worktree": "<fuera>"},
        {"worktree": "<ajeno>"},
        {"allow_test_runs": True},
        {"allow_test_runs": True, "test_basetemp_root": "<repo>"},
    ],
)
def test_open_scope_rejects_invalid_requests(repo, tmp_path, human, overrides):
    human.append(f"ABRIR {SCOPE_ID}")
    if overrides.get("worktree") == "<fuera>":
        overrides = {"worktree": str(tmp_path)}
    elif overrides.get("worktree") == "<ajeno>":
        _add_worktree(repo, "ajeno", repo_git=tmp_path / "otro-repo" / ".git")
        overrides = {"worktree": str(_wt(repo, "ajeno"))}
    elif overrides.get("test_basetemp_root") == "<repo>":
        overrides = {**overrides, "test_basetemp_root": str(repo / "tmp")}
    with pytest.raises(common.HarnessError):
        _open(repo, **overrides)
    assert not (repo / ".harness-runtime" / "maintenance" / f"{SCOPE_ID}.json").exists()


def test_open_scope_rejects_detached_head(repo, human):
    human.append(f"ABRIR {SCOPE_ID}")
    (repo / ".git" / "worktrees" / "wt" / "HEAD").write_text(SHA + "\n", encoding="utf-8")
    with pytest.raises(common.HarnessError):
        _open(repo)


def test_open_scope_requires_exact_confirmation(repo, human):
    human.append("abrir")
    with pytest.raises(common.HarnessError):
        _open(repo)
    assert not (repo / ".harness-runtime" / "maintenance" / f"{SCOPE_ID}.json").exists()


def test_open_scope_refuses_reused_id(repo, human):
    human.extend([f"ABRIR {SCOPE_ID}", f"ABRIR {SCOPE_ID}"])
    _open(repo)
    with pytest.raises(common.HarnessError):
        _open(repo)


def test_scope_commands_require_a_terminal(repo):
    with pytest.raises(common.HarnessError):
        _open(repo)
    with pytest.raises(common.HarnessError):
        approve.close_scope(repo, SCOPE_ID, "cierre sin terminal")

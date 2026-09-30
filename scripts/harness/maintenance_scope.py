"""Maintenance scope (Harness v1.2): a human-opened, time-boxed, path-bounded window.

Requested when the human launches the runtime with ``harness.maintenance_scope.env_var`` set.
Active only if, in addition, ``TPI_HARNESS_MAINTENANCE=1`` is set and the registry written by
``approve.py maintenance-scope open``:

* exists, validates against ``maintenance_scope.schema.json`` and is ``open``;
* is within its validity window;
* is bound to this control checkout;
* names a git worktree of *this* repository (``.git`` file -> ``<repo>/.git/worktrees/<n>``,
  whose ``commondir`` and ``gitdir`` point back), on the same branch and HEAD recorded at open.

Requested but not active raises ``ScopeError`` and guard.py denies writes and shell commands:
never a silent fallback. While any registry is open (or unreadable), plain maintenance without
the scope variable is also denied, so dropping the variable never widens permissions.

An active scope only narrows:

* Write/Edit only under ``write_paths`` of its worktree (canonical paths: ``..``, symlinks and
  junctions resolved; names that alias another target, such as NTFS ``file:stream`` or ``nul``,
  are refused) and never under ``never_writable``;
* shell only through an explicit allowlist (``shell_allowed``): verified read-only commands and
  the declared check/test entry points with validated arguments. A ``cd`` is honoured only as
  the first command of the line, followed by ``&&`` or ``;``. Everything else is denied;
* no MCP tool at all (the default MCP policy allows any non-AWS server).

What this guard cannot see: it judges only the tool calls that Claude Code delivers to the
PreToolUse hook (the ``matcher`` of .claude/settings.json). A tool outside that matcher (Monitor,
Agent/Task, Skill, EnterWorktree, WebFetch, ...) never reaches guard.py, so an active scope does
not restrict it. The human therefore launches the runtime with ``--tools`` limited to the
``runtime_tools`` of the policy and proves the effective list with ``check_scope_tools.py``
(runtime/claude/README.md); that, not this module, is what keeps those tools out.

What this does NOT bound: the allowlist is NOT an OS sandbox. Code executed by an allowed test run
(``python -m pytest``, only with ``allow_test_runs``) is code written in the worktree and runs with
the runtime's OS permissions. ``python -m black|ruff|pytest`` also import from the worktree root
(it is ``sys.path[0]``), so a module of the same name written at the root would run agent code;
the scope prevents that two ways: ``write_paths`` may not reach the root (see
``write_path_reaches_root``), and ``_Shell`` refuses the module if such a file already exists.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from . import command_analysis, common
except ImportError:  # executed as a script (guard.py hook)
    import command_analysis  # type: ignore[no-redef]
    import common  # type: ignore[no-redef]

SCOPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
_WRITE_PATH_RE = re.compile(r"^[A-Za-z0-9_.*-]+(/[A-Za-z0-9_.*-]+)*$")


def write_path_reaches_root(pattern: str) -> bool:
    """True if the write path can place a file at the worktree ROOT.

    Under a scope the only Python entry points are ``python -m black|ruff|pytest`` and the shell
    allowlist runs them from the worktree root (``cd <worktree> && python -m ...``), so Python puts
    the root first on ``sys.path``: a ``black.py``/``ruff.py``/``pytest.py`` (or a package
    directory, e.g. ``black/__main__.py``) written there would be imported instead of the real
    tool, executing agent-written code even without ``allow_test_runs``. A write path with no
    directory component, or whose first component has a wildcard, can reach the root and is
    refused: only ``<dir>/...`` paths under a concrete directory are accepted.
    """
    first = pattern.split("/", 1)[0]
    return "/" not in pattern or "*" in first or "?" in first


_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_NULL_TARGETS = {"/dev/null", "nul"}
_GLOB_CHARS = re.compile(r"[*?\[\]{}~]")
# Names the filesystem may map onto another target. The never_writable globs are case-sensitive
# and lexical, and Path.resolve() canonicalises only what already exists, so none of this can be
# left to them: a component like this is refused outright, whether or not the file exists yet.
#  * `:` (NTFS alternate data stream: `file:stream`, `file::$DATA`), the characters Win32 rejects
#    or reinterprets (`<>"|?*`, control characters) and `$` (NTFS metafiles, `CONIN$`/`CONOUT$`);
#  * a trailing dot or space, which Win32 strips: `.gitattributes.` creates `.gitattributes`;
#  * reserved DOS devices, with any trailing dots/spaces and extension: `nul`, `CoN `, `aux.py`,
#    `com1`, `COM\u00b9`, `lpt2.log`.
_AMBIGUOUS_NAME = re.compile(
    r"""[\x00-\x1f:<>"|?*$]
      | [. ]$
      | ^(?:con|prn|aux|nul|com[0-9\u00b9\u00b2\u00b3]|lpt[0-9\u00b9\u00b2\u00b3])[ .]*(?:\..*)?$""",
    re.IGNORECASE | re.VERBOSE,
)

PathCheck = Callable[[str], bool]


class ScopeError(common.HarnessError):
    """A maintenance scope was requested but cannot be activated: fail closed."""


@dataclass(frozen=True)
class Scope:
    id: str
    worktree: Path  # canonical
    branch: str
    head: str
    write_paths: tuple[str, ...]
    expires_at: str
    allow_test_runs: bool
    test_basetemp_root: Path | None


# ---------------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------------
def config(policies: Mapping[str, Any]) -> Mapping[str, Any]:
    scope = (policies.get("harness") or {}).get("maintenance_scope")
    if not scope:
        raise ScopeError("politica harness.maintenance_scope ausente")
    return scope


def requested_id(policies: Mapping[str, Any], env_vars: Mapping[str, str]) -> str | None:
    """The scope id the human asked for (possibly empty/invalid); None if none was requested."""
    scope = (policies.get("harness") or {}).get("maintenance_scope")
    if not scope:
        return None
    value = env_vars.get(scope["env_var"])
    return None if value is None else str(value)


def registry_dir(root: Path, policies: Mapping[str, Any]) -> Path:
    return root / config(policies)["registry_dir"]


def registry_path(root: Path, policies: Mapping[str, Any], scope_id: str) -> Path:
    if not isinstance(scope_id, str) or not SCOPE_ID_RE.fullmatch(scope_id):
        raise ScopeError("identificador de alcance invalido")
    return registry_dir(root, policies) / f"{scope_id}.json"


def open_scope_ids(root: Path, policies: Mapping[str, Any]) -> list[str]:
    """Registries that are open, or unreadable (fail closed: an unknown registry may be open)."""
    directory = registry_dir(root, policies)
    if not directory.is_dir():
        return []
    found: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            found.append(f"{path.stem} (ilegible)")
            continue
        if not isinstance(data, dict) or data.get("status") != "closed":
            found.append(path.stem)
    return found


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _time(value: Any, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ScopeError(f"{field} invalido") from error
    if parsed.tzinfo is None:
        raise ScopeError(f"{field} sin zona horaria")
    return parsed


def inside(child: Path, parent: Path) -> bool:
    """`child` is `parent` or below it (canonical paths; case-insensitive on Windows)."""
    c = os.path.normcase(str(child))
    p = os.path.normcase(str(parent)).rstrip("\\/")
    return c == p or c.startswith(p + os.sep)


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


# ---------------------------------------------------------------------------------------------
# Worktree identity (read from git metadata files: no subprocess inside the hook)
# ---------------------------------------------------------------------------------------------
def _read(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ScopeError(f"{what} ilegible") from error


def _ref_sha(common_git: Path, ref: str) -> str:
    loose = common_git / ref
    if loose.is_file():
        value = _read(loose, "referencia de rama")
        if _SHA_RE.fullmatch(value):
            return value
        raise ScopeError("referencia de rama invalida")
    packed = common_git / "packed-refs"
    if packed.is_file():
        for line in _read(packed, "packed-refs").splitlines():
            if line.startswith(("#", "^")):
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref and _SHA_RE.fullmatch(sha):
                return sha
    raise ScopeError("la rama del worktree no tiene un commit resoluble")


def worktree_identity(root: Path, worktree: Path) -> tuple[str, str]:
    """(branch, head) of `worktree` if it is a linked worktree of the repository at `root`."""
    common_git = (root / ".git").resolve()
    if not common_git.is_dir():
        raise ScopeError("el checkout de control no es el repositorio git principal")
    dotgit = worktree / ".git"
    if not dotgit.is_file():
        raise ScopeError("el worktree del alcance no existe o no es un worktree git enlazado")
    pointer = _read(dotgit, "archivo .git del worktree")
    if not pointer.startswith("gitdir:"):
        raise ScopeError("archivo .git del worktree invalido")
    gitdir = Path(pointer[len("gitdir:") :].strip())
    gitdir = (gitdir if gitdir.is_absolute() else worktree / gitdir).resolve()
    if _same(gitdir, common_git / "worktrees") or not inside(gitdir, common_git / "worktrees"):
        raise ScopeError("el worktree no pertenece al repositorio autorizado")
    commondir = Path(_read(gitdir / "commondir", "commondir del worktree"))
    commondir = (commondir if commondir.is_absolute() else gitdir / commondir).resolve()
    if not _same(commondir, common_git):
        raise ScopeError("el worktree no pertenece al repositorio autorizado (commondir)")
    # git >= 2.48 with worktree.useRelativePaths writes this pointer relative to `gitdir`.
    back = Path(_read(gitdir / "gitdir", "gitdir del worktree"))
    back = (back if back.is_absolute() else gitdir / back).resolve()
    if not _same(back, dotgit.resolve()):
        raise ScopeError("el repositorio no reconoce este worktree (gitdir)")
    head = _read(gitdir / "HEAD", "HEAD del worktree")
    if not head.startswith("ref: refs/heads/"):
        raise ScopeError("HEAD del worktree desacoplado: el alcance requiere una rama")
    branch = head[len("ref: refs/heads/") :]
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch.split("/"):
        raise ScopeError("nombre de rama del worktree invalido")
    return branch, _ref_sha(common_git, f"refs/heads/{branch}")


# ---------------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------------
def _basetemp_root(root: Path, value: Any) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        raise ScopeError("test_basetemp_root debe ser absoluta")
    path = path.resolve()
    if path.parent == path or _same(path, Path.home().resolve()) or inside(root.resolve(), path):
        raise ScopeError("test_basetemp_root no puede ser una raiz, el home ni contener el repo")
    if inside(path, root.resolve()):
        raise ScopeError("test_basetemp_root debe estar fuera del repositorio")
    if not path.is_dir():
        raise ScopeError("test_basetemp_root no existe")
    return path


def check_record(
    root: Path,
    policies: Mapping[str, Any],
    scope_id: str,
    data: Any,
    now: dt.datetime | None = None,
) -> Scope:
    cfg = config(policies)
    errors = common.validate_schema(root, "maintenance_scope", data)
    if errors:
        raise ScopeError("registro invalido: " + "; ".join(errors[:3]))
    if data["id"] != scope_id:
        raise ScopeError("el registro no corresponde al alcance solicitado")
    if data["status"] != "open":
        raise ScopeError("alcance cerrado")
    if not _same(Path(data["control_checkout"]).resolve(), root.resolve()):
        raise ScopeError("alcance ligado a otro checkout de control")
    worktrees = (root / cfg["worktrees_dir"]).resolve()
    worktree = Path(data["worktree"]).resolve()
    if _same(worktree, worktrees) or not inside(worktree, worktrees):
        raise ScopeError(f"el worktree debe estar dentro de {cfg['worktrees_dir']}/")
    branch, head = worktree_identity(root, worktree)
    # Defined behavior: any branch or HEAD change after opening (the agent cannot commit or
    # switch under a scope) deactivates the scope until the human closes it and opens a new one.
    if branch != data["branch"]:
        raise ScopeError("la rama del worktree cambio desde la apertura del alcance")
    if head != data["head"]:
        raise ScopeError("el HEAD del worktree cambio desde la apertura del alcance")
    for pattern in data["write_paths"]:
        if not _WRITE_PATH_RE.fullmatch(pattern) or ".." in pattern.split("/"):
            raise ScopeError(f"ruta de escritura no permitida en el registro: {pattern}")
        if write_path_reaches_root(pattern):
            raise ScopeError(
                f"ruta de escritura alcanza la raiz del worktree "
                f"(permitiria sustituir python -m black|ruff|pytest): {pattern}"
            )
    basetemp = None
    if data["allow_test_runs"]:
        basetemp = _basetemp_root(root, data["test_basetemp_root"])
    created = _time(data["created_at"], "created_at")
    expires = _time(data["expires_at"], "expires_at")
    current = now or dt.datetime.now(dt.UTC)
    if not created < expires <= created + dt.timedelta(hours=cfg["max_hours"]):
        raise ScopeError("vigencia del alcance invalida")
    if current < created:
        raise ScopeError("alcance con inicio futuro")
    if current >= expires:
        raise ScopeError("alcance vencido")
    return Scope(
        scope_id,
        worktree,
        branch,
        head,
        tuple(data["write_paths"]),
        data["expires_at"],
        bool(data["allow_test_runs"]),
        basetemp,
    )


def load(
    root: Path, policies: Mapping[str, Any], scope_id: str, now: dt.datetime | None = None
) -> Scope:
    path = registry_path(root, policies, scope_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ScopeError("alcance sin registro") from error
    except (OSError, ValueError) as error:
        raise ScopeError("registro ilegible o corrupto") from error
    return check_record(root, policies, scope_id, data, now)


# ---------------------------------------------------------------------------------------------
# Writes (Write/Edit tools)
# ---------------------------------------------------------------------------------------------
def write_allowed(
    root: Path, policies: Mapping[str, Any], scope: Scope, raw: str
) -> tuple[bool, str]:
    target = Path(raw)
    if not target.is_absolute():
        target = root / target
    try:
        resolved = target.resolve()
    except (OSError, RuntimeError, ValueError):
        return False, f"ruta de escritura no resoluble bajo alcance: {raw}"
    if _same(resolved, scope.worktree) or not inside(resolved, scope.worktree):
        return False, f"bajo alcance {scope.id} solo se escribe dentro de su worktree: {raw}"
    try:
        # Lexical (no abspath): os.path.relpath maps device names such as `nul` outside the tree.
        relative = resolved.relative_to(scope.worktree).as_posix()
    except ValueError:
        return False, f"ruta de escritura fuera del worktree bajo alcance: {raw}"
    if any(_AMBIGUOUS_NAME.search(part) for part in relative.split("/")):
        return (
            False,
            f"nombre de archivo ambiguo bajo alcance (stream NTFS o dispositivo): {relative}",
        )
    # NTFS, APFS and macOS default volumes are case-insensitive but the globs are not: compare
    # folded, so `.GitAttributes` or `Tasks/x.yaml` cannot slip past `**/.gitattributes`/`tasks/**`.
    never_writable = [pattern.lower() for pattern in config(policies)["never_writable"]]
    if common.matches_any(relative.lower(), never_writable):
        return False, f"ruta nunca escribible bajo alcance: {relative}"
    if not common.matches_any(relative, scope.write_paths):
        return False, f"ruta fuera de las rutas autorizadas del alcance {scope.id}: {relative}"
    return True, ""


# ---------------------------------------------------------------------------------------------
# Shell allowlist
# ---------------------------------------------------------------------------------------------
_GIT_READ: dict[str, set[str]] = {
    "status": {"-s", "--short", "--porcelain", "-b", "--branch"},
    "diff": {
        "--stat",
        "--name-only",
        "--name-status",
        "--cached",
        "--staged",
        "--check",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
    },
    "log": {"--oneline", "--stat", "--name-only", "--no-color", "--no-decorate", "--no-ext-diff"},
    "show": {"--stat", "--name-only", "--oneline", "--no-color", "--no-ext-diff", "--no-textconv"},
    "rev-parse": {"--abbrev-ref", "--show-toplevel", "--verify", "--short"},
    "ls-files": {"--others", "--exclude-standard", "--modified", "-m", "--cached"},
}
_READERS: dict[str, re.Pattern[str]] = {
    "cat": re.compile(r"^-[nbsAET]+$"),
    "head": re.compile(r"^-(\d+|[nc])$"),
    "tail": re.compile(r"^-(\d+|[nc])$"),
    "wc": re.compile(r"^-[lwcm]+$"),
    "ls": re.compile(r"^-[laR1hA]+$"),
}
_PYTEST_FLAGS = {"-q", "-v", "-vv", "-x", "-rA", "-ra", "--no-cov", "--tb=short", "--tb=line"}


class _DeniedError(Exception):
    pass


def _deny(reason: str) -> None:
    raise _DeniedError(reason)


class _Shell:
    def __init__(
        self,
        root: Path,
        scope: Scope,
        cwd: Path,
        path_allowed: PathCheck,
        cd_binds: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.scope = scope
        self.cwd = cwd
        self.path_allowed = path_allowed
        self.cd_binds = cd_binds  # a leading `cd` really changes the directory of what follows
        self.steps = 0

    def path(self, text: str, *, within: Path | None = None) -> Path:
        if not text or _GLOB_CHARS.search(text):
            _deny(f"ruta no admitida bajo alcance: {text!r}")
        candidate = Path(text)
        candidate = (candidate if candidate.is_absolute() else self.cwd / candidate).resolve()
        limit = within or self.root
        if not inside(candidate, limit):
            _deny(f"ruta fuera del area permitida bajo alcance: {text}")
        if not self.path_allowed(str(candidate)):
            _deny(f"lectura protegida: {text}")
        return candidate

    def step(self, command: command_analysis.SimpleCommand) -> None:
        leading = self.steps == 0
        self.steps += 1
        words = command.words
        if not words or command.call_operator or command.heredocs or command.here_strings:
            _deny("forma de comando no admitida bajo alcance")
        for word in words:
            if word.active or "\x00" in word.text or "$" in word.text or "`" in word.text:
                _deny("expansiones y sustituciones no admitidas bajo alcance")
        for redirect in command.redirects:
            if redirect.target is not None and redirect.target.text.lower() not in _NULL_TARGETS:
                _deny("redirecciones a archivo no admitidas bajo alcance")
        head = words[0].text
        if words[0].quoted or re.search(r"[\\/=]", head):
            _deny("el comando debe ser un nombre simple")
        name = head.lower().removesuffix(".exe")
        args = [w.text for w in words[1:]]
        if name == "cd":
            if len(args) != 1 or not _same(self.path(args[0]), self.scope.worktree):
                _deny("bajo alcance cd solo puede ir al worktree del alcance")
            if not (leading and self.cd_binds):
                # A cd in a pipeline, subshell, group, background or after `||`/`&&` may not run
                # in the shell that executes what follows, so the tracked directory would be false.
                _deny("bajo alcance cd debe ser el primer comando, seguido de && o ;")
            self.cwd = self.scope.worktree
        elif name == "git":
            self.git(args)
        elif name in _READERS:
            self.reader(name, args)
        elif name in ("python", "python3", "py"):
            self.python(args)
        else:
            _deny(f"comando no admitido bajo alcance: {name}")

    def git(self, args: list[str]) -> None:
        if args[:1] == ["--no-pager"]:
            args = args[1:]
        if args[:1] == ["-C"]:
            if len(args) < 2:
                _deny("git -C sin ruta")
            target = self.path(args[1])
            if not (_same(target, self.scope.worktree) or _same(target, self.root)):
                _deny("git -C solo admite el worktree del alcance o el checkout de control")
            args = args[2:]
        if not args or args[0] not in _GIT_READ:
            _deny(f"subcomando git no admitido bajo alcance: {args[:1]}")
        allowed = _GIT_READ[args[0]]
        separator = False
        for arg in args[1:]:
            if arg == "--":
                separator = True
                continue
            if arg.startswith("-") and not separator:
                if arg not in allowed and not re.fullmatch(r"-\d{1,3}", arg):
                    _deny(f"opcion git no admitida bajo alcance: {arg}")
                continue
            for part in arg.split(":")[1:] if ":" in arg else [arg]:
                if part and not self.path_allowed(part):
                    _deny(f"lectura protegida: {arg}")

    def reader(self, name: str, args: list[str]) -> None:
        options = _READERS[name]
        expects_value = False
        for arg in args:
            if expects_value:
                if not arg.isdigit():
                    _deny(f"valor de opcion no admitido: {arg}")
                expects_value = False
                continue
            if arg.startswith("-"):
                if not options.fullmatch(arg):
                    _deny(f"opcion no admitida bajo alcance: {name} {arg}")
                expects_value = name in ("head", "tail") and arg in ("-n", "-c")
                continue
            self.path(arg)
        if expects_value:
            _deny(f"opcion sin valor: {name}")

    def _shadowed(self, module: str) -> bool:
        """A file or package at the worktree root that ``python -m <module>`` would import first."""
        return (self.scope.worktree / f"{module}.py").is_file() or (
            self.scope.worktree / module
        ).is_dir()

    def python(self, args: list[str]) -> None:
        if len(args) < 2 or args[0] != "-m":
            _deny("bajo alcance python solo admite los puntos de entrada de checks y pruebas")
        if not _same(self.cwd, self.scope.worktree):
            _deny("los checks y pruebas se ejecutan desde el worktree: cd <worktree> && ...")
        module, rest = args[1], args[2:]
        if module in ("black", "ruff", "pytest") and self._shadowed(module):
            _deny(
                f"python -m {module} se sustituiria por codigo del worktree "
                f"(existe {module}.py o {module}/ en la raiz)"
            )
        if module == "black":
            self.black(rest)
        elif module == "ruff":
            self.ruff(rest)
        elif module == "pytest":
            self.pytest(rest)
        else:
            _deny(f"modulo python no admitido bajo alcance: {module}")

    def operand(self, text: str) -> None:
        self.path(text.split("::", 1)[0], within=self.scope.worktree)

    def black(self, args: list[str]) -> None:
        if "--check" not in args:
            _deny("black solo en modo --check bajo alcance")
        for arg in args:
            if arg.startswith("-"):
                if arg not in ("--check", "--diff", "-q", "--quiet"):
                    _deny(f"opcion black no admitida: {arg}")
            else:
                self.operand(arg)

    def ruff(self, args: list[str]) -> None:
        if args[:1] != ["check"]:
            _deny("ruff solo como 'ruff check' bajo alcance")
        for arg in args[1:]:
            if arg.startswith("-"):
                if arg not in ("-q", "--quiet", "--no-fix"):
                    _deny(f"opcion ruff no admitida: {arg}")
            else:
                self.operand(arg)

    def pytest(self, args: list[str]) -> None:
        if not self.scope.allow_test_runs or self.scope.test_basetemp_root is None:
            _deny("el alcance no autoriza ejecutar pruebas (allow_test_runs)")
        basetemp = no_cache = False
        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "-p" and args[index + 1 : index + 2] == ["no:cacheprovider"]:
                no_cache = True
                index += 2
                continue
            if arg == "-k" and index + 1 < len(args):
                index += 2
                continue
            if arg.startswith("--basetemp="):
                target = Path(arg.split("=", 1)[1])
                if not target.is_absolute():
                    _deny("--basetemp debe ser absoluta")
                target = target.resolve()
                if _same(target, self.scope.test_basetemp_root) or not inside(
                    target, self.scope.test_basetemp_root
                ):
                    _deny("--basetemp debe estar dentro de test_basetemp_root del alcance")
                basetemp = True
            elif arg.startswith("--maxfail="):
                if not arg.split("=", 1)[1].isdigit():
                    _deny(f"valor no admitido: {arg}")
            elif arg.startswith("-"):
                if arg not in _PYTEST_FLAGS:
                    _deny(f"opcion pytest no admitida bajo alcance: {arg}")
            else:
                self.operand(arg)
                if not inside((self.cwd / arg.split("::", 1)[0]).resolve(), self.cwd / "tests"):
                    _deny("pytest solo admite rutas bajo tests/ del worktree")
            index += 1
        if not (basetemp and no_cache):
            _deny("pytest requiere --basetemp=<dentro de test_basetemp_root> y -p no:cacheprovider")


_SEQUENTIAL = ("&&", ";", "\n")


def _cd_binds_the_rest(command: str) -> bool:
    """The first word starts the line (no `(`/`{` group) and is followed by `&&`, `;` or a newline.

    Only then does a leading `cd` run in the main shell before everything after it, which is what
    the directory tracking of `_Shell` assumes. `|`, `|&`, `&` and `||` would run it in a
    subshell, in the background or conditionally.
    """
    lexer = command_analysis._Lexer(command, "bash")
    seen_word = False
    try:
        while (token := lexer.next()) is not None:
            if isinstance(token, command_analysis.Word):
                seen_word = True
            elif isinstance(token, tuple):  # redirect: consume its target
                lexer.next_word()
            elif not seen_word:
                return False
            else:
                return token in _SEQUENTIAL
    except command_analysis._LexError:
        return False
    return seen_word


def shell_allowed(
    root: Path,
    scope: Scope,
    command: str,
    dialect: str,
    cwd: str | None,
    path_allowed: PathCheck,
) -> tuple[bool, str]:
    """Explicit allowlist for Bash under an active scope; everything else is denied."""
    if dialect != "bash":
        return False, "bajo alcance de mantencion solo se admite Bash con la allowlist"
    try:
        commands, substitutions = command_analysis._simple_commands(command, "bash")
    except command_analysis._LexError as error:
        return False, f"comando no analizable bajo alcance: {error}"
    if substitutions or not commands:
        return False, "comando vacio o con sustituciones: no admitido bajo alcance"
    shell = _Shell(
        root,
        scope,
        Path(cwd).resolve() if cwd else root.resolve(),
        path_allowed,
        _cd_binds_the_rest(command),
    )
    try:
        for simple in commands:
            shell.step(simple)
    except _DeniedError as denied:
        return False, str(denied)
    return True, ""

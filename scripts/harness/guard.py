"""Claude Code PreToolUse hook: enforce role/state policies before any tool call.

Reads the hook event JSON from stdin. Exit 0 allows the call; exit 2 blocks it and the
reason is returned to the model. Any internal error blocks (fail closed).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from . import command_analysis, common, denials, maintenance_scope
except ImportError:  # executed as a script
    try:
        import command_analysis  # type: ignore[no-redef]
        import common  # type: ignore[no-redef]
        import denials  # type: ignore[no-redef]
        import maintenance_scope  # type: ignore[no-redef]
    except Exception as error:  # noqa: BLE001 - missing module, SyntaxError, broken import...
        # An uncaught import error exits 1, which Claude Code treats as a NON-blocking hook error
        # (the tool call would run unguarded). Only exit 2 blocks, so block explicitly.
        sys.stderr.write(
            f"TPI HARNESS GUARD: DENIED - el guard no pudo cargar sus modulos: {error!r}\n"
        )
        sys.stderr.write(
            "Si esto bloquea una accion legitima: STOP y solicitar asistencia humana.\n"
        )
        raise SystemExit(2) from error

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep", "NotebookRead"}
SHELL_TOOLS = {"Bash", "PowerShell"}
PROTECTED_TOKENS = (
    "harness/",
    "harness\\",
    "state.json",
    "policies.yaml",
    "workflow.yaml",
    "evidence/",
    "evidence\\",
    "approvals",
    "scripts/harness",
    "scripts\\harness",
    ".claude",
    ".mcp.json",
    "AGENTS.md",
    "CLAUDE.md",
    "environments/",
    "tasks/",
    "agents/",
    # v1.1: ephemeral Supervisor latch/telemetry and the guard log are evidence of a DENIED;
    # a worker must not be able to erase them to make the Supervisor continue.
    ".harness-runtime/supervisor",
    ".harness-runtime\\supervisor",
    ".harness-runtime/guard.log",
    ".harness-runtime\\guard.log",
    # v1.2: registry of maintenance scopes (only approve.py maintenance-scope, run by the human).
    ".harness-runtime/maintenance",
    ".harness-runtime\\maintenance",
)
SENSITIVE_HOME_DIRS = ("/.aws/", "/.claude/", "/.codex/", "/.dsh/", "/.ssh/")

# Discovery/read-only tokens: they never write to the filesystem, so their presence in a
# command must never be classified as a filesystem mutation, even when the command also
# mentions a protected-path token (protected path != unreadable path). Mentioning one of
# these does not by itself make a command safe: `protected_write_verbs` below is still
# evaluated on what remains after stripping them, so a real write elsewhere in the same
# command (e.g. `git status; rm harness/x`) is still caught.
_SAFE_REDIRECTS = re.compile(
    r"""
    [012]?>&[012]\b            # fd duplication: 2>&1, 1>&2, >&2 -- no filesystem write
  | &>\s*/dev/null\b           # bash: discard both streams to the null device
  | [012]?>{1,2}\s*/dev/null\b # redirect/append to the Unix null device
  | [012]?>{1,2}\s*\$null\b    # redirect/append to the PowerShell null device
    """,
    re.VERBOSE,
)


def _strip_safe_redirects(command: str) -> str:
    """Remove redirects that can never mutate the repository (fd duplication, or
    discarding a stream to /dev/null or $null) before classifying a command as a
    write. A bare '>' matches both a real file write and harmless stream plumbing
    like '2>&1'; without this, any read-only discovery command that happens to
    redirect stderr (very common) would be misclassified as a protected write.
    """
    return _SAFE_REDIRECTS.sub(" ", command)


_QUOTED_LITERAL = re.compile(r'"[^"]*"|\'[^\']*\'')


def _strip_quoted(command: str) -> str:
    """Blank out quoted string literals before detecting a real git/gh subcommand.

    Without this, a command that merely *mentions* "git push" or "gh pr merge" inside
    a string literal -- a grep pattern, an echo message, a `git commit -m "..."` message
    body -- is misclassified as that subcommand and denied even though no such git/gh
    operation is actually being run. `git commit -m "..."` still matches correctly
    because the trigger text ("git commit") sits outside the quotes; only the message
    payload is blanked.
    """
    return _QUOTED_LITERAL.sub(lambda m: " " * len(m.group(0)), command)


def _developer_worktree(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """Return the registered worktree for the active task's Developer, if any."""
    task_id = ctx["state"].get("task_id") or ""
    prefix = f"{task_id}-developer-"
    for worktree in ctx["state"].get("worktrees") or []:
        if worktree.get("role") != "developer":
            continue
        path = str(worktree.get("path", "")).replace("\\", "/").rstrip("/")
        if path.rsplit("/", 1)[-1].startswith(prefix):
            return worktree
    return None


def _scoped_to_worktree(root: Path, command: str, cwd: str | None, worktree_path: str) -> bool:
    """True if a git-mutating command is actually operating inside the given worktree.

    Accepts three equivalent forms of evidence: the hook-reported working directory
    is the worktree (or a subdirectory of it); the command itself changes into the
    worktree first (`cd`/`Set-Location`); or the git invocation targets the worktree
    explicitly (`-C <path>` / `--git-dir=<path>/.git`).
    """
    wt = str(worktree_path).replace("\\", "/").rstrip("/")
    normalized = command.replace("\\", "/")
    patterns = (
        rf"\b(?:cd|Set-Location)\s+['\"]?{re.escape(wt)}(?:['\"]|[/\\]|\s|;|&|$)",
        rf"\bgit\s+-C\s+['\"]?{re.escape(wt)}\b",
        rf"--git-dir[= ]['\"]?{re.escape(wt)}/\.git\b",
    )
    if any(re.search(pattern, normalized) for pattern in patterns):
        return True
    if cwd:
        relative = common.to_repo_relative(root, cwd)
        if relative is not None and (relative == wt or relative.startswith(wt + "/")):
            return True
    return False


def _maintenance_commit_allowed(root: Path, policies: dict[str, Any]) -> bool:
    """True if every currently staged file is within harness.maintenance_allowlist.

    Mirrors check_write's existing maintenance carve-out (D3: allowlist declarativa, no
    bypass global) for the one case check_write cannot see: `git commit` itself. The
    Developer-worktree scope required elsewhere in check_command does not apply to a
    human-authorized maintenance session committing harness/agents/tests/scripts.harness
    files from the main checkout -- but only when every staged path is actually inside
    the declared allowlist; any staged path outside it still falls through to the normal
    Developer worktree-scoped rule (fail closed).
    """
    output = common.git(root, "diff", "--cached", "--name-only", check=False)
    staged = [line.strip() for line in output.splitlines() if line.strip()]
    if not staged:
        return False
    allowlist = policies["harness"]["maintenance_allowlist"]
    return all(common.matches_any(path.replace("\\", "/"), allowlist) for path in staged)


def _deny(reason: str) -> tuple[bool, str]:
    return False, reason


def _load(root: Path) -> dict[str, Any]:
    state = common.load_state(root)
    workflow = common.load_workflow(root)
    try:
        task = common.load_current_task(root)
    except Exception:  # noqa: BLE001 - a broken task file must not unlock writes
        task = None
    return {
        "state": state,
        "role": common.state_role(workflow, state["state"]),
        "policies": common.load_policies(root),
        "task": task,
    }


def check_read(root: Path, ctx: dict[str, Any], tool_input: dict[str, Any]) -> tuple[bool, str]:
    candidates = [
        tool_input.get(k) for k in ("file_path", "path", "notebook_path", "glob", "pattern")
    ]
    for value in filter(None, candidates):
        text = str(value).replace("\\", "/")
        relative = common.to_repo_relative(root, text) or text.lstrip("./")
        name = Path(text).name
        patterns = ctx["policies"]["secret_read_deny"]
        if common.matches_any(relative, patterns) or common.matches_any(name, patterns):
            return _deny(f"lectura de secretos prohibida: {value}")
        if name.startswith(".env") and name != ".env.example":
            return _deny(f"lectura de archivos .env prohibida: {value}")
    return True, ""


def check_write(
    root: Path, ctx: dict[str, Any], tool_input: dict[str, Any], maintenance: bool
) -> tuple[bool, str]:
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return _deny("herramienta de escritura sin ruta")
    relative = common.to_repo_relative(root, raw)
    if relative is None:
        lowered = str(raw).replace("\\", "/").lower()
        if any(part in lowered for part in SENSITIVE_HOME_DIRS):
            return _deny("escritura en configuracion de credenciales/runtime prohibida")
        return True, ""
    policies = ctx["policies"]
    role = ctx["role"]
    state = ctx["state"]
    task = ctx["task"] or {}
    worktree = re.match(r"^\.harness-worktrees/([^/]+)/(.*)$", relative)
    inner = worktree.group(2) if worktree else relative
    # D3: mantenimiento habilita SOLO la allowlist declarativa de harness/policies.yaml
    # (harness.maintenance_allowlist). Nunca un bypass global: fuera de la allowlist se
    # evaluan las reglas normales de protected_paths + rol + estado, igual que sin mantenimiento.
    if (
        maintenance
        and not worktree
        and common.matches_any(inner, policies["harness"]["maintenance_allowlist"])
    ):
        return True, ""
    if common.matches_any(inner, policies["protected_paths"]):
        return _deny(
            f"ruta protegida del Harness: {relative} (solo scripts o mantenimiento humano)"
        )
    if role not in common.AGENT_ROLES:
        if not worktree and common.matches_any(
            relative, ["progress/current.md", "progress/sessions/**"]
        ):
            return True, ""
        return _deny(f"estado {state['state']} pertenece a '{role}': sin escritura de agentes")
    role_policy = policies["roles"][role]
    if not worktree and common.matches_any(relative, role_policy["always_writable"]):
        return True, ""
    if state["state"] not in role_policy["work_states"]:
        return _deny(f"rol {role} sin escritura en estado {state['state']}")
    if role == "developer":
        if not worktree:
            return _deny(
                "el Developer escribe codigo solo dentro de su worktree .harness-worktrees/<task>-developer-*"
            )
        if not worktree.group(1).startswith(f"{state.get('task_id')}-developer-"):
            return _deny("worktree ajeno a la tarea/rol activo")
        allowed = common.matches_any(inner, role_policy["write_allow"])
        if task.get("change_class") == "C":
            allowed = allowed or common.matches_any(
                inner, role_policy["write_requires_change_class_c"]
            )
        if task.get("allow_lockfile_update"):
            allowed = allowed or common.matches_any(
                inner, role_policy["write_requires_lockfile_flag"]
            )
        scope = (task.get("scope") or {}).get("paths")
        if allowed and scope and not common.matches_any(inner, scope):
            return _deny(f"ruta fuera del scope de la tarea: {inner}")
        return (True, "") if allowed else _deny(f"el Developer no puede escribir {inner}")
    if worktree:
        return _deny(f"el rol {role} no modifica worktrees")
    if common.matches_any(relative, role_policy["write_allow"]):
        return True, ""
    return _deny(
        f"el rol {role} no puede modificar {relative} (Reviewer/Deployer no editan aplicacion)"
    )


def _gh_action_of(first: str, second: str | None) -> str:
    return "api" if first == "api" else f"{first} {second or ''}".strip()


def _gh_actions(view: CommandView) -> list[str]:
    """Action (``pr view``, ``api``...) of every real ``gh`` invocation in a command.

    Classified on the parsed invocations, not on the raw text: ``which gh git`` mentions gh but
    does not run it, and ``gh pr view 1 && gh pr merge 1`` runs two actions, both judged.
    """
    actions = []
    for invocation in view.invocations():
        argv = invocation.argv
        if not argv or _word_name(argv[0]) not in ("gh", "gh.exe"):
            continue
        words = [word.text for word in argv[1:] if not word.text.startswith("-")]
        if words:
            actions.append(_gh_action_of(words[0], words[1] if len(words) > 1 else None))
    for text in view.opaque_texts():  # code the parser cannot read keeps the v1 text rule
        match = re.search(r"\bgh\s+([a-z-]+)(?:\s+([a-z-]+))?", _legacy_view(text))
        if match:
            actions.append(_gh_action_of(match.group(1), match.group(2)))
    return actions


# ---------------------------------------------------------------------------
# v1.1 structural command classification (execute vs mention). See command_analysis.py.
# ---------------------------------------------------------------------------
HUMAN_SCRIPT_NAMES = {"approve.py", "approve.pyc", "approve.pyw"}
AWS_CLI_NAMES = {"aws", "aws.exe", "aws.cmd", "aws2", "aws2.exe"}
WRITE_COMMANDS = {
    "rm",
    "rmdir",
    "mv",
    "cp",
    "tee",
    "truncate",
    "touch",
    "ln",
    "install",
    "dd",
    "shred",
    "unlink",
    "rsync",
    "patch",
    "chmod",
    "chown",
    "set-content",
    "add-content",
    "out-file",
    "remove-item",
    "move-item",
    "copy-item",
    "new-item",
    "rename-item",
    "clear-content",
    "set-itemproperty",
    "sc",
    "ac",
    "ri",
    "mi",
    "cpi",
    "ni",
    "rni",
    "clc",
    "del",
    "erase",
    "move",
    "copy",
    "ren",
    "rename",
}
IN_PLACE_EDITORS = {"sed", "perl", "ruby", "gsed"}
GIT_WRITE_SUBCOMMANDS = {"checkout", "restore", "rm", "mv"}
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_CD_COMMANDS = {"cd", "set-location", "sl", "pushd", "chdir", "push-location"}
_ALIAS_COMMANDS = {"alias", "set-alias", "new-alias", "doskey", "sal", "nal"}
_MAX_EMBED_DEPTH = 3


def _word_name(word: command_analysis.Word) -> str:
    name = command_analysis.basename(word.text)
    return name


def _protected(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return any(token.replace("\\", "/") in normalized for token in PROTECTED_TOKENS)


def _legacy_view(text: str) -> str:
    """Conservative text view for opaque code: quotes do not hide anything."""
    return re.sub(r"[\"'`]", " ", text)


def _python_target(argv: list[command_analysis.Word]) -> tuple[str, str] | None:
    """('script', path) or ('module', name) for a python invocation; None for -c/stdin."""
    index = 1
    while index < len(argv):
        text = argv[index].text
        if text == "-m":
            return ("module", argv[index + 1].text) if index + 1 < len(argv) else None
        if text.startswith("-c") or text == "-":
            return None
        if text in ("-W", "-X", "--check-hash-based-pycs"):
            index += 2
            continue
        if text.startswith("-"):
            index += 1
            continue
        return ("script", text)
    return None


def _git_subcommand(argv: list[command_analysis.Word]) -> tuple[str | None, list[str]]:
    """Subcommand of a git invocation after its global options, plus -C/--git-dir values."""
    scopes: list[str] = []
    index = 1
    while index < len(argv):
        text = argv[index].text
        name, _, inline = text.partition("=")
        if name in _GIT_GLOBAL_WITH_VALUE:
            value = inline if inline else (argv[index + 1].text if index + 1 < len(argv) else "")
            if name in ("-C", "--git-dir", "--work-tree"):
                scopes.append(value)
            index += 1 if inline else 2
            continue
        if text.startswith("-"):
            index += 1
            continue
        return text, scopes
    return None, scopes


class CommandView:
    """What a shell command really executes, resolved once per guard decision."""

    def __init__(self, command: str, dialect: str, depth: int = 0) -> None:
        self.command = command
        self.analysis = command_analysis.analyze(command, dialect)
        self.embedded: list[CommandView] = []
        self.opaque: list[str] = list(self.analysis.opaque)
        if not self.analysis.ok:
            self.opaque.append(command)  # parser failed somewhere: whole command conservative
        for report in self.analysis.python:
            if not report.ok or report.opaque_exec:
                self.opaque.append(report.code)
        if depth < _MAX_EMBED_DEPTH:
            for text in self._embedded_texts():
                self.embedded.append(CommandView(text, "bash", depth + 1))

    def _embedded_texts(self) -> list[str]:
        """Command strings that will run later: assignment values, aliases, python exec calls."""
        texts: list[str] = []
        for invocation in self.analysis.invocations:
            texts += [a.split("=", 1)[1] for a in invocation.assignments if "=" in a]
            if invocation.argv and _word_name(invocation.argv[0]) in _ALIAS_COMMANDS:
                for word in invocation.argv[1:]:
                    texts.append(word.text.split("=", 1)[-1])
        for report in self.analysis.python:
            texts += [text for text in report.shell_strings if text.strip()]
        return [text for text in texts if text.strip()]

    def views(self) -> list[CommandView]:
        result = [self]
        for view in self.embedded:
            result += view.views()
        return result

    def invocations(self) -> list[command_analysis.Invocation]:
        return [inv for view in self.views() for inv in view.analysis.invocations]

    def python_reports(self) -> list[command_analysis.PythonReport]:
        return [report for view in self.views() for report in view.analysis.python]

    def opaque_texts(self) -> list[str]:
        return [text for view in self.views() for text in view.opaque if text]


def _human_script_name(text: str) -> bool:
    """The human script as a path, also when an unquoted Windows path lost its separators to
    bash escaping (scripts\\harness\\<name> -> scriptsharness<name>): fail closed."""
    name = command_analysis.basename(text)
    return name in HUMAN_SCRIPT_NAMES or any(
        name.endswith("harness" + human) for human in HUMAN_SCRIPT_NAMES
    )


def _executes_human_script(view: CommandView, legacy_pattern: str) -> bool:
    for invocation in view.invocations():
        if not invocation.argv:
            continue
        name = _word_name(invocation.argv[0])
        if _human_script_name(invocation.argv[0].text):
            return True
        if command_analysis._PY_RE.match(name):
            target = _python_target(invocation.argv)
            if target and target[0] == "script" and _human_script_name(target[1]):
                return True
            if target and target[0] == "module" and target[1].split(".")[-1] == "approve":
                return True
    if any(report.human_script for report in view.python_reports()):
        return True
    return any(re.search(legacy_pattern, _legacy_view(t)) for t in view.opaque_texts())


def _executes_aws_cli(view: CommandView, legacy_pattern: str) -> bool:
    for invocation in view.invocations():
        if invocation.argv and _word_name(invocation.argv[0]) in AWS_CLI_NAMES:
            return True
    if any(report.aws_cli for report in view.python_reports()):
        return True
    return any(re.search(legacy_pattern, _legacy_view(t)) for t in view.opaque_texts())


def _maintenance_assignment(command: str, var: str) -> bool:
    """Setting/unsetting the maintenance variable, as opposed to mentioning or reading it."""
    v = re.escape(var)
    patterns = (
        rf"(?<![\w]){v}['\"\]]*\s*(\+|\?\?)?=(?!=)",  # VAR=1, $env:VAR = 1, environ['VAR']=
        rf"['\"]{v}['\"]\s*:",  # {'VAR': '1'} (env dict for a child process)
        rf"(^|[;&|(\n]\s*|\b(then|do)\s+)(export|unset|setx|readonly|declare|typeset|local|"
        rf"set(?!-))\s+[^\n;|&]*\b{v}\b",
        rf"\b(putenv|unsetenv|SetEnvironmentVariable|setdefault|pop|update|__setitem__|"
        rf"__delitem__)\s*\([^)]*\b{v}\b",
        rf"\bdel\s+os\.environ\s*\[\s*['\"]{v}",
        rf"-(Item|ItemProperty|Variable)\b[^\n;|]*\benv:[\\/]?{v}\b",
        rf"\benv\b[^\n;|&]*\s-u\s*{v}\b",
    )
    return any(re.search(pattern, command, re.IGNORECASE) for pattern in patterns)


def _sets_maintenance_variable(policies: dict[str, Any], command: str) -> bool:
    """Setting/unsetting the maintenance variable or the v1.2 maintenance scope variable."""
    names = [policies["harness"]["maintenance_env_var"]]
    scope = policies["harness"].get("maintenance_scope") or {}
    if scope.get("env_var"):
        names.append(scope["env_var"])
    return any(_maintenance_assignment(command, name) for name in names)


_OPAQUE_WRITE_API = re.compile(
    r"writeFile|appendFile|unlink|rmSync|rmdir|renameSync|copyFile|File\.Write|File\.Delete|"
    r"open\s*\(|fopen|file_put_contents|IO\.write|File\.open",
    re.IGNORECASE,
)


def _legacy_protected_write(text: str, verbs: str) -> bool:
    if not _protected(text):
        return False
    view = _strip_safe_redirects(_legacy_view(text))
    return bool(re.search(verbs, view) or _OPAQUE_WRITE_API.search(view))


def _writes_protected(view: CommandView, verbs: str) -> str | None:
    command_mentions_protected = _protected(view.command)
    for invocation in view.invocations():
        for redirect in invocation.redirects:
            op = redirect.op.lstrip("0123456789&")
            if redirect.target is None or op.startswith("<"):
                continue
            target = redirect.target
            if target.text.strip().lower() in command_analysis._NULL_TARGETS:
                continue
            if _protected(target.text):
                return f"redireccion a ruta protegida: {target.text}"
            if (target.active or "$" in target.text) and command_mentions_protected:
                return "redireccion a destino dinamico en un comando que menciona rutas protegidas"
        argv = invocation.argv
        if not argv:
            continue
        name = _word_name(argv[0])
        name = name[:-4] if name.endswith(".exe") else name
        writes = name in WRITE_COMMANDS
        if name in IN_PLACE_EDITORS:
            writes = any(re.fullmatch(r"-[a-zA-Z]*i\S*|--in-place\S*", w.text) for w in argv[1:])
        if name == "git":
            writes = _git_subcommand(argv)[0] in GIT_WRITE_SUBCOMMANDS
        if writes and any(_protected(word.text) for word in argv[1:]):
            return f"{name} sobre ruta protegida"
    for report in view.python_reports():
        if not report.ok:
            continue  # evaluated below as opaque text
        for target in report.writes:
            if target is None:
                if any(_protected(f) for f in report.fragments) or any(
                    _protected(s) for s in report.strings
                ):
                    return "python escribe un destino no resoluble en codigo que menciona rutas protegidas"
            elif _protected(target):
                return f"python escribe ruta protegida: {target}"
    for text in view.opaque_texts():
        if _legacy_protected_write(text, verbs):
            return "codigo no analizable que podria modificar archivos protegidos"
    return None


def _git_subcommands(view: CommandView) -> list[tuple[str, list[str], list[str]]]:
    """(subcommand, scope values, words) for every git invocation, plus opaque fallbacks."""
    found = []
    for invocation in view.invocations():
        if invocation.argv and _word_name(invocation.argv[0]) in ("git", "git.exe"):
            sub, scopes = _git_subcommand(invocation.argv)
            if sub:
                found.append((sub, scopes, [w.text for w in invocation.argv]))
    for text in view.opaque_texts():
        for match in re.finditer(
            r"\bgit\s+(push|commit|merge|rebase|reset)(?![\w-])", _legacy_view(text)
        ):
            found.append((match.group(1), [], text.split()))
    return found


def _cd_targets(view: CommandView) -> list[str]:
    targets = []
    for invocation in view.invocations():
        argv = invocation.argv
        if argv and _word_name(argv[0]) in _CD_COMMANDS:
            targets += [w.text for w in argv[1:] if not w.text.startswith("-")][:1]
    return targets


def _scoped(
    root: Path, view: CommandView, scopes: list[str], cwd: str | None, worktree_path: str
) -> bool:
    wt = str(worktree_path).replace("\\", "/").rstrip("/")

    def inside(value: str) -> bool:
        normalized = value.replace("\\", "/").rstrip("/")
        relative = common.to_repo_relative(root, normalized)
        candidate = relative if relative is not None else normalized.lstrip("./")
        if candidate.endswith("/.git"):
            candidate = candidate[: -len("/.git")]
        return candidate == wt or candidate.startswith(wt + "/")

    if any(inside(value) for value in scopes + _cd_targets(view)):
        return True
    if cwd:
        relative = common.to_repo_relative(root, cwd)
        if relative is not None and (relative == wt or relative.startswith(wt + "/")):
            return True
    return False


def _check_gh_action(action: str, command: str, ctx: dict[str, Any]) -> tuple[bool, str] | None:
    """Deny decision for one ``gh`` action under the active role and state; None when allowed."""
    role, state, policies = ctx["role"], ctx["state"], ctx["policies"]
    if role not in common.AGENT_ROLES:
        return _deny(f"gh no permitido en estado {state['state']}")
    role_policy = policies["roles"][role]
    allowed = set(role_policy["gh_allow"]) | set(
        (role_policy.get("gh_state_allow") or {}).get(state["state"], [])
    )
    if action == "api":
        if "api-get" not in allowed:
            return _deny("gh api no permitido para este rol")
        if re.search(
            r"(-X|--method)\s*(POST|PUT|PATCH|DELETE)|\s(-f|-F|--field|--raw-field|--input)\s",
            command,
        ):
            return _deny("gh api solo lectura (GET)")
    elif action not in allowed:
        return _deny(f"gh {action} no permitido para {role} en {state['state']}")
    if action == "pr merge" and not re.search(
        r"--squash\b.*--match-head-commit\s+[0-9a-f]{40}|--match-head-commit\s+[0-9a-f]{40}.*--squash\b",
        command,
    ):
        return _deny("gh pr merge requiere --squash y --match-head-commit <reviewed_sha>")
    if action == "pr merge" and "--auto" in command:
        return _deny("auto-merge no disponible/aprobado")
    if action == "workflow run" and not re.search(
        r"publish-dev-ecr-images\.yml.*source_sha=[0-9a-f]{40}", command
    ):
        return _deny("solo gh workflow run publish-dev-ecr-images.yml -f source_sha=<release_sha>")
    return None


def check_command(
    root: Path,
    ctx: dict[str, Any],
    command: str,
    maintenance: bool,
    cwd: str | None = None,
    dialect: str = "bash",
) -> tuple[bool, str]:
    policies = ctx["policies"]
    role = ctx["role"]
    state = ctx["state"]
    bash = policies["bash"]
    structural = bash["structural_rules"]
    # Raw-text rules: destructive/secret/force-push patterns stay literal and conservative.
    for rule in bash["forbidden_everywhere"]:
        if re.search(rule["pattern"], command, re.IGNORECASE):
            return _deny(rule["reason"])
    if _sets_maintenance_variable(policies, command):
        return _deny(structural["maintenance_env"]["reason"])
    view = CommandView(command, dialect)
    if _executes_human_script(view, structural["human_script"]["legacy_pattern"]):
        return _deny(structural["human_script"]["reason"])
    if _executes_aws_cli(view, structural["aws_cli"]["legacy_pattern"]):
        return _deny(structural["aws_cli"]["reason"])
    for match in re.finditer(r"[^\s\"']*\baws_guard\.py\b", command):
        target = match.group(0).replace("\\", "/")
        if target not in ("scripts/harness/aws_guard.py", "./scripts/harness/aws_guard.py") and (
            common.to_repo_relative(root, target) != "scripts/harness/aws_guard.py"
        ):
            return _deny(
                "aws_guard debe invocarse desde scripts/harness/aws_guard.py del repositorio"
            )
    if not maintenance:
        # Evaluated on resolved write targets, not on whether the raw text names a protected
        # path: `Path('.') / 'harness' / 'x'` writes harness/x without the literal token.
        problem = _writes_protected(view, bash["protected_write_verbs"])
        if problem:
            return _deny(
                f"comando shell que podria modificar archivos protegidos del Harness ({problem})"
            )
    # git/gh: classify the real subcommand (git global options skipped, merge-base != merge).
    gits = _git_subcommands(view)
    subcommands = {sub for sub, _, _ in gits}
    if "push" in subcommands:
        task_id = state.get("task_id") or ""
        if role != "developer" or state["state"] != "DEVELOPING":
            return _deny(f"git push no permitido para {role} en {state['state']}")
        worktree = _developer_worktree(ctx)
        if not worktree:
            return _deny("no hay worktree de Developer registrado para la tarea activa")
        branch = worktree.get("branch") or f"harness/{task_id}"
        for sub, scopes, words in gits:
            if sub != "push":
                continue
            if not _scoped(root, view, scopes, cwd, worktree["path"]):
                return _deny(
                    "el Developer solo publica git desde su worktree registrado: "
                    f"{worktree['path']}"
                )
            if not any(branch in word for word in words):
                return _deny(f"el Developer solo publica la rama {branch}")
    if "commit" in subcommands:
        if not (maintenance and _maintenance_commit_allowed(root, policies)):
            if role != "developer" or state["state"] != "DEVELOPING":
                return _deny(f"git commit no permitido para {role} en {state['state']}")
            worktree = _developer_worktree(ctx)
            if not worktree:
                return _deny("no hay worktree de Developer registrado para la tarea activa")
            for sub, scopes, _ in gits:
                if sub == "commit" and not _scoped(root, view, scopes, cwd, worktree["path"]):
                    return _deny(
                        "el Developer solo hace commit desde su worktree registrado: "
                        f"{worktree['path']}"
                    )
    if subcommands & {"merge", "rebase", "reset"}:
        if role != "developer" or state["state"] != "DEVELOPING":
            return _deny(f"git merge/rebase/reset no permitido para {role} en {state['state']}")
    for action in _gh_actions(view):
        denial = _check_gh_action(action, command, ctx)
        if denial:
            return denial
    return True, ""


def check_mcp(ctx: dict[str, Any], tool_name: str) -> tuple[bool, str]:
    policies = ctx["policies"]["mcp"]
    parts = tool_name.split("__", 2)
    server = parts[1] if len(parts) > 1 else ""
    name = parts[2] if len(parts) > 2 else ""
    if name in policies["forbidden_tools"] or "run_script" in tool_name or "presigned" in tool_name:
        return _deny(f"tool MCP prohibida: {tool_name}")
    if server.startswith("aws") or name.startswith("aws___"):
        role = ctx["role"]
        if role not in ("reviewer", "deployer"):
            return _deny(f"AWS MCP no permitido para '{role}'")
        if name not in policies["knowledge_tools"]:
            return _deny(f"solo tools de conocimiento AWS: {name}")
    return True, ""


def decide(root: Path, event: dict[str, Any], env_vars: Mapping[str, str]) -> tuple[bool, str]:
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    ctx = _load(root)
    policies = ctx["policies"]
    maintenance = env_vars.get(policies["harness"]["maintenance_env_var"]) == "1"
    # v1.2 maintenance scope. Reads always keep check_read (protected != unreadable).
    scope_id = maintenance_scope.requested_id(policies, env_vars)
    if scope_id is not None and tool not in READ_TOOLS:
        # Requested: valid => it only narrows; invalid, expired or inconsistent => deny.
        try:
            if not maintenance:
                raise maintenance_scope.ScopeError(
                    "el alcance requiere tambien TPI_HARNESS_MAINTENANCE=1 fijado por el humano"
                )
            scope = maintenance_scope.load(root, policies, scope_id)
        except common.HarnessError as error:
            return _deny(f"alcance de mantencion solicitado pero no activable: {error}")
        return _decide_scoped(root, ctx, event, tool, tool_input, scope)
    if maintenance and tool not in READ_TOOLS:
        # Dropping the scope variable must never widen permissions: while a registry is open
        # (or unreadable), plain maintenance is denied until the human closes it.
        opened = maintenance_scope.open_scope_ids(root, policies)
        if opened:
            return _deny(
                "hay alcances de mantencion abiertos ("
                + ", ".join(opened)
                + "): la mantencion simple queda bloqueada hasta que el humano los cierre"
            )
    if tool in READ_TOOLS:
        return check_read(root, ctx, tool_input)
    if tool in WRITE_TOOLS:
        return check_write(root, ctx, tool_input, maintenance)
    if tool in SHELL_TOOLS:
        return check_command(
            root,
            ctx,
            str(tool_input.get("command") or ""),
            maintenance,
            cwd=(event.get("cwd") if isinstance(event.get("cwd"), str) else None),
            dialect="powershell" if tool == "PowerShell" else "bash",
        )
    if tool.startswith("mcp__"):
        return check_mcp(ctx, tool)
    return True, ""


def _decide_scoped(
    root: Path,
    ctx: dict[str, Any],
    event: dict[str, Any],
    tool: str,
    tool_input: dict[str, Any],
    scope: maintenance_scope.Scope,
) -> tuple[bool, str]:
    """Active scope: explicit allowlists only; nothing *delivered to this hook* falls through.

    Tools outside the hook ``matcher`` of .claude/settings.json never get here: keeping them out is
    the job of the launch (``--tools``, verified by check_scope_tools.py), not of this function.
    """
    policies = ctx["policies"]
    if tool in WRITE_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not raw:
            return _deny("herramienta de escritura sin ruta")
        return maintenance_scope.write_allowed(root, policies, scope, str(raw))
    if tool in SHELL_TOOLS:
        command = str(tool_input.get("command") or "")
        # Raw-text rules first (secrets, destructive, variable changes), then the allowlist.
        for rule in policies["bash"]["forbidden_everywhere"]:
            if re.search(rule["pattern"], command, re.IGNORECASE):
                return _deny(rule["reason"])
        if _sets_maintenance_variable(policies, command):
            return _deny(policies["bash"]["structural_rules"]["maintenance_env"]["reason"])
        return maintenance_scope.shell_allowed(
            root,
            scope,
            command,
            "powershell" if tool == "PowerShell" else "bash",
            event.get("cwd") if isinstance(event.get("cwd"), str) else None,
            lambda path: check_read(root, ctx, {"file_path": path})[0],
        )
    if tool.startswith("mcp__"):
        # check_mcp allows any non-AWS server by default; a file or shell MCP tool would bypass
        # the write and shell allowlists above. No MCP tool is on the scope allowlist.
        return _deny(f"Bajo alcance de mantencion no se admiten tools MCP: {tool}")
    return _deny(f"herramienta no contemplada bajo alcance de mantencion: {tool}")


def _log(
    root: Path,
    event: dict[str, Any],
    allowed: bool,
    reason: str,
    maintenance: bool,
    scope_id: str | None = None,
) -> None:
    try:
        directory = root / ".harness-runtime"
        directory.mkdir(exist_ok=True)
        tool_input = event.get("tool_input") or {}
        summary = tool_input.get("command") or tool_input.get("file_path") or ""
        record = {
            "at": common.now_iso(),
            "tool": event.get("tool_name"),
            "target": common.redact(str(summary))[:300],
            "allowed": allowed,
            "reason": reason,
            "session_id": event.get("session_id"),
            # D5: distingue runtime normal de bootstrap de mantenimiento en la evidencia.
            "maintenance_mode": maintenance,
            # v1.2: requested maintenance scope id (an identifier, never a secret).
            "maintenance_scope": scope_id[:64] if scope_id is not None else None,
            "context": "maintenance-bootstrap" if maintenance else "runtime-normal",
            # v1.1: Supervisor turn that launched this process tree (absent in manual mode).
            "supervisor_turn": denials.turn_id(),
        }
        with (directory / "guard.log").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> int:
    event: dict[str, Any] = {}
    maintenance = False
    scope_id: str | None = None
    try:
        event = json.loads(sys.stdin.read() or "{}")
        policies = common.load_policies(common.ROOT)
        maintenance = os.environ.get(policies["harness"]["maintenance_env_var"]) == "1"
        scope_id = maintenance_scope.requested_id(policies, os.environ)
        allowed, reason = decide(common.ROOT, event, os.environ)
    except Exception as error:  # noqa: BLE001 - fail closed
        allowed, reason = False, f"error interno del guard (fail closed): {error}"
    _log(common.ROOT, event, allowed, reason, maintenance, scope_id)
    if allowed:
        return 0
    # v1.1: structured, session-scoped latch so a Supervisor never continues after a DENIED.
    denials.record(common.ROOT, "guard", reason, label=str(event.get("tool_name") or ""))
    sys.stderr.write(f"TPI HARNESS GUARD: DENIED - {reason}\n")
    sys.stderr.write("Si esto bloquea una accion legitima: STOP y solicitar asistencia humana.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

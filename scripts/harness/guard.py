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
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

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


def _scoped_to_worktree(
    root: Path, command: str, cwd: str | None, worktree_path: str
) -> bool:
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


def _gh_action(command: str) -> str | None:
    match = re.search(r"\bgh\s+([a-z-]+)(?:\s+([a-z-]+))?", command)
    if not match:
        return None
    if match.group(1) == "api":
        return "api"
    return f"{match.group(1)} {match.group(2) or ''}".strip()


def check_command(
    root: Path,
    ctx: dict[str, Any],
    command: str,
    maintenance: bool,
    cwd: str | None = None,
) -> tuple[bool, str]:
    policies = ctx["policies"]
    role = ctx["role"]
    state = ctx["state"]
    for rule in policies["bash"]["forbidden_everywhere"]:
        if re.search(rule["pattern"], command, re.IGNORECASE):
            return _deny(rule["reason"])
    if re.search(
        r"harness[/\\. ]+\s*import\s+approve|import\s+approve\b|harness[/\\.]approve", command
    ):
        return _deny("Las decisiones humanas se ejecutan por el humano en su propia terminal")
    for match in re.finditer(r"[^\s\"']*\baws_guard\.py\b", command):
        target = match.group(0).replace("\\", "/")
        if target not in ("scripts/harness/aws_guard.py", "./scripts/harness/aws_guard.py") and (
            common.to_repo_relative(root, target) != "scripts/harness/aws_guard.py"
        ):
            return _deny(
                "aws_guard debe invocarse desde scripts/harness/aws_guard.py del repositorio"
            )
    if not maintenance and any(token in command for token in PROTECTED_TOKENS):
        if re.search(policies["bash"]["protected_write_verbs"], _strip_safe_redirects(command)):
            return _deny("comando shell que podria modificar archivos protegidos del Harness")
    # From here on, classify git/gh subcommands on the quote-stripped command: a bare
    # substring search over the raw text would also fire on a grep pattern, an echo
    # message, or a `git commit -m "..."` message body that merely mentions these
    # words, producing a false DENIED on a command that never actually runs them.
    stripped = _strip_quoted(command)
    if re.search(r"\bgit\s+push\b", stripped):
        task_id = state.get("task_id") or ""
        if role != "developer" or state["state"] != "DEVELOPING":
            return _deny(f"git push no permitido para {role} en {state['state']}")
        worktree = _developer_worktree(ctx)
        if not worktree:
            return _deny("no hay worktree de Developer registrado para la tarea activa")
        if not _scoped_to_worktree(root, stripped, cwd, worktree["path"]):
            return _deny(
                "el Developer solo publica git desde su worktree registrado: "
                f"{worktree['path']}"
            )
        branch = worktree.get("branch") or f"harness/{task_id}"
        if branch not in stripped:
            return _deny(f"el Developer solo publica la rama {branch}")
    if re.search(r"\bgit\s+commit\b", stripped):
        if not (maintenance and _maintenance_commit_allowed(root, policies)):
            if role != "developer" or state["state"] != "DEVELOPING":
                return _deny(f"git commit no permitido para {role} en {state['state']}")
            worktree = _developer_worktree(ctx)
            if not worktree:
                return _deny("no hay worktree de Developer registrado para la tarea activa")
            if not _scoped_to_worktree(root, stripped, cwd, worktree["path"]):
                return _deny(
                    "el Developer solo hace commit desde su worktree registrado: "
                    f"{worktree['path']}"
                )
    if re.search(r"\bgit\s+(merge|rebase|reset)\b", stripped):
        if role != "developer" or state["state"] != "DEVELOPING":
            return _deny(f"git merge/rebase/reset no permitido para {role} en {state['state']}")
    action = _gh_action(stripped)
    if action:
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
            return _deny(
                "solo gh workflow run publish-dev-ecr-images.yml -f source_sha=<release_sha>"
            )
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
    maintenance = env_vars.get(ctx["policies"]["harness"]["maintenance_env_var"]) == "1"
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
        )
    if tool.startswith("mcp__"):
        return check_mcp(ctx, tool)
    return True, ""


def _log(root: Path, event: dict[str, Any], allowed: bool, reason: str, maintenance: bool) -> None:
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
            "context": "maintenance-bootstrap" if maintenance else "runtime-normal",
        }
        with (directory / "guard.log").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> int:
    event: dict[str, Any] = {}
    maintenance = False
    try:
        event = json.loads(sys.stdin.read() or "{}")
        policies = common.load_policies(common.ROOT)
        maintenance = os.environ.get(policies["harness"]["maintenance_env_var"]) == "1"
        allowed, reason = decide(common.ROOT, event, os.environ)
    except Exception as error:  # noqa: BLE001 - fail closed
        allowed, reason = False, f"error interno del guard (fail closed): {error}"
    _log(common.ROOT, event, allowed, reason, maintenance)
    if allowed:
        return 0
    sys.stderr.write(f"TPI HARNESS GUARD: DENIED - {reason}\n")
    sys.stderr.write("Si esto bloquea una accion legitima: STOP y solicitar asistencia humana.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

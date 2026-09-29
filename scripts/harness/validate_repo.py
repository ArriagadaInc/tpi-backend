"""Structural validation of the harness (read-only; never repairs).

Usage: python scripts/harness/validate_repo.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from . import common, guards
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import guards  # type: ignore[no-redef]

REQUIRED_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    "init.sh",
    "init.ps1",
    ".mcp.json",
    ".claude/settings.json",
    "harness/project-profile.yaml",
    "harness/knowledge-sources.yaml",
    "harness/workflow.yaml",
    "harness/policies.yaml",
    "harness/tooling.yaml",
    "harness/state.json",
    "environments/dev.yaml",
    "tasks/current.yaml",
    "tasks/backlog.yaml",
    "tasks/completed",
    "progress/current.md",
    "progress/decisions.md",
    "progress/sessions",
    "evidence/README.md",
    "scripts/harness/init.py",
    "scripts/harness/transition.py",
    "scripts/harness/approve.py",
    "scripts/harness/aws_guard.py",
    "scripts/harness/guard.py",
    # v1.1: imported by guard.py / aws_guard.py / transition.py (a missing one fails closed)
    "scripts/harness/command_analysis.py",
    "scripts/harness/denials.py",
    "scripts/harness/progress_sync.py",
    "scripts/harness/log_scan.py",
    "scripts/harness/context_compact.py",
    "scripts/harness/worktree.py",
    "scripts/harness/evidence.py",
    "runtime/claude/README.md",
    "runtime/codex/README.md",
    "runtime/deepseek/README.md",
)
SCHEMAS = (
    "state",
    "task",
    "backlog",
    "workflow",
    "policies",
    "knowledge-sources",
    "environment",
    "project-profile",
    "evidence",
)
ROLE_FILES = ("PROMPT.md", "CONTEXT.md", "POLICIES.md")
SKILL_SECTIONS = (
    "## 1. Cuando se carga",
    "## 2. Puede",
    "## 3. No puede",
    "## 4. Precondiciones",
    "## 5. Comandos y herramientas",
    "## 6. Evidencia obligatoria",
    "## 7. STOP",
    "## 8. Fuentes",
)
MAX_CONTEXT_LINES = {"PROMPT.md": 80, "CONTEXT.md": 120, "POLICIES.md": 60}
MAX_SKILL_LINES = 110


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise common.HarnessError(f"{path}: sin frontmatter")
    return yaml.safe_load(match.group(1)) or {}


def all_skills(policies: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for role, spec in policies["roles"].items():
        names: set[str] = set()
        skills = spec.get("skills") or {}
        names.update(skills.get("always", []))
        names.update(skills.get("by_task", []))
        for items in (skills.get("by_state") or {}).values():
            names.update(items)
        result[role] = names
    return result


def validate(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"falta ruta obligatoria: {relative}")
    for schema in SCHEMAS:
        if not (root / "harness" / "schemas" / f"{schema}.schema.json").is_file():
            errors.append(f"falta schema: {schema}")
    if errors:
        return errors, warnings

    try:
        loaded = {
            "project-profile": common.load_profile(root),
            "knowledge-sources": common.load_knowledge(root),
            "workflow": common.load_workflow(root),
            "policies": common.load_policies(root),
            "state": common.load_state(root),
            "task": common.read_yaml(root / "tasks" / "current.yaml"),
            "backlog": common.load_backlog(root),
        }
        loaded["environment"] = common.load_environment(
            root, loaded["state"].get("environment", "dev")
        )
    except (OSError, ValueError, yaml.YAMLError, common.HarnessError) as error:
        return [f"archivo del Harness ilegible: {error}"], warnings
    for schema, data in loaded.items():
        errors.extend(
            f"{schema}: {message}" for message in common.validate_schema(root, schema, data)
        )
    if errors:
        return errors, warnings

    workflow = loaded["workflow"]
    policies = loaded["policies"]
    state = loaded["state"]
    states = workflow["states"]
    if workflow["initial_state"] not in states:
        errors.append("initial_state no declarado")
    for required_state in (
        "DEPLOY_FAILED",
        "VERIFY_FAILED",
        "BLOCKED_HUMAN",
        "WAITING_HUMAN_APPROVAL",
        "CANDIDATE_REVIEW",
        "DONE",
    ):
        if required_state not in states:
            errors.append(f"estado obligatorio ausente: {required_state}")
    seen_ids: set[str] = set()
    for transition in workflow["transitions"]:
        if transition["id"] in seen_ids:
            errors.append(f"transicion duplicada: {transition['id']}")
        seen_ids.add(transition["id"])
        for end in ("from", "to"):
            if transition[end] not in states:
                errors.append(
                    f"transicion {transition['id']}: estado desconocido {transition[end]}"
                )
        for guard in transition.get("guards", []):
            if not guards.known_guard(guard):
                errors.append(f"transicion {transition['id']}: guard desconocido {guard}")
        records = transition.get("records")
        if records and records not in workflow["evidence_kinds"]:
            errors.append(f"transicion {transition['id']}: records desconocido {records}")
        if (
            transition["actor"] in common.AGENT_ROLES
            and states[transition["from"]]["role"] != transition["actor"]
        ):
            errors.append(
                f"transicion {transition['id']}: actor distinto del rol del estado origen"
            )
    reachable = {workflow["initial_state"]}
    frontier = [workflow["initial_state"]]
    while frontier:
        current = frontier.pop()
        for transition in workflow["transitions"]:
            if transition["from"] == current and transition["to"] not in reachable:
                reachable.add(transition["to"])
                frontier.append(transition["to"])
    for name in states:
        if name not in reachable:
            errors.append(f"estado inalcanzable: {name}")

    if state["state"] not in states:
        errors.append(f"state.json en estado desconocido: {state['state']}")
    task = loaded["task"].get("task")
    if state["task_id"] is None and task is not None and state["state"] != "IDLE":
        errors.append("tarea en current.yaml sin vinculo en state.json")
    if state["task_id"] is not None and (task is None or task.get("id") != state["task_id"]):
        errors.append("state.task_id no coincide con tasks/current.yaml")
    if state["state"] == "IDLE" and state["task_id"] is not None:
        errors.append("IDLE con tarea vinculada")
    if state["state"] != "IDLE" and state["task_id"] is None:
        errors.append(f"estado {state['state']} sin tarea vinculada")
    for key, relative in (state.get("refs") or {}).items():
        try:
            common.load_ref(root, state, key)
        except common.HarnessError as error:
            errors.append(f"ref {key}: {error}")
            continue
        if not relative.startswith(f"evidence/{state['task_id']}/"):
            errors.append(f"ref {key} fuera de la evidencia de la tarea")

    skills_by_role = all_skills(policies)
    knowledge = loaded["knowledge-sources"]
    source_ids = set(knowledge["sources"]) | set(knowledge["tools"])
    for role in common.AGENT_ROLES:
        for filename in ROLE_FILES:
            path = root / "agents" / role / filename
            if not path.is_file():
                errors.append(f"falta agents/{role}/{filename}")
            elif len(path.read_text(encoding="utf-8").splitlines()) > MAX_CONTEXT_LINES[filename]:
                warnings.append(
                    f"agents/{role}/{filename} supera {MAX_CONTEXT_LINES[filename]} lineas"
                )
        for skill in sorted(skills_by_role.get(role, set())):
            path = root / "agents" / role / "skills" / skill / "SKILL.md"
            if not path.is_file():
                errors.append(f"skill requerida ausente: agents/{role}/skills/{skill}/SKILL.md")
                continue
            try:
                meta = _frontmatter(path)
            except common.HarnessError as error:
                errors.append(str(error))
                continue
            text = path.read_text(encoding="utf-8")
            if meta.get("name") != skill or meta.get("role") != role:
                errors.append(f"skill {skill}: frontmatter name/role incoherente")
            for source in meta.get("sources", []):
                if source not in source_ids:
                    errors.append(f"skill {skill}: fuente desconocida '{source}'")
            for section in SKILL_SECTIONS:
                if section not in text:
                    errors.append(f"skill {skill}: falta seccion '{section}'")
            if len(text.splitlines()) > MAX_SKILL_LINES:
                warnings.append(f"skill {skill} supera {MAX_SKILL_LINES} lineas")

    for source_id, spec in {**knowledge["sources"], **knowledge["tools"]}.items():
        path = root / spec["path"]
        if not path.exists():
            (errors if spec.get("required", True) else warnings).append(
                f"fuente {source_id} ausente: {spec['path']}"
            )
    tracked_candidates = [
        spec["path"] for spec in knowledge["sources"].values() if spec.get("required")
    ]
    ignored = _git_ignored(root, list(REQUIRED_PATHS) + tracked_candidates)
    errors.extend(f"ruta obligatoria ignorada por .gitignore: {path}" for path in ignored)

    environment = loaded["environment"]
    aws = policies["aws"]
    if environment["region"] != aws["region"] or environment["profile"] != aws["profile"]:
        errors.append("environments/dev.yaml incoherente con policies.aws (region/profile)")
    if environment["account_id"] not in (root / "AGENTS.md").read_text(encoding="utf-8"):
        errors.append("la cuenta AWS de dev.yaml no coincide con AGENTS.md")

    limit = int(policies["harness"]["progress_current_max_lines"])
    current_lines = len((root / "progress" / "current.md").read_text(encoding="utf-8").splitlines())
    if current_lines > limit:
        errors.append(
            f"progress/current.md supera {limit} lineas ({current_lines}); ejecutar context_compact.py"
        )

    for adapter in (
        "CLAUDE.md",
        "runtime/claude/README.md",
        "runtime/codex/README.md",
        "runtime/deepseek/README.md",
    ):
        text = (root / adapter).read_text(encoding="utf-8")
        if "AGENTS.md" not in text:
            errors.append(f"{adapter} no remite al protocolo canonico AGENTS.md")
        if len(text.splitlines()) > 90:
            warnings.append(f"{adapter} es demasiado largo para un adaptador")

    for folder in ("evidence", "progress"):
        for path in (root / folder).rglob("*"):
            if path.is_file() and path.suffix in (".json", ".jsonl", ".md", ".yaml"):
                text = path.read_text(encoding="utf-8", errors="replace")
                found = [f for f in common.find_sensitive(text) if f not in ("rut", "phone")]
                if found:
                    errors.append(
                        f"material sensible en {path.relative_to(root).as_posix()}: {found}"
                    )
    return errors, warnings


def _git_ignored(root: Path, paths: list[str]) -> list[str]:
    result = subprocess.run(  # noqa: S603
        ["git", "check-ignore", "--no-index", *paths],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    errors, warnings = validate(common.ROOT)
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}")
    print("VALIDATE: PASS" if not errors else "VALIDATE: FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

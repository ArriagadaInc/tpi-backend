"""Harness init: validate the repository and print the cold-start briefing.

Usage: python scripts/harness/init.py --runtime <claude|codex|deepseek|other> [--json]

init is a VALIDATOR. It never repairs or modifies the repository. If a critical check
fails: STOP, do not modify the repository, request human assistance.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from . import common, validate_repo
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import validate_repo  # type: ignore[no-redef]


def _guard_interpreter(root: Path) -> tuple[list[str], list[str]]:
    """Validate the canonical interpreter the PreToolUse hook resolves at call time.

    Mirrors .claude/settings.json's hook resolution exactly: try python3 then python,
    but only accept a candidate that actually runs (`-c ''`), not merely one that
    resolves on PATH. A PATH entry can exist and still be non-functional (e.g. the
    Windows Store python3.exe execution-alias stub, which resolves via `command -v`
    but exits with an error and never runs any script). Catching that here means init
    fails cold-start instead of every tool call silently denying with a misleading
    "no interpreter" reason.
    """
    errors: list[str] = []
    for candidate in ("python3", "python"):
        path = shutil.which(candidate)
        if not path:
            continue
        result = subprocess.run(  # noqa: S603
            [path, "-c", ""], capture_output=True, check=False, timeout=10
        )
        if result.returncode == 0:
            return errors, []
    errors.append(
        "sin interprete Python canonico funcional (python3/python) en PATH: el hook guard.py "
        "fallara fail-closed en cada llamada de herramienta"
    )
    return errors, []


def _tooling(root: Path, role: str, state_name: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tooling = common.read_yaml(root / "harness" / "tooling.yaml")
    minimum = tuple(int(part) for part in str(tooling["python_min"]).split("."))
    if sys.version_info[:2] < minimum:
        errors.append(f"Python {tooling['python_min']}+ requerido")
    for module in tooling["python_modules"]:
        if importlib.util.find_spec(module) is None:
            errors.append(f"modulo Python requerido ausente: {module}")
    for name, spec in tooling["tools"].items():
        roles = spec.get("required_for", [])
        needed = (
            "all" in roles or role in roles or state_name in spec.get("required_for_states", [])
        )
        if not needed or name == "python":
            continue
        if shutil.which(spec["check"][0]) is None:
            (warnings if spec.get("optional") else errors).append(
                f"herramienta requerida ausente: {name}"
            )
    return errors, warnings


def build_report(root: Path, runtime: str) -> dict[str, Any]:
    errors, warnings = validate_repo.validate(root)
    guard_errors, _ = _guard_interpreter(root)
    errors.extend(guard_errors)
    report: dict[str, Any] = {
        "root": str(root),
        "runtime": runtime,
        "errors": errors,
        "warnings": warnings,
    }
    if (
        subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0
    ):  # noqa: S603,S607
        errors.append("git no disponible")
    elif common.git(root, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        errors.append("no es un repositorio git")
    if errors and not (root / "harness" / "state.json").is_file():
        return report
    try:
        state = common.load_state(root)
        workflow = common.load_workflow(root)
        policies = common.load_policies(root)
        profile = common.load_profile(root)
        task = common.load_current_task(root)
    except Exception as error:  # noqa: BLE001 - init reports, never crashes silently
        errors.append(f"no se pudo cargar el Harness: {error}")
        return report
    state_name = state["state"]
    spec = workflow["states"].get(state_name, {})
    role = spec.get("role", "unknown")
    tool_errors, tool_warnings = _tooling(root, role, state_name)
    errors.extend(tool_errors)
    warnings.extend(tool_warnings)
    if (
        state_name in policies["harness"]["deploy_states"]
        and runtime not in policies["harness"]["deploy_capable_runtimes"]
    ):
        errors.append(
            f"el estado {state_name} requiere un runtime con enforcement demostrado ({policies['harness']['deploy_capable_runtimes']})"
        )
    if (
        state_name == "CANDIDATE_REVIEW"
        and runtime not in policies["harness"]["deploy_capable_runtimes"]
    ):
        errors.append("CANDIDATE_REVIEW requiere lecturas AWS via aws_guard: solo Claude Code")

    skills: list[str] = []
    if role in common.AGENT_ROLES:
        role_skills = policies["roles"][role]["skills"]
        skills = list(role_skills.get("always", [])) + list(
            (role_skills.get("by_state") or {}).get(state_name, [])
        )
        if role_skills.get("by_task"):
            skills.append("(segun la tarea) " + ", ".join(role_skills["by_task"]))
    events = sorted({t["event"] for t in workflow["transitions"] if t["from"] == state_name})
    report["briefing"] = {
        "project": f"{profile['project']['name']} ({profile['project']['repository']})",
        "environment_scope": profile["scope"]["environments"],
        "state": state_name,
        "state_description": spec.get("description"),
        "task": (
            {"id": task["id"], "title": task["title"], "change_class": task["change_class"]}
            if task
            else None
        ),
        "active_role": role,
        "role_files": (
            [f"agents/{role}/PROMPT.md", f"agents/{role}/CONTEXT.md", f"agents/{role}/POLICIES.md"]
            if role in common.AGENT_ROLES
            else []
        ),
        "skills_to_load": skills,
        "next_action": spec.get("next_action"),
        "allowed_events": events,
        "rework_round": f"{state['rework_round']}/{policies['harness']['max_rework_rounds']}",
        "progress": "progress/current.md",
        "stop_rule": "Detenerse al cambiar de rol, al llegar a un estado humano o ante cualquier error.",
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--runtime", required=True, choices=["claude", "codex", "deepseek", "other"]
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(common.ROOT, args.runtime)
    ok = not report["errors"]
    report["result"] = "PASS" if ok else "FAIL"
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for warning in report["warnings"]:
            print(f"WARN  {warning}")
        for error in report["errors"]:
            print(f"ERROR {error}")
        print(f"HARNESS INIT: {report['result']}")
        if ok:
            for key, value in report["briefing"].items():
                print(f"{key}: {value}")
    if not ok:
        print(common.STOP_BANNER, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Harness v1.2: the maintenance-scope policy is validated, and the launch is verifiable.

* `policies.schema.json` must reject a weakened or malformed `harness.maintenance_scope` (the
  reviewer's mutations): `validate_repo.py` and CI are where a bad policy has to be caught.
* `validate_repo.py` checks what a type-level schema cannot (cross-file protections).
* `check_scope_tools.py` proves the tool list the runtime really loaded, because the guard only
  judges the calls that the hook `matcher` delivers to it.

Fictitious data only; nothing launches Claude Code.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.harness import check_scope_tools, common, validate_repo
from tests.harness.conftest import REAL_ROOT

REQUIRED_NEVER_WRITABLE = [
    ".git",
    ".git/**",
    "**/.git",
    "**/.git/**",
    ".gitattributes",
    "**/.gitattributes",
    "pyproject.toml",
    "harness/state.json",
    "harness/workflow.yaml",
    "tasks/**",
    "evidence/**",
    "progress/**",
    ".harness-runtime/**",
    ".harness-worktrees/**",
    ".claude/**",
    ".mcp.json",
]
RUNTIME_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]


def _policies() -> dict[str, Any]:
    return copy.deepcopy(common.load_policies(REAL_ROOT))


def _scope(policies: dict[str, Any]) -> dict[str, Any]:
    return policies["harness"]["maintenance_scope"]


def _schema_errors(policies: dict[str, Any]) -> list[str]:
    return common.validate_schema(REAL_ROOT, "policies", policies)


# --- the real policy is valid, and stricter than a type check ------------------------------------
def test_real_policy_is_valid_and_complete():
    policies = _policies()
    assert _schema_errors(policies) == []
    assert _scope(policies)["runtime_tools"] == RUNTIME_TOOLS
    assert set(REQUIRED_NEVER_WRITABLE) <= set(_scope(policies)["never_writable"])


def test_extra_protections_are_allowed():
    policies = _policies()
    _scope(policies)["never_writable"].append("AGENTS.md")
    assert _schema_errors(policies) == []


# --- blocker 3: the reviewer's mutations (and more) must all be reported -------------------------
def _drop_section(p):
    del p["harness"]["maintenance_scope"]


def _remove_never_writable(entry):
    return lambda p: _scope(p)["never_writable"].remove(entry)


def _set(key, value):
    return lambda p: _scope(p).__setitem__(key, value)


def _drop_key(key):
    return lambda p: _scope(p).pop(key)


MUTATIONS: list[tuple[str, Any]] = [
    ("seccion ausente", _drop_section),
    ("never_writable vacio", _set("never_writable", [])),
    ("never_writable ausente", _drop_key("never_writable")),
    ("never_writable no es lista", _set("never_writable", ".git")),
    *[(f"sin {entry}", _remove_never_writable(entry)) for entry in REQUIRED_NEVER_WRITABLE],
    ("max_hours texto", _set("max_hours", "12")),
    ("max_hours 13", _set("max_hours", 13)),
    ("max_hours 24", _set("max_hours", 24)),
    ("max_hours 999", _set("max_hours", 999)),
    ("max_hours 0", _set("max_hours", 0)),
    ("max_hours negativo", _set("max_hours", -1)),
    ("max_hours nulo", _set("max_hours", None)),
    ("max_hours ausente", _drop_key("max_hours")),
    ("registry_dir distinto", _set("registry_dir", ".harness-runtime/otro")),
    ("registry_dir ausente", _drop_key("registry_dir")),
    ("worktrees_dir distinto", _set("worktrees_dir", ".worktrees")),
    ("env_var en minusculas", _set("env_var", "tpi_harness_scope")),
    ("env_var ajena al Harness", _set("env_var", "PATH")),
    ("clave extra", _set("grant", "all")),
    ("runtime_tools con Monitor", _set("runtime_tools", [*RUNTIME_TOOLS[:5], "Monitor"])),
    ("runtime_tools con PowerShell", _set("runtime_tools", [*RUNTIME_TOOLS[:5], "PowerShell"])),
    ("runtime_tools con TodoWrite", _set("runtime_tools", [*RUNTIME_TOOLS[:5], "TodoWrite"])),
    ("runtime_tools de mas", _set("runtime_tools", [*RUNTIME_TOOLS, "WebFetch"])),
    ("runtime_tools incompleto", _set("runtime_tools", RUNTIME_TOOLS[:5])),
    ("runtime_tools duplicado", _set("runtime_tools", [*RUNTIME_TOOLS[:5], "Read"])),
    ("runtime_tools vacio", _set("runtime_tools", [])),
    ("runtime_tools ausente", _drop_key("runtime_tools")),
    (
        "registro fuera de protected_paths",
        lambda p: p["protected_paths"].remove(".harness-runtime/maintenance/**"),
    ),
]


@pytest.mark.parametrize("label,mutate", MUTATIONS, ids=[label for label, _ in MUTATIONS])
def test_schema_rejects_a_weakened_or_malformed_scope_policy(label, mutate):
    policies = _policies()
    mutate(policies)
    assert _schema_errors(policies), f"la mutacion '{label}' pasa el schema"


# --- validate_repo: cross-file protections a type-level schema cannot express --------------------
def _write_policies(root: Path, policies: dict[str, Any]) -> None:
    (root / "harness" / "policies.yaml").write_text(
        yaml.safe_dump(policies, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def test_validate_repo_rejects_a_scope_variable_equal_to_the_maintenance_variable(
    tmp_harness_repo,
):
    policies = common.load_policies(tmp_harness_repo)
    _scope(policies)["env_var"] = policies["harness"]["maintenance_env_var"]
    _write_policies(tmp_harness_repo, policies)
    errors, _ = validate_repo.validate(tmp_harness_repo)
    assert any("env_var debe ser distinta" in e for e in errors), errors


def test_validate_repo_rejects_a_bash_rules_set_that_no_longer_covers_the_registry(
    tmp_harness_repo,
):
    policies = common.load_policies(tmp_harness_repo)
    rules = policies["bash"]["forbidden_everywhere"]
    policies["bash"]["forbidden_everywhere"] = [
        r for r in rules if "maintenance" not in r["pattern"]
    ]
    assert len(policies["bash"]["forbidden_everywhere"]) < len(rules)
    _write_policies(tmp_harness_repo, policies)
    errors, _ = validate_repo.validate(tmp_harness_repo)
    assert any("forbidden_everywhere cubre el registro" in e for e in errors), errors


def test_validate_repo_rejects_a_hook_matcher_that_drops_a_runtime_tool(tmp_harness_repo):
    settings_path = tmp_harness_repo / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["matcher"] = "Write|Edit|Read|Glob|Grep"  # no Bash
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    errors, _ = validate_repo.validate(tmp_harness_repo)
    assert any("no entrega al guard" in e and "Bash" in e for e in errors), errors


def test_validate_repo_rejects_a_weakened_scope_policy(tmp_harness_repo):
    policies = common.load_policies(tmp_harness_repo)
    _scope(policies)["never_writable"].remove(".claude/**")
    _write_policies(tmp_harness_repo, policies)
    errors, _ = validate_repo.validate(tmp_harness_repo)
    assert any(e.startswith("policies:") for e in errors), errors


# --- check_scope_tools: prove what the runtime really loaded -------------------------------------
# NOTE: these are synthetic init events (the real event format is not captured here; the human E2E
# captures it). The field names `session_id` and `cwd` are the assumptions isolated in
# check_scope_tools.init_session_id / init_cwd, to be confirmed against that capture.
def _init(
    tools: list[str],
    servers: list[Any] | None = None,
    session_id: str | None = "e2e-session-1",
    cwd: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "system",
        "subtype": "init",
        "tools": tools,
        "mcp_servers": servers or [],
    }
    if session_id is not None:
        event["session_id"] = session_id
    if cwd is not None:
        event["cwd"] = cwd
    return event


def _failures(events: list[dict[str, Any]], root: Path = REAL_ROOT, **kwargs: Any) -> list[str]:
    return [m for ok, m in check_scope_tools.assess(root, events, **kwargs) if not ok]


def test_the_intended_launch_passes():
    assert _failures([_init(list(RUNTIME_TOOLS))]) == []
    assert _failures([_init(["Read", "Bash"])]) == []  # fewer tools is narrower, never wider


@pytest.mark.parametrize(
    "tools",
    [
        [*RUNTIME_TOOLS, "TodoWrite"],
        [*RUNTIME_TOOLS, "Monitor"],
        [*RUNTIME_TOOLS, "Agent"],
        [*RUNTIME_TOOLS, "Skill"],
        [*RUNTIME_TOOLS, "EnterWorktree"],
        [*RUNTIME_TOOLS, "PowerShell"],
        [*RUNTIME_TOOLS, "mcp__aws__aws___call_aws"],
    ],
)
def test_any_tool_beyond_runtime_tools_fails_the_check(tools):
    assert _failures([_init(tools)])


def test_an_mcp_server_fails_the_check():
    failures = _failures([_init(list(RUNTIME_TOOLS), [{"name": "aws", "status": "connected"}])])
    assert any("sin MCP" in m for m in failures)


@pytest.mark.parametrize(
    "events",
    [
        [],  # zero init events: evidence missing
        [{"type": "system", "subtype": "init"}],  # init without a tool list
        [_init([])],  # empty tool list
        [_init(["Read"]), _init(["Read", "Write"])],  # ambiguous: two init events
    ],
    ids=["cero", "sin-tools", "tools-vacia", "dos-inits"],
)
def test_a_missing_empty_or_ambiguous_init_fails_the_check(events):
    assert _failures(events)


def test_a_tool_the_hook_matcher_does_not_deliver_fails_the_check(tmp_harness_repo):
    settings_path = tmp_harness_repo / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["matcher"] = "Write|Edit|Read|Glob|Grep"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    failures = _failures([_init(list(RUNTIME_TOOLS))], tmp_harness_repo)
    assert any("llega al hook" in m and "Bash" in m for m in failures), failures


def test_reaches_hook_needs_the_whole_name_not_a_substring():
    matchers = check_scope_tools.hook_matchers(REAL_ROOT)
    assert check_scope_tools.reaches_hook("Write", matchers)
    # Claude Code compiles this matcher as an unanchored regex, so TodoWrite *would* be delivered
    # to the hook; the check refuses to rely on that.
    assert not check_scope_tools.reaches_hook("TodoWrite", matchers)
    assert not check_scope_tools.reaches_hook("Monitor", matchers)


def test_init_events_collects_every_init_in_a_noisy_transcript(tmp_path):
    lines = [
        "",
        "not json",
        json.dumps({"type": "assistant", "message": {}}),
        json.dumps(_init(["Bash"], session_id="s-1")),
        json.dumps(_init(["Read", "Write"], session_id="s-2")),
    ]
    path = tmp_path / "init.jsonl"
    path.write_text("﻿" + "\n".join(lines), encoding="utf-8")
    events = check_scope_tools.init_events(path)
    assert [e["session_id"] for e in events] == ["s-1", "s-2"]
    assert check_scope_tools.read_init(path) is None  # two init events: refused, not "first wins"
    path.write_text("not json\n", encoding="utf-8")
    assert check_scope_tools.init_events(path) == []


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_read_init_accepts_the_encodings_a_windows_shell_produces(tmp_path, encoding):
    """`>` in Windows PowerShell 5.1 writes UTF-16 with a BOM; `Out-File -Encoding utf8` a UTF-8 BOM."""
    path = tmp_path / "init.jsonl"
    path.write_text(json.dumps(_init(["Read"])) + "\n", encoding=encoding)
    assert check_scope_tools.read_init(path)["tools"] == ["Read"]


def test_guard_log_check_only_counts_the_scope_under_test(tmp_path):
    log = tmp_path / "guard.log"
    entries = [
        {"tool": "Bash", "maintenance_scope": "a-1"},
        {"tool": "Monitor", "maintenance_scope": "a-1"},
        {"tool": "WebFetch", "maintenance_scope": "otro"},
        {"tool": "Edit", "maintenance_scope": None},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\nbasura\n", encoding="utf-8")
    assert check_scope_tools.logged_tools(log, "a-1") == {"Bash", "Monitor"}
    results = check_scope_tools.assess(
        REAL_ROOT, [_init(list(RUNTIME_TOOLS))], guard_log=log, scope_id="a-1"
    )
    assert any(not ok and "guard.log" in m and "Monitor" in m for ok, m in results)
    clean = check_scope_tools.assess(
        REAL_ROOT, [_init(list(RUNTIME_TOOLS))], guard_log=log, scope_id="otro-id"
    )
    assert all(ok for ok, _ in clean)


# --- F-A: session identity -----------------------------------------------------------------------
def test_a_foreign_session_id_fails_the_check():
    failures = _failures(
        [_init(list(RUNTIME_TOOLS), session_id="otra-sesion")], session_id="la-mia"
    )
    assert any("sesion esperada" in m for m in failures)


def test_the_expected_session_id_passes_the_check():
    assert _failures([_init(list(RUNTIME_TOOLS), session_id="la-mia")], session_id="la-mia") == []


def test_a_foreign_cwd_fails_the_check(tmp_path):
    failures = _failures(
        [_init(list(RUNTIME_TOOLS), cwd=str(tmp_path))], cwd=str(tmp_path / "otro")
    )
    assert any("cwd esperado" in m for m in failures)


def test_a_missing_session_id_fails_when_requested():
    failures = _failures([_init(list(RUNTIME_TOOLS), session_id=None)], session_id="la-mia")
    assert any("sesion esperada" in m for m in failures)


def test_the_init_is_bound_to_the_session_that_wrote_guard_log(tmp_path):
    log = tmp_path / "guard.log"
    entries = [
        {"tool": "Bash", "maintenance_scope": "a-1", "session_id": "s-work"},
        {"tool": "Edit", "maintenance_scope": "a-1", "session_id": "s-work"},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    ok = _failures([_init(list(RUNTIME_TOOLS), session_id="s-work")], guard_log=log, scope_id="a-1")
    assert not any("misma sesion" in m for m in ok)
    bad = _failures(
        [_init(list(RUNTIME_TOOLS), session_id="s-probe")], guard_log=log, scope_id="a-1"
    )
    assert any("misma sesion" in m for m in bad)


def test_cli_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.jsonl"
    good.write_text(json.dumps(_init(list(RUNTIME_TOOLS))) + "\n", encoding="utf-8")
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(_init([*RUNTIME_TOOLS, "Monitor"])) + "\n", encoding="utf-8")
    ambiguous = tmp_path / "ambiguous.jsonl"
    ambiguous.write_text(
        "\n".join(json.dumps(_init(["Read"])) for _ in range(2)) + "\n", encoding="utf-8"
    )
    assert check_scope_tools.main(["--init", str(good)]) == 0
    assert "CHECK: PASS" in capsys.readouterr().out
    assert check_scope_tools.main(["--init", str(bad)]) == 1
    assert "CHECK: FAIL" in capsys.readouterr().out
    assert check_scope_tools.main(["--init", str(ambiguous)]) == 1
    assert "ambigu" in capsys.readouterr().out
    assert check_scope_tools.main(["--init", str(tmp_path / "no-existe.jsonl")]) == 1


# --- the written procedure says what the policy says ---------------------------------------------
def test_launch_procedure_uses_exactly_the_policy_tools():
    readme = (REAL_ROOT / "runtime" / "claude" / "README.md").read_text(encoding="utf-8")
    flat = " ".join(readme.split())
    tools = ",".join(_scope(_policies())["runtime_tools"])
    assert flat.count(f'--tools "{tools}"') >= 2  # the effective-configuration check and the launch
    assert "--strict-mcp-config" in flat and "check_scope_tools.py" in flat
    assert "CHECK: PASS" in flat
    assert "no llega al guard" in flat and "no lo restringe" in flat
    claude_md = (REAL_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "runtime/claude/README.md" in claude_md

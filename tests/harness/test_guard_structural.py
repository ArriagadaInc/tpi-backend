"""Harness Hardening v1.1 / P0-2: the guard distinguishes EXECUTING from MENTIONING.

Every ALLOW case below is a read-only command (or a data payload) that the v1 guard denied
during the H3.3.6 dogfood or during the v1.1 maintenance session itself (several are copied
verbatim from .harness-runtime/guard.log). Every DENY case is a real execution that must stay
blocked. Same strategy as test_guard_headless.py: real policies.yaml, synthetic state.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.harness import command_analysis, common, denials, guard
from tests.harness.conftest import REAL_ROOT
from tests.harness.test_guard_headless import (
    DEV_WORKTREE_PATH,
    _dev_worktree,
    _fake_state,
    _fake_task,
)

HUMAN = "scripts/harness/approve.py"
VAR = "TPI_HARNESS_MAINTENANCE"


@pytest.fixture
def state_as(monkeypatch: pytest.MonkeyPatch):
    def _set(state_name: str, task_id: str | None = "TEST-1", worktrees=None) -> None:
        monkeypatch.setattr(
            common, "load_state", lambda root: _fake_state(state_name, task_id, worktrees)
        )
        monkeypatch.setattr(
            common, "load_current_task", lambda root: _fake_task() if task_id else None
        )

    return _set


def _decide(command: str, tool: str = "Bash", env: dict[str, str] | None = None, **extra: Any):
    event = {"tool_name": tool, "tool_input": {"command": command}, **extra}
    return guard.decide(REAL_ROOT, event, env or {})


# ---------------------------------------------------------------------------
# human script: data vs execution
# ---------------------------------------------------------------------------
HUMAN_SCRIPT_AS_DATA = [
    f"cat {HUMAN}",
    f"sed -n 1,40p {HUMAN}",
    f'grep -n "isatty\\|interactive" {HUMAN}',
    'grep -rn "approve.py" docs/ evidence/',
    "grep -rn approve.py evidence/H3.3.6/",
    f"wc -l {HUMAN} scripts/harness/validate_repo.py",
    # guard.log 2026-09-23T00:20:32Z (reviewer schema discovery)
    f"cat harness/schemas/task.schema.json; echo ----APPROVE; cat {HUMAN}",
    # guard.log 2026-09-23T14:05:54Z: deployer writes a merge payload that cites the script
    "mkdir -p .harness-release && cat > .harness-release/merge-input.json <<'EOF'\n"
    '{"task_id": "H3.3.6", "created_by": "scripts/harness/approve.py"}\nEOF',
    # guard.log 2026-09-23T15:36:55Z: python reads verification evidence mentioning it as data
    "python - <<'EOF'\nimport json\n"
    "v=json.load(open('evidence/H3.3.6/deployment/verification-01.json',encoding='utf-8'))\n"
    "assert v['acceptance_check']['created_by']=='scripts/harness/approve.py'\n"
    "json.dump(v, open('.harness-release/verification-input.json','w'))\nEOF",
    # v1.1 maintenance session: a python heredoc patching a scratch file whose replacement
    # strings mention the human script (denied by the v1 guard, no execution involved)
    "python - <<'EOF'\nfrom pathlib import Path\np = Path('/tmp/scratch/guard_candidate.py')\n"
    "s = p.read_text()\ns = s.replace('name in HUMAN', '_human_script_name(\"approve.py\")')\n"
    "p.write_text(s)\nEOF",
    # progress/current.md text that cites the human next_action
    "cat > progress/current.md <<'EOF'\n# Progreso\n- Proximo paso: python scripts/harness/"
    "approve.py gate (humano)\nEOF",
]

HUMAN_SCRIPT_EXECUTION = [
    f"python {HUMAN} gate",
    f"python3 {HUMAN} accept",
    "py -3 scripts\\harness\\approve.py accept",
    f"./{HUMAN} gate",
    f"cd /c/repo && python {HUMAN} resolve --to DEVELOPING",
    "python -m scripts.harness.approve gate",
    f"env FOO=1 python {HUMAN} gate",
    f"echo y | xargs python {HUMAN} gate",
    f'bash -c "python {HUMAN} gate"',
    f"echo $(python {HUMAN} gate)",
    f"uv run python {HUMAN} gate",
    f"python -c \"import runpy; runpy.run_path('{HUMAN}')\"",
    "python -c \"from scripts.harness import approve; approve.main(['gate'])\"",
    "python - <<'EOF'\nimport subprocess\nsubprocess.run(['python', 'scripts/harness/approve.py',"
    " 'gate'])\nEOF",
    f'echo "python {HUMAN} gate" | bash',
    f"alias ok='python {HUMAN} gate'",
]


@pytest.mark.parametrize("command", HUMAN_SCRIPT_AS_DATA)
def test_human_script_mentioned_as_data_is_allowed(state_as, command):
    state_as("PREPARING_DEPLOYMENT")
    allowed, reason = _decide(command)
    assert allowed, reason


@pytest.mark.parametrize("state_name", ["IDLE", "REVIEWING", "VERIFYING", "WAITING_HUMAN_APPROVAL"])
@pytest.mark.parametrize("command", HUMAN_SCRIPT_EXECUTION)
def test_human_script_execution_by_agent_is_denied(state_as, state_name, command):
    state_as(state_name, task_id=None if state_name == "IDLE" else "TEST-1")
    allowed, reason = _decide(command)
    assert not allowed
    assert "decisiones humanas" in reason


def test_human_script_execution_denied_even_in_maintenance(state_as):
    state_as("IDLE", task_id=None)
    allowed, reason = _decide(f"python {HUMAN} gate", env={VAR: "1"})
    assert not allowed and "decisiones humanas" in reason


def test_powershell_call_operator_human_script_denied(state_as):
    state_as("VERIFYING")
    allowed, _ = _decide(f"& python {HUMAN} accept", tool="PowerShell")
    assert not allowed


def test_reading_human_script_with_read_tool_allowed(state_as):
    state_as("IDLE", task_id=None)
    allowed, reason = guard.decide(
        REAL_ROOT, {"tool_name": "Read", "tool_input": {"file_path": HUMAN}}, {}
    )
    assert allowed, reason


# ---------------------------------------------------------------------------
# AWS CLI: data vs execution
# ---------------------------------------------------------------------------
AWS_AS_DATA = [
    # guard.log 2026-09-23T14:30:12Z (deployer read-only discovery)
    "git status --short evidence/ .harness-runtime 2>/dev/null | head; ls -la evidence/H3.3.6/"
    'deployment; grep -rln -i "expired\\|aws login" progress/ docs/BITACORA.md 2>/dev/null | head',
    'grep -rn "aws login" docs/',
    "rg -n 'aws s3 ls' agents/",
    "cat > .harness-release/note.md <<'EOF'\nNo ejecutar aws login ni aws s3 ls desde agentes.\nEOF",
    'echo "usar aws_guard en vez de aws cli"',
    # v1.1 maintenance session: writing a smoke script whose test data contains the text
    "cat > /tmp/scratch/smoke.py <<'PYEOF'\ncases = [\n ('bash', 'grep -rln -i \"expired\\\\|aws login\" "
    "progress/'),\n ('bash', 'aws login'),\n]\nPYEOF\npython /tmp/scratch/smoke.py",
    "python -c \"print('aws login es una operacion humana')\"",
    "python -m pytest tests/harness/test_aws_guard.py -q",
]

AWS_EXECUTION = [
    ("Bash", "aws login"),
    ("Bash", "aws s3 ls"),
    ("Bash", "cd /tmp && aws sts get-caller-identity"),
    ("Bash", "AWS_PROFILE=tpi-dev aws s3 ls"),
    ("Bash", "sudo aws s3 ls"),
    ("Bash", 'bash -c "aws s3 ls"'),
    ("Bash", 'echo "$(aws sts get-caller-identity)"'),
    ("Bash", "X=aws; $X s3 ls"),
    ("Bash", 'echo "aws s3 ls" | bash'),
    ("Bash", "python -c \"import subprocess; subprocess.run(['aws', 's3', 'ls'])\""),
    ("Bash", "python -c \"import os; os.system('aws s3 ls')\""),
    ("Bash", "/usr/local/bin/aws s3 ls"),
    ("PowerShell", "aws login"),
    ("PowerShell", '& "C:\\Program Files\\Amazon\\AWSCLIV2\\aws.exe" s3 ls'),
    ("PowerShell", "$r = aws sts get-caller-identity"),
    ("PowerShell", 'Invoke-Expression "aws s3 ls"'),
    ("PowerShell", 'cmd /c "aws s3 ls"'),
]


@pytest.mark.parametrize("command", AWS_AS_DATA)
def test_aws_text_as_search_or_data_is_allowed(state_as, command):
    state_as("VERIFYING")
    allowed, reason = _decide(command)
    assert allowed, reason


@pytest.mark.parametrize("tool,command", AWS_EXECUTION)
def test_aws_cli_execution_is_denied(state_as, tool, command):
    state_as("DEPLOYING")
    allowed, reason = _decide(command, tool=tool)
    assert not allowed
    assert "AWS CLI directo prohibido" in reason


# ---------------------------------------------------------------------------
# Maintenance variable: mention/read vs set/unset
# ---------------------------------------------------------------------------
MAINTENANCE_MENTION = [
    ("Bash", f'echo "MAINT=${VAR}"'),  # the exact v1.1 session-start false positive
    ("Bash", f'echo "MAINT=${VAR}" && cat AGENTS.md | head -150 && ls scripts/harness harness'),
    ("Bash", f"grep -rn {VAR} harness/ AGENTS.md"),
    ("Bash", f'if [ "${VAR}" == "1" ]; then echo on; fi'),
    ("Bash", f"python -c \"import os; print(os.environ.get('{VAR}'))\""),
    ("PowerShell", f"Write-Output $env:{VAR}"),
    ("PowerShell", f"if ($env:{VAR} -eq '1') {{ 'on' }}"),
]

MAINTENANCE_SET = [
    ("Bash", f"{VAR}=1 python scripts/harness/transition.py x"),
    ("Bash", f"export {VAR}=1"),
    ("Bash", f"export {VAR}"),
    ("Bash", f"unset {VAR}"),
    ("Bash", f"env {VAR}=1 claude"),
    ("Bash", f"env -u {VAR} claude"),
    ("Bash", f"setx {VAR} 1"),
    ("Bash", f"python -c \"import os; os.environ['{VAR}'] = '1'\""),
    ("Bash", f"python -c \"import os; os.putenv('{VAR}', '1')\""),
    ("Bash", f"python -c \"import subprocess; subprocess.run(['x'], env={{'{VAR}': '1'}})\""),
    ("PowerShell", f"$env:{VAR} = '1'"),
    ("PowerShell", f"$env:{VAR}='1'; claude"),
    ("PowerShell", f"[Environment]::SetEnvironmentVariable('{VAR}', '1', 'User')"),
    ("PowerShell", f"Remove-Item env:{VAR}"),
    ("PowerShell", f"Set-Item -Path env:{VAR} -Value 1"),
]


@pytest.mark.parametrize("tool,command", MAINTENANCE_MENTION)
def test_maintenance_variable_mention_is_allowed(state_as, tool, command):
    state_as("IDLE", task_id=None)
    allowed, reason = _decide(command, tool=tool)
    assert allowed, reason


@pytest.mark.parametrize("tool,command", MAINTENANCE_SET)
def test_maintenance_variable_assignment_is_denied(state_as, tool, command):
    state_as("IDLE", task_id=None)
    for env in ({}, {VAR: "1"}):  # maintenance never grants the power to (re)set itself
        allowed, reason = _decide(command, tool=tool, env=env)
        assert not allowed
        assert "mantenimiento" in reason


# ---------------------------------------------------------------------------
# git: merge-base is not merge; global options do not hide a subcommand
# ---------------------------------------------------------------------------
GIT_READ_ONLY = [
    "git merge-base --is-ancestor 78bf33bcb946fc442a8e5488cdf0d2f89fd190c2 origin/main && echo IN",
    # guard.log 2026-09-23T00:20:49Z (verbatim shape)
    "git fetch origin main -q; git rev-parse origin/main 'origin/main^{tree}'; git log -3 "
    "--oneline origin/main; git merge-base --is-ancestor 78bf33b origin/main && echo H335_IN_MAIN",
    "git log -1 --format='%P %s' 5f5b3d3; git merge-base HEAD origin/main",
    'grep -rn "git merge" docs/',
    'git log --grep "git reset"',
]


@pytest.mark.parametrize("state_name", ["REVIEWING", "CANDIDATE_REVIEW", "MERGING", "IDLE"])
@pytest.mark.parametrize("command", GIT_READ_ONLY)
def test_git_merge_base_and_mentions_allowed(state_as, state_name, command):
    state_as(state_name, task_id=None if state_name == "IDLE" else "TEST-1")
    allowed, reason = _decide(command)
    assert allowed, reason


@pytest.mark.parametrize(
    "command",
    [
        "git merge origin/main",
        "git rebase main",
        "git -c core.editor=true merge origin/main",
        "git -C .harness-worktrees/X merge origin/main",
        "python -c \"import subprocess; subprocess.run(['git', 'merge', 'x'])\"",
    ],
)
def test_git_merge_outside_developer_denied(state_as, command):
    state_as("REVIEWING")
    allowed, reason = _decide(command)
    assert not allowed
    assert "merge/rebase/reset" in reason


def test_git_merge_allowed_for_developer_in_developing(state_as):
    state_as("DEVELOPING", worktrees=[_dev_worktree()])
    allowed, reason = _decide(f"cd {DEV_WORKTREE_PATH} && git merge origin/main")
    assert allowed, reason


@pytest.mark.parametrize(
    "command",
    [
        "git -c user.name=x -c user.email=y commit -m msg",
        "git --no-pager commit -m msg",
        "git -C /tmp/elsewhere commit -m msg",
    ],
)
def test_git_global_options_do_not_hide_commit(state_as, command):
    """v1 gap found in this session: `git -c k=v commit` was not recognized as a commit."""
    state_as("IDLE", task_id=None)
    allowed, reason = _decide(command)
    assert not allowed
    assert "git commit no permitido" in reason


def test_developer_commit_with_git_dash_c_scoped_to_worktree_allowed(state_as):
    state_as("DEVELOPING", worktrees=[_dev_worktree()])
    allowed, reason = _decide(f"git -C {DEV_WORKTREE_PATH} commit -m 'feat: x'")
    assert allowed, reason


def test_developer_push_with_quoted_cd_scope_allowed(state_as):
    state_as("DEVELOPING", worktrees=[_dev_worktree()])
    allowed, reason = _decide(f'cd "{DEV_WORKTREE_PATH}" && git push origin harness/TEST-1-slug')
    assert allowed, reason


def test_scope_mentioned_only_inside_a_string_does_not_count(state_as):
    state_as("DEVELOPING", worktrees=[_dev_worktree()])
    allowed, _ = _decide(f'echo "cd {DEV_WORKTREE_PATH}"; git commit -m x')
    assert not allowed


# ---------------------------------------------------------------------------
# Python: read-only with >= vs writes to protected paths
# ---------------------------------------------------------------------------
PYTHON_READ_ONLY = [
    # guard.log 2026-09-23T15:44:01Z (verbatim shape)
    "python -c \"\nimport json\nfor l in open('evidence/H3.3.6/aws-audit.jsonl'):\n"
    "    d=json.loads(l)\n    if d['at']>='2026-09-23T15:30': print(d['at'],d['operation'])\n\"",
    # guard.log 2026-09-23T19:50:39Z
    "ls progress/sessions | grep H3.3.6; sed -n 1,40p scripts/harness/closure.py; python - <<'EOF'"
    "\nimport json\nfor l in open('evidence/H3.3.6/aws-audit.jsonl'):\n    d=json.loads(l)\n"
    "    if d['at']>='2026-09-23T15:30' and d['allowed'] >= False: print(d['operation'])\nEOF",
    "python -c \"import json; d=json.load(open('harness/state.json')); print(d['state'])\"",
    # guard.log 2026-09-23T02:19:52Z: rewrite an allowed payload while quoting evidence paths
    "python - <<'EOF'\nimport json\np='.harness-runtime/payloads/review-01.json'\n"
    "s=open(p,encoding='utf-8').read().replace('evidence/H3.3.6/x','<ref>')\n"
    "open(p,'w',encoding='utf-8').write(s)\nEOF",
]

PYTHON_PROTECTED_WRITE = [
    "python - <<'EOF'\nopen('harness/state.json','w').write('{}')\nEOF",
    "python -c \"from pathlib import Path; Path('evidence/X/a.json').write_text('x')\"",
    "python -c \"import shutil; shutil.copy('a.json', 'evidence/X/a.json')\"",
    "python -c \"import os; os.remove('harness/policies.yaml')\"",
    "python -c \"import sys; open(sys.argv[1], 'w').write(open('evidence/a').read())\" x",
    "python - <<'EOF'\nfrom pathlib import Path\nroot = Path('.')\n"
    "(root / 'scripts' / 'harness' / 'guard.py').write_text('')\nEOF",
    "python -c \"import json; json.dump({}, open('tasks/current.yaml', 'a'))\"",
    "python -c \"import os; os.remove('.harness-runtime/supervisor/denials/x.jsonl')\"",
]


@pytest.mark.parametrize("command", PYTHON_READ_ONLY)
def test_python_read_only_with_comparison_operators_allowed(state_as, command):
    state_as("VERIFYING")
    allowed, reason = _decide(command)
    assert allowed, reason


@pytest.mark.parametrize("command", PYTHON_PROTECTED_WRITE)
def test_python_writing_protected_file_denied(state_as, command):
    state_as("VERIFYING")
    allowed, reason = _decide(command)
    assert not allowed
    assert "protegidos" in reason


@pytest.mark.parametrize(
    "command",
    [
        "echo x > harness/policies.yaml",
        "echo x >> evidence/X/a.json",
        "ls 2>&1 > harness/out.log",
        "tee evidence/x.json < a.json",
        "sed -i s/a/b/ harness/workflow.yaml",
        "cp a.json evidence/X/a.json",
        "rm .harness-runtime/guard.log",
        "Remove-Item .harness-runtime/supervisor/denials/x.jsonl",
        "node -e \"require('fs').writeFileSync('harness/x', '')\"",
    ],
)
def test_shell_protected_writes_still_denied(state_as, command):
    state_as("VERIFYING")
    allowed, _ = _decide(command)
    assert not allowed


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard origin/main",
        "rm -rf .harness-worktrees",
        "Remove-Item -Recurse -Force .harness-worktrees/x",
        "git push --force origin harness/TEST-1-slug",
        "git push origin main",
        "cat .env",
        "docker push x",
        "gh secret list",
    ],
)
def test_legitimate_v1_denials_are_preserved(state_as, command):
    state_as("DEVELOPING", worktrees=[_dev_worktree()])
    allowed, _ = _decide(command)
    assert not allowed


def test_unparseable_command_falls_back_to_conservative_rules(state_as):
    state_as("VERIFYING")
    # unbalanced quote: the analyzer cannot establish structure -> legacy text rules apply
    allowed, _ = _decide("echo 'unterminated ; aws s3 ls")
    assert not allowed


def test_analyzer_reports_heredoc_to_file_as_data():
    analysis = command_analysis.analyze(
        'cat > .harness-release/a.json <<\'EOF\'\n{"x": "aws login"}\nEOF'
    )
    assert analysis.ok
    names = [command_analysis.basename(i.argv[0].text) for i in analysis.invocations if i.argv]
    assert names == ["cat"]
    assert analysis.invocations[0].redirects[0].target.text == ".harness-release/a.json"


# ---------------------------------------------------------------------------
# P0-1: session-scoped DENIED latch written by guard.main()
# ---------------------------------------------------------------------------
def _run_guard_main(monkeypatch, root: Path, tool: str, tool_input: dict[str, Any]) -> int:
    monkeypatch.setattr(common, "ROOT", root)
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": tool, "tool_input": tool_input}))
    )
    return guard.main()


def test_guard_deny_writes_latch_for_supervisor_turn(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.setenv(denials.ENV_VAR, "claude-202609230000-deployer-supabc123")
    code = _run_guard_main(monkeypatch, tmp_harness_repo, "Bash", {"command": "aws s3 ls"})
    assert code == 2
    records = denials.read(tmp_harness_repo, "claude-202609230000-deployer-supabc123")
    assert len(records) == 1 and records[0]["source"] == "guard"
    assert "AWS CLI" in records[0]["reason"] and records[0]["label"] == "Bash"
    log = (tmp_harness_repo / ".harness-runtime" / "guard.log").read_text(encoding="utf-8")
    assert (
        json.loads(log.splitlines()[-1])["supervisor_turn"]
        == "claude-202609230000-deployer-supabc123"
    )


def test_guard_allow_writes_no_latch(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.setenv(denials.ENV_VAR, "claude-202609230000-deployer-supabc124")
    assert _run_guard_main(monkeypatch, tmp_harness_repo, "Bash", {"command": "git status"}) == 0
    assert denials.read(tmp_harness_repo, "claude-202609230000-deployer-supabc124") == []


def test_manual_mode_deny_writes_no_latch(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.delenv(denials.ENV_VAR, raising=False)
    assert _run_guard_main(monkeypatch, tmp_harness_repo, "Bash", {"command": "aws s3 ls"}) == 2
    assert not (tmp_harness_repo / denials.DENIALS_DIR).exists()


def test_latch_is_session_scoped(monkeypatch, tmp_harness_repo: Path):
    monkeypatch.setenv(denials.ENV_VAR, "claude-202609230000-deployer-supaaaaaa")
    _run_guard_main(monkeypatch, tmp_harness_repo, "Bash", {"command": "aws s3 ls"})
    assert denials.read(tmp_harness_repo, "claude-202609230001-deployer-supbbbbbb") == []


@pytest.mark.parametrize("value", ["", "../../etc/x", "a b", "short"])
def test_invalid_turn_ids_are_ignored(value):
    assert denials.turn_id({denials.ENV_VAR: value}) is None

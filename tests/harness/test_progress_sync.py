"""Harness v1.1 / P0-3: progress/current.md is a reliable projection of harness/state.json.

Real transition.py in a tmp repo. Workflow guards and evidence validation are bypassed with
the same technique as supervisor_fake_runtime.py (they have their own tests): what is under
test here is only the post-transition projection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.harness import common, context_compact, evidence, guards, progress_sync, transition
from tests.harness.conftest import bind_task

PATH_TO_CLOSE = [
    ("start_review", "REVIEWING"),
    ("review_reject", "REVIEW_REJECTED"),
    ("resume_development", "DEVELOPING"),
    ("submit_for_review", "READY_FOR_REVIEW"),
    ("start_review", "REVIEWING"),
    ("review_approve", "REVIEW_APPROVED"),
    ("start_merge", "MERGING"),
    ("merged", "PREPARING_DEPLOYMENT"),
    ("candidate_ready", "CANDIDATE_REVIEW"),
    ("candidate_approve", "WAITING_HUMAN_APPROVAL"),
]
RUNTIME = {
    "developer": "deepseek",
    "reviewer": "claude",
    "deployer": "claude",
}


@pytest.fixture
def repo(tmp_harness_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(guards, "evaluate", lambda name, ctx: None)
    monkeypatch.setattr(evidence, "validate_reference", lambda root, state, path, **kw: path)
    return tmp_harness_repo


def _fire(root: Path, event: str, *, human: bool = False) -> dict:
    state = common.load_state(root)
    workflow = common.load_workflow(root)
    spec = next(
        t for t in workflow["transitions"] if t["event"] == event and t["from"] == state["state"]
    )
    evidence_path = None
    if spec.get("records"):
        kind = workflow["evidence_kinds"][spec["records"]]
        directory = root / "evidence" / state["task_id"] / common.ROLE_EVIDENCE_DIR[spec["actor"]]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind}-{len(list(directory.glob('*.json'))) + 1:02d}.json"
        # closure.py summarises the verification result when the task closes
        path.write_text(
            json.dumps({"kind": kind, "fake": True, "result": "PASS"}), encoding="utf-8"
        )
        evidence_path = path.relative_to(root).as_posix()
    actor = spec["actor"]
    return transition.apply_transition(
        root,
        event,
        runtime=None if human else RUNTIME.get(actor, "claude"),
        session=None if human else f"{actor}-session-{event}",
        evidence_path=evidence_path,
        _human=human,
    )


def _projection(root: Path) -> str:
    return (root / "progress" / "current.md").read_text(encoding="utf-8")


def _assert_projects(root: Path, state: dict) -> None:
    text = _projection(root)
    workflow = common.load_workflow(root)
    spec = workflow["states"][state["state"]]
    assert f"- Estado del Harness: {state['state']} (rol: {spec['role']})" in text
    assert f"- Tarea: {state.get('task_id') or 'ninguna'}" in text
    assert f"- Proximo paso: {spec['next_action']}" in text
    assert f"- Actualizado: {state['updated_at']}" in text
    assert progress_sync.in_sync(root, state)
    assert text.count(progress_sync.BEGIN) == 1


def test_projection_follows_every_transition_of_the_cycle(repo: Path):
    bind_task(repo, state_name="READY_FOR_REVIEW")
    for event, expected in PATH_TO_CLOSE:
        state = _fire(repo, event)
        assert state["state"] == expected
        _assert_projects(repo, state)


@pytest.mark.parametrize(
    "start,event,expected",
    [
        ("REVIEWING", "review_approve", "REVIEW_APPROVED"),
        ("REVIEWING", "review_reject", "REVIEW_REJECTED"),
        ("MERGING", "merged", "PREPARING_DEPLOYMENT"),
        ("PREPARING_DEPLOYMENT", "candidate_ready", "CANDIDATE_REVIEW"),
        ("CANDIDATE_REVIEW", "candidate_approve", "WAITING_HUMAN_APPROVAL"),
        ("VERIFYING", "verified", "IDLE"),  # DONE auto-closes: the projection shows IDLE
    ],
)
def test_projection_after_required_transitions(repo: Path, start: str, event: str, expected: str):
    bind_task(repo, state_name=start)
    state = _fire(repo, event)
    assert state["state"] == expected
    _assert_projects(repo, common.load_state(repo))


def test_compact_before_transition_no_longer_leaves_stale_state(repo: Path):
    """Exact H3.3.6 pattern: context_compact.py ran BEFORE transition.py."""
    bind_task(repo, state_name="REVIEWING")
    (repo / "progress" / "current.md").write_text(
        "# Progreso actual\n\n## Estado reciente\n- revise el PR\nDECISION: aprobar\n",
        encoding="utf-8",
    )
    context_compact.compact(repo, label="rev-close")
    assert "- Estado del Harness: REVIEWING" in _projection(repo)
    state = _fire(repo, "review_approve")
    text = _projection(repo)
    assert "- Estado del Harness: REVIEW_APPROVED (rol: deployer)" in text
    assert "REVIEWING (rol" not in text
    assert "- revise el PR" in text  # free notes are preserved
    _assert_projects(repo, state)


def test_legacy_current_md_is_converted_and_notes_kept(repo: Path):
    bind_task(repo, state_name="REVIEWING")
    (repo / "progress" / "current.md").write_text(
        "# Progreso actual\n\n## Estado\n- Estado del Harness: DEVELOPING (rol: developer)\n"
        "- Tarea: TEST-1\n- Ultima sesion archivada: x.md\n\n## Estado reciente\n- nota libre\n"
        "\n## Bloqueos\n- BLOCKER: algo\n",
        encoding="utf-8",
    )
    state = _fire(repo, "review_reject")
    text = _projection(repo)
    assert "DEVELOPING (rol: developer)" not in text
    for kept in ("- Ultima sesion archivada: x.md", "- nota libre", "- BLOCKER: algo"):
        assert kept in text
    _assert_projects(repo, state)


def test_human_transition_through_transition_py_is_projected(repo: Path):
    """approve.py applies human events through transition.apply_transition(_human=True)."""
    bind_task(repo, state_name="NEW")
    state = common.load_state(repo)
    state.update(state="IDLE", task_id=None)
    (repo / "harness" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    new_state = transition.apply_transition(repo, "activate_task", _human=True)
    assert new_state["state"] == "NEW"
    _assert_projects(repo, new_state)


def test_projection_failure_never_invalidates_the_transition(repo: Path, capsys):
    bind_task(repo, state_name="REVIEWING")
    current = repo / "progress" / "current.md"
    current.unlink()
    current.mkdir()  # unwritable projection target
    state = _fire(repo, "review_reject")
    assert state["state"] == "REVIEW_REJECTED"
    assert common.load_state(repo)["state"] == "REVIEW_REJECTED"
    err = capsys.readouterr().err
    assert "WARNING" in err and "state.json conserva la autoridad" in err


def test_projection_block_without_end_marker_is_a_warning_not_a_corruption(repo: Path):
    bind_task(repo, state_name="REVIEWING")
    broken = "# Progreso\n\n## Estado\n" + progress_sync.BEGIN + "\n- a mano\n"
    (repo / "progress" / "current.md").write_text(broken, encoding="utf-8")
    state = _fire(repo, "review_reject")
    assert state["state"] == "REVIEW_REJECTED"
    assert _projection(repo) == broken  # untouched; the human/LLM fixes it


def test_real_repository_current_md_is_small_enough_after_projection():
    root = Path(__file__).resolve().parents[2]
    text = (root / "progress" / "current.md").read_text(encoding="utf-8")
    state = common.load_state(root)
    projected = progress_sync.apply(text, progress_sync.render(state, common.load_workflow(root)))
    limit = int(common.load_policies(root)["harness"]["progress_current_max_lines"])
    assert len(projected.splitlines()) <= limit

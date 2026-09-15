"""Coverage for incorporating the python-design-patterns skill into the Developer baseline.

Scope: the skill exists, is declared for the developer role, cold start surfaces it, and it is
registered as a non-canonical (reference) knowledge source. Full structural/schema validation
of the resulting repo is already covered by test_b_clean_clone_validates.
"""

from __future__ import annotations

from pathlib import Path

from scripts.harness import common, init
from tests.harness.conftest import bind_task


def test_skill_file_exists_and_declared_for_developer():
    path = Path(
        "agents/developer/skills/python-design-patterns/SKILL.md"
    )
    assert (common.ROOT / path).is_file()
    policies = common.load_policies(common.ROOT)
    assert "python-design-patterns" in policies["roles"]["developer"]["skills"]["by_task"]


def test_cold_start_surfaces_skill_for_developer(tmp_harness_repo: Path):
    bind_task(tmp_harness_repo, state_name="DEVELOPING")
    report = init.build_report(tmp_harness_repo, "claude")
    assert not report["errors"]
    skills_to_load = " ".join(report["briefing"]["skills_to_load"])
    assert "python-design-patterns" in skills_to_load


def test_knowledge_source_is_reference_not_canonical():
    knowledge = common.load_knowledge(common.ROOT)
    entry = knowledge["sources"]["python_design_patterns_skill"]
    assert entry["authority"] == "reference"
    assert entry["origin"] == "external_skill"
    assert entry["path"] == "agents/developer/skills/python-design-patterns/SKILL.md"

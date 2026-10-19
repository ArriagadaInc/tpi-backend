"""Regression tests for the AWS DEV ECR lifecycle policy.

The policy lives in a single file (`deployment/ecr/lifecycle-policy.json`) shared by the
`tpi-dev-app` and `tpi-dev-caddy` repositories. These tests run without AWS and guard the
retention rules so that a future reduction (or a malformed rule) breaks CI instead of
silently expiring images required by the last known good (LKG) release.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
POLICY_PATH = ROOT / "deployment" / "ecr" / "lifecycle-policy.json"

RETENTION_MINIMUM = 100


def _load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _rules() -> list:
    rules = _load_policy()["rules"]
    assert isinstance(rules, list)
    return rules


def _rule_by_priority(priority: int) -> dict:
    for rule in _rules():
        if rule["rulePriority"] == priority:
            return rule
    raise AssertionError(f"no existe la regla con prioridad {priority}")


def test_policy_has_rules_with_unique_priorities() -> None:
    rules = _rules()
    assert rules, "la policy no puede quedar sin reglas"
    priorities = [rule["rulePriority"] for rule in rules]
    assert len(priorities) == len(set(priorities)), "prioridades de regla repetidas"


def test_rule_1_untagged_seven_day_expiry_is_unchanged() -> None:
    rule_1 = _rule_by_priority(1)
    assert rule_1["selection"] == {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 7,
    }
    assert rule_1["action"] == {"type": "expire"}


def test_rule_2_retains_100_images_with_tag_any_and_expire() -> None:
    rule_2 = _rule_by_priority(2)
    assert rule_2["selection"] == {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": RETENTION_MINIMUM,
    }
    assert rule_2["action"] == {"type": "expire"}


def test_retention_count_is_not_below_100() -> None:
    retention = [
        rule for rule in _rules() if rule["selection"]["countType"] == "imageCountMoreThan"
    ]
    assert len(retention) == 1, "debe existir una única regla de retención por conteo"
    assert retention[0]["selection"]["countNumber"] >= RETENTION_MINIMUM


def test_no_rule_expires_tagged_images_by_age() -> None:
    for rule in _rules():
        selection = rule["selection"]
        if selection["countType"] == "sinceImagePushed":
            assert (
                selection["tagStatus"] == "untagged"
            ), "una regla expira por antigüedad imágenes con etiqueta"

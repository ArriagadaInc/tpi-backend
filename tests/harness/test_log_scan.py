"""Harness v1.1 / P1-7: strong vs weak sensitive-data indicators in count-only log scans."""

from __future__ import annotations

import json

import pytest

from scripts.harness import common, log_scan
from tests.harness.conftest import REAL_ROOT

POLICIES = common.load_policies(REAL_ROOT)
STRONG = ["Authorization", "Bearer", "password", "cookie", "raw_payload", "secret", "token"]


def test_policy_declares_strong_and_weak_lists():
    strong, weak = log_scan.indicators(POLICIES)
    assert set(STRONG) <= set(strong)
    assert weak == ["hash"]


def test_cert_hash_is_a_weak_indicator():
    result = log_scan.classify({"Authorization": 0, "password": 0, "hash": 1}, POLICIES)
    assert result == {
        "strong_matches": 0,
        "strong_hits": {},
        "weak_matches": {"hash": 1},
        "classification_required": True,
    }


@pytest.mark.parametrize("pattern", STRONG + ["AUTHORIZATION", "Password"])
def test_strong_indicators(pattern):
    result = log_scan.classify({pattern: 2}, POLICIES)
    assert result["strong_matches"] == 2 and result["weak_matches"] == {}


def test_unknown_pattern_is_treated_as_strong():
    assert log_scan.classify({"api_key": 1}, POLICIES)["strong_matches"] == 1


def _scan(**overrides):
    scan = {"matches": 0, "raw_pattern_hits": {"hash": 1}, "false_positives": []}
    scan.update(overrides)
    return scan


HUMAN_FP = {
    "pattern": "hash",
    "count": 1,
    "classified_by": "human",
    "classification": "FALSE_POSITIVE",
    "triggering_field": "cert_hash",
}


def test_weak_hit_with_human_classification_passes():
    assert log_scan.check(_scan(false_positives=[HUMAN_FP]), POLICIES) == []


def test_weak_hit_without_classification_blocks():
    reasons = log_scan.check(_scan(), POLICIES)
    assert reasons and "clasificacion humana" in reasons[0]


def test_weak_hit_classified_by_agent_does_not_count():
    fp = dict(HUMAN_FP, classified_by="deployer")
    assert log_scan.check(_scan(false_positives=[fp]), POLICIES)


def test_weak_count_must_be_fully_covered():
    assert log_scan.check(_scan(raw_pattern_hits={"hash": 3}, false_positives=[HUMAN_FP]), POLICIES)


@pytest.mark.parametrize("pattern", STRONG)
def test_strong_hit_is_never_downgraded_even_if_classified(pattern):
    fp = dict(HUMAN_FP, pattern=pattern)
    reasons = log_scan.check(_scan(raw_pattern_hits={pattern: 1}, false_positives=[fp]), POLICIES)
    assert reasons and "indicador fuerte" in reasons[0]


def test_confirmed_matches_still_block():
    assert "posible PII en logs" in log_scan.check(
        _scan(matches=1, false_positives=[HUMAN_FP]), POLICIES
    )


def test_new_structured_fields_are_honoured():
    scan = {"matches": 0, "strong_matches": 1, "weak_matches": {}, "false_positives": []}
    assert log_scan.check(scan, POLICIES)
    scan = {
        "matches": 0,
        "strong_matches": 0,
        "weak_matches": {"hash": 1},
        "false_positives": [HUMAN_FP],
    }
    assert log_scan.check(scan, POLICIES) == []


def test_h336_real_evidence_passes_under_v11_model():
    data = json.loads(
        (REAL_ROOT / "evidence" / "H3.3.6" / "deployment" / "verification-02.json").read_text(
            encoding="utf-8"
        )
    )
    assert log_scan.check(data["pii_log_scan"], POLICIES) == []


def test_cli_classify(capsys):
    assert log_scan.main(["classify", "--counts", '{"hash": 1, "Bearer": 0}']) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["weak_matches"] == {"hash": 1} and out["strong_matches"] == 0
    assert log_scan.main(["classify", "--counts", "[1]"]) == 1

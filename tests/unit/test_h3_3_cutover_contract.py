"""Regression tests for the one-time H3.3 source/target preflight distinction."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.release.validate_h3_3_cutover_contract import (
    SOURCE_CONTRACT,
    TARGET_CONTRACT,
    mismatched_names,
)

ROOT = Path(__file__).parents[2]
VALIDATOR = ROOT / "scripts/release/validate_h3_3_cutover_contract.py"


def _settings(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"Name": name, "Value": value} for name, value in values.items()]


def test_source_contract_is_only_the_observed_legacy_starting_state() -> None:
    assert mismatched_names(_settings(SOURCE_CONTRACT), SOURCE_CONTRACT) == []
    with_zone = dict(SOURCE_CONTRACT, TPI_ROUTE53_HOSTED_ZONE_ID="Z07053592LX0W8GJXNI1C")
    assert mismatched_names(_settings(with_zone), SOURCE_CONTRACT) == ["TPI_ROUTE53_HOSTED_ZONE_ID"]


def test_target_contract_requires_all_four_tpi_values() -> None:
    assert mismatched_names(_settings(TARGET_CONTRACT), TARGET_CONTRACT) == []
    assert "TPI_PUBLIC_SITE_URL" in mismatched_names(_settings(SOURCE_CONTRACT), TARGET_CONTRACT)


def test_validator_reports_source_or_target_without_echoing_domain_values() -> None:
    source = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", "source"],
        input=json.dumps(_settings(SOURCE_CONTRACT)),
        capture_output=True,
        check=False,
        text=True,
    )
    assert source.returncode == 0
    assert "SOURCE CONTRACT = PASS" in source.stdout

    target = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", "target"],
        input=json.dumps(_settings(SOURCE_CONTRACT)),
        capture_output=True,
        check=False,
        text=True,
    )
    assert target.returncode == 1
    assert "TARGET CONTRACT = FAIL" in target.stdout
    assert "PREFLIGHT = FAIL" in target.stdout
    assert "genialabs.cl" not in target.stdout + target.stderr

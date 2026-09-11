"""Regression tests for the exact non-secret AWS DEV environment contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.release.validate_dev_environment_contract import (
    EXPECTED_DEV_ENVIRONMENT,
    mismatched_names,
)

ROOT = Path(__file__).parents[2]
VALIDATOR = ROOT / "scripts/release/validate_dev_environment_contract.py"


def _settings(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"Name": name, "Value": value} for name, value in values.items()]


def test_exact_dev_environment_contract_passes() -> None:
    assert mismatched_names(_settings(EXPECTED_DEV_ENVIRONMENT)) == []


def test_genialabs_contract_is_rejected_without_echoing_values() -> None:
    obsolete = dict(EXPECTED_DEV_ENVIRONMENT)
    obsolete.update(
        {
            "TPI_PUBLIC_SITE_URL": "https://dev.genialabs.cl/",
            "TPI_PUBLIC_SITE_ADDRESS": "https://dev.genialabs.cl",
            "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.genialabs.cl",
        }
    )

    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        input=json.dumps(_settings(obsolete)),
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "PREFLIGHT = FAIL" in result.stdout
    assert "genialabs.cl" not in result.stdout + result.stderr
    assert "TPI_PUBLIC_SITE_URL" in result.stderr


def test_missing_hosted_zone_id_is_rejected() -> None:
    incomplete = dict(EXPECTED_DEV_ENVIRONMENT)
    incomplete.pop("TPI_ROUTE53_HOSTED_ZONE_ID")

    assert mismatched_names(_settings(incomplete)) == ["TPI_ROUTE53_HOSTED_ZONE_ID"]

"""Fail closed unless Elastic Beanstalk has the exact public DEV domain contract."""

from __future__ import annotations

import json
import sys
from typing import Any, Final

EXPECTED_DEV_ENVIRONMENT: Final = {
    "TPI_PUBLIC_SITE_URL": "https://dev.tupensioninteligente.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.tupensioninteligente.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.tupensioninteligente.cl",
    "TPI_ROUTE53_HOSTED_ZONE_ID": "Z07053592LX0W8GJXNI1C",
}


def mismatched_names(option_settings: Any) -> list[str]:
    """Return only contract variable names whose values are absent or incorrect."""
    if not isinstance(option_settings, list):
        return sorted(EXPECTED_DEV_ENVIRONMENT)

    observed = {
        item.get("Name", item.get("OptionName")): item.get("Value")
        for item in option_settings
        if isinstance(item, dict)
        and item.get("Name", item.get("OptionName")) in EXPECTED_DEV_ENVIRONMENT
    }
    return sorted(
        name
        for name, expected in EXPECTED_DEV_ENVIRONMENT.items()
        if observed.get(name) != expected
    )


def main() -> int:
    try:
        option_settings = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print("PREFLIGHT = FAIL")
        print("Invalid DEV environment contract input", file=sys.stderr)
        return 1

    mismatches = mismatched_names(option_settings)
    if mismatches:
        print("PREFLIGHT = FAIL")
        print("Mismatched DEV variables: " + ", ".join(mismatches), file=sys.stderr)
        return 1

    print("PREFLIGHT = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

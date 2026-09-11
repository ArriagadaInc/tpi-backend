"""Validate the one-time H3.3 legacy-to-TPI Elastic Beanstalk contract transition."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Final

SOURCE_CONTRACT: Final = {
    "TPI_PUBLIC_SITE_URL": "https://dev.genialabs.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.genialabs.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.genialabs.cl",
}
TARGET_CONTRACT: Final = {
    "TPI_PUBLIC_SITE_URL": "https://dev.tupensioninteligente.cl/",
    "TPI_PUBLIC_SITE_ADDRESS": "https://dev.tupensioninteligente.cl",
    "TPI_BACKOFFICE_SITE_ADDRESS": "https://backoffice.dev.tupensioninteligente.cl",
    "TPI_ROUTE53_HOSTED_ZONE_ID": "Z07053592LX0W8GJXNI1C",
}
CONTRACT_NAMES: Final = tuple(TARGET_CONTRACT)


def mismatched_names(option_settings: Any, expected: dict[str, str]) -> list[str]:
    """Return only non-secret contract variable names that differ from the requested state."""
    if not isinstance(option_settings, list):
        return list(CONTRACT_NAMES)

    observed: dict[str, str] = {}
    duplicates: set[str] = set()
    for item in option_settings:
        if not isinstance(item, dict):
            return list(CONTRACT_NAMES)
        name = item.get("Name", item.get("OptionName"))
        value = item.get("Value")
        if name not in CONTRACT_NAMES or not isinstance(value, str):
            return list(CONTRACT_NAMES)
        if name in observed:
            duplicates.add(name)
        observed[name] = value

    mismatches = {name for name in CONTRACT_NAMES if observed.get(name) != expected.get(name)}
    mismatches.update(duplicates)
    return sorted(mismatches)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=("source", "target"), required=True)
    arguments = parser.parse_args()
    expected = SOURCE_CONTRACT if arguments.state == "source" else TARGET_CONTRACT

    try:
        option_settings = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print(f"{arguments.state.upper()} CONTRACT = FAIL")
        print("PREFLIGHT = FAIL")
        print("Invalid non-secret DEV environment contract input", file=sys.stderr)
        return 1

    mismatches = mismatched_names(option_settings, expected)
    if mismatches:
        print(f"{arguments.state.upper()} CONTRACT = FAIL")
        print("PREFLIGHT = FAIL")
        print("Mismatched DEV variables: " + ", ".join(mismatches), file=sys.stderr)
        return 1

    print(f"{arguments.state.upper()} CONTRACT = PASS")
    print("PREFLIGHT = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

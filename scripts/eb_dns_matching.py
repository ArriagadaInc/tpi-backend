"""Resolve one Elastic Beanstalk environment from public DNS evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import TypedDict, cast


class EnvironmentRecord(TypedDict, total=False):
    """Relevant, non-sensitive fields returned by Elastic Beanstalk."""

    Application: str
    Environment: str
    CNAME: str | None
    Status: str
    Health: str
    HealthStatus: str
    VersionLabel: str | None


class DnsRecord(TypedDict):
    cname: str | None
    addresses: list[str]


def _normalize_dns_name(value: str | None) -> str:
    return (value or "").strip().rstrip(".").lower()


def _normalize_addresses(values: Sequence[str]) -> set[str]:
    return {value.strip() for value in values if value.strip()}


def matching_environments(
    environments: Sequence[EnvironmentRecord],
    domain_record: DnsRecord,
    environment_addresses: Mapping[str, Sequence[str]],
) -> list[EnvironmentRecord]:
    """Return environments matching a domain's CNAME or resolved A records."""

    cname = _normalize_dns_name(domain_record.get("cname"))
    if cname:
        return [
            environment
            for environment in environments
            if _normalize_dns_name(environment.get("CNAME")) == cname
        ]

    domain_addresses = _normalize_addresses(domain_record.get("addresses", []))
    if not domain_addresses:
        return []

    candidates: list[EnvironmentRecord] = []
    for environment in environments:
        environment_cname = _normalize_dns_name(environment.get("CNAME"))
        if not environment_cname:
            continue
        resolved_addresses = _normalize_addresses(environment_addresses.get(environment_cname, []))
        if domain_addresses.intersection(resolved_addresses):
            candidates.append(environment)
    return candidates


def identify_environment(
    environments: Sequence[EnvironmentRecord],
    domain_records: Mapping[str, DnsRecord],
    environment_addresses: Mapping[str, Sequence[str]],
) -> EnvironmentRecord:
    """Require every public DEV domain to identify the same one environment."""

    selected: EnvironmentRecord | None = None
    selected_key: tuple[str, str] | None = None
    for domain, domain_record in domain_records.items():
        candidates = matching_environments(environments, domain_record, environment_addresses)
        if len(candidates) != 1:
            raise ValueError(
                f"DNS domain {domain!r} identified {len(candidates)} environments; expected exactly one."
            )
        candidate = candidates[0]
        candidate_key = (
            candidate.get("Application", ""),
            candidate.get("Environment", ""),
        )
        if selected_key is None:
            selected = candidate
            selected_key = candidate_key
        elif candidate_key != selected_key:
            raise ValueError("DEV domains identify different Elastic Beanstalk environments.")

    if selected is None:
        raise ValueError("No DEV domains were provided for environment identification.")
    return selected


def _parse_input(payload: object) -> tuple[
    list[EnvironmentRecord],
    Mapping[str, DnsRecord],
    Mapping[str, Sequence[str]],
]:
    if not isinstance(payload, dict):
        raise ValueError("DNS matching input must be a JSON object.")
    environments = payload.get("environments")
    domain_records = payload.get("domain_records")
    environment_addresses = payload.get("environment_addresses")
    if not isinstance(environments, list):
        raise ValueError("DNS matching input must contain an environments list.")
    if not isinstance(domain_records, dict):
        raise ValueError("DNS matching input must contain domain_records.")
    if not isinstance(environment_addresses, dict):
        raise ValueError("DNS matching input must contain environment_addresses.")
    return (
        cast(list[EnvironmentRecord], environments),
        cast(Mapping[str, DnsRecord], domain_records),
        cast(Mapping[str, Sequence[str]], environment_addresses),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        environments, domain_records, environment_addresses = _parse_input(payload)
        selected = identify_environment(environments, domain_records, environment_addresses)
    except (json.JSONDecodeError, ValueError) as error:
        print(f"DNS environment matching failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(selected, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Strong vs weak sensitive-data indicators for count-only log scans (Harness v1.1).

Usage (Deployer, to build `pii_log_scan` of the verification evidence):
  python scripts/harness/log_scan.py classify --counts '{"Authorization": 0, "hash": 1}'

The counts come from `aws_guard.py logs filter-log-events ... --query 'length(events)'`: the
Deployer never reads log lines. Indicators live in harness/policies.yaml
(`observability.log_indicators`):

- strong (Authorization, Bearer, password, cookie, raw_payload, secret, token): any hit blocks
  `verified` and can NEVER be downgraded, not even by a recorded classification.
- weak (e.g. `hash`, which matches Caddy's `cert_hash` TLS fingerprint): not equivalent to a
  secret, but every hit requires a human classification recorded in `false_positives`
  (classified_by: human) before `verified`.
- a pattern that is in neither list is treated as strong (fail closed).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]


def indicators(policies: dict[str, Any]) -> tuple[list[str], list[str]]:
    config = (policies.get("observability") or {}).get("log_indicators") or {}
    return list(config.get("strong") or []), list(config.get("weak") or [])


def _kind(pattern: str, strong: list[str], weak: list[str]) -> str:
    lowered = pattern.lower()
    if lowered in {s.lower() for s in strong}:
        return "strong"
    if lowered in {w.lower() for w in weak}:
        return "weak"
    return "unknown"


def classify(counts: dict[str, int], policies: dict[str, Any]) -> dict[str, Any]:
    strong, weak = indicators(policies)
    strong_hits: dict[str, int] = {}
    weak_hits: dict[str, int] = {}
    for pattern, raw in counts.items():
        count = int(raw)
        if count <= 0:
            continue
        if _kind(pattern, strong, weak) == "weak":
            weak_hits[pattern] = count
        else:
            strong_hits[pattern] = count  # strong or unknown: fail closed
    return {
        "strong_matches": sum(strong_hits.values()),
        "strong_hits": strong_hits,
        "weak_matches": weak_hits,
        "classification_required": bool(weak_hits),
    }


def check(scan: dict[str, Any], policies: dict[str, Any]) -> list[str]:
    """Reasons why `pii_log_scan` does not allow `verified` (empty list = OK)."""
    reasons: list[str] = []
    if int(scan.get("matches", 0)) != 0:
        reasons.append("posible PII en logs")
    raw = dict(scan.get("raw_pattern_hits") or {})
    for pattern, count in (scan.get("weak_matches") or {}).items():
        raw[pattern] = max(int(count), int(raw.get(pattern, 0)))
    for pattern, count in (scan.get("strong_hits") or {}).items():
        raw[pattern] = max(int(count), int(raw.get(pattern, 0)))
    result = classify(raw, policies)
    if result["strong_matches"] or int(scan.get("strong_matches", 0)):
        names = ", ".join(sorted(result["strong_hits"])) or "strong_matches"
        reasons.append(f"indicador fuerte en logs ({names}): nunca se degrada automaticamente")
    covered: dict[str, int] = {}
    for item in scan.get("false_positives") or []:
        if (
            isinstance(item, dict)
            and item.get("classified_by") == "human"
            and str(item.get("classification", "")).upper() == "FALSE_POSITIVE"
        ):
            key = str(item.get("pattern", "")).lower()
            covered[key] = covered.get(key, 0) + int(item.get("count", 0))
    for pattern, count in result["weak_matches"].items():
        if covered.get(pattern.lower(), 0) < count:
            reasons.append(
                f"indicador debil '{pattern}' ({count}) sin clasificacion humana registrada"
            )
    return reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    classify_parser = sub.add_parser("classify")
    classify_parser.add_argument("--counts", required=True, help="JSON {patron: conteo}")
    args = parser.parse_args(argv)
    try:
        counts = json.loads(args.counts)
        if not isinstance(counts, dict):
            raise ValueError("--counts debe ser un objeto JSON")
        result = classify(counts, common.load_policies(common.ROOT))
    except (ValueError, TypeError) as error:
        print(f"LOG SCAN ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

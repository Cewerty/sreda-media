#!/usr/bin/env python3
"""Read-only resource gate for ADR 0006 §4.

Without approval or real measurements the gate returns NO-GO/SKIP. It never
enables ``ENABLE_*`` flags, touches a host, or changes a CI required status.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUDGET = ROOT / "deploy" / "host" / "resource-budget.json"
FIELDS = (
    "cpu_idle_percent",
    "ram_idle_mb",
    "disk_free_gb",
    "egress_mbps",
    "restore_minutes",
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def evaluate(budget: dict[str, Any]) -> dict[str, Any]:
    """Evaluate measurements against the approved limits."""
    reasons: list[str] = []
    breaches: list[str] = []
    measurements = budget.get("measurements")
    if not budget.get("approved"):
        reasons.append("not approved by owner (ADR 0006 §4)")
    if not isinstance(measurements, dict):
        reasons.append("no real measurements")
        measurements = {}
    limits = budget.get("limits", {})
    for field in FIELDS:
        value = measurements.get(field)
        limit = limits.get(field)
        if value is None:
            reasons.append(f"missing measurement: {field}")
            continue
        if not isinstance(value, (int, float)) or not isinstance(limit, (int, float)):
            reasons.append(f"invalid measurement or limit: {field}")
            continue
        if value > limit:
            breaches.append(f"{field}={value} > limit={limit}")
    if breaches:
        verdict, exit_code = "FAIL", 1
    elif reasons:
        verdict, exit_code = "NO-GO", 3
    else:
        verdict, exit_code = "PASS", 0
    return {
        "verdict": verdict,
        "exit_code": exit_code,
        "schema_version": budget.get("schema_version"),
        "owner": budget.get("owner"),
        "reasons": reasons,
        "breaches": breaches,
        "does_not_prove": [
            "provider or tariff availability",
            "actual DNS cutover or RTO",
            "database or media consistency",
        ],
    }


def main() -> int:
    """Entry point."""
    args = parse_args()
    result = evaluate(json.loads(BUDGET.read_text(encoding="utf-8")))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"{result['verdict']}: resource gate")
        for item in result["reasons"]:
            print(f"  {item}")
        for item in result["breaches"]:
            print(f"  breach: {item}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

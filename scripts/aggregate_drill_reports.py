#!/usr/bin/env python3
"""Aggregate machine-readable drill contracts without gating CI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS = ROOT / "deploy" / "reports" / "drills"
VERIFIER = ROOT / "scripts" / "verify_drill_contract.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--verify-timeout", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="treat an absent reports directory as SKIP instead of FAIL",
    )
    return parser.parse_args(argv)


def verify_report(path: Path, timeout: int) -> dict[str, Any]:
    """Run the standalone verifier and return its machine-readable verdict."""
    result = subprocess.run(
        [sys.executable, str(VERIFIER), str(path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "verdict": "FAIL",
            "exit_code": 1,
            "reasons": [f"invalid verifier output for {path.name}"],
        }
    payload["report"] = path.name
    return payload


def aggregate(args: argparse.Namespace) -> dict[str, Any]:
    reasons: list[str] = []
    if not args.reports_dir.is_dir():
        reason = f"reports dir missing: {args.reports_dir}"
        if args.allow_missing:
            return {
                "schema_version": "drill-gate/v1",
                "verdict": "SKIP",
                "exit_code": 0,
                "reasons": [reason],
                "reports": [],
                "does_not_prove": ["all drill evidence"],
            }
        return {
            "schema_version": "drill-gate/v1",
            "verdict": "FAIL",
            "exit_code": 1,
            "reasons": [reason],
            "reports": [],
            "does_not_prove": ["all drill evidence"],
        }
    reports = sorted(args.reports_dir.glob("*.json"))
    results = [verify_report(path, args.verify_timeout) for path in reports]
    statuses = [str(item.get("verdict", "FAIL")) for item in results]
    if not reports:
        verdict, exit_code = "NO-GO", 3
        reasons.append("no drill contracts found")
    elif "FAIL" in statuses:
        verdict, exit_code = "FAIL", 1
        reasons.append("one or more contracts failed")
    elif "NO-GO" in statuses:
        verdict, exit_code = "NO-GO", 3
        reasons.append("one or more contracts are NO-GO")
    else:
        verdict, exit_code = "PASS", 0
    return {
        "schema_version": "drill-gate/v1",
        "verdict": verdict,
        "exit_code": exit_code,
        "reasons": reasons,
        "reports": results,
        "does_not_prove": [
            "production availability",
            "DNS cutover",
            "database consistency",
            "alert delivery",
        ],
    }


def render_summary(payload: dict[str, Any]) -> str:
    lines = ["## Drill evidence gate", "", f"Verdict: **{payload['verdict']}**", ""]
    for reason in payload.get("reasons", []):
        lines.append(f"- {reason}")
    for item in payload["reports"]:
        lines.append(f"- `{item['report']}`: {item.get('verdict', 'FAIL')}")
    if not payload["reports"]:
        lines.append("- no drill contracts found")
    lines.extend(["", "Report-only: this job is not a required status."])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = aggregate(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.summary:
        print(render_summary(payload))
    else:
        print(f"{payload['verdict']}: {len(payload['reports'])} drill contract(s)")
    return int(payload["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Aggregate read-only pin audits into one machine-readable report.

The script never edits files and never gates CI. It combines the existing
``check_tool_pins.py`` and ``audit_workflows.py`` verdicts into a single JSON
or text summary with explicit ``does_not_prove`` claims.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PIN_LINE = re.compile(r"\bpin[s]?\b|\buses\b|\bsha256\b", re.IGNORECASE)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--tool-pins",
        default="scripts/check_tool_pins.py",
        help="relative path to the tool pin checker",
    )
    parser.add_argument(
        "--workflow-pins",
        default="scripts/audit_workflows.py",
        help="relative path to the workflow pin checker",
    )
    return parser.parse_args(argv)


def run_check(relative_path: str) -> dict[str, Any]:
    """Run one read-only checker and normalise its result."""
    path = ROOT / relative_path
    if not path.is_file():
        return {
            "id": path.name,
            "status": "FAIL",
            "returncode": 1,
            "evidence": [f"missing checker: {relative_path}"],
            "does_not_prove": ["checker was not executed"],
        }
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    evidence = [line.strip() for line in output.splitlines() if PIN_LINE.search(line)]
    status = "PASS" if result.returncode == 0 else "FAIL"
    return {
        "id": path.name,
        "status": status,
        "returncode": result.returncode,
        "evidence": evidence[:20],
        "does_not_prove": [
            "version freshness",
            "lockfile correctness",
            "ci.yml changes",
        ],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """Build the combined pin report."""
    checks = [run_check(args.tool_pins), run_check(args.workflow_pins)]
    failures = [check["id"] for check in checks if check["status"] == "FAIL"]
    verdict = "FAIL" if failures else "PASS"
    return {
        "schema_version": "pin-report/v1",
        "verdict": verdict,
        "exit_code": 1 if failures else 0,
        "checks": checks,
        "does_not_prove": [
            "freshness of pinned versions",
            "correctness of apps lockfiles",
            "any modification of ci.yml",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"pin report: {report['verdict']}")
        for check in report["checks"]:
            print(f"  {check['id']}: {check['status']}")
        print("does_not_prove: " + ", ".join(report["does_not_prove"]))
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

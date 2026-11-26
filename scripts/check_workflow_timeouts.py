#!/usr/bin/env python3
"""Report-only check for timeout and concurrency in non-CI workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = {"ci.yml"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def scan(path: Path) -> list[str]:
    """Return findings for one workflow file."""
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []
    if not re.search(r"^\s*timeout-minutes:\s*\d+\s*$", text, re.MULTILINE):
        findings.append("missing timeout-minutes")
    if "schedule:" in text and not re.search(
        r"^concurrency:\s*$", text, re.MULTILINE
    ):
        findings.append("scheduled workflow missing concurrency")
    return findings


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    directory = ROOT / args.workflows_dir
    findings: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.yml")):
        if path.name in ALLOWLIST:
            continue
        issues = scan(path)
        if issues:
            findings[path.name] = issues
    verdict = "FAIL" if findings else "PASS"
    details: dict[str, Any] = {
        "schema_version": "workflow-timeout-report/v1",
        "verdict": verdict,
        "exit_code": 1 if findings else 0,
        "checked": sorted(p.name for p in directory.glob("*.yml") if p.name not in ALLOWLIST),
        "allowlist": sorted(ALLOWLIST),
        "findings": findings,
        "does_not_prove": [
            "GitHub runner behaviour",
            "required status configuration",
            "runtime duration of any job",
        ],
    }
    if args.json:
        print(json.dumps(details, indent=2, sort_keys=True))
    else:
        if findings:
            for name, issues in findings.items():
                print(f"FAIL {name}: {', '.join(issues)}", file=sys.stderr)
        else:
            print("ok: workflow timeouts and concurrency (ci.yml allowlisted)")
    return int(details["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Report-only per-job timeout and concurrency check for non-CI workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = {"ci.yml"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", default=".github/workflows")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def scan(path: Path) -> list[str]:
    """Return per-job findings for one workflow file."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        return [f"unparseable workflow: {error}"]
    findings: list[str] = []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return ["missing jobs"]
    for name, job in jobs.items():
        if not isinstance(job, dict) or "uses" in job:
            continue
        if not isinstance(job.get("timeout-minutes"), int):
            findings.append(f"job {name}: missing timeout-minutes")
    on_key = "on" if "on" in document else True
    triggers = document.get(on_key)
    if isinstance(triggers, dict) and "schedule" in triggers:
        if "concurrency" not in document:
            findings.append("scheduled workflow missing concurrency")
    return findings


def collect(directory: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Return checked files and findings, never touching CI."""
    checked: list[str] = []
    findings: dict[str, list[str]] = {}
    patterns = ("*.yml", "*.yaml")
    for pattern in patterns:
        for path in sorted(directory.glob(pattern)):
            checked.append(path.name)
            if path.name in ALLOWLIST:
                continue
            issues = scan(path)
            if issues:
                findings[path.name] = issues
    return sorted(checked), findings


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    checked, findings = collect(ROOT / args.workflows_dir)
    verdict = "FAIL" if findings else "PASS"
    details: dict[str, Any] = {
        "schema_version": "workflow-timeout-report/v1",
        "verdict": verdict,
        "exit_code": 1 if findings else 0,
        "checked": checked,
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
                for issue in issues:
                    print(f"FAIL {name}: {issue}", file=sys.stderr)
        else:
            print("ok: workflow timeouts and concurrency (ci.yml allowlisted)")
    return int(details["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check that DEVOPS-STATUS header matches the current branch.

Read-only and report-only. Does not edit documentation or CI.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BRANCH_RE = re.compile(r"Ветка:\*{0,2}\s*`([^`]+)`")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-file",
        default="docs/DEVOPS-STATUS.md",
        help="path to the status document",
    )
    parser.add_argument("--branch", help="override current git branch")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser.parse_args(argv)


def current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def evaluate(args: argparse.Namespace) -> tuple[int, str, dict[str, Any]]:
    path = Path(args.status_file)
    if not path.is_file():
        return 1, "FAIL: status file missing", {"verdict": "FAIL", "reasons": ["status file missing"]}
    match = BRANCH_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return 1, "FAIL: branch header missing", {"verdict": "FAIL", "reasons": ["branch header missing"]}
    documented = match.group(1).strip()
    actual = args.branch or current_branch()
    reasons: list[str] = []
    verdict = "PASS" if documented == actual else "NO-GO"
    if verdict != "PASS":
        reasons.append(f"status branch {documented!r} != current branch {actual!r}")
    details: dict[str, Any] = {
        "verdict": verdict,
        "status_branch": documented,
        "current_branch": actual,
        "reasons": reasons,
        "does_not_prove": ["deployment readiness", "DNS cutover", "runtime availability"],
    }
    return (0 if verdict == "PASS" else 3), f"{verdict}: status branch={documented}", details


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        code, summary, details = evaluate(args)
    except (OSError, subprocess.CalledProcessError) as error:
        details = {"verdict": "FAIL", "reasons": [str(error)]}
        print(details if args.json else f"FAIL: {error}", file=sys.stderr)
        return 1
    details["exit_code"] = code
    if args.json:
        import json

        print(json.dumps(details, ensure_ascii=False, sort_keys=True))
    else:
        print(summary, file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())

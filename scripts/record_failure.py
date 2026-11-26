#!/usr/bin/env python3
"""Append a failure event to a local append-only JSONL journal."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL = Path("deploy/reports/failures.jsonl")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drill_id", help="stable drill or check identifier")
    parser.add_argument("reason", help="short human-readable failure reason")
    parser.add_argument("--evidence", default="", help="optional evidence reference")
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--now", help="UTC timestamp override for tests")
    return parser.parse_args(argv)


def utc_now(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        generated_at = utc_now(args.now)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    event: dict[str, Any] = {
        "schema_version": "failure-journal/v1",
        "generated_at": generated_at,
        "drill_id": args.drill_id,
        "reason": args.reason,
        "evidence": args.evidence,
        "mode": "report-only",
        "does_not_prove": ["runtime availability", "DNS cutover", "database state"],
    }
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.journal.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as error:
        print(f"FAIL: cannot append journal: {error}", file=sys.stderr)
        return 1
    print(json.dumps(event, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

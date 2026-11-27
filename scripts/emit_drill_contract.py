#!/usr/bin/env python3
"""Emit an additive machine-readable drill contract in UTC.

The emitter never edits existing scripts and never touches CI. It only writes
a standalone JSON document that can be validated by
``scripts/verify_drill_contract.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sha256_util import normalize_sha256

SCHEMA_VERSION = "drill-contract/v1"
STATUSES = {"PASS", "SKIP", "FAIL"}
SKIP_REASONS = {
    "not_applicable",
    "blocked",
    "not_run",
    "missing_tool",
    "missing_secret",
}
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drill_id", help="stable identifier of the drill")
    parser.add_argument(
        "--artifact-sha256",
        default=os.environ.get("SREDA_ARTIFACT_SHA256", ""),
        help="canonical digest of the artifact under test",
    )
    parser.add_argument(
        "--checks",
        required=True,
        type=Path,
        help="JSON file with a list of check objects",
    )
    parser.add_argument(
        "--required-check",
        action="append",
        default=[],
        dest="required_checks",
        help="check id that must not be SKIP (repeatable)",
    )
    parser.add_argument("--commit", help="defaults to current git HEAD")
    parser.add_argument(
        "--mode",
        default="drill",
        help="drill|dry-run|standby|active|real|static|simulated|skipped",
    )
    parser.add_argument("--generator", default="emit_drill_contract.py")
    parser.add_argument(
        "--prev-contract-sha256",
        help="canonical SHA-256 of the previous contract (optional chain)",
    )
    parser.add_argument("--target", help="logical target, not a real address")
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    parser.add_argument(
        "--now",
        help="override generated_at for deterministic tests (UTC Z)",
    )
    parser.add_argument(
        "--out",
        default="-",
        help="output path; '-' writes to stdout",
    )
    return parser.parse_args(argv)


def utc_now(value: str | None) -> datetime:
    """Return a timezone-aware UTC timestamp."""
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def current_commit() -> str:
    """Return the current git commit used as the source of truth."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def normalize_checks(raw: Any) -> list[dict[str, Any]]:
    """Normalize and sanity-check the user-provided check list."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("--checks must contain a non-empty JSON list")
    checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"check #{index} must be an object")
        name = item.get("id")
        status = item.get("status")
        if not isinstance(name, str) or not name:
            raise ValueError(f"check #{index} has no id")
        if name in seen:
            raise ValueError(f"duplicate check id: {name}")
        if status not in STATUSES:
            raise ValueError(f"check {name}: bad status {status!r}")
        proves = item.get("proves", [])
        does_not_prove = item.get("does_not_prove", [])
        if not isinstance(proves, list) or not isinstance(does_not_prove, list):
            raise ValueError(f"check {name}: proves/does_not_prove must be lists")
        skip_reason = item.get("skip_reason")
        if skip_reason is not None and skip_reason not in SKIP_REASONS:
            raise ValueError(f"check {name}: bad skip_reason {skip_reason!r}")
        normalized: dict[str, Any] = {
            "id": name,
            "status": status,
            "proves": proves,
            "does_not_prove": does_not_prove,
        }
        if skip_reason is not None:
            normalized["skip_reason"] = skip_reason
        if "evidence" in item:
            normalized["evidence"] = item["evidence"]
        checks.append(normalized)
        seen.add(name)
    return checks


def build_contract(args: argparse.Namespace) -> dict[str, Any]:
    """Build the contract dictionary from validated inputs."""
    artifact = normalize_sha256(args.artifact_sha256)
    commit = args.commit or current_commit()
    if not COMMIT.fullmatch(commit):
        raise ValueError("commit must be 7-40 lowercase hex chars")
    if args.ttl_seconds <= 0:
        raise ValueError("--ttl-seconds must be positive")
    previous = args.prev_contract_sha256
    if previous is not None:
        previous = normalize_sha256(previous)
    raw = json.loads(args.checks.read_text(encoding="utf-8"))
    checks = normalize_checks(raw)
    required = args.required_checks or [check["id"] for check in checks]
    unknown = set(required) - {check["id"] for check in checks}
    if unknown:
        raise ValueError("unknown required check(s): " + ", ".join(sorted(unknown)))
    generated = utc_now(args.now)
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generator": args.generator,
        "generated_at": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_until": (generated + timedelta(seconds=args.ttl_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "mode": args.mode,
        "commit": commit,
        "artifact_sha256": artifact,
        "checks": checks,
    }
    if previous is not None:
        contract["prev_contract_sha256"] = previous
    if args.target:
        contract["target"] = args.target
    contract["required_checks"] = required
    return contract


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    try:
        contract = build_contract(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    payload = json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out == "-":
        sys.stdout.write(payload)
    else:
        Path(args.out).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

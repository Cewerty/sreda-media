#!/usr/bin/env python3
"""Validate a machine-readable drill contract without external packages.

Exit codes: 0 = PASS, 3 = NO-GO (inconclusive/expired), 1 = FAIL (malformed
contract or a failing check). ``SKIP`` is never converted to ``PASS``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "drill-contract/v1"
STATUSES = {"PASS", "SKIP", "FAIL"}
SKIP_REASONS = {
    "not_applicable",
    "blocked",
    "not_run",
    "missing_tool",
    "missing_secret",
}
AUTHORITATIVE_MODES = {"active", "real"}
MODES = {
    "drill",
    "dry-run",
    "standby",
    "active",
    "real",
    "static",
    "simulated",
    "skipped",
}
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="contract JSON or '-'")
    parser.add_argument("--at", help="evaluate TTL at this UTC timestamp")
    parser.add_argument(
        "--allow-other-commit",
        action="store_true",
        help="do not require the contract commit to equal current HEAD",
    )
    parser.add_argument(
        "--allow-informational-skip",
        action="store_true",
        help="accept required SKIP only in non-authoritative modes",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat every mode as authoritative; never accept required SKIP",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable verdict instead of a summary line",
    )
    parser.add_argument(
        "--expect-mode",
        choices=sorted(MODES),
        help="NO-GO when the contract mode differs (blocks drill-to-real replay)",
    )
    parser.add_argument(
        "--prev-contract",
        help="verify prev_contract_sha256 against this previous contract file",
    )
    return parser.parse_args(argv)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp ending in Z."""
    if not TIMESTAMP.fullmatch(value):
        raise ValueError(f"timestamp must be UTC ISO-8601 with Z: {value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def git_head() -> str | None:
    """Return current git HEAD when available."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def load_contract(path: str) -> dict[str, Any]:
    """Load the contract from a file or stdin."""
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("contract must be a JSON object")
    return data


def require_string(data: dict[str, Any], key: str) -> str:
    """Return a required non-empty string field."""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def canonical_sha256(data: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 of a JSON object."""
    payload = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_shape(contract: dict[str, Any]) -> None:
    """Validate the minimal shape of the contract."""
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version must be 'drill-contract/v1'")
    for key in (
        "generator",
        "generated_at",
        "ttl_until",
        "mode",
        "commit",
        "artifact_sha256",
    ):
        require_string(contract, key)
    if contract["mode"] not in MODES:
        raise ValueError(f"unknown mode: {contract['mode']!r}")
    if not COMMIT.fullmatch(contract["commit"]):
        raise ValueError("commit must be 7-40 lowercase hex chars")
    if not SHA256.fullmatch(contract["artifact_sha256"]):
        raise ValueError("artifact_sha256 must be 64 lowercase hex chars")
    generated = parse_timestamp(contract["generated_at"])
    expires = parse_timestamp(contract["ttl_until"])
    if expires <= generated:
        raise ValueError("ttl_until must be later than generated_at")
    if "checks" not in contract or not isinstance(contract["checks"], list):
        raise ValueError("checks must be a non-empty list")
    if not contract["checks"]:
        raise ValueError("checks must be a non-empty list")
    if "required_checks" in contract:
        required = contract["required_checks"]
        if not isinstance(required, list) or not all(
            isinstance(item, str) and item for item in required
        ):
            raise ValueError("required_checks must be a list of strings")
    if "notes" in contract and not isinstance(contract["notes"], list):
        raise ValueError("notes must be a list")
    if "prev_contract_sha256" in contract:
        previous = contract["prev_contract_sha256"]
        if not isinstance(previous, str) or not SHA256.fullmatch(previous):
            raise ValueError("prev_contract_sha256 must be 64 lowercase hex chars")


def validate_checks(contract: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Validate checks and return (failing, required_skip, warnings)."""
    ids: set[str] = set()
    failing: list[str] = []
    required_skip: list[str] = []
    warnings: list[str] = []
    for index, check in enumerate(contract["checks"]):
        if not isinstance(check, dict):
            raise ValueError(f"check #{index} must be an object")
        name = require_string(check, "id")
        if name in ids:
            raise ValueError(f"duplicate check id: {name}")
        ids.add(name)
        status = check.get("status")
        if status not in STATUSES:
            raise ValueError(f"check {name}: bad status {status!r}")
        proves = check.get("proves")
        does_not_prove = check.get("does_not_prove")
        if not isinstance(proves, list) or not isinstance(does_not_prove, list):
            raise ValueError(f"check {name}: proves/does_not_prove must be lists")
        if not all(isinstance(item, str) and item for item in proves):
            raise ValueError(f"check {name}: proves items must be strings")
        if not all(isinstance(item, str) and item for item in does_not_prove):
            raise ValueError(f"check {name}: does_not_prove items must be strings")
        skip_reason = check.get("skip_reason")
        if skip_reason is not None and skip_reason not in SKIP_REASONS:
            raise ValueError(f"check {name}: bad skip_reason {skip_reason!r}")
        if status == "PASS" and not proves:
            raise ValueError(f"check {name}: PASS requires proves")
        if status == "SKIP":
            if not skip_reason:
                raise ValueError(f"check {name}: SKIP requires skip_reason")
            if proves:
                raise ValueError(f"check {name}: SKIP must not claim proves")
            if not does_not_prove:
                raise ValueError(f"check {name}: SKIP requires does_not_prove")
        if status == "FAIL" and not does_not_prove:
            raise ValueError(f"check {name}: FAIL requires does_not_prove")
        if status == "FAIL":
            failing.append(name)
    required = contract.get("required_checks") or sorted(ids)
    missing = set(required) - ids
    if missing:
        raise ValueError("required check(s) absent: " + ", ".join(sorted(missing)))
    for name in required:
        check = next(item for item in contract["checks"] if item["id"] == name)
        if check["status"] == "SKIP":
            required_skip.append(name)
        if check["status"] == "PASS" and not check.get("does_not_prove"):
            warnings.append(f"{name}: PASS has empty does_not_prove")
    return failing, required_skip, warnings


def decide(
    args: argparse.Namespace, contract: dict[str, Any]
) -> tuple[int, str, dict[str, Any]]:
    """Return exit code, summary line, and machine-readable details."""
    validate_shape(contract)
    failing, required_skip, warnings = validate_checks(contract)
    reasons: list[str] = []
    details: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": contract["mode"],
        "commit": contract["commit"],
        "artifact_sha256": contract["artifact_sha256"],
        "failing_checks": failing,
        "required_skips": required_skip,
        "warnings": list(warnings),
        "reasons": reasons,
    }

    def finish(code: int, verdict: str) -> tuple[int, str, dict[str, Any]]:
        details["exit_code"] = code
        details["verdict"] = verdict
        return code, f"{verdict}: " + "; ".join(reasons), details

    if failing:
        reasons.extend(failing)
        return finish(1, "FAIL")
    if args.expect_mode and contract["mode"] != args.expect_mode:
        reasons.append(f"mode {contract['mode']} != expected {args.expect_mode}")
        return finish(3, "NO-GO")
    if args.prev_contract:
        previous = load_contract(args.prev_contract)
        actual = canonical_sha256(previous)
        expected = contract.get("prev_contract_sha256")
        if expected is None:
            reasons.append("prev_contract_sha256 absent")
            return finish(3, "NO-GO")
        if expected != actual:
            reasons.append("prev_contract_sha256 mismatch")
            return finish(1, "FAIL")
    if not args.allow_other_commit:
        head = git_head()
        if head is None:
            reasons.append("cannot read current git commit")
            return finish(3, "NO-GO")
        if head != contract["commit"]:
            reasons.append(f"commit {contract['commit']} != HEAD {head}")
            return finish(3, "NO-GO")
    at_value = parse_timestamp(args.at) if args.at else datetime.now(timezone.utc)
    if at_value > parse_timestamp(contract["ttl_until"]):
        reasons.append("contract TTL expired")
        return finish(3, "NO-GO")
    if required_skip:
        informational = (
            args.allow_informational_skip
            and not args.strict
            and contract["mode"] not in AUTHORITATIVE_MODES
        )
        if informational:
            reasons.append("informational SKIP accepted: " + ", ".join(required_skip))
        else:
            reasons.append("required SKIP: " + ", ".join(required_skip))
            return finish(3, "NO-GO")
    reasons.extend(warnings)
    if not reasons:
        reasons.append("all required checks PASS")
    return finish(0, "PASS")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    try:
        contract = load_contract(args.path)
        code, summary, details = decide(args, contract)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "verdict": "FAIL",
                        "exit_code": 1,
                        "reasons": [str(error)],
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(details, sort_keys=True))
    else:
        print(summary)
    return code


if __name__ == "__main__":
    sys.exit(main())

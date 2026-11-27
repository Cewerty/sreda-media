#!/usr/bin/env python3
"""Compare served response bytes with an expected SHA-256 digest.

This is a read-only, report-only check. It never deploys, never writes to the
repository and never treats HTTP headers, gzip or chunking as evidence: the
body is decoded by urllib and hashed as raw bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from sha256_util import normalize_sha256

TIMEOUT_SECONDS = 5


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="single URL to fetch")
    parser.add_argument(
        "--expected-sha256", help="expected SHA-256 of the response body"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="JSON mapping of relative path to expected SHA-256",
    )
    parser.add_argument("--base-url", help="base URL used with --manifest")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    return parser.parse_args(argv)


def fetch_sha256(url: str, timeout: int) -> str:
    """Fetch one URL and return the SHA-256 of the decoded response body."""
    request = urllib.request.Request(
        url,
        headers={"Accept-Encoding": "identity", "User-Agent": "sreda-bytes-check/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return hashlib.sha256(body).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """Build a machine-readable report without touching the repository."""
    entries: list[dict[str, Any]] = []
    if args.manifest:
        if not args.base_url:
            raise ValueError("--base-url is required with --manifest")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("--manifest must be a JSON object")
        if not manifest:
            raise ValueError("manifest is empty")
        for relpath, expected in sorted(manifest.items()):
            url = args.base_url.rstrip("/") + "/" + str(relpath).lstrip("/")
            expected_digest = normalize_sha256(str(expected))
            error_message: str | None = None
            try:
                actual = fetch_sha256(url, args.timeout)
                status = "PASS" if actual == expected_digest else "FAIL"
            except Exception as error:  # noqa: BLE001 - report-only diagnostic
                actual = None
                status = "FAIL"
                error_message = str(error)
            entries.append(
                {
                    "path": str(relpath),
                    "url": url,
                    "expected_sha256": expected_digest,
                    "actual_sha256": actual,
                    "status": status,
                    "error": error_message,
                }
            )
    else:
        if not args.url or not args.expected_sha256:
            raise ValueError("--url and --expected-sha256 are required")
        expected_digest = normalize_sha256(args.expected_sha256)
        error_message: str | None = None
        try:
            actual = fetch_sha256(args.url, args.timeout)
            status = "PASS" if actual == expected_digest else "FAIL"
        except Exception as error:  # noqa: BLE001 - report-only diagnostic
            actual = None
            status = "FAIL"
            error_message = str(error)
        entries.append(
            {
                "url": args.url,
                "expected_sha256": expected_digest,
                "actual_sha256": actual,
                "status": status,
                "error": error_message,
            }
        )
    if not entries:
        raise ValueError("manifest is empty")
    verdict = (
        "PASS"
        if all(item["status"] == "PASS" for item in entries)
        else "FAIL"
    )
    return {
        "schema_version": "served-bytes/v1",
        "verdict": verdict,
        "exit_code": 0 if verdict == "PASS" else 1,
        "checks": entries,
        "proves": ["response body sha256"] if verdict == "PASS" else [],
        "does_not_prove": [
            "TLS identity",
            "DNS cutover",
            "database consistency",
            "runtime availability",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point: 0 PASS, 1 FAIL."""
    args = parse_args(argv)
    try:
        report = build_report(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "schema_version": "served-bytes/v1",
            "verdict": "FAIL",
            "exit_code": 1,
            "checks": [],
            "proves": [],
            "does_not_prove": ["all checks"],
            "error": str(error),
        }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{report['verdict']}: {len(report['checks'])} served-byte check(s)")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Read-only validation of DRAFT replica topology templates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    Path("deploy/host/replica.template.yaml"),
    Path("deploy/host/Caddyfile.replica.template"),
    Path("deploy/uptime-kuma/allowlist.yaml"),
)
PLACEHOLDER = re.compile(r"\{\$SREDA_[A-Z0-9_]+\}")
REAL_HOST = re.compile(r"(?:https?://)(?!example\.invalid)[^\s}\]]+")
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def monitor_errors(text: str) -> list[str]:
    """Return errors for any monitor block that is not explicitly disabled."""
    errors: list[str] = []
    blocks = re.split(r"(?m)^\s*-\s+name:\s*", text)[1:]
    for block in blocks:
        name = block.splitlines()[0].strip() if block.splitlines() else "?"
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip().startswith("enable:")
        ]
        if not lines or not any(line == "enable: false" for line in lines):
            errors.append(f"monitor {name}: enable must be explicitly false")
    return errors


def validate() -> tuple[bool, list[str]]:
    """Validate that templates stay placeholder-only and not provisioned."""
    errors: list[str] = []
    for rel in FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "DRAFT" not in text or "NOT PROVISIONED" not in text:
            errors.append(f"{rel}: missing DRAFT/NOT PROVISIONED marker")
        if not PLACEHOLDER.search(text):
            errors.append(f"{rel}: no {{$SREDA_*}} placeholder")
        if REAL_HOST.search(text) or IP.search(text):
            errors.append(f"{rel}: real address found")
        if re.search(r"\bENABLE_[A-Z_]+\b", text):
            errors.append(f"{rel}: ENABLE_* flag found")
        if "reverse_proxy {$SREDA_API_UPSTREAM}" in text and not any(
            line.strip().startswith("#")
            and "reverse_proxy {$SREDA_API_UPSTREAM}" in line
            for line in text.splitlines()
        ):
            errors.append(f"{rel}: active reverse_proxy before Q-1")
    allowlist = ROOT / FILES[2]
    if allowlist.is_file():
        errors.extend(
            monitor_errors(allowlist.read_text(encoding="utf-8"))
        )
    return not errors, errors


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    passed, errors = validate()
    result: dict[str, Any] = {
        "schema_version": "template-check/v1",
        "verdict": "PASS" if passed else "FAIL",
        "exit_code": 0 if passed else 1,
        "errors": errors,
        "does_not_prove": [
            "DNS cutover",
            "real provisioning",
            "database consistency",
            "runtime availability",
        ],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif passed:
        print("PASS: replica templates are DRAFT, placeholder-only, not enabled")
    else:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

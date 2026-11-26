#!/usr/bin/env python3
"""Synthetic restore rehearsal in a temporary directory; never touches a host."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_PATHS = ("/srv", "/etc", "/var/lib/postgresql")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", help="write the emitted contract to this path")
    return parser.parse_args(argv)


def guard(args: argparse.Namespace) -> list[str]:
    """Return hard-guard violations before any work is performed."""
    violations: list[str] = []
    for key, value in sorted(os.environ.items()):
        if key.startswith("ENABLE_") and value.lower() not in {"", "0", "false"}:
            violations.append(f"enabled flag: {key}")
    for value in os.environ.values():
        if any(marker in value for marker in FORBIDDEN_PATHS):
            violations.append("real host path present in environment")
            break
    return sorted(set(violations))


def synthetic_digest(root: Path) -> str:
    """Create a synthetic tree and return its canonical digest."""
    payload = root / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "b.txt").write_text("beta", encoding="utf-8")
    (payload / "a.txt").write_text("alpha", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "canonical_tree_digest.py"), str(payload)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def build_contract(root: Path, expected: str, ttl: int) -> dict[str, Any]:
    """Build a drill contract for the synthetic restore."""
    digest = synthetic_digest(root)
    matched = digest == expected
    checks = [
        {
            "id": "restored_tree_digest",
            "status": "PASS" if matched else "FAIL",
            "proves": ["synthetic tree digest matched"] if matched else [],
            "does_not_prove": []
            if matched
            else ["restored tree does not match the supplied digest"],
        },
        {
            "id": "age_decryption",
            "status": "SKIP",
            "proves": [],
            "does_not_prove": ["encrypted backup payload was not decrypted"],
            "skip_reason": "not_applicable",
        },
    ]
    checks_path = root / "checks.json"
    checks_path.write_text(json.dumps(checks), encoding="utf-8")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    emit = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "emit_drill_contract.py"),
            "restore-synthetic",
            "--artifact-sha256",
            expected,
            "--checks",
            str(checks_path),
            "--commit",
            commit,
            "--mode",
            "drill",
            "--ttl-seconds",
            str(ttl),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(emit.stdout)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    violations = guard(args)
    if violations:
        print("FAIL: " + "; ".join(violations), file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="sreda-restore-drill-") as tmp:
        contract = build_contract(Path(tmp), args.artifact_sha256, args.ttl_seconds)
    payload = json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    elif args.json:
        sys.stdout.write(payload)
    else:
        verdict = "PASS" if all(c["status"] != "FAIL" for c in contract["checks"]) else "FAIL"
        print(f"{verdict}: synthetic restore drill completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

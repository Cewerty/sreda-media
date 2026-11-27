#!/usr/bin/env python3
"""Read-only audit of backup sets; never deletes or restores anything."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "backup-audit/v1"
PROTECTED = {".last", ".last-good"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="backup root to inspect")
    parser.add_argument("--min-keep", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_set(path: Path) -> dict[str, Any]:
    """Verify one completed backup set using manifest and sidecar files."""
    checks: list[dict[str, Any]] = []
    manifest = path / "manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return {
                "status": "FAIL",
                "proves": [],
                "does_not_prove": [f"manifest unreadable: {error}"],
            }
        files = data.get("files", {}) if isinstance(data, dict) else {}
        if not files:
            checks.append(
                {
                    "id": "manifest:empty",
                    "status": "FAIL",
                    "proves": [],
                    "does_not_prove": ["no verified backup content"],
                }
            )
        for name, expected in sorted(files.items()):
            target = path / name
            if not target.is_file() or sha256_file(target) != expected:
                checks.append(
                    {
                        "id": f"sha:{name}",
                        "status": "FAIL",
                        "proves": [],
                        "does_not_prove": ["file content mismatch"],
                    }
                )
    for sidecar in sorted(path.glob("*.sha256")):
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            expected, _, name = line.partition("  ")
            target = path / name
            if not target.is_file() or sha256_file(target) != expected:
                checks.append(
                    {
                        "id": f"sidecar:{name}",
                        "status": "FAIL",
                        "proves": [],
                        "does_not_prove": ["sidecar digest mismatch"],
                    }
                )
    for archive in sorted(path.glob("*.gz")):
        result = subprocess.run(
            ["gzip", "-t", str(archive)], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            checks.append(
                {
                    "id": f"gzip:{archive.name}",
                    "status": "FAIL",
                    "proves": [],
                    "does_not_prove": ["archive integrity"],
                }
            )
    return {
        "status": "FAIL" if any(c["status"] == "FAIL" for c in checks) else "PASS",
        "proves": [f"verified {len(list(path.iterdir()))} entries"],
        "does_not_prove": [
            "age-encrypted payloads were not decrypted",
            "restore was not performed",
        ],
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    if not args.root.is_dir():
        print("FAIL: backup root does not exist", file=sys.stderr)
        return 1
    sets = [p for p in sorted(args.root.iterdir()) if p.is_dir()]
    completed = [p for p in sets if (p / "manifest.json").is_file() or list(p.glob("*.sha256"))]
    protected_missing = []
    if not any((args.root / name).exists() for name in PROTECTED):
        protected_missing = sorted(PROTECTED)
    reports = {p.name: verify_set(p) for p in completed}
    failing = [name for name, report in reports.items() if report["status"] == "FAIL"]
    reasons: list[str] = []
    if protected_missing:
        reasons.append("protected marker missing: " + ", ".join(protected_missing))
    if failing:
        reasons.append("failed sets: " + ", ".join(sorted(failing)))
    if len(completed) < args.min_keep:
        reasons.append(f"completed sets {len(completed)} < min-keep {args.min_keep}")
    verdict = "FAIL" if failing else "NO-GO" if reasons else "PASS"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "root": str(args.root),
        "verdict": verdict,
        "exit_code": 1 if failing else 3 if reasons else 0,
        "completed_sets": [p.name for p in completed],
        "protected_missing": protected_missing,
        "reasons": reasons,
        "does_not_prove": ["age encryption", "actual restore", "offsite copy"],
        "reports": reports,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{verdict}: {'; '.join(reasons) if reasons else 'backup audit clean'}")
    return int(payload["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

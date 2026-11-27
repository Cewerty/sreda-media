#!/usr/bin/env python3
"""Read-only guard for backup retention plans.

It never deletes anything. It checks that a retention plan keeps the protected
``.last`` set and enough verified sets to survive a bad run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--min-keep", type=int, default=2)
    parser.add_argument("--last-name", default=".last")
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="name that a retention job plans to remove (repeatable)",
    )
    return parser.parse_args(argv)


def completed_sets(backup_dir: Path) -> set[str]:
    """Return names that look like completed, verifiable backup sets."""
    names: set[str] = set()
    for child in backup_dir.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir() and (child / "manifest.json").is_file():
            names.add(child.name)
        elif child.is_file() and child.name.endswith(".sha256"):
            names.add(child.name[: -len(".sha256")])
    return names


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    backup_dir = args.backup_dir.resolve()
    if not backup_dir.is_dir():
        print(f"FAIL: not a directory: {backup_dir}", file=sys.stderr)
        return 1
    if args.min_keep < 1:
        print("FAIL: --min-keep must be >= 1", file=sys.stderr)
        return 1
    names = completed_sets(backup_dir)
    last = backup_dir / args.last_name
    last_target: str | None = None
    if last.exists() or last.is_symlink():
        last_target = last.resolve().name
    errors: list[str] = []
    if len(names) < args.min_keep:
        errors.append(
            f"only {len(names)} completed set(s); need >= {args.min_keep}"
        )
    if last_target is None:
        errors.append(f"protected set {args.last_name} missing")
    elif last_target not in names:
        errors.append(f"{args.last_name} points to an incomplete set: {last_target}")
    for candidate in args.candidate:
        if candidate == args.last_name or candidate == last_target:
            errors.append(f"retention plan would delete protected set: {candidate}")
    kept = names - set(args.candidate)
    if len(kept) < args.min_keep:
        errors.append(
            f"retention plan leaves {len(kept)} completed set(s); "
            f"need >= {args.min_keep}"
        )
    if errors:
        for message in errors:
            print(f"FAIL: {message}", file=sys.stderr)
        return 1
    print(f"PASS: retention plan keeps {len(kept)} set(s) and {args.last_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

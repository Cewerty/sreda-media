#!/usr/bin/env python3
"""Compare two local site trees with canonical digests (SIMULATED only)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIGEST = ROOT / "scripts" / "canonical_tree_digest.py"


def tree_digest(path: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(DIGEST), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=Path)
    parser.add_argument("standby", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    left, right = tree_digest(args.primary), tree_digest(args.standby)
    passed = left == right
    payload: dict[str, Any] = {
        "schema_version": "mirror-verify/v1",
        "mode": "SIMULATED",
        "verdict": "PASS" if passed else "FAIL",
        "exit_code": 0 if passed else 1,
        "primary_digest": left,
        "standby_digest": right,
        "does_not_prove": [
            "production DNS cutover",
            "database consistency",
            "TLS identity",
            "runtime availability",
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['verdict']}: {left} / {right}")
    return int(payload["exit_code"])


if __name__ == "__main__":
    sys.exit(main())

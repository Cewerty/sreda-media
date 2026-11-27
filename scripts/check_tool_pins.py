#!/usr/bin/env python3
"""Report-only pin audit for DevOps tools outside Ilya's CI zone.

Reads ``deploy/toolchain.json`` and scans ``justfile``, ``scripts/`` and
non-CI workflows. It never edits files and never changes a CI gate.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOOLCHAIN = ROOT / "deploy" / "toolchain.json"
SCAN_GLOBS = ("justfile", "scripts/*.py", "scripts/*.sh", ".github/workflows/*.yml")

UVX_FROM = re.compile(r"uvx\s+--from\s+([A-Za-z0-9_.-]+)(==[0-9A-Za-z_.-]+)?")
UNPINNED = (
    re.compile(
        r"go\s+install\s+(?!\S+@(?:v?\d[0-9A-Za-z.-]*|sha256:))\S+"
    ),
    re.compile(r"(?:uses:|image:)\s*\S+@v[0-9]"),
    re.compile(r"glitchtip/glitchtip:latest"),
)


def has_unpinned_uvx(line: str) -> bool:
    """Return True if any uvx --from invocation on the line lacks ==version."""
    return any(match.group(2) is None for match in UVX_FROM.finditer(line))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def scan_sources() -> dict[str, str]:
    """Return source texts that this audit is allowed to inspect."""
    sources: dict[str, str] = {}
    for pattern in SCAN_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.name == "ci.yml" or path.name == "check_tool_pins.py":
                continue
            if path.name.startswith("test_"):
                continue
            sources[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
    return sources


def check_pins(sources: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare expected pins and unpinned patterns against scanned sources."""
    expected: list[str] = manifest.get("expected_pins", [])
    allowed: list[str] = manifest.get("allow_with_warning", [])
    joined = "\n".join(sources.values())
    missing = [pin for pin in expected if pin not in joined]
    warnings: list[str] = []
    findings: list[str] = []
    for name, text in sources.items():
        for line_number, line in enumerate(text.splitlines(), start=1):
            if has_unpinned_uvx(line) or any(
                pattern.search(line) for pattern in UNPINNED
            ):
                marker = f"{name}:{line_number}: {line.strip()}"
                if any(item in line for item in allowed):
                    warnings.append(marker)
                else:
                    findings.append(marker)
    verdict = "FAIL" if missing or findings else "PASS"
    return {
        "verdict": verdict,
        "expected_pins": len(expected),
        "missing_pins": missing,
        "warnings": warnings,
        "findings": findings,
        "does_not_prove": [
            "correctness or freshness of pinned versions",
            "lockfiles and ci.yml (out of scope)",
        ],
    }


def main() -> int:
    """Entry point."""
    args = parse_args()
    manifest = json.loads(TOOLCHAIN.read_text(encoding="utf-8"))
    result = check_pins(scan_sources(), manifest)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"{result['verdict']}: pins={result['expected_pins']}")
        for item in result["missing_pins"]:
            print(f"  missing pin: {item}")
        for item in result["findings"]:
            print(f"  unpinned: {item}")
        for item in result["warnings"]:
            print(f"  warning (allowed): {item}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

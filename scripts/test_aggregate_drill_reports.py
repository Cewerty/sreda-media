#!/usr/bin/env python3
"""Tests for the report-only drill evidence aggregator."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 64
NOW = datetime.now(timezone.utc).replace(microsecond=0).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class AggregateDrillReportsTest(unittest.TestCase):
    """Exercise aggregation without touching CI or production."""

    def test_missing_reports_are_no_go(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "aggregate_drill_reports.py"),
                 "--reports-dir", tmp, "--json"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "NO-GO")

    def test_missing_dir_is_fail_without_allow_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "absent")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "aggregate_drill_reports.py"),
                 "--reports-dir", missing, "--json"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "FAIL")

    def test_missing_dir_is_skip_when_expected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "absent")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "aggregate_drill_reports.py"),
                 "--reports-dir", missing, "--allow-missing", "--summary"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("SKIP", result.stdout)
            self.assertIn("reports dir missing", result.stdout)

    def test_good_report_is_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            checks = reports / "checks.json"
            contract = reports / "drills"
            contract.mkdir()
            checks.write_text(json.dumps([{
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": ["runtime behaviour"],
            }]), encoding="utf-8")
            emit = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "emit_drill_contract.py"),
                 "unit", "--artifact-sha256", SHA, "--checks", str(checks),
                 "--commit", git_head(), "--now", NOW, "--ttl-seconds", "86400",
                 "--out", str(contract / "unit.json")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(emit.returncode, 0)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "aggregate_drill_reports.py"),
                 "--reports-dir", str(contract), "--json"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()

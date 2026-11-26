#!/usr/bin/env python3
"""Tests for the report-only workflow timeout checker."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_workflow_timeouts.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class WorkflowTimeoutTest(unittest.TestCase):
    def test_repository_workflows_are_reported_honestly(self) -> None:
        result = run("--json")
        self.assertEqual(result.returncode, 1)
        details = json.loads(result.stdout)
        self.assertIn("findings", details)
        self.assertNotIn("ci.yml", details["findings"])

    def test_missing_timeout_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "x.yml").write_text("name: x\njobs:\n  x:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
            result = run("--workflows-dir", str(directory), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing timeout-minutes", result.stdout)


if __name__ == "__main__":
    unittest.main()

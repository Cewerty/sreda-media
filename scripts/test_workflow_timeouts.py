#!/usr/bin/env python3
"""Fixture-based tests for the report-only workflow timeout checker."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the checker with the given arguments."""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_workflow_timeouts.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def check(text: str, name: str = "x.yml") -> tuple[int, dict[str, object], str]:
    """Check one inline workflow fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / name).write_text(text, encoding="utf-8")
        result = run("--workflows-dir", str(directory), "--json")
        return result.returncode, json.loads(result.stdout), result.stdout


class WorkflowTimeoutTest(unittest.TestCase):
    """Verify per-job findings rather than repository state."""

    def test_repository_report_is_valid_json(self) -> None:
        result = run("--json")
        details = json.loads(result.stdout)
        self.assertEqual(details["schema_version"], "workflow-timeout-report/v1")
        self.assertIn("ci.yml", details["checked"])
        self.assertNotIn("ci.yml", details["findings"])
        self.assertIn(result.returncode, (0, 1))

    def test_second_job_without_timeout_is_found(self) -> None:
        fixture = """\
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
  b:
    runs-on: ubuntu-latest
"""
        code, details, text = check(fixture)
        self.assertEqual(code, 1)
        self.assertTrue(any("job b" in item for item in details["findings"]["x.yml"]))
        self.assertIn("job b", text)

    def test_step_level_timeout_does_not_count(self) -> None:
        fixture = """\
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
        timeout-minutes: 5
"""
        code, details, _ = check(fixture)
        self.assertEqual(code, 1)
        self.assertTrue(
            any("job x" in item for item in details["findings"]["x.yml"])
        )

    def test_literal_in_run_block_does_not_count(self) -> None:
        fixture = """\
jobs:
  x:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: |
          echo 'timeout-minutes: 9'
"""
        code, _, _ = check(fixture)
        self.assertEqual(code, 0)

    def test_schedule_needs_concurrency(self) -> None:
        fixture = """\
on:
  schedule:
    - cron: '0 0 * * *'
jobs:
  x:
    runs-on: ubuntu-latest
    timeout-minutes: 5
"""
        code, details, _ = check(fixture)
        self.assertEqual(code, 1)
        self.assertTrue(
            any("concurrency" in item for item in details["findings"]["x.yml"])
        )

    def test_flow_style_concurrency_counts(self) -> None:
        fixture = """\
on:
  schedule:
    - cron: '0 0 * * *'
concurrency: {group: g}
jobs:
  x:
    runs-on: ubuntu-latest
    timeout-minutes: 5
"""
        code, _, _ = check(fixture)
        self.assertEqual(code, 0)

    def test_reusable_call_job_is_skipped(self) -> None:
        fixture = """\
jobs:
  call:
    uses: org/repo/.github/workflows/x.yml@v1
"""
        code, _, _ = check(fixture)
        self.assertEqual(code, 0)

    def test_broken_yaml_is_a_finding(self) -> None:
        code, details, _ = check("jobs: [unclosed\n")
        self.assertEqual(code, 1)
        self.assertTrue(any("unparseable" in item for item in details["findings"]["x.yml"]))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for the append-only failure journal."""

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
        [sys.executable, str(ROOT / "scripts" / "record_failure.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class FailureJournalTest(unittest.TestCase):
    def test_append_keeps_both_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "failures.jsonl"
            first = run("backup-drill", "expired", "--journal", str(journal), "--now", "2026-11-26T00:00:00Z")
            second = run("alert-drill", "blocked", "--journal", str(journal), "--now", "2026-11-26T01:00:00Z")
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            lines = journal.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["drill_id"], "backup-drill")
            self.assertEqual(json.loads(lines[1])["drill_id"], "alert-drill")


if __name__ == "__main__":
    unittest.main()

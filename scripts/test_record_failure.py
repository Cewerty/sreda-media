#!/usr/bin/env python3
"""Tests for the append-only failure journal."""

from __future__ import annotations

import importlib.util
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


    def test_append_without_fcntl_is_best_effort(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "record_failure", ROOT / "scripts" / "record_failure.py"
        )
        if spec is None or spec.loader is None:
            raise AssertionError("cannot load record_failure")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.fcntl = None
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "failures.jsonl"
            code = module.main(
                ["portable-drill", "no-lock", "--journal", str(journal)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(journal.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()

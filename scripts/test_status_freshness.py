#!/usr/bin/env python3
"""Tests for status-document freshness checker."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_status_freshness.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class StatusFreshnessTest(unittest.TestCase):
    def test_matching_branch_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("**Ветка:** `devops/test`\n", encoding="utf-8")
            result = run("--status-file", str(path), "--branch", "devops/test")
            self.assertEqual(result.returncode, 0)

    def test_stale_branch_is_no_go(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("**Ветка:** `old`\n", encoding="utf-8")
            result = run("--status-file", str(path), "--branch", "devops/test", "--json")
            self.assertEqual(result.returncode, 3)
            self.assertIn("NO-GO", result.stdout)

    def test_bold_header_is_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("> **Ветка:** `devops/test`\n", encoding="utf-8")
            result = run("--status-file", str(path), "--branch", "devops/test")
            self.assertEqual(result.returncode, 0)


    def test_plain_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("Ветка: `devops/test`\n", encoding="utf-8")
            result = run(
                "--status-file", str(path), "--branch", "devops/test", "--json"
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("branch header missing", result.stdout)

    def test_git_error_still_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATUS.md"
            path.write_text("**Ветка:** `devops/test`\n", encoding="utf-8")
            result = run("--status-file", str(path), "--json", cwd=Path(tmp))
            self.assertEqual(result.returncode, 1)
            import json

            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "FAIL")
            self.assertEqual(payload["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()

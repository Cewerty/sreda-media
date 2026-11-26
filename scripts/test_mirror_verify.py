#!/usr/bin/env python3
"""Tests for local mirror equality verification."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "mirror_verify.py"


def run(primary: Path, standby: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(primary), str(standby), "--json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


class MirrorVerifyTest(unittest.TestCase):
    def test_equal_trees_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "a", root / "b"
            a.mkdir(); b.mkdir()
            (a / "index.html").write_text("ok", encoding="utf-8")
            (b / "index.html").write_text("ok", encoding="utf-8")
            result = run(a, b)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")

    def test_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "a", root / "b"
            a.mkdir(); b.mkdir()
            (a / "index.html").write_text("ok", encoding="utf-8")
            (b / "index.html").write_text("drift", encoding="utf-8")
            result = run(a, b)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()

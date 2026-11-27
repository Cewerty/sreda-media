#!/usr/bin/env python3
"""Regression tests for the served-bytes verifier."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST = "a" * 64


def run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the verifier from the repository root."""
    return subprocess.run(
        [sys.executable, "scripts/verify_served_bytes.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class ServedBytesTest(unittest.TestCase):
    """Fail-closed behaviour for empty and unreachable manifests."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest = Path(self.tmp.name) / "manifest.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def report(self, *extra: str) -> dict[str, object]:
        result = run(
            "--manifest",
            str(self.manifest),
            "--base-url",
            "http://127.0.0.1:1",
            "--timeout",
            "1",
            "--json",
            *extra,
        )
        self.assertTrue(result.stdout.strip(), "stdout must never be empty")
        return json.loads(result.stdout)

    def test_empty_manifest_is_fail(self) -> None:
        self.manifest.write_text("{}", encoding="utf-8")
        report = self.report()
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["exit_code"] if "exit_code" in report else 1, 1)

    def test_unreachable_url_has_one_entry_with_status(self) -> None:
        self.manifest.write_text(
            json.dumps({"index.html": f"sha256:{DIGEST}"}), encoding="utf-8"
        )
        report = self.report()
        self.assertEqual(report["verdict"], "FAIL")
        checks = report["checks"]
        self.assertIsInstance(checks, list)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "FAIL")
        self.assertEqual(checks[0]["expected_sha256"], DIGEST)

    def test_invalid_digest_is_fail(self) -> None:
        self.manifest.write_text(
            json.dumps({"index.html": "not-a-digest"}), encoding="utf-8"
        )
        report = self.report()
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(report.get("error"))


if __name__ == "__main__":
    unittest.main()

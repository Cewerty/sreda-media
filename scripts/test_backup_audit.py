#!/usr/bin/env python3
"""Tests for the read-only backup audit and synthetic restore drill."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 64


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a repository script."""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def synthetic_digest() -> str:
    """Compute the digest of the tree the drill synthesizes."""
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "payload"
        payload.mkdir()
        (payload / "b.txt").write_text("beta", encoding="utf-8")
        (payload / "a.txt").write_text("alpha", encoding="utf-8")
        return run("canonical_tree_digest.py", str(payload)).stdout.strip()


class BackupAuditTest(unittest.TestCase):
    """Tests for audit_backups.py and restore_drill.py."""

    def test_valid_sets_require_protected_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("2026-11-25", "2026-11-26"):
                child = root / name
                child.mkdir()
                payload = child / "blob.txt"
                payload.write_text("data", encoding="utf-8")
                (child / "manifest.json").write_text(
                    json.dumps(
                        {"files": {"blob.txt": hashlib.sha256(b"data").hexdigest()}}
                    ),
                    encoding="utf-8",
                )
            (root / ".last").symlink_to(root / "2026-11-26")
            good = run("audit_backups.py", str(root), "--json")
            self.assertEqual(good.returncode, 0)
            (root / ".last").unlink()
            bad = run("audit_backups.py", str(root), "--json")
            self.assertEqual(bad.returncode, 3)
            self.assertIn("protected marker missing", bad.stdout)

    def test_corrupt_sidecar_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "2026-11-26"
            child.mkdir()
            (child / "blob.txt").write_text("data", encoding="utf-8")
            (child / "blob.txt.sha256").write_text(
                "0" * 64 + "  blob.txt\n", encoding="utf-8"
            )
            (root / ".last").symlink_to(child)
            result = run("audit_backups.py", str(root), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL", result.stdout)

    def test_restore_drill_emits_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "contract.json"
            result = run(
                "restore_drill.py",
                "--artifact-sha256",
                synthetic_digest(),
                "--out",
                str(out),
            )
            self.assertEqual(result.returncode, 0)
            contract = json.loads(out.read_text(encoding="utf-8"))
            statuses = {c["status"] for c in contract["checks"]}
            self.assertIn("SKIP", statuses)


    def test_empty_manifest_is_not_a_valid_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "2026-11-26"
            child.mkdir()
            (child / "manifest.json").write_text("{}", encoding="utf-8")
            (root / ".last").symlink_to(child)
            result = run("audit_backups.py", str(root), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("manifest:empty", result.stdout)

    def test_restore_drill_exit_follows_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = run(
                "restore_drill.py", "--artifact-sha256", synthetic_digest()
            )
            self.assertEqual(good.returncode, 0)
            bad = run(
                "restore_drill.py",
                "--artifact-sha256",
                "0" * 64,
                "--json",
            )
            self.assertEqual(bad.returncode, 1)
            self.assertIn("FAIL", bad.stdout)


if __name__ == "__main__":
    unittest.main()

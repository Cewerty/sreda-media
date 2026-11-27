#!/usr/bin/env python3
"""Self-contained tests for the additive drill-evidence layer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 64
NOW = datetime.now(timezone.utc).replace(microsecond=0).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def git_head() -> str:
    """Return the repository HEAD used by contract tests."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a repository script with an explicit working directory."""
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class DrillContractTest(unittest.TestCase):
    """Tests for emit/verify drill contract scripts."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.checks = self.dir / "checks.json"
        self.contract = self.dir / "contract.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_checks(self, *checks: dict[str, object]) -> None:
        self.checks.write_text(json.dumps(list(checks)), encoding="utf-8")

    def emit(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run(
            "emit_drill_contract.py",
            "unit",
            "--artifact-sha256",
            SHA,
            "--checks",
            str(self.checks),
            "--now",
            NOW,
            "--ttl-seconds",
            "86400",
            "--out",
            str(self.contract),
            *extra,
        )

    def verify(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return run("verify_drill_contract.py", str(self.contract), *extra)

    def test_pass_and_skip_are_distinct(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": ["runtime behaviour"],
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        self.assertEqual(self.verify().returncode, 0)
        self.write_checks(
            {
                "id": "artifact",
                "status": "SKIP",
                "proves": [],
                "does_not_prove": ["digest was not checked"],
                "skip_reason": "not_run",
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        denied = self.verify()
        self.assertEqual(denied.returncode, 3)
        self.assertIn("required SKIP", denied.stdout)
        allowed = self.verify("--allow-informational-skip")
        self.assertEqual(allowed.returncode, 0)
        self.assertIn("informational SKIP", allowed.stdout)

    def test_expired_contract_is_not_evidence(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": [],
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        later = (
            datetime.fromisoformat(NOW.replace("Z", "+00:00")) + timedelta(hours=25)
        )
        result = self.verify("--at", later.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(result.returncode, 3)
        self.assertIn("TTL expired", result.stdout)

    def test_foreign_commit_and_failed_check(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": [],
            }
        )
        self.assertEqual(self.emit("--commit", "b" * 40).returncode, 0)
        self.assertEqual(self.verify().returncode, 3)
        self.write_checks(
            {
                "id": "artifact",
                "status": "FAIL",
                "proves": [],
                "does_not_prove": ["artifact is not equal"],
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        self.assertEqual(self.verify().returncode, 1)

    def test_missing_signature_is_honest_skip(self) -> None:
        self.write_checks(
            {
                "id": "signature",
                "status": "SKIP",
                "proves": [],
                "does_not_prove": ["authenticity/signature not verified"],
                "skip_reason": "missing_tool",
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        contract = json.loads(self.contract.read_text(encoding="utf-8"))
        self.assertNotIn("cosign_verified", contract)
        self.assertEqual(self.verify().returncode, 3)
        self.assertEqual(self.verify("--allow-informational-skip").returncode, 0)

    def test_strict_and_json_verdict(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "SKIP",
                "proves": [],
                "does_not_prove": ["digest was not checked"],
                "skip_reason": "not_run",
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        strict = self.verify("--strict", "--allow-informational-skip")
        self.assertEqual(strict.returncode, 3)
        payload = json.loads(self.verify("--json").stdout)
        self.assertEqual(payload["verdict"], "NO-GO")
        self.assertEqual(payload["exit_code"], 3)

    def test_expect_mode_blocks_replay(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": [],
            }
        )
        self.assertEqual(
            self.emit("--commit", git_head(), "--mode", "drill").returncode, 0
        )
        self.assertEqual(self.verify("--expect-mode", "real").returncode, 3)
        self.assertEqual(self.verify("--expect-mode", "drill").returncode, 0)

    def test_prev_contract_chain(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest matched"],
                "does_not_prove": [],
            }
        )
        self.assertEqual(self.emit("--commit", git_head()).returncode, 0)
        previous = self.dir / "prev.json"
        previous.write_text(self.contract.read_text(encoding="utf-8"), encoding="utf-8")
        digest = hashlib.sha256(
            json.dumps(
                json.loads(previous.read_text(encoding="utf-8")),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        self.contract.unlink()
        self.assertEqual(
            self.emit(
                "--commit", git_head(), "--prev-contract-sha256", digest
            ).returncode,
            0,
        )
        self.assertEqual(self.verify("--prev-contract", str(previous)).returncode, 0)
        data = json.loads(self.contract.read_text(encoding="utf-8"))
        data["prev_contract_sha256"] = "0" * 64
        self.contract.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.verify("--prev-contract", str(previous)).returncode, 1)


    def test_empty_contract_is_fail(self) -> None:
        """An empty object is missing evidence, not a passing contract."""
        self.contract.write_text("{}", encoding="utf-8")
        result = self.verify("--json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["verdict"], "FAIL")

    def test_prefixed_contract_digest_is_normalized(self) -> None:
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest"],
                "does_not_prove": [],
            }
        )
        self.assertEqual(self.emit().returncode, 0)
        data = json.loads(self.contract.read_text(encoding="utf-8"))
        data["artifact_sha256"] = f"sha256:{SHA}"
        self.contract.write_text(json.dumps(data), encoding="utf-8")
        result = self.verify("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["artifact_sha256"], SHA)

    def test_sha256_prefix_is_normalized(self) -> None:
        """Digest output from canonical_tree_digest can be piped in directly."""
        self.write_checks(
            {
                "id": "artifact",
                "status": "PASS",
                "proves": ["digest"],
                "does_not_prove": [],
            }
        )
        result = run(
            "emit_drill_contract.py",
            "unit",
            "--artifact-sha256",
            f"sha256:{SHA}",
            "--checks",
            str(self.checks),
            "--now",
            NOW,
            "--ttl-seconds",
            "86400",
            "--out",
            str(self.contract),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.contract.read_text(encoding="utf-8"))
        self.assertEqual(data["artifact_sha256"], SHA)
        self.assertEqual(self.verify().returncode, 0)


class SupportScriptTest(unittest.TestCase):
    """Tests for canonical digest and retention guard."""

    def test_canonical_digest_ignores_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            first = run("canonical_tree_digest.py", str(root)).stdout.strip()
            os.utime(root / "a.txt", (100, 100))
            second = run("canonical_tree_digest.py", str(root)).stdout.strip()
            self.assertEqual(first, second)
            (root / "a.txt").write_text("changed", encoding="utf-8")
            third = run("canonical_tree_digest.py", str(root)).stdout.strip()
            self.assertNotEqual(first, third)

    def test_retention_guard_protects_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("2026-11-25", "2026-11-26"):
                child = root / name
                child.mkdir()
                (child / "manifest.json").write_text("{}", encoding="utf-8")
            (root / ".last").symlink_to(root / "2026-11-26")
            self.assertEqual(run("retention_guard.py", str(root)).returncode, 0)
            denied = run(
                "retention_guard.py",
                str(root),
                "--candidate",
                ".last",
            )
            self.assertEqual(denied.returncode, 1)


if __name__ == "__main__":
    unittest.main()

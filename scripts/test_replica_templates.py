#!/usr/bin/env python3
"""Tests for the read-only replica template validator."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_replica_templates.py"


def load_module():
    """Load the validator module from its file path."""
    spec = importlib.util.spec_from_file_location("check_replica_templates", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReplicaTemplateTest(unittest.TestCase):
    """Tests for DRAFT topology guardrails."""

    def test_repository_templates_pass(self) -> None:
        module = load_module()
        passed, errors = module.validate()
        self.assertTrue(passed, errors)

    def test_real_address_is_rejected(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in module.FILES:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "DRAFT NOT PROVISIONED {$SREDA_SITE_HOST}\n",
                    encoding="utf-8",
                )
            bad = root / module.FILES[0]
            bad.write_text(
                "DRAFT NOT PROVISIONED {$SREDA_SITE_HOST}\nhttps://real.example\n",
                encoding="utf-8",
            )
            old_root = module.ROOT
            module.ROOT = root
            try:
                passed, errors = module.validate()
            finally:
                module.ROOT = old_root
            self.assertFalse(passed)
            self.assertTrue(any("real address" in error for error in errors))


    def test_every_monitor_must_be_disabled(self) -> None:
        module = load_module()
        fixture = """
monitors:
  - name: first
    enable: false
  - name: second
    enable: true
"""
        errors = module.monitor_errors(fixture)
        self.assertTrue(any("second" in error for error in errors))
        self.assertEqual(module.monitor_errors("monitors:\n  - name: a\n    enable: false\n"), [])


if __name__ == "__main__":
    unittest.main()

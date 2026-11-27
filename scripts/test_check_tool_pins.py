#!/usr/bin/env python3
"""Regression tests for the toolchain pin auditor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_tool_pins import check_pins  # noqa: E402


class PinAuditTest(unittest.TestCase):
    """Verify per-invocation pin detection."""

    def test_second_unpinned_invocation_on_same_line_is_found(self) -> None:
        sources = {
            "justfile": (
                "uvx --from mkdocs-material==9.8.2 mkdocs build && "
                "uvx --from rust-just just"
            )
        }
        result = check_pins(sources, {"expected_pins": [], "allow_with_warning": []})
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("rust-just" in item for item in result["findings"]))

    def test_go_install_without_version_is_found(self) -> None:
        sources = {"scripts/workflows_lint.sh": "go install example.com/tool"}
        result = check_pins(sources, {"expected_pins": [], "allow_with_warning": []})
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("go install" in item for item in result["findings"]))

    def test_pinned_invocations_pass(self) -> None:
        sources = {
            "justfile": (
                "uvx --from mkdocs-material==9.8.2 mkdocs build && "
                "uvx --from rust-just==1.59.0 just\n"
                "go install example.com/tool@v1.2.3"
            )
        }
        result = check_pins(sources, {"expected_pins": [], "allow_with_warning": []})
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["findings"], [])


if __name__ == "__main__":
    unittest.main()

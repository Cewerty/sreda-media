#!/usr/bin/env python3
"""Regression tests for resource budget comparison directions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resource_gate import evaluate  # noqa: E402


def budget(measurements: dict[str, float]) -> dict[str, object]:
    return {
        "schema_version": "resource-budget/v1",
        "owner": "Cewerty",
        "approved": True,
        "limits": {
            "cpu_idle_percent": 20,
            "ram_idle_mb": 512,
            "disk_free_gb": 10,
            "egress_mbps": 10,
            "restore_minutes": 15,
        },
        "measurements": measurements,
    }


GOOD = {
    "cpu_idle_percent": 40,
    "ram_idle_mb": 1024,
    "disk_free_gb": 30,
    "egress_mbps": 5,
    "restore_minutes": 8,
}


class ResourceGateTest(unittest.TestCase):
    """Verify minimum floors and maximum ceilings."""

    def test_good_measurements_pass(self) -> None:
        result = evaluate(budget(dict(GOOD)))
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["exit_code"], 0)

    def test_low_free_ram_fails(self) -> None:
        data = dict(GOOD)
        data["ram_idle_mb"] = 100
        result = evaluate(budget(data))
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("ram_idle_mb" in b for b in result["breaches"]))

    def test_low_free_disk_fails(self) -> None:
        data = dict(GOOD)
        data["disk_free_gb"] = 2
        result = evaluate(budget(data))
        self.assertEqual(result["verdict"], "FAIL")

    def test_high_restore_time_fails(self) -> None:
        data = dict(GOOD)
        data["restore_minutes"] = 40
        result = evaluate(budget(data))
        self.assertEqual(result["verdict"], "FAIL")
        self.assertTrue(any("restore_minutes" in b for b in result["breaches"]))

    def test_unapproved_budget_is_no_go(self) -> None:
        data = budget(dict(GOOD))
        data["approved"] = False
        result = evaluate(data)
        self.assertEqual(result["verdict"], "NO-GO")
        self.assertEqual(result["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Сверка сценариев хаоса с runbook_url и якорями алертов."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"
RUNBOOK = ROOT / "docs/runbook.md"
PREFIX = "https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#"
SCENARIO_UIDS = {
    "stop-loki": "sreda-loki-errors",
    "disk-full": "sreda-disk-low",
    "stale-backup": "sreda-backup-stale",
}


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def main():
    errors = []
    try:
        rules = RULES.read_text(encoding="utf-8")
    except OSError as exc:
        fail_all([f"rules.yml: не удалось прочитать: {exc}"])
    try:
        runbook = RUNBOOK.read_text(encoding="utf-8")
    except OSError as exc:
        fail_all([f"docs/runbook.md: не удалось прочитать: {exc}"])

    current = None
    urls = {}
    for line in rules.splitlines():
        stripped = line.strip()
        if stripped.startswith("- uid:"):
            current = stripped.split("uid:", 1)[1].strip()
        elif stripped.startswith("runbook_url:") and current:
            urls[current] = stripped.split(":", 1)[1].strip()

    if len(urls) < 10:
        errors.append(f"ожидались 10 runbook_url, найдено {len(urls)}")

    for uid, wanted in urls.items():
        expected = f"{PREFIX}{uid}"
        if wanted != expected:
            errors.append(f"{uid}: runbook_url должен быть {expected}")
        if f'<a id="{uid}"></a>' not in runbook:
            errors.append(f"{uid}: нет якоря в docs/runbook.md")

    for scenario, uid in SCENARIO_UIDS.items():
        if uid not in urls:
            errors.append(f"сценарий {scenario}: в rules.yml нет UID {uid}")
        elif f'<a id="{uid}"></a>' not in runbook:
            errors.append(f"сценарий {scenario}: нет якоря {uid}")

    if re.search(r'[\u4e00-\u9fff]', rules + runbook):
        errors.append("обнаружены иноязычные артефакты в rules.yml/runbook.md")

    if errors:
        fail_all(errors)
    print(f"ok: chaos runbook — {len(urls)} правил, 3 сценария со ссылками и якорями")


if __name__ == "__main__":
    main()

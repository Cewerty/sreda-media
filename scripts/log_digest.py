#!/usr/bin/env python3
"""Демо: детерминированный SRE-дайджест по фиксированным локальным событиям.

Не является контрактом входа: критерий релевантности и источник событий
должны быть определены отдельно.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
LOGS = ROOT / "docs/examples/logs/sreda-sample.jsonl"
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"
RUNBOOK = ROOT / "docs/runbook.md"


def main():
    if not LOGS.is_file():
        print("[sre-digest] нет данных: docs/examples/logs/sreda-sample.jsonl")
        return
    counts = Counter()
    total = 0
    warnings = []
    try:
        for number, line in enumerate(LOGS.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                warnings.append(f"строка {number}: битой JSON, пропущена")
                continue
            if not isinstance(record, dict):
                warnings.append(f"строка {number}: не mapping, пропущена")
                continue
            key = (
                str(record.get("event", "-")),
                str(record.get("component", "-")),
                str(record.get("outcome", "-")),
            )
            counts[key] += 1
            total += 1
    except OSError as exc:
        raise SystemExit(f"FAIL: логи не прочитаны: {exc}")

    uids = []
    if RULES.is_file():
        uids = re.findall(r"^\s*-\s+uid:\s+(\S+)", RULES.read_text(encoding="utf-8"), re.M)
    anchors = []
    if RUNBOOK.is_file():
        anchors = re.findall(r'<a id="([^"]+)"></a>', RUNBOOK.read_text(encoding="utf-8"))
    relevant = [uid for uid in uids if uid in anchors]

    print("# SRE digest (детерминированный, без внешней модели)")
    print()
    print(f"- Всего событий: {total}")
    print(f"- Групп: {len(counts)}")
    print()
    print("| event | component | outcome | count |")
    print("| --- | --- | --- | --- |")
    for (event, component, outcome), count in sorted(counts.items()):
        print(f"| `{event}` | `{component}` | `{outcome}` | {count} |")
    print()
    print("## Релевантные runbook-якоря")
    print()
    if relevant:
        for uid in relevant:
            print(f"- `{uid}` — `docs/runbook.md#{uid}`")
    else:
        print("- Нет")
    print()
    print("## Предупреждения")
    print()
    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- Нет")


if __name__ == "__main__":
    main()

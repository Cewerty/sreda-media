#!/usr/bin/env python3
"""Сверка runbook_url правил Grafana Alerting с якорями в docs/runbook.md."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"
SLO = ROOT / "deploy/observability/slo.json"
RUNBOOK = ROOT / "docs/runbook.md"
PREFIX = "https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#"
MISSING = object()


def fail_all(errors):
    """Напечатать все ошибки в stderr и выйти без traceback."""
    raise SystemExit("\n".join(f"FAIL: {error}" for error in errors))


def read_inputs():
    """Прочитать входы и собрать ошибки чтения, не прерывая проверку."""
    errors = []
    slo = data = runbook = MISSING
    try:
        slo = json.loads(SLO.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"slo.json: не удалось прочитать: {exc}")
    try:
        data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"rules.yml: не удалось прочитать: {exc}")
    try:
        runbook = RUNBOOK.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"docs/runbook.md: не удалось прочитать: {exc}")
    return slo, data, runbook, errors


def main():
    slo, data, runbook, errors = read_inputs()

    expected = None
    if slo is not MISSING:
        if isinstance(slo, dict) and isinstance(slo.get("rule_uids"), list):
            expected = set(slo["rule_uids"])
        else:
            errors.append("slo.json: rule_uids должен быть списком")

    groups = None
    if data is not MISSING:
        if not isinstance(data, dict):
            errors.append("rules.yml: ожидается mapping")
        elif not isinstance(data.get("groups"), list):
            errors.append("rules.yml: groups должен быть списком")
        else:
            groups = data["groups"]

    seen = set()
    if groups is not None and runbook is not MISSING:
        for group in groups:
            if not isinstance(group, dict):
                errors.append("rules.yml: группа должна быть mapping")
                continue
            rules = group.get("rules")
            if not isinstance(rules, list):
                errors.append("rules.yml: rules должен быть списком")
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    errors.append("rules.yml: правило должно быть mapping")
                    continue
                uid = rule.get("uid")
                if not uid:
                    errors.append("правило без uid")
                    continue
                seen.add(uid)
                annotations = rule.get("annotations") or {}
                if not isinstance(annotations, dict):
                    errors.append(f"{uid}: annotations должен быть mapping")
                    continue
                wanted = f"{PREFIX}{uid}"
                if annotations.get("runbook_url") != wanted:
                    errors.append(f"{uid}: runbook_url должен быть {wanted}")
                if f'<a id="{uid}"></a>' not in runbook:
                    errors.append(f'{uid}: в docs/runbook.md нет якоря <a id="{uid}"></a>')

    if expected is not None and groups is not None:
        missing = expected - seen
        if missing:
            errors.append("в rules.yml нет UID из slo.json: " + ", ".join(sorted(missing)))

    if errors:
        fail_all(errors)
    print(f"ok: alert runbooks — {len(seen)} правил со ссылками и якорями")


if __name__ == "__main__":
    main()

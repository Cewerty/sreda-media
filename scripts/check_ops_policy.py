#!/usr/bin/env python3
"""Read-only проверка операционной политики: backup, ресурсы и логи."""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
OBS = ROOT / "deploy/observability"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def read(rel):
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail_all([f"{rel}: не удалось прочитать: {exc}"])


def main():
    errors = []

    timer = read("deploy/observability/backup.timer")
    if "OnCalendar=daily" not in timer:
        errors.append("backup.timer: нужен OnCalendar=daily")

    try:
        slo = json.loads((OBS / "slo.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail_all([f"slo.json: не удалось прочитать: {exc}"])
    if not isinstance(slo, dict):
        fail_all(["slo.json: ожидается JSON-объект"])
    if slo.get("backup_freshness_hours") != 24:
        errors.append("slo.json: backup_freshness_hours должен быть 24")

    restore = read("scripts/restore-observability.sh")
    if not re.search(r'\[\s*"\$CONFIRM"\s*=\s*"1"\s*\]', restore):
        errors.append("restore-observability.sh: нет guard CONFIRM=1")

    env = read("deploy/observability/.env.example")
    for name in ("SREDA_BACKUP_AGE_RECIPIENT", "SREDA_BACKUP_AGE_IDENTITY"):
        if name not in env:
            errors.append(f".env.example: нет имени {name}")

    backup = read("scripts/backup-observability.sh")
    if "sha256sum" not in backup or "MANIFEST" not in backup:
        errors.append("backup-observability.sh: нет манифеста SHA256")

    try:
        rules = yaml.safe_load(read("deploy/observability/grafana-provisioning/alerting/rules.yml"))
    except yaml.YAMLError as exc:
        fail_all([f"rules.yml: не удалось прочитать YAML: {exc}"])
    stale = None
    groups = rules.get("groups") if isinstance(rules, dict) else None
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("rules"), list):
                continue
            for rule in group["rules"]:
                if isinstance(rule, dict) and rule.get("uid") == "sreda-backup-stale":
                    stale = rule
    if not isinstance(stale, dict):
        errors.append("rules.yml: нет правила sreda-backup-stale")
    else:
        labels = stale.get("labels")
        if not isinstance(labels, dict) or "enabled" not in labels or str(labels.get("enabled")).lower() != "false":
            errors.append("sreda-backup-stale: правило должно оставаться enabled=false")

    budget_path = ROOT / "docs/resource-budget.md"
    if not budget_path.is_file():
        errors.append("нет docs/resource-budget.md")
    else:
        try:
            budget = budget_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            fail_all([f"resource-budget.md: не удалось прочитать: {exc}"])
        for needle in ("500", "20%", "ADR 0006", "idle", "peak"):
            if needle not in budget:
                errors.append(f"resource-budget.md: нет '{needle}'")

    compose = read("deploy/observability/docker-compose.yml")
    try:
        compose_yaml = yaml.safe_load(compose)
    except yaml.YAMLError as exc:
        fail_all([f"docker-compose.yml: не удалось прочитать YAML: {exc}"])
    services = compose_yaml.get("services") if isinstance(compose_yaml, dict) else None
    if not isinstance(services, dict):
        fail_all(["docker-compose.yml: нет services"])
    for name in ("prometheus", "node-exporter", "blackbox-exporter"):
        service = services.get(name)
        if not isinstance(service, dict):
            errors.append(f"docker-compose.yml: нет сервиса {name}")
            continue
        profiles = service.get("profiles")
        if not isinstance(profiles, list) or "logs" not in profiles:
            errors.append(f"{name}: сервис должен быть под профилем logs")
    if "DJANGO_DEBUG=1" in compose:
        errors.append("docker-compose.yml: DEBUG не должен включаться по умолчанию")

    api_env = read("apps/cms-api/.env.example")
    if "LOG_LEVEL=INFO" not in api_env:
        errors.append("cms-api/.env.example: LOG_LEVEL по умолчанию должен быть INFO")
    for flag in ("RAW_BODY", "LOG_RAW", "CAPTURE_BODY"):
        if flag in compose:
            errors.append(f"docker-compose.yml: флаг {flag} захвата raw body запрещён")

    if errors:
        fail_all(errors)
    print("ok: ops policy — backup, resource gate и логирование согласованы")


if __name__ == "__main__":
    main()

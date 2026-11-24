#!/usr/bin/env python3
"""Статическая проверка Grafana alert provisioning (issue #14, этап 0.2).

Проверяет, что алерты подготовлены, но НЕ активны до появления сайта и адреса:
все правила имеют labels.enabled="false", политика пропускает только enabled=true,
а Telegram-секреты задаются переменными окружения, а не захардкожены в репозитории.
Запуск: uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    print("FAIL: нужен PyYAML (uv run --with pyyaml==6.0.4 ...)", exc, file=sys.stderr)
    sys.exit(1)

BASE = (
    Path(__file__).resolve().parent.parent
    / "deploy/observability/grafana-provisioning/alerting"
)
FILES = ("contact-points.yml", "policies.yml", "rules.yml")
ENV_REF = re.compile(r"^\$\{(GRAFANA_[A-Z0-9_]+)\}$|^\$(GRAFANA_[A-Z0-9_]+)$")
DURATION = re.compile(r"^\d+[smhd]$")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def load(name: str) -> dict:
    path = BASE / name
    if not path.is_file():
        fail(f"нет файла {path.relative_to(BASE.parent.parent.parent)}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"неверный YAML в {name}: {exc}")
    if not isinstance(data, dict):
        fail(f"{name}: ожидается mapping")
    if data.get("apiVersion") != 1:
        fail(f"{name}: apiVersion должен быть 1")
    return data


def check_contacts() -> set[str]:
    data = load("contact-points.yml")
    points = data.get("contactPoints")
    if not isinstance(points, list) or not points:
        fail("contact-points.yml: пустой contactPoints")
    names: set[str] = set()
    for point in points:
        name = point.get("name")
        if not isinstance(name, str) or not name:
            fail("contact-points.yml: контакт без name")
        names.add(name)
        receivers = point.get("receivers")
        if not isinstance(receivers, list) or not receivers:
            fail(f"контакт {name}: пустые receivers")
        for receiver in receivers:
            if receiver.get("type") != "telegram":
                fail(f"контакт {name}: ожидается type=telegram")
            settings = receiver.get("settings") or {}
            secure = receiver.get("secure_settings") or {}
            chatid = str(settings.get("chatid", ""))
            token = str(secure.get("bottoken", ""))
            if not ENV_REF.match(chatid):
                fail(f"контакт {name}: chatid должен быть env-ссылкой GRAFANA_*")
            if not ENV_REF.match(token):
                fail(f"контакт {name}: bottoken должен быть env-ссылкой GRAFANA_*")
    return names


def check_policies(contact_names: set[str]) -> None:
    data = load("policies.yml")
    policies = data.get("policies")
    if not isinstance(policies, list) or not policies:
        fail("policies.yml: пустой policies")
    for policy in policies:
        receiver = policy.get("receiver")
        if receiver not in contact_names:
            fail(f"policies.yml: receiver {receiver!r} нет среди контактов")
        matchers = policy.get("object_matchers") or []
        if ["enabled", "=", "true"] not in matchers:
            fail("policies.yml: нужен object_matchers ['enabled', '=', 'true']")
        for key in ("group_wait", "group_interval", "repeat_interval"):
            value = str(policy.get(key, ""))
            if not DURATION.match(value):
                fail(f"policies.yml: неверная длительность {key}={value!r}")


def check_rules() -> int:
    data = load("rules.yml")
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        fail("rules.yml: пустой groups")
    count = 0
    uids: set[str] = set()
    for group in groups:
        rules = group.get("rules") or []
        if not rules:
            fail(f"группа {group.get('name')!r} без правил")
        for rule in rules:
            uid = rule.get("uid")
            if not isinstance(uid, str) or not uid or uid in uids:
                fail(f" rules.yml: отсутствует или дублируется uid {uid!r}")
            uids.add(uid)
            if rule.get("labels", {}).get("enabled") != "false":
                fail(f"{uid}: labels.enabled должен быть \"false\" до PR #16 и Q-1")
            condition = rule.get("condition")
            if condition != "B":
                fail(f"{uid}: ожидается condition B")
            queries = {item.get("refId"): item for item in (rule.get("data") or [])}
            if set(queries) != {"A", "B"}:
                fail(f"{uid}: нужны запросы A и B")
            source = queries["A"].get("datasourceUid")
            if source not in {"loki", "prometheus", "observability-sql"}:
                fail(f"{uid}: неизвестный datasourceUid {source!r}")
            model_a = queries["A"].get("model") or {}
            if not str(model_a.get("expr", "")).strip():
                fail(f"{uid}: пустое выражение в A")
            model_b = queries["B"].get("model") or {}
            if model_b.get("expression") != "A":
                fail(f"{uid}: B должен ссылаться на A")
            for key in ("title", "annotations"):
                if not rule.get(key):
                    fail(f"{uid}: нет {key}")
            count += 1
    return count


def main() -> None:
    contacts = check_contacts()
    check_policies(contacts)
    rules = check_rules()
    print(
        f"ok: Grafana alerting — контактов {len(contacts)}, "
        f"правил {rules}, все отключены (enabled=false), секреты через env"
    )


if __name__ == "__main__":
    main()
